from unittest.mock import patch


class TestApiCli:
    def test_main_entry_forwards_api_options(self):
        import chargeghost_evse.main as main_module

        with patch(
            "sys.argv",
            [
                "chargeghost-evse",
                "--api",
                "--host",
                "127.0.0.1",
                "--port",
                "9001",
                "--log-level",
                "debug",
            ],
        ):
            with patch("chargeghost_evse.api.server.run_server") as mock_run_server:
                result = main_module.main_entry()

        assert result == 0
        mock_run_server.assert_called_once_with(
            host="127.0.0.1", port=9001, log_level="debug"
        )

    def test_api_server_entrypoint_parses_args(self):
        import chargeghost_evse.api_server as api_server_module

        with patch(
            "sys.argv",
            [
                "chargeghost-api",
                "--host",
                "127.0.0.1",
                "--port",
                "9001",
                "--log-level",
                "debug",
            ],
        ):
            with patch("chargeghost_evse.api.server.run_server") as mock_run_server:
                result = api_server_module.main()

        assert result == 0
        mock_run_server.assert_called_once_with(
            host="127.0.0.1", port=9001, log_level="debug"
        )
