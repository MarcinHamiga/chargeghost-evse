import sys

from chargeghost_evse.devtools.scenario_cli import add_cli_args, run_headless


def main_entry() -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="chargeghost-evse")
    add_cli_args(parser)
    args = parser.parse_args()

    if args.run_scenario:
        return run_headless(args.run_scenario, timeout=args.timeout)

    from chargeghost_evse.ui.app import main
    main()
    return 0


if __name__ == "__main__":
    sys.exit(main_entry())
