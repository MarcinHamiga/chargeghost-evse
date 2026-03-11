# Logging Overhaul Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the custom Event-based logging system with Python's `logging` module, structured log records, and collapsible UI payloads.

**Architecture:** Python `logging` as the backbone for all log generation and file output. A thin `LogBridgeHandler` converts log records into Qt signals for the UI. Components use named loggers (`chargeghost.engine`, `chargeghost.ocpp`, `chargeghost.bridge`) with a `_log()` wrapper. File output uses `RotatingFileHandler` with a JSON formatter.

**Tech Stack:** Python `logging`, PySide6 (`Signal`, `QScrollArea`, `QLabel`), `RotatingFileHandler`

**Spec:** `docs/superpowers/specs/2026-03-12-logging-overhaul-design.md`

---

## Chunk 1: Logging Infrastructure

### Task 1: Extract `_strip_markup` to shared utility

**Files:**
- Create: `src/chargeghost_evse/util/markup.py`
- Modify: `src/chargeghost_evse/util/session_logger.py:12-17`
- Test: `tests/test_markup.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_markup.py`:

```python
from chargeghost_evse.util.markup import strip_markup


class TestStripMarkup:
	def test_strips_rich_tags(self):
		assert strip_markup("[yellow]Engine:[/yellow] started") == "Engine: started"

	def test_preserves_plain_text(self):
		assert strip_markup("no tags here") == "no tags here"

	def test_strips_nested_tags(self):
		assert strip_markup("[bold][red]Error[/red][/bold]") == "Error"

	def test_empty_string(self):
		assert strip_markup("") == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_markup.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `src/chargeghost_evse/util/markup.py`:

```python
import re

_MARKUP_RE = re.compile(r"\[/?[^\]]+\]")


