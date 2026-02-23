from dataclasses import dataclass


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
