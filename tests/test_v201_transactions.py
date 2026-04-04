import uuid

import pytest

from chargeghost_evse.ocpp_adapter.transaction_manager_v201 import (
    TransactionManagerV201,
    TxStartStopPointConfig,
    connector_state_to_charging_state,
    engine_event_to_trigger_reason,
)


class TestTransactionManagerBegin:
    def test_first_transaction_gets_uuid(self):
        mgr = TransactionManagerV201()
        tx_id = mgr.begin_transaction(1)
        assert isinstance(tx_id, str)
        uuid.UUID(tx_id)

    def test_second_transaction_gets_different_uuid(self):
        mgr = TransactionManagerV201()
        tx_id1 = mgr.begin_transaction(1)
        tx_id2 = mgr.begin_transaction(2)
        assert tx_id1 != tx_id2

    def test_begin_resets_seq_no(self):
        mgr = TransactionManagerV201()
        tx_id = mgr.begin_transaction(1)
        assert mgr.get_next_seq_no(tx_id) == 0


class TestTransactionManagerSeqNo:
    def test_seq_no_increments(self):
        mgr = TransactionManagerV201()
        tx_id = mgr.begin_transaction(1)

        assert mgr.get_next_seq_no(tx_id) == 0
        assert mgr.get_next_seq_no(tx_id) == 1
        assert mgr.get_next_seq_no(tx_id) == 2

    def test_separate_transactions_have_independent_seq(self):
        mgr = TransactionManagerV201()
        tx1 = mgr.begin_transaction(1)
        tx2 = mgr.begin_transaction(2)

        assert mgr.get_next_seq_no(tx1) == 0
        assert mgr.get_next_seq_no(tx2) == 0
        assert mgr.get_next_seq_no(tx1) == 1
        assert mgr.get_next_seq_no(tx2) == 1

    def test_get_current_seq_no(self):
        mgr = TransactionManagerV201()
        tx_id = mgr.begin_transaction(1)
        assert mgr.get_current_seq_no(tx_id) == 0
        mgr.get_next_seq_no(tx_id)
        assert mgr.get_current_seq_no(tx_id) == 1


class TestTransactionManagerGet:
    def test_get_active_transaction(self):
        mgr = TransactionManagerV201()
        tx_id = mgr.begin_transaction(1)
        assert mgr.get_transaction_id(1) == tx_id

    def test_get_returns_none_for_unknown_evse(self):
        mgr = TransactionManagerV201()
        assert mgr.get_transaction_id(99) is None


class TestTransactionManagerEnd:
    def test_end_removes_transaction(self):
        mgr = TransactionManagerV201()
        tx_id = mgr.begin_transaction(1)
        ended = mgr.end_transaction(1)

        assert ended == tx_id
        assert mgr.get_transaction_id(1) is None

    def test_end_returns_none_for_unknown(self):
        mgr = TransactionManagerV201()
        assert mgr.end_transaction(99) is None

    def test_end_clears_seq_no(self):
        mgr = TransactionManagerV201()
        tx_id = mgr.begin_transaction(1)
        mgr.get_next_seq_no(tx_id)
        mgr.end_transaction(1)

        assert mgr.get_current_seq_no(tx_id) == 0


class TestTransactionManagerActive:
    def test_active_transactions_returns_copy(self):
        mgr = TransactionManagerV201()
        mgr.begin_transaction(1)
        active = mgr.active_transactions
        active[2] = "999"
        assert 2 not in mgr.active_transactions

    def test_active_transactions_empty(self):
        mgr = TransactionManagerV201()
        assert mgr.active_transactions == {}

    def test_multiple_active(self):
        mgr = TransactionManagerV201()
        mgr.begin_transaction(1)
        mgr.begin_transaction(2)
        assert len(mgr.active_transactions) == 2


class TestTransactionManagerSeqPersistence:
    def test_get_all_seq_numbers(self):
        mgr = TransactionManagerV201()
        tx1 = mgr.begin_transaction(1)
        tx2 = mgr.begin_transaction(2)
        mgr.get_next_seq_no(tx1)
        mgr.get_next_seq_no(tx1)
        mgr.get_next_seq_no(tx2)

        seq_data = mgr.get_all_seq_numbers()
        assert seq_data[tx1] == 2
        assert seq_data[tx2] == 1

    def test_restore_seq_numbers(self):
        mgr = TransactionManagerV201()
        tx_id = mgr.begin_transaction(1)

        seq_data = {tx_id: 5}
        mgr.restore_seq_numbers(seq_data)

        assert mgr.get_current_seq_no(tx_id) == 5
        assert mgr.get_next_seq_no(tx_id) == 5


class TestTxStartStopPointConfig:
    def test_default_config_authorized(self):
        config = TxStartStopPointConfig()
        assert config.start_on_ev_connected is False
        assert config.start_on_authorized is True
        assert config.start_on_energy_transfer is False

    def test_trigger_reason_authorized(self):
        config = TxStartStopPointConfig()
        reason = config.trigger_reason_for_start(
            ev_connected=True, authorized=True, energy_transfer=False
        )
        assert reason == "Authorized"

    def test_trigger_reason_energy_transfer(self):
        config = TxStartStopPointConfig(start_on_energy_transfer=True)
        reason = config.trigger_reason_for_start(
            ev_connected=True, authorized=True, energy_transfer=True
        )
        assert reason == "EnergyTransfer"

    def test_trigger_reason_ev_connected(self):
        config = TxStartStopPointConfig(start_on_ev_connected=True)
        reason = config.trigger_reason_for_start(
            ev_connected=True, authorized=False, energy_transfer=False
        )
        assert reason == "CablePluggedIn"

    def test_trigger_reason_none(self):
        config = TxStartStopPointConfig(
            start_on_ev_connected=False,
            start_on_authorized=False,
            start_on_energy_transfer=False,
        )
        reason = config.trigger_reason_for_start(
            ev_connected=True, authorized=False, energy_transfer=False
        )
        assert reason is None


class TestConnectorStateToChargingState:
    def test_charging(self):
        from chargeghost_evse.engine.connector import ConnectorState

        result = connector_state_to_charging_state(ConnectorState.CHARGING)
        assert result == "Charging"

    def test_suspended_ev(self):
        from chargeghost_evse.engine.connector import ConnectorState

        result = connector_state_to_charging_state(ConnectorState.SUSPENDED_EV)
        assert result == "SuspendedEV"

    def test_suspended_evse(self):
        from chargeghost_evse.engine.connector import ConnectorState

        result = connector_state_to_charging_state(ConnectorState.SUSPENDED_EVSE)
        assert result == "SuspendedEVSE"

    def test_available(self):
        from chargeghost_evse.engine.connector import ConnectorState

        result = connector_state_to_charging_state(ConnectorState.AVAILABLE)
        assert result is None


class TestEngineEventToTriggerReason:
    def test_all_trigger_reasons(self):
        reasons = [
            "CablePluggedIn",
            "Authorized",
            "ChargingStateChanged",
            "ChargingRateChanged",
            "MeterValuePeriodic",
            "MeterValueClock",
            "EVDeparted",
            "StopRequested",
            "DeAuthorized",
            "EnergyLimitReached",
            "Trigger",
            "UnlockCommand",
            "RemoteStart",
            "RemoteStop",
        ]
        for reason in reasons:
            result = engine_event_to_trigger_reason(reason)
            assert result == reason, f"Failed for {reason}"

    def test_unknown_returns_trigger(self):
        result = engine_event_to_trigger_reason("UnknownEvent")
        assert result == "Trigger"
