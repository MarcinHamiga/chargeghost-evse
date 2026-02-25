import aiohttp
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

GITHUB_LATEST_RELEASE_URL = (
	"https://api.github.com/repos/MarcinHamiga/chargeghost-evse/releases/latest"
)

ProgressFn = Callable[[int], None]


@dataclass
class ReleaseInfo:
	tag_name: str
	body: str
	published_at: str
	assets: list[dict]


class UpdateManager:
	def __init__(self, current_version: str, config):
		self.current_version = current_version
		self.config = config

	@staticmethod
	def normalize_version(version: str) -> str:
		return version.strip().lstrip("vV")

	@classmethod
	def is_update_available(cls, current: str, latest_tag: str) -> bool:
		try:
			def parse(v: str) -> tuple[int, ...]:
				base = cls.normalize_version(v).split("-")[0]  # strip pre-release suffix
				return tuple(int(x) for x in base.split(".") if x)
			return parse(latest_tag) > parse(current)
		except (ValueError, AttributeError):
			return False

	async def fetch_latest_release(self) -> ReleaseInfo:
		from aiohttp import ClientTimeout
		
		timeout = ClientTimeout(total=15)
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
		if system_name == "Windows":
			for a in assets:
				if a.get("name", "").endswith(".exe"):
					return a
			for a in assets:
				if a.get("name", "").endswith("windows.zip"):
					return a
		elif system_name == "Darwin":
			for a in assets:
				if a.get("name", "").endswith(".dmg"):
					return a
			for a in assets:
				if a.get("name", "").endswith("macos.zip"):
					return a
		elif system_name == "Linux":
			# Linux: no packaged installer provided yet
			return None
		return None

	async def download_update(self, url: str, target_file: Path, on_progress: Optional[ProgressFn] = None) -> Path:
		from aiohttp import ClientTimeout
		timeout = ClientTimeout(total=300, connect=15)
		async with aiohttp.ClientSession() as session:
			async with session.get(url, timeout=timeout) as resp:
				resp.raise_for_status()
				total = int(resp.headers.get("Content-Length", "0"))
				received = 0
				with open(target_file, "wb") as f:
					async for chunk in resp.content.iter_chunked(64 * 1024):
						f.write(chunk)
						received += len(chunk)
						if on_progress and total > 0:
							on_progress(min(100, int(received * 100 / total)))
		return target_file
