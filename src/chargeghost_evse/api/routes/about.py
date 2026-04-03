from __future__ import annotations

from fastapi import APIRouter

from chargeghost_evse import __version__
from chargeghost_evse.api.schemas import AboutInfo

router = APIRouter(prefix="/api/v1", tags=["about"])


@router.get("/about", response_model=AboutInfo)
async def get_about() -> AboutInfo:
	return AboutInfo(
		version=__version__,
		description="ChargeGhost EVSE Simulator",
		ocpp_versions=["OCPP 1.6J"],
		license="AGPLv3",
		features=[
			"REST API",
			"WebSocket",
			"OCPP 1.6J",
			"Smart Charging",
			"Local Auth List",
			"Firmware Management",
		],
	)
