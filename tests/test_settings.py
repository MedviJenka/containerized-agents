import importlib
import os
import unittest
from pathlib import Path
from unittest.mock import patch


class SettingsTests(unittest.TestCase):
    def test_env_file_is_resolved_from_settings_module(self) -> None:
        with patch.dict(os.environ, {"LOGFIRE_WRITE_TOKEN": "test-token"}):
            settings = importlib.import_module("settings")

        env_file = Path(type(settings.Config).model_config["env_file"])

        self.assertEqual(env_file, Path(settings.__file__).with_name(".env"))


if __name__ == "__main__":
    unittest.main()
