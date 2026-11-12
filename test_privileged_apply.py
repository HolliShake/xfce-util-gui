import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import theme
from theme import CursorData, IconData, ThemeData, WindowData


class PrivilegedApplyTests(unittest.TestCase):
    def test_all_user_selectors_authenticate_before_updating_the_session(self):
        cases = (
            ("gtk", theme.select_gtk_theme, ThemeData("Adwaita", "/usr/share/themes/Adwaita", False, False, False, False, None, None)),
            ("window", theme.select_window_theme, WindowData("Adwaita", "/usr/share/themes/Adwaita")),
            ("icon", theme.select_icon_theme, IconData("Adwaita", "/usr/share/icons/Adwaita", None)),
            ("cursor", theme.select_cursor_theme, CursorData("Adwaita", "/usr/share/icons/Adwaita")),
        )
        for kind, select, data in cases:
            with self.subTest(kind=kind):
                calls = []
                with (
                    patch.object(
                        theme,
                        "_apply_all_users_with_authentication",
                        side_effect=lambda operation, _data: calls.append(("auth", operation)),
                    ),
                    patch.object(
                        theme,
                        "_set_related_theme",
                        side_effect=lambda operation, *_args: calls.append(("session", operation)),
                    ),
                    patch.object(theme, "_icon_theme_roots", return_value=[]),
                    patch.object(theme, "_cursor_theme_roots", return_value=[]),
                ):
                    select(data, applyToAllUser=True)
                self.assertEqual(calls[0], ("auth", kind))
                self.assertTrue(any(call[0] == "session" for call in calls))

    def test_pkexec_launches_the_isolated_all_user_helper(self):
        with (
            patch.object(theme.shutil, "which", return_value="/usr/bin/pkexec"),
            patch.object(
                theme,
                "_require_trusted_root_path",
                side_effect=lambda path, _description: Path(path).resolve(),
            ),
            patch.object(
                theme.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
            ) as run,
        ):
            theme._apply_all_users_with_authentication(
                "cursor", CursorData("Adwaita", "/usr/share/icons/Adwaita")
            )

        command = run.call_args.args[0]
        self.assertEqual(command[0], "/usr/bin/pkexec")
        self.assertEqual(command[1], str(Path(sys.executable).resolve()))
        self.assertEqual(command[2:5], ["-I", str(Path(theme.__file__).resolve()), "--apply-all-users"])
        self.assertEqual(command[5:], ["cursor", "Adwaita"])

    def test_authentication_cancellation_is_reported(self):
        with (
            patch.object(theme.shutil, "which", return_value="/usr/bin/pkexec"),
            patch.object(
                theme,
                "_require_trusted_root_path",
                side_effect=lambda path, _description: Path(path).resolve(),
            ),
            patch.object(
                theme.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=126, stdout="", stderr="Not authorized"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "Not authorized"):
                theme._apply_all_users_with_authentication(
                    "icon", IconData("Adwaita", "/usr/share/icons/Adwaita", None)
                )

    def test_privileged_gtk_apply_rejects_user_home_theme_paths(self):
        with self.assertRaisesRegex(ValueError, "require a theme installed under"):
            theme._system_gtk_theme_for_all_users(
                "MyTheme", "/home/alice/.themes/MyTheme"
            )

    def test_privileged_cli_updates_only_the_requested_setting_kind(self):
        with (
            patch.object(theme.os, "geteuid", return_value=0),
            patch.object(theme, "_apply_xsettings_theme_to_homes") as apply,
        ):
            result = theme._apply_all_users_as_root(["icon", "Adwaita"])

        self.assertEqual(result, 0)
        apply.assert_called_once_with(
            "Adwaita",
            Path("/home"),
            "icon",
            "gtk-icon-theme-name",
            "Net",
            "IconThemeName",
        )


if __name__ == "__main__":
    unittest.main()
