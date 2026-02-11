# ChargeGhost EVSE
An EVSE simulator written in Python, beautified and made easy with the help of Textual

## CLI Usage

The CLI provides both one-shot and interactive modes to test the Engine capabilities.

### Running the CLI

```bash
PYTHONPATH=/path/to/project/src python3 src/chargeghost_evse/cli.py [command] [options]
```

Or for interactive mode:

```bash
PYTHONPATH=/path/to/project/src python3 src/chargeghost_evse/cli.py --interactive
```

### Available Commands

#### One-Shot Mode

Each command creates a new Engine instance:

```bash
# Add a connector
python3 src/chargeghost_evse/cli.py add-connector --voltage 230 --current 32 --phase 1

# Remove a connector
python3 src/chargeghost_evse/cli.py remove-connector 0

# Start a session
python3 src/chargeghost_evse/cli.py start-session 0 --transaction-id 1 --max-energy 55000

# Stop a session
python3 src/chargeghost_evse/cli.py stop-session

# Run simulation steps
python3 src/chargeghost_evse/cli.py simulate --steps 5

# Run continuous simulation with output
python3 src/chargeghost_evse/cli.py run --steps 10

# Show status
python3 src/chargeghost_evse/cli.py status
```

#### Interactive Mode

In interactive mode, the Engine state persists across commands:

```bash
python3 src/chargeghost_evse/cli.py --interactive
```

Interactive commands:
- `add-connector [--voltage V] [--current A] [--phase P]`
- `remove-connector <id>`
- `start-session <id> [--transaction-id T] [--max-energy E]`
- `stop-session`
- `simulate [--steps N]`
- `run [--steps N]`
- `status`
- `help`
- `exit`