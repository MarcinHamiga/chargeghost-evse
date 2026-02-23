import platform
import aiohttp
from dataclasses import dataclass

GITHUB_LATEST_RELEASE_URL = (
	"https://api.github.com/repos/mhamiga/chargeghost-evse/releases/latest"
)


@dataclass
class ReleaseInfo:
	tag_name: str
	body: str
	published_at: str
	assets: list[dict]


class UpdateManager:
	@staticmethod
	def normalize_version(version: str) -> str:
		return version.strip().lstrip("vV")

	@classmethod
	def is_update_available(cls, current: str, latest_tag: str) -> bool:
		cur = tuple(int(x) for x in cls.normalize_version(current).split("."))
		new = tuple(int(x) for x in cls.normalize_version(latest_tag).split("."))
		return new > cur

	async def fetch_latest_release(self) -> ReleaseInfo:
		async with aiohttp.ClientSession() as session:
			async with session.get(GITHUB_LATEST_RELEASE_URL, timeout=15) as resp:
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
		return None
