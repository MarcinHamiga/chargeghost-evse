from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from chargeghost_evse.api.dependencies import get_runtime
from chargeghost_evse.api.runtime import SimulationRuntime
from chargeghost_evse.api.schemas import (
    ActionResult,
    DataTransferRequest,
    DiagnosticsStatusRequest,
    FirmwareStatusRequest,
    MeterValuesRequest,
    OcppConfigKeyInfo,
    OcppConfigKeyUpdateRequest,
    RawStartTransactionRequest,
    RawStopTransactionRequest,
    SecurityEventRequest,
    StatusNotificationRequest,
)

router = APIRouter(prefix="/api/v1/ocpp", tags=["ocpp"])


@router.post("/connect", response_model=ActionResult)
async def connect(runtime: SimulationRuntime = Depends(get_runtime)) -> ActionResult:
    return await runtime.call(runtime.controller.connect)


@router.post("/disconnect", response_model=ActionResult)
async def disconnect(runtime: SimulationRuntime = Depends(get_runtime)) -> ActionResult:
    return await runtime.call(runtime.controller.disconnect)


@router.post("/authorize", response_model=ActionResult)
async def authorize(
    id_tag: str = "",
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
    return await runtime.call(runtime.controller.authorize, id_tag)


@router.post("/heartbeat", response_model=ActionResult)
async def send_heartbeat(
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
    return await runtime.call(runtime.controller.send_heartbeat)


@router.get("/connection_status")
async def connection_status(
    runtime: SimulationRuntime = Depends(get_runtime),
) -> dict[str, bool]:
    connected = await runtime.call(lambda: runtime.controller.is_connected)
    return {"connected": connected}


@router.get("/config-keys", response_model=list[OcppConfigKeyInfo])
async def get_config_keys(
    runtime: SimulationRuntime = Depends(get_runtime),
) -> list[OcppConfigKeyInfo]:
    keys = await runtime.call(
        lambda: (
            []
            if runtime.bridge is None
            else [
                {
                    "key": config_key.key,
                    "value": config_key.get_value(),
                    "readonly": config_key.readonly,
                    "default": config_key.default,
                    "description": config_key.description,
                    "mandatory": config_key.mandatory,
                    "category": config_key.category,
                }
                for config_key in runtime.bridge.get_ocpp_config_keys()
            ]
        )
    )
    return [OcppConfigKeyInfo.model_validate(config_key) for config_key in keys]


@router.put("/config-keys", response_model=ActionResult)
async def update_config_key(
    request: OcppConfigKeyUpdateRequest,
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
    if (
        runtime.bridge is None
        or runtime.bridge.runner is None
        or runtime.bridge.runner.adapter is None
    ):
        return ActionResult(
            success=False,
            message="OCPP not connected",
            details={"status": "not_supported"},
        )

    def do_update() -> ActionResult:
        status = runtime._set_ocpp_config_key_sync(request.key, request.value)
        if status == "accepted":
            return ActionResult(
                success=True, message=f"Configuration key '{request.key}' updated"
            )
        return ActionResult(
            success=False,
            message=f"Configuration key update failed: {status}",
            details={"status": status},
        )

    return await runtime.call(do_update)


def _require_adapter(runtime: SimulationRuntime) -> None:
    if (
        runtime.bridge is None
        or runtime.bridge.runner is None
        or runtime.bridge.runner.adapter is None
    ):
        raise HTTPException(status_code=503, detail="OCPP adapter not available")


@router.post("/boot-notification", response_model=ActionResult)
async def boot_notification(
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
    _require_adapter(runtime)
    result = await runtime.send_ocpp_raw("send_boot_notification")
    return ActionResult(
        success=True, message="BootNotification sent", details=_detail(result)
    )


@router.post("/status-notification", response_model=ActionResult)
async def status_notification(
    request: StatusNotificationRequest,
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
    _require_adapter(runtime)
    result = await runtime.send_ocpp_raw(
        "send_status_notification",
        request.connector_id,
        request.error_code,
        request.status,
    )
    return ActionResult(
        success=True, message="StatusNotification sent", details=_detail(result)
    )


@router.post("/start-transaction", response_model=ActionResult)
async def start_transaction(
    request: RawStartTransactionRequest,
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
    _require_adapter(runtime)
    meter_start = request.meter_start if request.meter_start is not None else 0
    timestamp = request.timestamp or datetime.now(timezone.utc).isoformat()
    result = await runtime.send_ocpp_raw(
        "send_start_transaction",
        request.connector_id,
        request.id_tag,
        meter_start,
        timestamp,
    )
    return ActionResult(
        success=True, message="StartTransaction sent", details=_detail(result)
    )


@router.post("/stop-transaction", response_model=ActionResult)
async def stop_transaction(
    request: RawStopTransactionRequest,
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
    _require_adapter(runtime)
    meter_stop = request.meter_stop if request.meter_stop is not None else 0
    timestamp = request.timestamp or datetime.now(timezone.utc).isoformat()
    result = await runtime.send_ocpp_raw(
        "send_stop_transaction",
        meter_stop,
        timestamp,
        request.transaction_id,
        request.reason,
    )
    return ActionResult(
        success=True, message="StopTransaction sent", details=_detail(result)
    )


@router.post("/meter-values", response_model=ActionResult)
async def meter_values(
    request: MeterValuesRequest,
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
    _require_adapter(runtime)
    value = request.value if request.value is not None else 0.0
    result = await runtime.send_ocpp_raw(
        "send_meter_values",
        request.connector_id,
        value,
        request.transaction_id,
    )
    return ActionResult(
        success=True, message="MeterValues sent", details=_detail(result)
    )


@router.post("/data-transfer", response_model=ActionResult)
async def data_transfer(
    request: DataTransferRequest,
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
    _require_adapter(runtime)
    result = await runtime.send_ocpp_raw(
        "send_data_transfer",
        request.vendor_id,
        request.message_id,
        request.data,
    )
    return ActionResult(
        success=True, message="DataTransfer sent", details=_detail(result)
    )


@router.post("/diagnostics-status-notification", response_model=ActionResult)
async def diagnostics_status_notification(
    request: DiagnosticsStatusRequest,
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
    _require_adapter(runtime)
    result = await runtime.send_ocpp_raw(
        "send_diagnostics_status_notification",
        request.status,
    )
    return ActionResult(
        success=True,
        message="DiagnosticsStatusNotification sent",
        details=_detail(result),
    )


@router.post("/firmware-status-notification", response_model=ActionResult)
async def firmware_status_notification(
    request: FirmwareStatusRequest,
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
    _require_adapter(runtime)
    result = await runtime.send_ocpp_raw(
        "send_firmware_status_notification",
        request.status,
    )
    return ActionResult(
        success=True, message="FirmwareStatusNotification sent", details=_detail(result)
    )


@router.post("/security-event-notification", response_model=ActionResult)
async def security_event_notification(
    request: SecurityEventRequest,
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
    _require_adapter(runtime)
    ts = request.timestamp or datetime.now(timezone.utc)
    result = await runtime.send_ocpp_raw(
        "send_security_event_notification",
        request.event_type,
        ts,
        request.tech_info,
    )
    return ActionResult(
        success=True, message="SecurityEventNotification sent", details=_detail(result)
    )


def _detail(result: Any) -> dict[str, Any]:
    if result is None:
        return {}
    if hasattr(result, "__dict__"):
        return result.__dict__
    return {"result": str(result)}
