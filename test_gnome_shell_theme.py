import unittest
from unittest.mock import patch

import theme
from theme import ThemeData, select_gtk_theme


class GnomeShellThemeTests(unittest.TestCase):
    def test_detects_gnome_from_xdg_current_desktop(self):
        with patch.dict(theme.os.environ, {"XDG_CURRENT_DESKTOP": "GNOME:GNOME-Classic"}, clear=True):
            self.assertTrue(theme._is_gnome_desktop())

    def test_uses_desktop_session_when_xdg_current_desktop_is_unset(self):
        with patch.dict(theme.os.environ, {"DESKTOP_SESSION": "gnome-xorg"}, clear=True):
            self.assertTrue(theme._is_gnome_desktop())

    def test_does_not_classify_xfce_as_gnome(self):
        with patch.dict(theme.os.environ, {"XDG_CURRENT_DESKTOP": "XFCE"}, clear=True):
            self.assertFalse(theme._is_gnome_desktop())

    def test_shell_only_theme_sets_user_theme_setting_in_gnome(self):
        selected = ThemeData(
            "ShellTheme", "/usr/share/themes/ShellTheme",
            False, False, False, False, None, None, gnomeShell=True,
        )

        with (
            patch("theme._is_gnome_desktop", return_value=True),
            patch("theme._gsettings_set", return_value=True) as set_gsettings,
            patch("theme._set_related_theme") as set_related,
        ):
            select_gtk_theme(selected)

        set_gsettings.assert_called_once_with(
            "org.gnome.shell.extensions.user-theme", "name", "ShellTheme"
        )
        set_related.assert_not_called()

    def test_shell_only_theme_reports_missing_user_themes_extension(self):
        selected = ThemeData(
            "ShellTheme", "/usr/share/themes/ShellTheme",
            False, False, False, False, None, None, gnomeShell=True,
        )

        with (
            patch("theme._is_gnome_desktop", return_value=True),
            patch("theme._gsettings_set", return_value=False),
            self.assertRaisesRegex(RuntimeError, "User Themes extension"),
        ):
            select_gtk_theme(selected)

    def test_shell_only_theme_is_rejected_outside_gnome(self):
        selected = ThemeData(
            "ShellTheme", "/usr/share/themes/ShellTheme",
            False, False, False, False, None, None, gnomeShell=True,
        )

        with (
            patch("theme._is_gnome_desktop", return_value=False),
            patch("theme._gsettings_set") as set_gsettings,
            self.assertRaisesRegex(RuntimeError, "GNOME desktop session"),
        ):
            select_gtk_theme(selected)

        set_gsettings.assert_not_called()

    def test_combined_gtk_shell_theme_only_sets_shell_setting_in_gnome(self):
        selected = ThemeData(
            "CombinedTheme", "/usr/share/themes/CombinedTheme",
            False, True, False, False, None, None, gnomeShell=True,
        )

        with (
            patch("theme._is_gnome_desktop", return_value=False),
            patch("theme._set_related_theme") as set_related,
            patch("theme._icon_theme_roots", return_value=[]),
            patch("theme._cursor_theme_roots", return_value=[]),
            patch.object(theme, "_gsettings_set") as set_gsettings,
        ):
            select_gtk_theme(selected)

        set_related.assert_called_once_with(
            "GTK", "CombinedTheme", "xsettings", "/Net/ThemeName",
            "org.gnome.desktop.interface", "gtk-theme",
        )
        set_gsettings.assert_not_called()


if __name__ == "__main__":
    unittest.main()
