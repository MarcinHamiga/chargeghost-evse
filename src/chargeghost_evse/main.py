import sys
import warnings
from typing import Optional

from chargeghost_evse.devtools.scenario_cli import add_cli_args, run_headless
from chargeghost_evse.devtools.timeline_store import TimelineStore


def main_entry() -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="chargeghost-evse")
    add_cli_args(parser)
    parser.add_argument(
        "--api",
        action="store_true",
        help="Start the headless API server instead of the GUI",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    if args.api:
        from chargeghost_evse.api.server import run_server

        run_server(host=args.host, port=args.port, log_level=args.log_level)
        return 0

    if args.run_scenario:
        timeline_store: Optional[TimelineStore] = None
        if args.timeline_export:
            timeline_store = TimelineStore()
        return run_headless(
            args.run_scenario,
            timeout=args.timeout,
            timeline_store=timeline_store,
            timeline_export_path=args.timeline_export,
        )

    warnings.warn(
        "The desktop GUI is deprecated and will be removed in a future release. "
        "Use 'poetry run api' for the headless REST API server.",
        DeprecationWarning,
        stacklevel=2,
    )
    try:
        from chargeghost_evse.ui.app import main
    except ImportError:
        sys.exit(
            "GUI mode requires PySide6. Install with: poetry install --with gui"
        )

    main()
    return 0


if __name__ == "__main__":
    sys.exit(main_entry())
