import importlib
import os
import subprocess
import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import MagicMock, patch


class LoggerTests(unittest.TestCase):
    def tearDown(self) -> None:
        sys.modules.pop("functions.log", None)

    def test_import_has_no_logging_side_effects(self) -> None:
        sys.modules.pop("functions.log", None)

        with (
            patch.dict(os.environ, {"LOGFIRE_WRITE_TOKEN": "test-token"}),
            patch("logfire.configure") as configure,
            patch("logfire.info"),
        ):
            importlib.import_module("functions.log")

        configure.assert_not_called()

    def test_routes_each_level_to_the_configured_client(self) -> None:
        client = MagicMock()
        client.span.return_value = nullcontext()
        sys.modules.pop("functions.log", None)

        with (
            patch.dict(os.environ, {"LOGFIRE_WRITE_TOKEN": "test-token"}),
            patch("logfire.configure", return_value=client),
            patch("logfire.info"),
            patch("logfire.error"),
            patch("logfire.debug"),
            patch("logfire.warning"),
            patch("logfire.fatal"),
        ):
            module = importlib.import_module("functions.log")
            client.reset_mock()
            logger = module.Logger(name="app")

            for level in ("info", "error", "debug", "warning", "fatal"):
                with self.subTest(level=level):
                    client.reset_mock()
                    logger.fire("hello", level, job_id="job-123")
                    getattr(client, level).assert_called_once_with(
                        "hello", job_id="job-123"
                    )

            client.reset_mock()
            logger.fire("fallback", "unknown")
            client.info.assert_called_once_with("fallback")

    def test_script_configures_logfire_when_run_directly(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        environment = os.environ.copy()
        environment.update(
            LOGFIRE_SEND_TO_LOGFIRE="false",
            LOGFIRE_WRITE_TOKEN="test-token",
        )

        result = subprocess.run(
            [sys.executable, "functions/log.py"],
            cwd=project_root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("app", result.stdout)


if __name__ == "__main__":
    unittest.main()
