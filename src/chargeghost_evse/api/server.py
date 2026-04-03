from __future__ import annotations

import uvicorn

VALID_LOG_LEVELS = frozenset({"critical", "error", "warning", "info", "debug", "trace"})


def run_server(
	host: str = "127.0.0.1",
	port: int = 8080,
	log_level: str = "info",
) -> None:
    if log_level not in VALID_LOG_LEVELS:
        raise ValueError(
            f"Invalid log level: {log_level!r}. "
            f"Must be one of {sorted(VALID_LOG_LEVELS)}"
        )
    uvicorn.run(
        "chargeghost_evse.api.app:create_app",
        host=host,
        port=port,
        log_level=log_level,
        factory=True,
    )
