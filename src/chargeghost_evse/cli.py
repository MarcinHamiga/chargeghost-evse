import argparse
import sys
from chargeghost_evse.engine.engine import Engine
from chargeghost_evse.engine.connector import ConnectorState


def run_interactive_mode():
    engine = Engine()
    print("ChargeGhost EVSE CLI - Interactive Mode")
    print("Type 'help' for available commands, 'exit' to quit")

    while True:
        try:
            user_input = input("evse> ").strip()
            if not user_input:
                continue

            if user_input == "exit":
                print("Exiting...")
                break

            if user_input == "help":
                print("Available commands:")
                print("  add-connector [--voltage V] [--current A] [--phase P]")
                print("  remove-connector <id>")
                print("  start-session <id> [--transaction-id T] [--max-energy E]")
                print("  stop-session")
                print("  simulate [--steps N]")
                print("  status")
                print("  run [--steps N]")
                print("  exit")
                continue

            args = user_input.split()
            command = args[0]

            if command == "add-connector":
                voltage = 230.0
                current = 32.0
                phase = 1
                i = 1
                while i < len(args):
                    if args[i] == "--voltage" and i + 1 < len(args):
                        voltage = float(args[i + 1])
                        i += 2
                    elif args[i] == "--current" and i + 1 < len(args):
                        current = float(args[i + 1])
                        i += 2
                    elif args[i] == "--phase" and i + 1 < len(args):
                        phase = int(args[i + 1])
                        i += 2
                    else:
                        i += 1
                connector = engine.add_connector(voltage, current, phase)
                print(f"Added connector {connector.id}: {voltage}V, {current}A, {phase} phase(s)")

            elif command == "remove-connector":
                if len(args) < 2:
                    print("Error: connector_id required")
                    continue
                connector_id = int(args[1])
                engine.remove_connector(connector_id)
                print(f"Removed connector {connector_id}")

            elif command == "start-session":
                if len(args) < 2:
                    print("Error: connector_id required")
                    continue
                connector_id = int(args[1])
                transaction_id = 1
                max_energy = 55000.0
                i = 2
                while i < len(args):
                    if args[i] == "--transaction-id" and i + 1 < len(args):
                        transaction_id = int(args[i + 1])
                        i += 2
                    elif args[i] == "--max-energy" and i + 1 < len(args):
                        max_energy = float(args[i + 1])
                        i += 2
                    else:
                        i += 1
                engine.start_session(connector_id, transaction_id, max_energy)
                print(f"Started session on connector {connector_id}: transaction_id={transaction_id}, max_energy={max_energy}Wh")

            elif command == "stop-session":
                engine.stop_session()
                print("Stopped session")

            elif command == "simulate":
                steps = 1
                i = 1
                while i < len(args):
                    if args[i] == "--steps" and i + 1 < len(args):
                        steps = int(args[i + 1])
                        i += 2
                    else:
                        i += 1
                for _ in range(steps):
                    engine.simulate()
                print(f"Simulated {steps} step(s)")

            elif command == "status":
                print("=" * 50)
                print("ENGINE STATUS")
                print("=" * 50)
                print(f"Connectors: {len(engine.connectors)}")
                for connector in engine.connectors:
                    print(f"  Connector {connector.id}: {connector.status.name} - {connector.voltage}V, {connector.current}A, {connector.phase} phase(s)")
                print(f"Energy Meter: {engine.energy_meter.get_meter_reading()} {engine.energy_meter.unit}")
                if engine.session:
                    print(engine.get_session_info())
                else:
                    print("No active session")
                print("=" * 50)

            elif command == "run":
                steps = 10
                i = 1
                while i < len(args):
                    if args[i] == "--steps" and i + 1 < len(args):
                        steps = int(args[i + 1])
                        i += 2
                    else:
                        i += 1
                print(f"Running {steps} simulation steps...")
                for i in range(steps):
                    engine.simulate()
                    if i % 5 == 0 or i == steps - 1:
                        print(f"Step {i + 1}: {engine.energy_meter.get_meter_reading()} {engine.energy_meter.unit}")
                print("Simulation complete")

            else:
                print(f"Unknown command: {command}")
                print("Type 'help' for available commands")

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")


