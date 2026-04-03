from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI

from chargeghost_evse.api.app import create_app
from chargeghost_evse.api.server import VALID_LOG_LEVELS, run_server


class TestCreateApp:
    def test_returns_fastapi_instance(self) -> None:
        app = create_app()
        assert isinstance(app, FastAPI)

    def test_includes_all_routers(self) -> None:
        app = create_app()
        route_paths = {getattr(route, "path", "") for route in app.routes}
        expected_prefixes = [
            "/api/v1/status",
            "/api/v1/connectors",
            "/api/v1/sessions",
            "/api/v1/config",
            "/api/v1/ocpp",
            "/ws/state",
        ]
        for prefix in expected_prefixes:
            assert any(
                path.startswith(prefix) for path in route_paths
            ), f"Missing route matching {prefix}"

    def test_app_metadata(self) -> None:
        app = create_app()
        assert app.title == "ChargeGhost EVSE API"


class TestRunServer:
    @patch("chargeghost_evse.api.server.uvicorn.run")
    def test_run_server_calls_uvicorn(self, mock_run: MagicMock) -> None:
        run_server(host="0.0.0.0", port=8000, log_level="info")
        mock_run.assert_called_once_with(
            "chargeghost_evse.api.app:create_app",
            host="0.0.0.0",
            port=8000,
            log_level="info",
            factory=True,
        )

    def test_run_server_validates_log_level(self) -> None:
        with pytest.raises(ValueError, match="Invalid log level"):
            run_server(log_level="invalid")

    @patch("chargeghost_evse.api.server.uvicorn.run")
    def test_run_server_default_values(self, mock_run: MagicMock) -> None:
        run_server()
        mock_run.assert_called_once_with(
            "chargeghost_evse.api.app:create_app",
            host="127.0.0.1",
            port=8080,
            log_level="info",
            factory=True,
        )


class TestValidLogLevels:
    def test_contains_expected_levels(self) -> None:
        expected = {"critical", "error", "warning", "info", "debug", "trace"}
        assert VALID_LOG_LEVELS == frozenset(expected)


class TestApiServerCli:
    @patch("chargeghost_evse.api.server.run_server")
    def test_main_with_custom_args(self, mock_run_server: MagicMock) -> None:
        import chargeghost_evse.api_server as api_server_module

        result = api_server_module.main(
            ["--host", "0.0.0.0", "--port", "9000", "--log-level", "debug"]
        )
        assert result == 0
        mock_run_server.assert_called_once_with(
            host="0.0.0.0", port=9000, log_level="debug"
        )

    def test_main_rejects_invalid_log_level(self) -> None:
        import chargeghost_evse.api_server as api_server_module

        with pytest.raises(SystemExit):
            api_server_module.main(["--log-level", "invalid"])
