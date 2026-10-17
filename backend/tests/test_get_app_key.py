"""Registration is simulated; the helper must leave .env under user control."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from aiohue.errors import LinkButtonNotPressed

import config
import get_app_key


class RegistrationTests(unittest.TestCase):
    def test_prints_generated_key_after_prompt_without_modifying_env(self):
        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            env = Path(directory) / ".env"
            original = "HUE_BRIDGE_IP=192.0.2.10\nHUE_APP_KEY=old-key\n"
            env.write_text(original, encoding="utf-8")
            output = StringIO()
            with (
                patch.object(config, "ENV_PATH", env),
                patch.object(get_app_key, "create_app_key", new_callable=AsyncMock) as create,
                patch("builtins.input", return_value="") as prompt,
                redirect_stdout(output),
            ):
                create.return_value = "new-key"
                self.assertEqual(get_app_key.main(), 0)
            prompt.assert_called_once()
            self.assertIn("Bridge", prompt.call_args.args[0])
            create.assert_awaited_once_with("192.0.2.10", "local-hue#desktop")
            self.assertIn("HUE_APP_KEY=new-key", output.getvalue())
            self.assertEqual(env.read_text(encoding="utf-8"), original)

    def test_link_button_failure_is_readable_and_leaves_env_unchanged(self):
        with TemporaryDirectory(dir=Path(__file__).parent) as directory:
            env = Path(directory) / ".env"
            original = "HUE_BRIDGE_IP=192.0.2.10\nHUE_APP_KEY=old-key\n"
            env.write_text(original, encoding="utf-8")
            output = StringIO()
            with (
                patch.object(config, "ENV_PATH", env),
                patch.object(get_app_key, "create_app_key", new_callable=AsyncMock) as create,
                patch("builtins.input", return_value=""),
                redirect_stdout(output),
            ):
                create.side_effect = LinkButtonNotPressed("internal exception detail")
                self.assertEqual(get_app_key.main(), 1)
            self.assertIn("dugme nije pritisnuto", output.getvalue())
            self.assertNotIn("internal exception detail", output.getvalue())
            self.assertNotIn("HUE_APP_KEY=", output.getvalue())
            self.assertEqual(env.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
