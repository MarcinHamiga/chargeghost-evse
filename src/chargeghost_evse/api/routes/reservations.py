from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends

from chargeghost_evse.api.dependencies import get_runtime
from chargeghost_evse.api.runtime import SimulationRuntime
from chargeghost_evse.api.schemas import (
    ActionResult,
    ReservationCreateRequest,
    ReservationInfo,
)

router = APIRouter(prefix="/api/v1/reservations", tags=["reservations"])


@router.get("", response_model=list[ReservationInfo])
async def list_reservations(
    runtime: SimulationRuntime = Depends(get_runtime),
) -> list[ReservationInfo]:
    def do_list() -> list[ReservationInfo]:
        results: list[ReservationInfo] = []
        for connector_id, reservation in runtime.engine._reservations.items():
            if reservation.is_expired():
                continue
            results.append(
                ReservationInfo(
                    reservation_id=reservation.reservation_id,
                    connector_id=reservation.connector_id,
                    id_tag=reservation.id_tag,
                    expiry_date=reservation.expiry_date.isoformat(),
                    parent_id_tag=reservation.parent_id_tag,
                )
            )
        return results

    return await runtime.call(do_list)


@router.get("/{connector_id}", response_model=Optional[ReservationInfo])
async def get_reservation(
    connector_id: int,
    runtime: SimulationRuntime = Depends(get_runtime),
) -> Optional[ReservationInfo]:
    def do_get() -> Optional[ReservationInfo]:
        reservation = runtime.engine.get_reservation(connector_id)
        if reservation is None or reservation.is_expired():
            return None
        return ReservationInfo(
            reservation_id=reservation.reservation_id,
            connector_id=reservation.connector_id,
            id_tag=reservation.id_tag,
            expiry_date=reservation.expiry_date.isoformat(),
            parent_id_tag=reservation.parent_id_tag,
        )

    return await runtime.call(do_get)


@router.post("", response_model=ActionResult)
async def create_reservation(
    request: ReservationCreateRequest,
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
    def do_create() -> ActionResult:
        try:
            expiry = datetime.fromisoformat(request.expiry_date)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
        except ValueError:
            return ActionResult(
                success=False,
                message="Invalid expiry_date format. Use ISO 8601 format.",
            )

        result = runtime.engine.reserve_connector(
            connector_id=request.connector_id,
            reservation_id=request.reservation_id,
            id_tag=request.id_tag,
            expiry_date=expiry,
            parent_id_tag=request.parent_id_tag,
        )
        if result == "accepted":
            return ActionResult(
                success=True,
                message=f"Reservation {request.reservation_id} created for connector {request.connector_id}",
            )
        return ActionResult(success=False, message=f"Reservation failed: {result}")

    return await runtime.call(do_create)


@router.delete("/{reservation_id}", response_model=ActionResult)
async def cancel_reservation(
    reservation_id: int,
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
    def do_cancel() -> ActionResult:
        result = runtime.engine.cancel_reservation(reservation_id)
        if result == "accepted":
            return ActionResult(
                success=True, message=f"Reservation {reservation_id} cancelled"
            )
        return ActionResult(success=False, message=f"Cancellation failed: {result}")

    return await runtime.call(do_cancel)
