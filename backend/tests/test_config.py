"""Configuration updates preserve other entries and replace .env atomically."""

import importlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import config


class ConfigPathTests(unittest.TestCase):
    def test_env_file_can_be_moved_for_a_second_instance(self):
        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            env = Path(directory) / ".env.mock"
            env.write_text("HUE_BRIDGE_IP=127.0.0.1\nHUE_APP_KEY=mock-key\n", encoding="utf-8")
            with patch.dict("os.environ", {"HUE_ENV_FILE": str(env)}):
                reloaded = importlib.reload(config)
                try:
                    self.assertEqual(reloaded.ENV_PATH, env.resolve())
                    self.assertEqual(reloaded.read_config(), ("127.0.0.1", "mock-key"))
                finally:
                    os.environ.pop("HUE_ENV_FILE", None)
                    importlib.reload(config)
        self.assertEqual(config.ENV_PATH, (Path(config.__file__).parent / ".env").resolve())


class ConfigPersistenceTests(unittest.TestCase):
    def test_save_preserves_comments_and_unrelated_settings(self):
        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            env = Path(directory) / ".env"
            env.write_text(
                "# My local settings\nEXTRA_OPTION='keep me'\n"
                "HUE_BRIDGE_IP=192.0.2.10\nHUE_APP_KEY=old-key\n",
                encoding="utf-8",
            )
            with patch.object(config, "ENV_PATH", env):
                config.write_config("192.0.2.20", "new-private-key")
                self.assertEqual(config.read_config(), ("192.0.2.20", "new-private-key"))
            updated = env.read_text(encoding="utf-8")
            self.assertIn("# My local settings", updated)
            self.assertIn("EXTRA_OPTION='keep me'", updated)
            self.assertEqual(list(Path(directory).iterdir()), [env])

    def test_save_creates_env_when_it_does_not_exist(self):
        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            env = Path(directory) / ".env"
            with patch.object(config, "ENV_PATH", env):
                config.write_config("192.0.2.20", "first-key")
                self.assertEqual(config.read_config(), ("192.0.2.20", "first-key"))
            self.assertEqual(list(Path(directory).iterdir()), [env])

    def test_failed_atomic_replace_preserves_original_bytes_and_cleans_temporary_file(self):
        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            env = Path(directory) / ".env"
            original = b"# Original\r\nHUE_BRIDGE_IP=192.0.2.10\r\nHUE_APP_KEY=old-key\r\n"
            env.write_bytes(original)
            with (
                patch.object(config, "ENV_PATH", env),
                patch.object(Path, "replace", side_effect=PermissionError("save denied")),
            ):
                with self.assertRaises(OSError):
                    config.write_config("192.0.2.20", "new-key")
            self.assertEqual(env.read_bytes(), original)
            self.assertEqual(list(Path(directory).iterdir()), [env])


if __name__ == "__main__":
    unittest.main()
