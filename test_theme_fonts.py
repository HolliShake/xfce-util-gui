import subprocess
import unittest
from unittest.mock import patch

from theme import get_available_fonts


class AvailableFontsTests(unittest.TestCase):
    @patch("theme._run")
    @patch("theme.shutil.which", return_value="/usr/bin/fc-list")
    def test_splits_deduplicates_and_sorts_families(self, _which, run):
        run.return_value = subprocess.CompletedProcess(
            args=["fc-list"],
            returncode=0,
            stdout="Noto Sans, Noto Sans UI\nLiberation Sans\nNoto Sans\n",
        )

        self.assertEqual(
            get_available_fonts(),
            [
                "Liberation Sans",
                "Monospace",
                "Noto Sans",
                "Noto Sans UI",
                "Sans",
                "Serif",
            ],
        )

    @patch("theme.shutil.which", return_value=None)
    def test_missing_fontconfig_command_is_reported(self, _which):
        with self.assertRaisesRegex(RuntimeError, "fc-list command is not available"):
            get_available_fonts()

    @patch("theme._run", side_effect=subprocess.CalledProcessError(1, ["fc-list"], stderr="failed"))
    @patch("theme.shutil.which", return_value="/usr/bin/fc-list")
    def test_fontconfig_failure_is_reported(self, _which, _run):
        with self.assertRaisesRegex(RuntimeError, "Failed to get available fonts"):
            get_available_fonts()


if __name__ == "__main__":
    unittest.main()
