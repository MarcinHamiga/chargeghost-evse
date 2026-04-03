from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends

from chargeghost_evse.api.dependencies import get_runtime
from chargeghost_evse.api.runtime import SimulationRuntime
from chargeghost_evse.api.schemas import (
    ActionResult,
    DownloadProgressInfo,
    ReleaseInfoResponse,
    VersionInfo,
)

router = APIRouter(prefix="/api/v1/updates", tags=["updates"])


@router.get("/check")
async def check_for_updates(
    runtime: SimulationRuntime = Depends(get_runtime),
) -> dict:
    result = await runtime.check_for_updates()
    if "release" in result:
        result["release"] = ReleaseInfoResponse.model_validate(result["release"])
    return result


@router.get("/status", response_model=VersionInfo)
async def get_version_info(
    runtime: SimulationRuntime = Depends(get_runtime),
) -> VersionInfo:
    update_mgr = runtime.update_manager
    if update_mgr is None:
        return VersionInfo(current_version="0.0.0", update_available=False)

    current = update_mgr.current_version
    latest = None
    update_available = False

    if runtime._latest_release is not None:
        latest = runtime._latest_release.tag_name
        update_available = update_mgr.is_update_available(current, latest)

    return VersionInfo(
        current_version=current,
        latest_version=latest,
        update_available=update_available,
    )


@router.post("/download")
async def download_update(
    runtime: SimulationRuntime = Depends(get_runtime),
    url: Optional[str] = None,
) -> DownloadProgressInfo:
    result = await runtime.download_update(url)
    return DownloadProgressInfo.model_validate(result)


@router.post("/ignore", response_model=ActionResult)
async def ignore_version(
    tag: str,
    runtime: SimulationRuntime = Depends(get_runtime),
) -> ActionResult:
    def do_ignore() -> ActionResult:
        runtime.ignore_version_sync(tag)
        return ActionResult(success=True, message=f"Ignored version {tag}")

    return await runtime.call(do_ignore)
