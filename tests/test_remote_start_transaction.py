import asyncio
import queue
import threading
from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from ocpp.v16.enums import (
    ChargingProfileKindType,
    ChargingProfilePurposeType,
    ChargingRateUnitType,
    RemoteStartStopStatus,
)

from chargeghost_evse.bridge.bridge import Bridge
from chargeghost_evse.engine.engine import Engine
from chargeghost_evse.ocpp_adapter.adapter import Adapter
from chargeghost_evse.ocpp_adapter.charging_profile_manager import (
    ChargingProfileManager,
)


def _make_remote_start_profile(
    *,
    profile_id: int = 11,
    limit: float = 8.0,
    purpose: ChargingProfilePurposeType = ChargingProfilePurposeType.tx_profile,
    kind: ChargingProfileKindType = ChargingProfileKindType.relative,
) -> dict:
    profile = {
        "charging_profile_id": profile_id,
        "stack_level": 1,
        "charging_profile_purpose": purpose.value,
        "charging_profile_kind": kind.value,
        "charging_schedule": {
            "charging_rate_unit": ChargingRateUnitType.amps.value,
            "charging_schedule_period": [
                {
                    "start_period": 0,
                    "limit": limit,
                }
            ],
        },
    }
    if kind == ChargingProfileKindType.absolute:
        profile["charging_schedule"]["start_schedule"] = datetime.now(
            timezone.utc
        ).isoformat()
    return profile


def _make_adapter(command_queue: queue.Queue) -> Adapter:
    mock_conn = MagicMock()
    mock_conn.recv = AsyncMock()
    mock_conn.send = AsyncMock()
    return Adapter("CP_1", mock_conn, command_queue=command_queue)


def _run_loop_until_idle(loop: asyncio.AbstractEventLoop) -> None:
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    sentinel = asyncio.run_coroutine_threadsafe(asyncio.sleep(0), loop)
    sentinel.result(timeout=5)
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=2)


def test_remote_start_transaction_enqueues_valid_tx_profile() -> None:
    command_queue: queue.Queue = queue.Queue()
    adapter = _make_adapter(command_queue)

    result = asyncio.run(
        adapter.on_remote_start_transaction(
            connector_id=1,
            id_tag="TAG-1",
            charging_profile=_make_remote_start_profile(),
        )
    )

    assert result.status == RemoteStartStopStatus.accepted
    command = command_queue.get_nowait()
    assert command["action"] == "START"
    assert command["connector_id"] == 1
    assert command["id_tag"] == "TAG-1"
    assert command["charging_profile"] is not None
    assert command["charging_profile"].charging_profile_id == 11
    assert (
        command["charging_profile"].charging_profile_purpose
        == ChargingProfilePurposeType.tx_profile
    )
    assert command["charging_profile"].transaction_id is None


def test_remote_start_transaction_rejects_unknown_connector_id() -> None:
    command_queue: queue.Queue = queue.Queue()
    adapter = _make_adapter(command_queue)
    adapter.known_connector_ids = [1, 2]

    result = asyncio.run(
        adapter.on_remote_start_transaction(
            connector_id=99,
            id_tag="TAG-1",
        )
    )

    assert result.status == RemoteStartStopStatus.rejected
    assert command_queue.empty()


def test_remote_start_transaction_rejects_non_tx_profile() -> None:
    command_queue: queue.Queue = queue.Queue()
    adapter = _make_adapter(command_queue)

    result = asyncio.run(
        adapter.on_remote_start_transaction(
            connector_id=1,
            id_tag="TAG-1",
            charging_profile=_make_remote_start_profile(
                purpose=ChargingProfilePurposeType.tx_default_profile,
            ),
        )
    )

    assert result.status == RemoteStartStopStatus.rejected
    assert command_queue.empty()


def test_remote_start_transaction_rejects_malformed_profile() -> None:
    command_queue: queue.Queue = queue.Queue()
    adapter = _make_adapter(command_queue)
    charging_profile = _make_remote_start_profile()
    del charging_profile["charging_schedule"]["charging_rate_unit"]

    result = asyncio.run(
        adapter.on_remote_start_transaction(
            connector_id=1,
            id_tag="TAG-1",
            charging_profile=charging_profile,
        )
    )

    assert result.status == RemoteStartStopStatus.rejected
    assert command_queue.empty()


def test_remote_start_profile_changes_active_limit_after_transaction_start(
) -> None:
    engine = Engine()
    engine.add_connector()
    engine.plug_in(1)

    bridge = Bridge(engine=engine, url="ws://localhost:3000/CP_1")
    bridge.engine.session_started.subscribe(bridge.on_engine_session_started)

    adapter = MagicMock()
    adapter.send_start_transaction = AsyncMock(
        return_value=MagicMock(transaction_id=77, id_tag_info={"status": "Accepted"})
    )
    adapter.charging_profile_manager = ChargingProfileManager()
    bridge.runner.adapter = adapter

    loop = asyncio.new_event_loop()
    bridge.runner.loop = loop
    bridge._inject_limit_getter()

    charging_profile = ChargingProfileManager.from_ocpp_dict(
        _make_remote_start_profile(limit=8.0)
    )
    engine.command_queue.put(
        {
            "action": "START",
            "connector_id": 1,
            "id_tag": "TAG-1",
            "charging_profile": charging_profile,
            "timeout": 30,
        }
    )
    engine._process_commands()
    _run_loop_until_idle(loop)
    loop.close()

    assert engine.session is not None
    assert engine.session.transaction_id == 77
    assert engine.session.remote_start_charging_profile is None
    assert engine.get_limit is not None
    assert engine.get_limit(1, 77) == pytest.approx(8.0)


def test_later_tx_profile_replaces_remote_start_profile_at_same_stack_level(
) -> None:
    manager = ChargingProfileManager()
    initial = ChargingProfileManager.from_ocpp_dict(
        _make_remote_start_profile(profile_id=11, limit=8.0)
    )
    replacement_profile = ChargingProfileManager.from_ocpp_dict(
        _make_remote_start_profile(profile_id=12, limit=4.0)
    )

    assert manager.set_profile(1, replace(initial, transaction_id=77)) is None
    assert (
        manager.set_profile(1, replace(replacement_profile, transaction_id=77))
        is None
    )

    tx_profiles = manager.get_profiles_for_purpose(
        ChargingProfilePurposeType.tx_profile,
        1,
    )
    matching_ids = [
        profile.charging_profile_id
        for profile in tx_profiles
        if profile.transaction_id == 77
    ]

    assert matching_ids == [12]
    assert manager.get_composite_limit(
        connector_id=1,
        transaction_id=77,
        now=datetime.now(timezone.utc),
        connector_voltage=230.0,
        transaction_start=datetime.now(timezone.utc),
    ) == pytest.approx(4.0)
