from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from chargeghost_evse.api.dependencies import get_runtime
from chargeghost_evse.api.runtime import SimulationRuntime
from chargeghost_evse.api.schemas import (
	ActionResult,
	ConnectorCreateRequest,
	ConnectorInfo,
	ConnectorUpdateRequest,
)
from chargeghost_evse.api.serializers import serialize_connector
from chargeghost_evse.util.config import ConnectorConfig

router = APIRouter(prefix="/api/v1/connectors", tags=["connectors"])


def _save_connector_config(runtime: SimulationRuntime) -> None:
	runtime.config.connectors = [
		ConnectorConfig(voltage=c.voltage, current=c.current, phase=c.phase)
		for c in runtime.engine.connectors
	]
	runtime.config.save()


@router.get("", response_model=list[ConnectorInfo])
async def list_connectors(
	runtime: SimulationRuntime = Depends(get_runtime),
) -> list[ConnectorInfo]:
	data = await runtime.call(
		lambda: [serialize_connector(connector) for connector in runtime.engine.connectors]
	)
	return [ConnectorInfo.model_validate(item) for item in data]


@router.get("/{connector_id}", response_model=ConnectorInfo)
async def get_connector(
	connector_id: int,
	runtime: SimulationRuntime = Depends(get_runtime),
) -> ConnectorInfo:
	def _get() -> dict | None:
		connector = runtime.engine.get_connector(connector_id)
		if connector is None:
			return None
		return serialize_connector(connector)

	data = await runtime.call(_get)
	if data is None:
		raise HTTPException(status_code=404, detail=f"Connector {connector_id} not found")
	return ConnectorInfo.model_validate(data)


@router.post("", response_model=ActionResult)
async def create_connector(
	payload: ConnectorCreateRequest,
	runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
	def _create() -> ActionResult:
		connector_config = ConnectorConfig(
			voltage=payload.voltage,
			current=payload.current,
			phase=payload.phase,
		)
		error = connector_config.validate()
		if error is not None:
			return ActionResult(success=False, message=error)

		connector = runtime.engine.add_connector(
			voltage=payload.voltage,
			current=payload.current,
			phase=payload.phase,
		)
		_save_connector_config(runtime)
		return ActionResult(
			success=True,
			message=f"Created connector {connector.id}",
			details={"connector": serialize_connector(connector)},
		)

	return await runtime.call(_create)


@router.put("/{connector_id}", response_model=ActionResult)
async def update_connector(
	connector_id: int,
	payload: ConnectorUpdateRequest,
	runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
	def _update() -> ActionResult:
		error = runtime.engine.update_connector(
			connector_id=connector_id,
			voltage=payload.voltage,
			current=payload.current,
			phase=payload.phase,
		)
		if error is not None:
			return ActionResult(success=False, message=error)

		connector = runtime.engine.get_connector(connector_id)
		if connector is None:
			return ActionResult(
				success=False, message=f"Connector {connector_id} not found"
			)

		_save_connector_config(runtime)
		return ActionResult(
			success=True,
			message=f"Updated connector {connector_id}",
			details={"connector": serialize_connector(connector)},
		)

	return await runtime.call(_update)


@router.delete("/{connector_id}", response_model=ActionResult)
async def delete_connector(
	connector_id: int,
	runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
	def _delete() -> ActionResult:
		try:
			runtime.engine.remove_connector(connector_id)
		except ValueError as exc:
			return ActionResult(success=False, message=str(exc))

		_save_connector_config(runtime)
		return ActionResult(
			success=True,
			message=f"Removed connector {connector_id}",
			details={"connector_id": connector_id},
		)

	return await runtime.call(_delete)


@router.post("/{connector_id}/plug_in", response_model=ActionResult)
async def plug_in(
	connector_id: int,
	runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
	return await runtime.call(runtime.controller.plug_in, connector_id)


@router.post("/{connector_id}/unplug", response_model=ActionResult)
async def unplug(
	connector_id: int,
	runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
	return await runtime.call(runtime.controller.unplug, connector_id)


@router.post("/{connector_id}/suspend_ev", response_model=ActionResult)
async def suspend_ev(
	connector_id: int,
	runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
	return await runtime.call(runtime.controller.suspend_ev, connector_id)


@router.post("/{connector_id}/resume_charging", response_model=ActionResult)
async def resume_charging(
	connector_id: int,
	runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
	return await runtime.call(runtime.controller.resume_charging, connector_id)


@router.post("/{connector_id}/start-charging", response_model=ActionResult)
async def start_charging(
	connector_id: int,
	runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
	return await runtime.call(runtime.controller.start_charging, connector_id)


@router.post("/{connector_id}/stop-charging", response_model=ActionResult)
async def stop_charging(
	connector_id: int,
	runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
	return await runtime.call(runtime.controller.stop_charging, connector_id)


@router.put("/{connector_id}/rfid", response_model=ActionResult)
async def set_rfid(
	connector_id: int,
	rfid_tag: str = "",
	runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
	return await runtime.call(runtime.controller.set_rfid, rfid_tag, connector_id)


@router.delete("/{connector_id}/rfid", response_model=ActionResult)
async def clear_rfid(
	connector_id: int,
	runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
	return await runtime.call(runtime.controller.clear_rfid, connector_id)
