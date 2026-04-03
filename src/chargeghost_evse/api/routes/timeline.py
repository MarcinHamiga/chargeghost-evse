from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from chargeghost_evse.api.dependencies import get_runtime
from chargeghost_evse.api.runtime import SimulationRuntime
from chargeghost_evse.api.schemas import TimelineEventInfo, TimelineQueryParams
from chargeghost_evse.api.serializers import serialize_timeline_event
from chargeghost_evse.devtools.timeline_models import TimelineFilter

router = APIRouter(prefix="/api/v1/timeline", tags=["timeline"])


def _unavailable() -> JSONResponse:
	return JSONResponse(status_code=503, content={"detail": "Timeline store not available"})


@router.get("", response_model=list[TimelineEventInfo])
async def get_timeline(
	source: Optional[str] = Query(default=None),
	direction: Optional[str] = Query(default=None),
	event_type: Optional[str] = Query(default=None),
	action: Optional[str] = Query(default=None),
	limit: Optional[int] = Query(default=None),
	offset: Optional[int] = Query(default=None),
	connector_id: Optional[int] = Query(default=None),
	transaction_id: Optional[int] = Query(default=None),
	min_level: Optional[int] = Query(default=None),
	tags: Optional[list[str]] = Query(default=None),
	search: Optional[str] = Query(default=None),
	runtime: SimulationRuntime = Depends(get_runtime),
) -> JSONResponse | list[TimelineEventInfo]:
	if runtime.bridge is None or runtime.bridge.timeline_store is None:
		return _unavailable()

	params = TimelineQueryParams(
		source=source,
		direction=direction,
		event_type=event_type,
		action=action,
		limit=limit,
		offset=offset,
		connector_id=connector_id,
		transaction_id=transaction_id,
		min_level=min_level,
		tags=tags,
		search=search,
	)
	filter_obj = TimelineFilter(
		source=params.source,
		direction=params.direction,
		event_type=params.event_type,
		action=params.action,
		connector_id=params.connector_id,
		transaction_id=params.transaction_id,
		min_level=params.min_level,
		tags=params.tags,
		search=params.search,
	)
	events = await runtime.call(lambda: runtime.bridge.timeline_store.query(filter_obj))
	events = events[offset:] if offset else events
	events = events[:limit] if limit else events
	return [TimelineEventInfo.model_validate(serialize_timeline_event(e)) for e in events]


@router.get("/count", response_model=None)
async def get_timeline_count(
	runtime: SimulationRuntime = Depends(get_runtime),
) -> JSONResponse | dict[str, int]:
	if runtime.bridge is None or runtime.bridge.timeline_store is None:
		return _unavailable()
	count = await runtime.call(lambda: runtime.bridge.timeline_store.count)
	return {"count": count}


@router.delete("")
async def clear_timeline(
	runtime: SimulationRuntime = Depends(get_runtime),
) -> JSONResponse:
	if runtime.bridge is None or runtime.bridge.timeline_store is None:
		return _unavailable()
	await runtime.call(lambda: (runtime.bridge.timeline_store.clear(), None)[1])
	return JSONResponse(status_code=200, content={"success": True})