def strip_markup(text: str) -> str:
	"""Remove Rich-style markup tags from text."""
	return _MARKUP_RE.sub("", text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_markup.py -v`
Expected: PASS

- [ ] **Step 5: Update `session_logger.py` to import from new location**

In `src/chargeghost_evse/util/session_logger.py`, replace the local `_strip_markup` and `_MARKUP_RE` (lines 12-17) with:

```python
from chargeghost_evse.util.markup import strip_markup as _strip_markup
```

Remove:
```python
_MARKUP_RE = re.compile(r"\[/?[^\]]+\]")

def _strip_markup(text: str) -> str:
	return _MARKUP_RE.sub("", text)
```

Also remove the `import re` since it's no longer needed.

- [ ] **Step 6: Run existing session logger tests**

Run: `poetry run pytest tests/test_session_logger.py -v`
Expected: All PASS (no behavior change)

- [ ] **Step 7: Commit**

```bash
git add src/chargeghost_evse/util/markup.py tests/test_markup.py src/chargeghost_evse/util/session_logger.py
git commit -m "refactor: extract strip_markup to shared util/markup.py"
```

---

### Task 2: Create `JsonLogFormatter`

**Files:**
- Create: `src/chargeghost_evse/util/log_setup.py`
- Test: `tests/test_log_setup.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_log_setup.py`:

```python
import json
import logging
from datetime import datetime, timezone

from chargeghost_evse.util.log_setup import JsonLogFormatter


class TestJsonLogFormatter:
	def _make_record(self, message: str, **extra) -> logging.LogRecord:
		record = logging.LogRecord(
			name="chargeghost.engine",
			level=logging.INFO,
			pathname="",
			lineno=0,
			msg=message,
			args=None,
			exc_info=None,
		)
		for k, v in extra.items():
			setattr(record, k, v)
		return record

	def test_basic_fields(self):
		formatter = JsonLogFormatter()
		record = self._make_record("hello")
		output = json.loads(formatter.format(record))
		assert output["message"] == "hello"
		assert output["level"] == "INFO"
		assert output["logger"] == "chargeghost.engine"
		assert "ts" in output
		# Verify ts is valid UTC ISO format
		parsed = datetime.fromisoformat(output["ts"])
		assert parsed.tzinfo is not None

	def test_strips_rich_markup(self):
		formatter = JsonLogFormatter()
		record = self._make_record("[yellow]Engine:[/yellow] started")
		output = json.loads(formatter.format(record))
		assert output["message"] == "Engine: started"

	def test_includes_extra_fields(self):
		formatter = JsonLogFormatter()
		record = self._make_record("test", source="engine", connector_id=1)
		output = json.loads(formatter.format(record))
		assert output["source"] == "engine"
		assert output["connector_id"] == 1

	def test_includes_ocpp_fields(self):
		formatter = JsonLogFormatter()
		record = self._make_record(
			"TX BootNotification",
			ocpp_direction="TX",
			ocpp_action="BootNotification",
			ocpp_payload={"vendor": "ChargeGhost"},
		)
		output = json.loads(formatter.format(record))
		assert output["ocpp_direction"] == "TX"
		assert output["ocpp_action"] == "BootNotification"
		assert output["ocpp_payload"] == {"vendor": "ChargeGhost"}

	def test_omits_absent_extra_fields(self):
		formatter = JsonLogFormatter()
		record = self._make_record("plain")
		output = json.loads(formatter.format(record))
		assert "ocpp_direction" not in output
		assert "connector_id" not in output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_log_setup.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the implementation**

Create `src/chargeghost_evse/util/log_setup.py`:

```python
import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from chargeghost_evse.util.markup import strip_markup

_LOG_DIR = Path.home() / ".chargeghost" / "logs"

EXTRA_KEYS = (
	"source",
	"ocpp_direction",
	"ocpp_action",
	"ocpp_message_id",
	"ocpp_payload",
	"ocpp_correlated_id",
	"connector_id",
	"transition_from",
	"transition_to",
	"evaluated_profiles",
	"winning_profile",
	"computed_limit_amps",
	"reason",
)


class JsonLogFormatter(logging.Formatter):
	"""Formats log records as JSON lines with structured extra fields."""

	def format(self, record: logging.LogRecord) -> str:
		entry: dict = {
			"ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
			"level": record.levelname,
			"logger": record.name,
			"message": strip_markup(record.getMessage()),
		}
		for key in EXTRA_KEYS:
			value = getattr(record, key, None)
			if value is not None:
				entry[key] = value
		return json.dumps(entry)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_log_setup.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chargeghost_evse/util/log_setup.py tests/test_log_setup.py
git commit -m "feat: add JsonLogFormatter for structured JSON file logging"
```

---

### Task 3: Create `LogBridgeHandler`

**Files:**
- Modify: `src/chargeghost_evse/util/log_setup.py`
- Test: `tests/test_log_setup.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_log_setup.py`:

```python
from unittest.mock import MagicMock

from chargeghost_evse.util.log_setup import LogBridgeHandler


class TestLogBridgeHandler:
	def test_emit_calls_signal(self):
		mock_signal = MagicMock()
		handler = LogBridgeHandler(mock_signal)
		record = logging.LogRecord(
			name="chargeghost.engine",
			level=logging.INFO,
			pathname="",
			lineno=0,
			msg="test",
			args=None,
			exc_info=None,
		)
		handler.emit(record)
		mock_signal.emit.assert_called_once_with(record)

	def test_handler_level_filtering(self):
		mock_signal = MagicMock()
		handler = LogBridgeHandler(mock_signal)
		handler.setLevel(logging.WARNING)

		logger = logging.getLogger("chargeghost.test.bridge_handler")
		logger.addHandler(handler)
		logger.setLevel(logging.DEBUG)

		logger.debug("ignored")
		logger.warning("shown")

		assert mock_signal.emit.call_count == 1
		assert mock_signal.emit.call_args[0][0].getMessage() == "shown"

		logger.removeHandler(handler)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_log_setup.py::TestLogBridgeHandler -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the implementation**

Add to `src/chargeghost_evse/util/log_setup.py`:

```python
class LogBridgeHandler(logging.Handler):
	"""Routes Python log records to a Qt Signal for UI consumption.

	The signal parameter is typed as ``object`` because PySide6 signals
	are defined with ``Signal(object)`` to avoid Qt meta-type registration
	issues with ``logging.LogRecord``.
	"""

	def __init__(self, signal: object) -> None:
		super().__init__()
		self._signal = signal

	def emit(self, record: logging.LogRecord) -> None:
		self._signal.emit(record)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_log_setup.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chargeghost_evse/util/log_setup.py tests/test_log_setup.py
git commit -m "feat: add LogBridgeHandler for Python logging to Qt signal bridge"
```

---

### Task 4: Add `setup_file_logging()` helper

**Files:**
- Modify: `src/chargeghost_evse/util/log_setup.py`
- Test: `tests/test_log_setup.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_log_setup.py`:

```python
class TestSetupFileLogging:
	def test_creates_log_file(self, tmp_path):
		from chargeghost_evse.util.log_setup import setup_file_logging

		handler = setup_file_logging(log_dir=tmp_path)
		logger = logging.getLogger("chargeghost.test.file")
		logger.addHandler(handler)
		logger.setLevel(logging.DEBUG)

		logger.info("test message", extra={"source": "engine"})

		# Flush handler
		handler.flush()

		log_file = tmp_path / "chargeghost.log"
		assert log_file.exists()
		line = log_file.read_text().strip()
		record = json.loads(line)
		assert record["message"] == "test message"
		assert record["source"] == "engine"
		assert record["level"] == "INFO"

		logger.removeHandler(handler)
		handler.close()

	def test_strips_markup_in_file(self, tmp_path):
		from chargeghost_evse.util.log_setup import setup_file_logging

		handler = setup_file_logging(log_dir=tmp_path)
		logger = logging.getLogger("chargeghost.test.file2")
		logger.addHandler(handler)
		logger.setLevel(logging.DEBUG)

		logger.info("[yellow]Engine:[/yellow] started")
		handler.flush()

		log_file = tmp_path / "chargeghost.log"
		record = json.loads(log_file.read_text().strip())
		assert record["message"] == "Engine: started"

		logger.removeHandler(handler)
		handler.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_log_setup.py::TestSetupFileLogging -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the implementation**

Add to `src/chargeghost_evse/util/log_setup.py`:

```python
def setup_file_logging(
	log_dir: Optional[Path] = None,
) -> RotatingFileHandler:
	"""
	Create and return a RotatingFileHandler with JSON formatting.

	Args:
		log_dir: Directory for log files. Defaults to ~/.chargeghost/logs/.

	Returns:
		Configured RotatingFileHandler (caller must attach to a logger).
	"""
	log_dir = log_dir or _LOG_DIR
	log_dir.mkdir(parents=True, exist_ok=True)

	handler = RotatingFileHandler(
		log_dir / "chargeghost.log",
		maxBytes=5 * 1024 * 1024,
		backupCount=5,
	)
	handler.setLevel(logging.DEBUG)
	handler.setFormatter(JsonLogFormatter())
	return handler
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_log_setup.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chargeghost_evse/util/log_setup.py tests/test_log_setup.py
git commit -m "feat: add setup_file_logging with RotatingFileHandler + JSON formatter"
```

---

### Task 5: Update `LogMode` config and backward compatibility

**Files:**
- Modify: `src/chargeghost_evse/util/config.py:53,157,185,278,308`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_log_mode_shallow_deep_values(tmp_path, monkeypatch):
	"""log_mode must accept 'shallow' and 'deep' values."""
	config_file = tmp_path / "config.json"
	config_file.write_text(json.dumps({"log_mode": "deep"}))
	monkeypatch.setattr(cfg_module, "CONFIG_FILE", config_file)

	config = SimulationConfig.load()
	assert config.log_mode == "deep"


def test_log_mode_backward_compat_compact(tmp_path, monkeypatch):
	"""Old 'compact' value must be migrated to 'shallow'."""
	config_file = tmp_path / "config.json"
	config_file.write_text(json.dumps({"log_mode": "compact"}))
	monkeypatch.setattr(cfg_module, "CONFIG_FILE", config_file)

	config = SimulationConfig.load()
	assert config.log_mode == "shallow"


def test_log_mode_backward_compat_verbose(tmp_path, monkeypatch):
	"""Old 'verbose' value must be migrated to 'deep'."""
	config_file = tmp_path / "config.json"
	config_file.write_text(json.dumps({"log_mode": "verbose"}))
	monkeypatch.setattr(cfg_module, "CONFIG_FILE", config_file)

	config = SimulationConfig.load()
	assert config.log_mode == "deep"


def test_log_mode_default_is_shallow():
	"""Default log_mode must be 'shallow'."""
	config = SimulationConfig()
	assert config.log_mode == "shallow"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_config.py -v`
Expected: FAIL (default is "compact", not "shallow")

- [ ] **Step 3: Write the implementation**

In `src/chargeghost_evse/util/config.py`:

1. Change line 53:
```python
LogMode = Literal["shallow", "deep"]
```

2. Change line 157 (docstring):
```python
log_mode: OCPP message logging format ('shallow' or 'deep').
```

3. Change line 185:
```python
log_mode: LogMode = field(default="shallow")
```

4. After line 278 (`log_mode=data.get("log_mode", "compact")`), replace with:
```python
log_mode=_migrate_log_mode(data.get("log_mode", "shallow")),
```

5. Add this helper function before the `SimulationConfig` class:
```python
def _migrate_log_mode(value: str) -> "LogMode":
	"""Map old log mode values to new ones. Unknown values default to 'shallow'."""
	_COMPAT_MAP: dict[str, "LogMode"] = {"compact": "shallow", "verbose": "deep"}
	return _COMPAT_MAP.get(value, "shallow")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_config.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chargeghost_evse/util/config.py tests/test_config.py
git commit -m "feat: rename LogMode to shallow/deep with backward compat migration"
```

---

## Chunk 2: Component Migration

### Task 6: Migrate Engine and Connector logging

**Files:**
- Modify: `src/chargeghost_evse/engine/engine.py:26,112,128-136` and all `_log()` call sites
- Modify: `src/chargeghost_evse/engine/connector.py` (add logger for state transitions)
- Test: `tests/test_engine.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_engine.py`:

```python
import logging


class TestEngineLogging:
	def test_engine_uses_python_logger(self):
		"""Engine must use a named Python logger, not Event."""
		engine = Engine()
		assert hasattr(engine, 'logger')
		assert engine.logger.name == "chargeghost.engine"

	def test_engine_log_emits_to_python_logging(self, caplog):
		"""Engine._log must emit to Python logging system."""
		engine = Engine()
		with caplog.at_level(logging.DEBUG, logger="chargeghost.engine"):
			engine._log("[yellow]Engine:[/yellow] test message")

		assert len(caplog.records) == 1
		assert caplog.records[0].getMessage() == "[yellow]Engine:[/yellow] test message"
		assert caplog.records[0].source == "engine"

	def test_engine_no_on_log_event(self):
		"""Engine must not have on_log Event after migration."""
		engine = Engine()
		assert not hasattr(engine, 'on_log')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_engine.py::TestEngineLogging -v`
Expected: FAIL

- [ ] **Step 3: Migrate Engine**

In `src/chargeghost_evse/engine/engine.py`:

1. Add `import logging` to stdlib imports.

2. Remove `from chargeghost_evse.util.event import Event` only if `Event` is no longer used in this file. **Check first**: `session_started`, `session_stopped`, `connector_status_changed`, `connector_parameters_changed` still use `Event` — so keep the import.

3. Replace line 112 (`self.on_log: Event = Event()`) — delete this line.

4. Add after `super().__init__()` (line 81):
```python
self.logger = logging.getLogger("chargeghost.engine")
self._session_logger = logging.getLogger("chargeghost.engine.session")
```

5. Replace the `_log` method (lines 128-136) with:
```python
def _log(self, message: str, *, level: int = logging.INFO, **extra) -> None:
	self.logger.log(level, message, extra={"source": "engine", **extra})
```

6. Update all `_log` calls — remove any `is_important=True/False` or `is_ocpp_message=...` kwargs (Engine doesn't use these today, but verify). Assign levels to each call:
   - Error messages (e.g. "Cannot plug in", "is not plugged in", "not found") → add `level=logging.ERROR`
   - Warning messages (e.g. "expired", "Error:") → add `level=logging.WARNING`
   - Debug messages (e.g. session timing `_log(f"Session time [s]: ...")`) → add `level=logging.DEBUG`
   - All others stay at default INFO

   For session-lifecycle calls (session start, stop, suspend, resume, timing), use `self._session_logger` directly:
   ```python
   self._session_logger.info("Session started on connector %d", connector_id, extra={"source": "engine", "connector_id": connector_id})
   self._session_logger.debug("Session time [s]: %.1f", elapsed, extra={"source": "engine"})
   ```

7. For connector state change log calls, add structured extras:
```python
self._log(
	f"Connector {connector_id}: {old_status.value} → {new_status.value}",
	transition_from=old_status.value,
	transition_to=new_status.value,
	connector_id=connector_id,
)
```

8. **Add logger to Connector** (`src/chargeghost_evse/engine/connector.py`):
   - Add `import logging` at top
   - In `Connector.__init__`, add:
     ```python
     self.logger = logging.getLogger("chargeghost.engine.connector")
     ```
   - Add a `_log` wrapper:
     ```python
     def _log(self, message: str, *, level: int = logging.INFO, **extra) -> None:
     	self.logger.log(level, message, extra={"source": "engine", "connector_id": self.id, **extra})
     ```
   - Connector has no logging calls currently, but the logger is available for future use and for state transition logging if desired.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_engine.py -v`
Expected: All PASS (new and existing tests)

- [ ] **Step 5: Fix any broken tests that relied on `on_log`**

Some existing tests may subscribe to `engine.on_log`. Search for these patterns in test files:
```
engine.on_log
```
If found, remove those subscriptions — they're no longer needed since logging goes through Python's logging module.

- [ ] **Step 6: Commit**

```bash
git add src/chargeghost_evse/engine/engine.py src/chargeghost_evse/engine/connector.py tests/test_engine.py
git commit -m "refactor: migrate Engine and Connector logging from Event to Python logging"
```

---

### Task 7: Migrate Bridge/AsyncRunner logging

**Files:**
- Modify: `src/chargeghost_evse/bridge/bridge.py:137,151-159,450,727-735`
- Test: `tests/test_bridge_inject.py`

- [ ] **Step 1: Write the failing test**

Add to an appropriate test file (create `tests/test_bridge_logging.py` if needed):

```python
import logging
from unittest.mock import MagicMock

from chargeghost_evse.bridge.bridge import AsyncRunner


class TestBridgeLogging:
	def test_runner_uses_python_logger(self):
		runner = AsyncRunner(
			url="ws://localhost:9000/test",
			charge_point_id="CP_1",
			password="",
			command_queue=MagicMock(),
		)
		assert hasattr(runner, 'logger')
		assert runner.logger.name == "chargeghost.bridge"

	def test_runner_log_emits(self, caplog):
		runner = AsyncRunner(
			url="ws://localhost:9000/test",
			charge_point_id="CP_1",
			password="",
			command_queue=MagicMock(),
		)
		with caplog.at_level(logging.DEBUG, logger="chargeghost.bridge"):
			runner._log(message="connecting")
		assert len(caplog.records) == 1
		assert caplog.records[0].source == "bridge"

	def test_runner_no_on_log_event(self):
		runner = AsyncRunner(
			url="ws://localhost:9000/test",
			charge_point_id="CP_1",
			password="",
			command_queue=MagicMock(),
		)
		assert not hasattr(runner, 'on_log')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_bridge_logging.py -v`
Expected: FAIL

- [ ] **Step 3: Migrate AsyncRunner and Bridge**

In `src/chargeghost_evse/bridge/bridge.py`:

**AsyncRunner:**

1. Add `import logging` at the top.

2. In `__init__`, replace `self.on_log = Event()` (line 137) with:
```python
self.logger = logging.getLogger("chargeghost.bridge")
```

3. Replace `_log` method (lines 151-159) with:
```python
def _log(self, message: str, *, level: int = logging.INFO, **extra) -> None:
	self.logger.log(level, message, extra={"source": "bridge", **extra})
```

4. Update log call sites with appropriate levels:
   - Connection errors → `level=logging.ERROR`
   - Reconnect/backoff → `level=logging.WARNING`
   - "Connecting to...", "WebSocket connected", etc. → INFO (default)

**Bridge:**

1. Remove `self.on_log = self.runner.on_log` (line 450) — Bridge no longer needs its own `on_log` reference.

2. Replace Bridge's `_log` method (lines 727-735) with:
```python
def _log(self, message: str, *, level: int = logging.INFO, **extra) -> None:
	self.runner.logger.log(level, message, extra={"source": "bridge", **extra})
```
(Bridge delegates to runner's logger since they share `chargeghost.bridge`.)

- [ ] **Step 4: Run tests**

Run: `poetry run pytest tests/test_bridge_logging.py tests/test_bridge_inject.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chargeghost_evse/bridge/bridge.py tests/test_bridge_logging.py
git commit -m "refactor: migrate Bridge/AsyncRunner logging from Event to Python logging"
```

---

### Task 8: Migrate FirmwareManager logging

**Files:**
- Modify: `src/chargeghost_evse/ocpp_adapter/firmware_manager.py:54,59-60`
- Modify: `src/chargeghost_evse/ocpp_adapter/adapter.py:161,288-295`
- Test: `tests/test_firmware_manager.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_firmware_manager.py`:

```python
import logging


class TestFirmwareManagerLogging:
	def test_uses_python_logger(self):
		from chargeghost_evse.ocpp_adapter.firmware_manager import FirmwareManager
		fm = FirmwareManager()
		assert hasattr(fm, 'logger')
		assert fm.logger.name == "chargeghost.ocpp.firmware"

	def test_no_on_log_event(self):
		from chargeghost_evse.ocpp_adapter.firmware_manager import FirmwareManager
		fm = FirmwareManager()
		assert not hasattr(fm, 'on_log')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_firmware_manager.py::TestFirmwareManagerLogging -v`
Expected: FAIL

- [ ] **Step 3: Migrate FirmwareManager**

In `src/chargeghost_evse/ocpp_adapter/firmware_manager.py`:

1. Add `import logging` at top.

2. Replace `self.on_log: Event = Event()` (line 54) with:
```python
self.logger = logging.getLogger("chargeghost.ocpp.firmware")
```

3. Replace `_log` method (lines 59-60) with:
```python
def _log(self, message: str, *, level: int = logging.INFO) -> None:
	self.logger.log(level, message, extra={"source": "ocpp"})
```

4. Remove the `Event` import if it's no longer used in this file. Check: `on_diagnostics_status_changed` and `on_firmware_status_changed` still use `Event` — keep the import if so.

**In `src/chargeghost_evse/ocpp_adapter/adapter.py`:**

5. Remove line 161: `self.firmware_manager.on_log.subscribe(self._log_from_firmware_manager)`

6. Remove the `_log_from_firmware_manager` method (lines 288-295).

- [ ] **Step 4: Run tests**

Run: `poetry run pytest tests/test_firmware_manager.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chargeghost_evse/ocpp_adapter/firmware_manager.py src/chargeghost_evse/ocpp_adapter/adapter.py tests/test_firmware_manager.py
git commit -m "refactor: migrate FirmwareManager logging to Python logging"
```

---

### Task 9: Migrate OCPP Adapter logging

**Files:**
- Modify: `src/chargeghost_evse/ocpp_adapter/adapter.py:141,212-231,297-351` and all `_log()` call sites
- Test: `tests/test_callerror_handling.py`

This is the largest migration (~120 call sites). The key changes are:

- [ ] **Step 1: Write the failing test**

Create `tests/test_adapter_logging.py`:

```python
import logging
from unittest.mock import AsyncMock, MagicMock

from chargeghost_evse.ocpp_adapter.adapter import Adapter


def _make_adapter() -> Adapter:
	"""Create an Adapter with mocked connection for testing."""
	mock_conn = MagicMock()
	mock_conn.recv = AsyncMock()
	mock_conn.send = AsyncMock()
	adapter = Adapter(
		id="CP_1",
		connection=mock_conn,
		command_queue=MagicMock(),
	)
	return adapter


class TestAdapterLogging:
	def test_adapter_has_python_logger(self):
		adapter = _make_adapter()
		assert hasattr(adapter, 'logger')
		assert adapter.logger.name == "chargeghost.ocpp"
		assert adapter._tx_logger.name == "chargeghost.ocpp.tx"

	def test_adapter_no_on_log_event(self):
		adapter = _make_adapter()
		assert not hasattr(adapter, 'on_log')

	def test_adapter_log_emits_to_python_logging(self, caplog):
		adapter = _make_adapter()
		with caplog.at_level(logging.DEBUG, logger="chargeghost.ocpp"):
			adapter._log("test config change")
		assert len(caplog.records) >= 1
		assert caplog.records[0].source == "ocpp"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_adapter_logging.py -v`
Expected: FAIL

- [ ] **Step 3: Migrate the Adapter**

**Behavioral note:** `MeterValues` and `Heartbeat` are demoted from INFO to DEBUG (they were in the old `is_important` set but the spec categorizes them as DEBUG-level noise in shallow mode).

In `src/chargeghost_evse/ocpp_adapter/adapter.py`:

1. Add `import logging` at top.

2. Replace `self.on_log = Event()` (line 141) with:
```python
self.logger = logging.getLogger("chargeghost.ocpp")
self._tx_logger = logging.getLogger("chargeghost.ocpp.tx")
```

3. Replace `_log` method (lines 212-231) with:
```python
def _log(
	self,
	message: str,
	*,
	level: int = logging.INFO,
	**extra,
) -> None:
	self.logger.log(level, message, extra={"source": "ocpp", **extra})
```

4. Replace `_log_ocpp_raw` method (lines 297-351) with:
```python
def _log_ocpp_raw(
	self,
	direction: str,
	action: str,
	payload: Any,
	message_id: str = "",
) -> None:
	try:
		if isinstance(payload, dict):
			payload_str = json.dumps(payload, indent=2)
		else:
			payload_str = str(payload)
	except (TypeError, ValueError):
		payload_str = str(payload)

	raw_msg = f"[{direction}] {action}"
	if message_id:
		raw_msg += f" (id={message_id})"
	raw_msg += f"\n{payload_str}"

	# Important actions shown in shallow mode (INFO), others are DEBUG
	important_actions = {
		"BootNotification",
		"StartTransaction",
		"StopTransaction",
		"Authorize",
		"RemoteStartTransaction",
		"RemoteStopTransaction",
		"Reset",
		"StatusNotification",
		"GetDiagnostics",
		"DiagnosticsStatusNotification",
		"UpdateFirmware",
		"FirmwareStatusNotification",
		"GetConfiguration",
		"ChangeConfiguration",
		"SendLocalList",
		"GetLocalListVersion",
	}
	level = logging.INFO if action in important_actions else logging.DEBUG

	self.on_ocpp_message.emit(
		direction=direction, action=action, payload=payload_str
	)
	self._tx_logger.log(
		level,
		raw_msg,
		extra={
			"source": "ocpp",
			"ocpp_direction": direction,
			"ocpp_action": action,
			"ocpp_message_id": message_id,
			"ocpp_payload": payload if isinstance(payload, dict) else payload_str,
			# For RX (responses), set correlated_id to match the TX message_id.
			# In OCPP 1.6, the response uses the same unique_id as the request,
			# so this equals ocpp_message_id on RX records. The UI can group
			# TX+RX records by matching TX.ocpp_message_id == RX.ocpp_correlated_id.
			"ocpp_correlated_id": message_id if direction == "RX" else None,
		},
	)
```

5. Update all existing `_log()` call sites:
   - Remove `is_ocpp_message=False` and `is_ocpp_message=True` kwargs everywhere
   - Remove `is_important=True` kwargs (now default INFO level)
   - Replace `is_important=False` with `level=logging.DEBUG`
   - Use `level=logging.WARNING` for rejected/error messages
   - Use `level=logging.ERROR` for exceptions

- [ ] **Step 4: Run tests**

Run: `poetry run pytest tests/test_callerror_handling.py tests/test_adapter_logging.py -v`
Expected: All PASS

Run: `poetry run pytest -x`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chargeghost_evse/ocpp_adapter/adapter.py
git commit -m "refactor: migrate OCPP Adapter logging to Python logging"
```

---

## Chunk 3: UI Integration & QtSignalBridge

### Task 10: Migrate QtSignalBridge

**Files:**
- Modify: `src/chargeghost_evse/ui/bridge.py:9,17,23-24,45-51`

- [ ] **Step 1: Write the test**

Add to `tests/test_ui_widgets.py` (or create `tests/test_qt_signal_bridge.py`):

```python
class TestQtSignalBridgeLogging:
	def test_has_log_record_received_signal(self):
		from chargeghost_evse.ui.bridge import QtSignalBridge
		assert hasattr(QtSignalBridge, 'log_record_received')

	def test_no_log_received_signal(self):
		from chargeghost_evse.ui.bridge import QtSignalBridge
		assert not hasattr(QtSignalBridge, 'log_received')
```

- [ ] **Step 2: Migrate QtSignalBridge**

In `src/chargeghost_evse/ui/bridge.py`:

1. Replace `log_received = Signal(str, str, bool)` (line 9) with:
```python
log_record_received = Signal(object)
```

2. In `__init__`, remove lines 23-24:
```python
engine.on_log.subscribe(self._on_engine_log)
bridge.on_log.subscribe(self._on_bridge_log)
```

3. Remove `_on_engine_log` and `_on_bridge_log` methods (lines 45-51).

**Note:** The `LogBridgeHandler` will be attached in `MainWindow.__init__` instead. The QtSignalBridge no longer needs to know about engine/bridge log events.

- [ ] **Step 2: Run tests**

Run: `poetry run pytest -x`
Expected: Some UI tests may fail if they reference `log_received` — fix in next task.

- [ ] **Step 3: Commit**

```bash
git add src/chargeghost_evse/ui/bridge.py
git commit -m "refactor: replace QtSignalBridge log_received with log_record_received"
```

---

### Task 11: Update MainWindow logging setup

**Files:**
- Modify: `src/chargeghost_evse/ui/app.py:45,844,847,901-904,923-925,1049-1053,1092-1111,1219`

- [ ] **Step 1: Update imports**

In `src/chargeghost_evse/ui/app.py`:

1. Remove line 45: `from chargeghost_evse.util.session_logger import SessionFileLogger`
2. Add:
```python
import logging
from chargeghost_evse.util.log_setup import LogBridgeHandler, setup_file_logging
```

- [ ] **Step 2: Replace SessionFileLogger with new handlers**

In `MainWindow.__init__`, replace line 844 (`self._session_logger = SessionFileLogger(...)`) with:

```python
# Set up Python logging for chargeghost namespace
cg_logger = logging.getLogger("chargeghost")
cg_logger.setLevel(logging.DEBUG)

# File handler: rotating JSON logs (attach before banner so it's captured)
self._file_handler = setup_file_logging()
cg_logger.addHandler(self._file_handler)

# UI handler: bridge to Qt signal
self._ui_handler = LogBridgeHandler(self.signal_bridge.log_record_received)
self._ui_handler.setLevel(logging.DEBUG)
cg_logger.addHandler(self._ui_handler)

cg_logger.info("=== ChargeGhost session started ===")
```

- [ ] **Step 3: Update signal connection**

Replace line 847 (`self.signal_bridge.log_received.connect(self.on_log_received)`) with:
```python
self.signal_bridge.log_record_received.connect(self.on_log_received)
```

- [ ] **Step 4: Update `on_log_received` method (interim — Task 17 will replace with `log_record`)**

Replace lines 1092-1111 with:

```python
@Slot(object)
def on_log_received(self, record: object) -> None:
	import logging as _logging
	if self.app_settings.log_mode == "shallow" and record.levelno < _logging.INFO:
		return

	# Derive source tag from logger name
	name = record.name
	if name.startswith("chargeghost.engine"):
		tag = "engine"
		source = "Engine"
	elif name.startswith("chargeghost.ocpp") or name.startswith("chargeghost.bridge"):
		tag = "ocpp"
		source = "OCPP"
	else:
		tag = "white"
		source = "System"

	message = record.getMessage()
	formatted_message = f"[{tag}]{source}:[/] {message}"

	if self.stack.currentWidget() != self.mode_select:
		self._global_log_panel.log_message(formatted_message)

	if self.stack.currentWidget() == self.manual:
		self.manual.log_message(formatted_message)
```

**Note:** This interim version uses `log_message()` with pre-formatted strings. Task 17 will replace this to use `log_record()` with collapsible entries.

- [ ] **Step 5: Update log mode toggle methods**

Replace all occurrences of `"compact"` with `"shallow"` and `"verbose"` with `"deep"` in:
- `_on_global_log_mode_toggle` (line 1049-1053)
- `ManualModeWidget.action_toggle_log_mode` references
- Initial button state checks (lines 901-904, 923-925)

Update button labels: `"Detailed"` → `"Deep"`, `"Compact"` → `"Shallow"`.

- [ ] **Step 6: Update cleanup**

Replace line 1219 (`self._session_logger.close()`) with:

```python
cg_logger = logging.getLogger("chargeghost")
cg_logger.removeHandler(self._file_handler)
cg_logger.removeHandler(self._ui_handler)
self._file_handler.close()
```

- [ ] **Step 7: Run tests**

Run: `poetry run pytest -x`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add src/chargeghost_evse/ui/app.py
git commit -m "feat: wire LogBridgeHandler and RotatingFileHandler into MainWindow"
```

---

### Task 12: Update CollapsibleLogPanel button labels

**Files:**
- Modify: `src/chargeghost_evse/ui/widgets/collapsible_log.py:76,148`

- [ ] **Step 1: Update labels**

In `src/chargeghost_evse/ui/widgets/collapsible_log.py`:

1. Line 76: Change `"Detailed"` to `"Deep"`
2. Line 148: Change `"Compact" if is_detailed else "Detailed"` to `"Shallow" if is_detailed else "Deep"`

- [ ] **Step 2: Run tests**

Run: `poetry run pytest tests/test_ui_widgets.py -v`
Expected: PASS (update any tests that assert on old label text)

- [ ] **Step 3: Commit**

```bash
git add src/chargeghost_evse/ui/widgets/collapsible_log.py
git commit -m "refactor: rename log mode buttons from Detailed/Compact to Deep/Shallow"
```

---

## Chunk 4: Cleanup & SessionFileLogger Removal

### Task 13: Delete SessionFileLogger and update tests

**Files:**
- Delete: `src/chargeghost_evse/util/session_logger.py`
- Delete: `tests/test_session_logger.py`

- [ ] **Step 1: Verify no remaining imports**

Search for any remaining references to `SessionFileLogger` or `session_logger`:

```bash
poetry run ruff check src/ --select F811,F401
```

Also manually grep:
```
grep -r "session_logger\|SessionFileLogger" src/ tests/
```

If any remain beyond the file itself and its test, update those files first.

- [ ] **Step 2: Delete the files**

```bash
git rm src/chargeghost_evse/util/session_logger.py
git rm tests/test_session_logger.py
```

- [ ] **Step 3: Run all tests**

Run: `poetry run pytest -x`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git commit -m "refactor: remove SessionFileLogger, replaced by RotatingFileHandler"
```

---

### Task 14: Clean up Event imports no longer needed for logging

**Files:**
- Modify: various files that imported Event only for `on_log`

- [ ] **Step 1: Audit Event usage**

For each file that was migrated, check if `Event` is still imported and used for non-logging events:

- `engine.py`: still uses Event for `session_started`, `session_stopped`, `connector_status_changed`, `connector_parameters_changed` → **keep import**
- `bridge.py` (AsyncRunner): still uses Event for `on_adapter_registered`, `on_reset_requested` → **keep import**
- `adapter.py`: still uses Event for `on_ocpp_message`, `on_reset_requested`, `on_registration_accepted`, `on_heartbeat_response` → **keep import**
- `firmware_manager.py`: still uses Event for `on_diagnostics_status_changed`, `on_firmware_status_changed` → **keep import**

No imports to remove. Skip this task if all files still use Event for other purposes.

- [ ] **Step 2: Run linter**

Run: `poetry run ruff check src/ --fix`

- [ ] **Step 3: Commit (if changes)**

```bash
git add -u
git commit -m "chore: clean up unused Event imports after logging migration"
```

---

## Chunk 5: ChargingProfileManager Logging (Net-New)

### Task 15: Add logging to ChargingProfileManager

**Files:**
- Modify: `src/chargeghost_evse/ocpp_adapter/charging_profile_manager.py:143+,201-243,245-284,329-380`
- Test: `tests/test_charging_profile_logging.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_charging_profile_logging.py`:

```python
import logging
from datetime import datetime, timezone

from ocpp.v16.enums import (
	ChargingProfileKindType,
	ChargingProfilePurposeType,
	ChargingRateUnitType,
)

from chargeghost_evse.ocpp_adapter.charging_profile_manager import (
	ChargingProfileData,
	ChargingProfileManager,
	ChargingScheduleData,
	ChargingSchedulePeriodData,
)


def _make_profile(
	profile_id: int = 1,
	stack_level: int = 0,
	purpose: ChargingProfilePurposeType = ChargingProfilePurposeType.tx_default_profile,
	limit: float = 16.0,
	transaction_id: int = None,
) -> ChargingProfileData:
	return ChargingProfileData(
		charging_profile_id=profile_id,
		stack_level=stack_level,
		charging_profile_purpose=purpose,
		charging_profile_kind=ChargingProfileKindType.absolute,
		charging_schedule=ChargingScheduleData(
			charging_rate_unit=ChargingRateUnitType.a,
			charging_schedule_period=(
				ChargingSchedulePeriodData(start_period=0, limit=limit),
			),
		),
		transaction_id=transaction_id,
	)


class TestChargingProfileLogging:
	def test_set_profile_logs_info(self, caplog):
		mgr = ChargingProfileManager()
		profile = _make_profile(limit=16.0)
		with caplog.at_level(logging.INFO, logger="chargeghost.ocpp.profiles"):
			mgr.set_profile(connector_id=1, profile=profile)
		assert any("installed" in r.message.lower() for r in caplog.records)

	def test_clear_profiles_logs_info(self, caplog):
		mgr = ChargingProfileManager()
		profile = _make_profile()
		mgr.set_profile(connector_id=1, profile=profile)
		caplog.clear()
		with caplog.at_level(logging.INFO, logger="chargeghost.ocpp.profiles"):
			mgr.clear_profiles(profile_id=1)
		assert any("cleared" in r.message.lower() for r in caplog.records)

	def test_get_composite_limit_logs_debug_trace(self, caplog):
		mgr = ChargingProfileManager()
		profile = _make_profile(limit=16.0)
		mgr.set_profile(connector_id=1, profile=profile)
		with caplog.at_level(logging.DEBUG, logger="chargeghost.ocpp.profiles"):
			mgr.get_composite_limit(
				connector_id=1,
				transaction_id=None,
				now=datetime.now(timezone.utc),
				connector_voltage=230.0,
			)
		debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
		assert len(debug_records) >= 1
		# Verify structured extras
		trace = debug_records[0]
		assert hasattr(trace, 'evaluated_profiles')
		assert hasattr(trace, 'computed_limit_amps')

	def test_no_profiles_logs_debug(self, caplog):
		mgr = ChargingProfileManager()
		with caplog.at_level(logging.DEBUG, logger="chargeghost.ocpp.profiles"):
			result = mgr.get_composite_limit(
				connector_id=1,
				transaction_id=None,
				now=datetime.now(timezone.utc),
				connector_voltage=230.0,
			)
		assert result is None
		debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
		assert any("no active profile" in r.message.lower() for r in debug_records)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_charging_profile_logging.py -v`
Expected: FAIL

- [ ] **Step 3: Add logging to ChargingProfileManager**

In `src/chargeghost_evse/ocpp_adapter/charging_profile_manager.py`:

1. Add `import logging` at top.

2. In `ChargingProfileManager.__init__` (around line 190), add:
```python
self.logger = logging.getLogger("chargeghost.ocpp.profiles")
```

3. At the end of `set_profile()`, before `return None` (line 243), add:
```python
self.logger.info(
	f"Profile installed: {profile.charging_profile_purpose.value} "
	f"#{profile.charging_profile_id} "
	f"(stack_level={profile.stack_level}, "
	f"{profile.charging_profile_kind.value}, "
	f"{profile.charging_schedule.charging_schedule_period[0].limit}A limit)"
	if profile.charging_schedule.charging_schedule_period else
	f"Profile installed: {profile.charging_profile_purpose.value} "
	f"#{profile.charging_profile_id}",
	extra={"source": "ocpp", "connector_id": connector_id},
)
```

4. In `clear_profiles()`, after the removal loop and before `return len(to_remove)` (line 284), add:
```python
if to_remove:
	self.logger.info(
		f"Profile(s) cleared: {to_remove}",
		extra={"source": "ocpp"},
	)
```

5. In `get_composite_limit()`, after calculating the result (line 380), add DEBUG trace logging:
```python
# Build evaluation trace
evaluated = []
if cp_max_limit is not None:
	evaluated.append({
		"purpose": "ChargePointMaxProfile",
		"limit": cp_max_limit,
	})
if tx_limit is not None:
	evaluated.append({
		"purpose": "TxProfile/TxDefaultProfile",
		"limit": tx_limit,
	})

if not active_limits:
	self.logger.debug(
		f"No active profile for connector {connector_id}",
		extra={
			"source": "ocpp",
			"connector_id": connector_id,
			"evaluated_profiles": [],
			"computed_limit_amps": None,
		},
	)
	return None

result = min(active_limits)
self.logger.debug(
	f"Profile evaluation for connector {connector_id}: limit={result}A",
	extra={
		"source": "ocpp",
		"connector_id": connector_id,
		"evaluated_profiles": evaluated,
		"computed_limit_amps": result,
	},
)
return result
```

Note: You'll need to restructure the method slightly so the trace logging happens before the return. The current code at line 378-380 returns directly — change it to store the result first, log, then return.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_charging_profile_logging.py -v`
Expected: All PASS

- [ ] **Step 5: Run all tests**

Run: `poetry run pytest -x`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/chargeghost_evse/ocpp_adapter/charging_profile_manager.py tests/test_charging_profile_logging.py
git commit -m "feat: add structured logging to ChargingProfileManager"
```

---

## Chunk 6: UI Collapsible Payloads

### Task 16: Add collapsible log entry widget

**Files:**
- Create: `src/chargeghost_evse/ui/widgets/log_entry.py`
- Test: `tests/test_ui_widgets.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_ui_widgets.py`:

```python
from chargeghost_evse.ui.widgets.log_entry import CollapsibleLogEntry


class TestCollapsibleLogEntry:
	def test_creates_with_summary(self, qtbot):
		entry = CollapsibleLogEntry(summary="TX BootNotification", detail='{"vendor": "CG"}')
		qtbot.addWidget(entry)
		assert entry._summary_label.text() is not None
		assert not entry._detail_label.isVisible()

	def test_click_toggles_detail(self, qtbot):
		entry = CollapsibleLogEntry(summary="TX BootNotification", detail='{"vendor": "CG"}')
		qtbot.addWidget(entry)
		assert not entry._detail_label.isVisible()
		entry._on_toggle()
		assert entry._detail_label.isVisible()
		entry._on_toggle()
		assert not entry._detail_label.isVisible()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_ui_widgets.py::TestCollapsibleLogEntry -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the implementation**

Create `src/chargeghost_evse/ui/widgets/log_entry.py`:

```python
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from chargeghost_evse.ui.styles import colors


class CollapsibleLogEntry(QWidget):
	"""A log entry with a clickable summary and togglable detail section."""

	def __init__(
		self,
		summary: str,
		detail: Optional[str] = None,
		parent: Optional[QWidget] = None,
	) -> None:
		super().__init__(parent)

		layout = QVBoxLayout(self)
		layout.setContentsMargins(0, 0, 0, 0)
		layout.setSpacing(0)

		self._summary_label = QLabel(summary)
		self._summary_label.setTextFormat(Qt.TextFormat.RichText)
		self._summary_label.setWordWrap(True)
		layout.addWidget(self._summary_label)

		self._detail_label = QLabel(detail or "")
		self._detail_label.setTextFormat(Qt.TextFormat.PlainText)
		self._detail_label.setWordWrap(True)
		self._detail_label.setStyleSheet(
			f"font-family: monospace; color: {colors.TEXT_SECONDARY}; "
			f"padding: 4px 0 4px 20px;"
		)
		self._detail_label.hide()
		layout.addWidget(self._detail_label)

		if detail:
			self._summary_label.setCursor(Qt.CursorShape.PointingHandCursor)
			self._summary_label.mousePressEvent = lambda _: self._on_toggle()

	def _on_toggle(self) -> None:
		self._detail_label.setVisible(not self._detail_label.isVisible())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_ui_widgets.py::TestCollapsibleLogEntry -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chargeghost_evse/ui/widgets/log_entry.py tests/test_ui_widgets.py
git commit -m "feat: add CollapsibleLogEntry widget for expandable log payloads"
```

---

### Task 17: Update LogPanel to support LogRecord rendering with collapsible entries

**Files:**
- Modify: `src/chargeghost_evse/ui/widgets/log_panel.py`
- Test: `tests/test_ui_widgets.py`

- [ ] **Step 1: Redesign LogPanel**

Replace the current `QTextEdit`-based `LogPanel` with a `QScrollArea`-based panel that can hold both simple text entries and collapsible entries.

**Known trade-offs:** The `QTextEdit` supports text selection and copy. The new `QScrollArea` with `QLabel` children does not natively support selecting text across entries. Individual `QLabel` text can be selected if `setTextInteractionFlags` is set. This is acceptable — the primary use case is visual inspection, and file logs serve the copy/paste debugging need.

In `src/chargeghost_evse/ui/widgets/log_panel.py`:

```python
import json
import logging
import re
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from chargeghost_evse.ui.styles import colors
from chargeghost_evse.ui.widgets.log_entry import CollapsibleLogEntry

_MAX_ENTRIES = 500


class LogPanel(QScrollArea):
	def __init__(self, parent: Optional[QWidget] = None) -> None:
		super().__init__(parent)
		self.setObjectName("LogPanel")
		self.setWidgetResizable(True)
		self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

		self._container = QWidget()
		self._layout = QVBoxLayout(self._container)
		self._layout.setContentsMargins(4, 4, 4, 4)
		self._layout.setSpacing(2)
		self._layout.addStretch()
		self.setWidget(self._container)

		self._entry_count = 0

	def log_message(self, message: str) -> None:
		"""Add a simple text log entry (backward compatible)."""
		html = self._textual_to_html(message)
		label = QLabel(html)
		label.setTextFormat(Qt.TextFormat.RichText)
		label.setWordWrap(True)
		self._add_entry(label)

	def log_record(self, record: logging.LogRecord) -> None:
		"""Add a log entry from a Python LogRecord, with collapsible support."""
		message = record.getMessage()
		html_message = self._textual_to_html(self._format_summary(record, message))

		# Check for collapsible content
		payload = getattr(record, "ocpp_payload", None)
		evaluated = getattr(record, "evaluated_profiles", None)

		if payload is not None:
			detail = json.dumps(payload, indent=2) if isinstance(payload, dict) else str(payload)
			entry = CollapsibleLogEntry(summary=html_message, detail=detail)
			self._add_entry(entry)
		elif evaluated is not None:
			limit = getattr(record, "computed_limit_amps", None)
			lines = [f"Profiles evaluated: {len(evaluated)}"]
			for p in evaluated:
				lines.append(f"  {p.get('purpose', '?')}: {p.get('limit', '?')}A")
			if limit is not None:
				lines.append(f"Effective limit: {limit}A")
			entry = CollapsibleLogEntry(summary=html_message, detail="\n".join(lines))
			self._add_entry(entry)
		else:
			label = QLabel(html_message)
			label.setTextFormat(Qt.TextFormat.RichText)
			label.setWordWrap(True)
			self._add_entry(label)

	def _format_summary(self, record: logging.LogRecord, message: str) -> str:
		"""Format a one-line summary for the log entry."""
		name = record.name
		if name.startswith("chargeghost.engine"):
			tag = "engine"
			source = "Engine"
		elif name.startswith("chargeghost.ocpp") or name.startswith("chargeghost.bridge"):
			tag = "ocpp"
			source = "OCPP"
		else:
			tag = "white"
			source = "System"

		prefix = ""
		if record.levelno >= logging.ERROR:
			prefix = "[red]ERROR[/red] "
		elif record.levelno >= logging.WARNING:
			prefix = "[yellow]WARN[/yellow] "

		return f"{prefix}[{tag}]{source}:[/] {message}"

	def _add_entry(self, widget: QWidget) -> None:
		"""Add widget before the stretch, enforce max entries."""
		self._layout.insertWidget(self._layout.count() - 1, widget)
		self._entry_count += 1

		while self._entry_count > _MAX_ENTRIES:
			item = self._layout.itemAt(0)
			if item and item.widget():
				w = item.widget()
				self._layout.removeWidget(w)
				w.deleteLater()
				self._entry_count -= 1
			else:
				break  # safety: don't remove stretch or spacer items

		# Auto-scroll to bottom
		self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

	def clear(self) -> None:
		"""Remove all log entries."""
		while self._layout.count() > 1:  # keep the stretch
			item = self._layout.takeAt(0)
			if item and item.widget():
				item.widget().deleteLater()
		self._entry_count = 0

	def _textual_to_html(self, text: str) -> str:
		text = self._escape_html(text)
		text = self._convert_style_tags(text)
		return text

	def _escape_html(self, text: str) -> str:
		text = text.replace("&", "&amp;")
		text = text.replace("<", "&lt;")
		text = text.replace(">", "&gt;")
		return text

	def _convert_style_tags(self, text: str) -> str:
		style_map = {
			"b": "font-weight: bold",
			"bold": "font-weight: bold",
			"i": "font-style: italic",
			"italic": "font-style: italic",
			"u": "text-decoration: underline",
			"underline": "text-decoration: underline",
			"dim": f"color: {colors.TEXT_MUTED}",
		}

		color_map = {
			"blue": colors.INFO,
			"yellow": colors.WARNING,
			"green": colors.SUCCESS,
			"red": colors.DANGER,
			"cyan": colors.INFO,
			"magenta": "#a371f7",
			"white": colors.TEXT_PRIMARY,
			"black": colors.BG_MAIN,
			"orange": colors.WARNING,
			"purple": "#a371f7",
			"teal": colors.ACCENT_TEAL,
			"gray": colors.TEXT_SECONDARY,
			"muted": colors.TEXT_MUTED,
			"engine": colors.LOG_COLORS["engine"],
			"ocpp": colors.LOG_COLORS["ocpp"],
			"ui": colors.LOG_COLORS["ui"],
		}

		tag_pattern = re.compile(r"\[([^\]]+)\]")

		result = []
		pos = 0
		open_tags: list[str] = []

		for match in tag_pattern.finditer(text):
			result.append(text[pos : match.start()])
			pos = match.end()

			tag = match.group(1)

			if tag.startswith("/"):
				if open_tags:
					open_tags.pop()
					result.append("</span>")
			elif tag in style_map:
				result.append(f'<span style="{style_map[tag]}">')
				open_tags.append(tag)
			elif tag in color_map:
				result.append(f'<span style="color:{color_map[tag]}">')
				open_tags.append(tag)
			else:
				result.append(match.group(0))

		result.append(text[pos:])

		while open_tags:
			result.append("</span>")
			open_tags.pop()

		return "".join(result)
```

- [ ] **Step 2: Update CollapsibleLogPanel**

`CollapsibleLogPanel.log_message` (line 156-157) still delegates to `self.log_panel.log_message()` — this continues to work. Add a new method:

```python
def log_record(self, record: object) -> None:
	"""Add a log record with collapsible support."""
	self.log_panel.log_record(record)
```

- [ ] **Step 3: Update MainWindow to use `log_record`**

In `MainWindow.on_log_received`, instead of formatting and calling `log_message`, pass the raw record:

```python
@Slot(object)
def on_log_received(self, record: object) -> None:
	import logging as _logging
	if self.app_settings.log_mode == "shallow" and record.levelno < _logging.INFO:
		return

	if self.stack.currentWidget() != self.mode_select:
		self._global_log_panel.log_record(record)

	if self.stack.currentWidget() == self.manual:
		self.manual.log_record(record)
```

This means the `LogPanel.log_record` method handles both formatting and collapsibility internally.

- [ ] **Step 4: Update ManualModeWidget**

Ensure `ManualModeWidget` has a `log_record` method that delegates to its log panel, same as `log_message` does today.

- [ ] **Step 5: Run tests**

Run: `poetry run pytest tests/test_ui_widgets.py -v`
Expected: All PASS

Run: `poetry run pytest -x`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/chargeghost_evse/ui/widgets/log_panel.py src/chargeghost_evse/ui/widgets/collapsible_log.py src/chargeghost_evse/ui/app.py
git commit -m "feat: redesign LogPanel with QScrollArea and collapsible entries"
```

---

## Chunk 7: Documentation & Final Verification

### Task 18: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update logging convention**

In `CLAUDE.md`, replace the logging convention:

Old:
```
- **Logging**: classes expose `on_log: Event`; emit via `self._log(message="...")`. Log prefixes use Rich markup: `"[yellow]Engine:[/yellow]"`.
```

New:
```
- **Logging**: classes use Python `logging` module with named loggers under the `chargeghost` namespace (e.g., `logging.getLogger("chargeghost.engine")`). The `_log()` wrapper standardizes the `source` extra field. Log levels: ERROR (failures), WARNING (rejected/retry), INFO (lifecycle/state changes — shown in shallow mode), DEBUG (payloads/traces — shown in deep mode). Rich markup in messages is supported for UI rendering and stripped for file output. File logs: `~/.chargeghost/logs/chargeghost.log` (rotating JSON).
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md logging convention for Python logging migration"
```

---

### Task 19: Final verification

- [ ] **Step 1: Run full test suite**

Run: `poetry run pytest -v`
Expected: All PASS

- [ ] **Step 2: Run linter and type checker**

Run: `poetry run ruff check src/`
Run: `poetry run mypy src/`

Fix any issues.

- [ ] **Step 3: Run the app**

Run: `poetry run dev`

Verify:
1. App launches without errors
2. Log panel shows messages
3. Shallow/Deep toggle works
4. Connecting to a CPMS shows OCPP messages
5. In Deep mode, OCPP payloads are collapsible

- [ ] **Step 4: Check file logging**

Verify `~/.chargeghost/logs/chargeghost.log` exists and contains valid JSON lines after running the app.

- [ ] **Step 5: Final commit if any fixes needed**

```bash
git add -u
git commit -m "fix: address issues found during final verification"
```