def main():
    parser = argparse.ArgumentParser(description="ChargeGhost EVSE CLI - Test Engine capabilities")
    parser.add_argument("--interactive", "-i", action="store_true", help="Run in interactive mode")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    parser_add = subparsers.add_parser("add-connector", help="Add a new connector")
    parser_add.add_argument("--voltage", type=float, default=230.0, help="Voltage in Volts (default: 230)")
    parser_add.add_argument("--current", type=float, default=32.0, help="Current in Amps (default: 32)")
    parser_add.add_argument("--phase", type=int, default=1, help="Number of phases (default: 1)")

    parser_remove = subparsers.add_parser("remove-connector", help="Remove a connector")
    parser_remove.add_argument("connector_id", type=int, help="Connector ID to remove")

    parser_start = subparsers.add_parser("start-session", help="Start a charging session")
    parser_start.add_argument("connector_id", type=int, help="Connector ID to start session on")
    parser_start.add_argument("--transaction-id", type=int, default=1, help="Transaction ID (default: 1)")
    parser_start.add_argument("--max-energy", type=float, default=55000.0, help="Max energy in Wh (default: 55000)")

    parser_stop = subparsers.add_parser("stop-session", help="Stop the current session")

    parser_simulate = subparsers.add_parser("simulate", help="Run a simulation step")
    parser_simulate.add_argument("--steps", type=int, default=1, help="Number of steps to simulate (default: 1)")

    parser_status = subparsers.add_parser("status", help="Show current status")

    parser_run = subparsers.add_parser("run", help="Run continuous simulation")
    parser_run.add_argument("--steps", type=int, default=10, help="Number of steps to run (default: 10)")

    args = parser.parse_args()

    if args.interactive:
        run_interactive_mode()
        return

    engine = Engine()

    if not args.command:
        parser.print_help()
        return

    if args.command == "add-connector":
        connector = engine.add_connector(args.voltage, args.current, args.phase)
        print(f"Added connector {connector.id}: {args.voltage}V, {args.current}A, {args.phase} phase(s)")

    elif args.command == "remove-connector":
        engine.remove_connector(args.connector_id)
        print(f"Removed connector {args.connector_id}")

    elif args.command == "start-session":
        engine.start_session(args.connector_id, args.transaction_id, args.max_energy)
        print(f"Started session on connector {args.connector_id}: transaction_id={args.transaction_id}, max_energy={args.max_energy}Wh")

    elif args.command == "stop-session":
        engine.stop_session()
        print("Stopped session")

    elif args.command == "simulate":
        for _ in range(args.steps):
            engine.simulate()
        print(f"Simulated {args.steps} step(s)")

    elif args.command == "status":
        print("=" * 50)
        print("ENGINE STATUS")
        print("=" * 50)
        print(f"Connectors: {len(engine.connectors)}")
        for connector in engine.connectors:
            print(f"  Connector {connector.id}: {connector.status.name} - {connector.voltage}V, {connector.current}A, {connector.phase} phase(s)")
        print(f"Energy Meter: {engine.energy_meter.get_meter_reading()} {engine.energy_meter.unit}")
        if engine.session:
            print(engine.get_session_info())
        else:
            print("No active session")
        print("=" * 50)

    elif args.command == "run":
        print(f"Running {args.steps} simulation steps...")
        for i in range(args.steps):
            engine.simulate()
            if i % 5 == 0 or i == args.steps - 1:
                print(f"Step {i + 1}: {engine.energy_meter.get_meter_reading()} {engine.energy_meter.unit}")
        print("Simulation complete")


if __name__ == "__main__":
    main()
