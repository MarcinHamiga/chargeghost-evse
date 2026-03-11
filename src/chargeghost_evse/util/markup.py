import re

_MARKUP_RE = re.compile(r"\[/?[^\]]+\]")


def strip_markup(text: str) -> str:
	"""Remove Rich-style markup tags from text."""
	return _MARKUP_RE.sub("", text)
