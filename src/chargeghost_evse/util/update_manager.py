"""
Application Update Manager Module.

This module provides functionality for checking and downloading application
updates from GitHub Releases. It handles version comparison, platform-specific
asset selection, and download progress reporting.

Classes:
    ReleaseInfo: Data class for GitHub release information.
    UpdateManager: Manages update checking and downloading.

Constants:
    GITHUB_LATEST_RELEASE_URL: API endpoint for latest release.

Example:
    >>> from chargeghost_evse.util.update_manager import UpdateManager
    >>> 
    >>> manager = UpdateManager("1.0.0", config)
    >>> release = await manager.fetch_latest_release()
    >>> if UpdateManager.is_update_available("1.0.0", release.tag_name):
    ...     print(f"Update available: {release.tag_name}")
    ...     asset = UpdateManager.select_asset_for_platform("Darwin", release.assets)
    ...     await manager.download_update(asset["url"], Path("/tmp/update.dmg"))
"""

import aiohttp
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

# GitHub API endpoint for latest release
GITHUB_LATEST_RELEASE_URL = (
    "https://api.github.com/repos/MarcinHamiga/chargeghost-evse/releases/latest"
)

# Type alias for progress callback function
ProgressFn = Callable[[int], None]


@dataclass
class ReleaseInfo:
    """
    GitHub release information.

    Attributes:
        tag_name: Git tag name (e.g., "v1.2.3").
        body: Release notes/body text (markdown).
        published_at: ISO 8601 timestamp of publication.
        assets: List of release asset dictionaries with download URLs.
    """

    tag_name: str
    body: str
    published_at: str
    assets: list[dict]


class UpdateManager:
    """
    Manages application update checking and downloading.

    Provides methods to check for updates via GitHub API, select the
    appropriate platform-specific asset, and download updates with
    progress reporting.

    Attributes:
        current_version: Currently installed version string.
        config: Application configuration (for ignored versions).

    Example:
        >>> manager = UpdateManager("1.0.0", config)
        >>> 
        >>> # Check for updates
        >>> try:
        ...     release = await manager.fetch_latest_release()
        ...     if manager.is_update_available(manager.current_version, release.tag_name):
        ...         print(f"New version available: {release.tag_name}")
        ... except aiohttp.ClientError as e:
        ...     print(f"Failed to check for updates: {e}")
    """

    def __init__(self, current_version: str, config) -> None:
        """
        Initialize the update manager.

        Args:
            current_version: Current application version string.
            config: Application configuration object with ignored_version field.
        """
        self.current_version = current_version
        self.config = config

    @staticmethod
    def normalize_version(version: str) -> str:
        """
        Normalize a version string for comparison.

        Removes leading 'v' or 'V' prefix and strips whitespace.

        Args:
            version: Version string (e.g., "v1.2.3" or "1.2.3").

        Returns:
            Normalized version string (e.g., "1.2.3").
        """
        return version.strip().lstrip("vV")

    @classmethod
    def is_update_available(cls, current: str, latest_tag: str) -> bool:
        """
        Compare version strings to determine if an update is available.

        Parses semantic version strings and compares them numerically.
        Pre-release suffixes (e.g., "-beta") are stripped before comparison.

        Args:
            current: Current version string.
            latest_tag: Latest release tag name.

        Returns:
            True if latest_tag > current, False otherwise or on parse error.

        Example:
            >>> UpdateManager.is_update_available("1.0.0", "v1.2.0")
            True
            >>> UpdateManager.is_update_available("2.0.0", "v1.9.9")
            False
        """
        try:
            def parse(v: str) -> tuple[int, ...]:
                # Strip pre-release suffix and parse numeric parts
                base = cls.normalize_version(v).split("-")[0]
                return tuple(int(x) for x in base.split(".") if x)

            return parse(latest_tag) > parse(current)
        except (ValueError, AttributeError):
            # Invalid version format, don't suggest update
            return False

    async def fetch_latest_release(self) -> ReleaseInfo:
        """
        Fetch the latest release information from GitHub.

        Makes an API call to GitHub's releases endpoint to get the
        latest release details including version, notes, and assets.

        Returns:
            ReleaseInfo with release details.

        Raises:
            aiohttp.ClientError: On network or HTTP errors.
            aiohttp.ClientResponseError: On non-2xx responses.

        Note:
            Uses a 15-second timeout for the API request.
        """
        from aiohttp import ClientTimeout

        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession() as session:
            async with session.get(GITHUB_LATEST_RELEASE_URL, timeout=timeout) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return ReleaseInfo(
                    tag_name=data.get("tag_name", ""),
                    body=data.get("body", ""),
                    published_at=data.get("published_at", ""),
                    assets=data.get("assets", []),
                )

    @staticmethod
    def select_asset_for_platform(system_name: str, assets: list[dict]) -> dict | None:
        """
        Select the appropriate download asset for the current platform.

        Searches release assets for platform-specific installers:
        - Windows: Prefers .exe, falls back to windows.zip
        - macOS: Prefers .dmg, falls back to macos.zip
        - Linux: No packaged installer (returns None)

        Args:
            system_name: Platform name from platform.system() ("Windows", "Darwin", "Linux").
            assets: List of asset dictionaries from GitHub API.

        Returns:
            Asset dictionary with 'name', 'url', etc., or None if no match found.
        """
        if system_name == "Windows":
            # Prefer Windows installer
            for a in assets:
                if a.get("name", "").endswith(".exe"):
                    return a
            # Fall back to zip archive
            for a in assets:
                if a.get("name", "").endswith("windows.zip"):
                    return a
        elif system_name == "Darwin":
            # Prefer macOS disk image
            for a in assets:
                if a.get("name", "").endswith(".dmg"):
                    return a
            # Fall back to zip archive
            for a in assets:
                if a.get("name", "").endswith("macos.zip"):
                    return a
        elif system_name == "Linux":
            # Linux: no packaged installer provided yet
            return None
        return None

    async def download_update(
        self,
        url: str,
        target_file: Path,
        on_progress: Optional[ProgressFn] = None,
    ) -> Path:
        """
        Download an update file with optional progress reporting.

        Downloads the update file from the given URL to the target path,
        calling the progress callback with percentage updates.

        Args:
            url: Download URL for the asset.
            target_file: Path to save the downloaded file.
            on_progress: Optional callback for progress updates.
                Receives integer percentage (0-100).

        Returns:
            Path to the downloaded file.

        Raises:
            aiohttp.ClientError: On network or HTTP errors.

        Note:
            Uses a 5-minute total timeout and 15-second connect timeout.
            Downloads in 64KB chunks for responsive progress updates.
        """
        from aiohttp import ClientTimeout

        timeout = aiohttp.ClientTimeout(total=300, connect=15)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=timeout) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("Content-Length", "0"))
                received = 0

                with open(target_file, "wb") as f:
                    # Download in 64KB chunks for progress updates
                    async for chunk in resp.content.iter_chunked(64 * 1024):
                        f.write(chunk)
                        received += len(chunk)
                        if on_progress and total > 0:
                            on_progress(min(100, int(received * 100 / total)))

        return target_file
