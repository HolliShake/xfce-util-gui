import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from theme import get_available_themes


class AvailableThemesTests(unittest.TestCase):
    def test_detects_gnome_shell_only_themes(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            shell_theme = root / "ShellOnly" / "gnome-shell"
            shell_theme.mkdir(parents=True)
            (shell_theme / "gnome-shell.css").write_text("", encoding="utf-8")

            unrelated_theme = root / "Unrelated" / "gnome-shell"
            unrelated_theme.mkdir(parents=True)
            (unrelated_theme / "stylesheet.css").write_text("", encoding="utf-8")

            with patch("theme._theme_roots", return_value=[root]):
                themes = get_available_themes()

        self.assertEqual([theme.name for theme in themes], ["ShellOnly"])
        self.assertTrue(themes[0].gnomeShell)
        self.assertFalse(themes[0].gtk2)
        self.assertFalse(themes[0].gtk3)
        self.assertFalse(themes[0].gtk4)
        self.assertFalse(themes[0].xfwm4)


if __name__ == "__main__":
    unittest.main()
