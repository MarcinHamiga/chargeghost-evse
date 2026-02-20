_TRUE_VALUES = frozenset(("true", "1", "yes", "on"))


def parse_bool_string(value: str) -> bool:
    return value.lower() in _TRUE_VALUES
