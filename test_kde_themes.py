import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import theme
from theme import (
    KdeThemeData,
    get_available_kde_themes,
    get_kde_theme_name,
    select_kde_theme,
)


class KdeThemeTests(unittest.TestCase):
    def _write_theme(
        self, root: Path, folder: str, package_id: str, name: str, description: str = ""
    ) -> Path:
        theme_path = root / "plasma" / "look-and-feel" / folder
        theme_path.mkdir(parents=True)
        metadata = {
            "KPlugin": {
                "Id": package_id,
                "Name": name,
                "Description": description,
            }
        }
        (theme_path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        return theme_path

    def test_discovery_reads_xdg_paths_and_prefers_user_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            user_root = base / "user-data"
            system_root = base / "system-data"
            user_theme_path = self._write_theme(
                user_root, "breeze-user", "org.kde.breeze", "User Breeze", "User copy"
            )
            self._write_theme(
                system_root, "breeze", "org.kde.breeze", "Breeze", "System copy"
            )
            self._write_theme(
                system_root, "oxygen", "org.kde.oxygen", "Oxygen"
            )
            with patch.dict(
                os.environ,
                {
                    "XDG_DATA_HOME": str(user_root),
                    "XDG_DATA_DIRS": str(system_root),
                },
            ):
                themes = get_available_kde_themes()

        self.assertEqual(
            [item.package_id for item in themes], ["org.kde.breeze", "org.kde.oxygen"]
        )
        self.assertEqual(themes[0].name, "User Breeze")
        self.assertEqual(themes[0].description, "User copy")
        self.assertEqual(themes[0].absolute_path, str(user_theme_path))

    def test_discovery_skips_invalid_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_home = Path(temporary)
            system_data = data_home / "system"
            system_data.mkdir()
            broken = data_home / "plasma" / "look-and-feel" / "broken"
            broken.mkdir(parents=True)
            (broken / "metadata.json").write_text("{invalid", encoding="utf-8")
            with (
                patch.dict(
                    os.environ,
                    {
                        "XDG_DATA_HOME": str(data_home),
                        "XDG_DATA_DIRS": str(system_data),
                    },
                ),
                self.assertWarnsRegex(UserWarning, "invalid metadata.json"),
            ):
                self.assertEqual(get_available_kde_themes(), [])

    def test_get_kde_theme_name_reads_xdg_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            config_home = Path(temporary)
            (config_home / "kdeglobals").write_text(
                "[KDE]\nLookAndFeelPackage=org.kde.breeze\n", encoding="utf-8"
            )
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(config_home)}):
                self.assertEqual(get_kde_theme_name(), "org.kde.breeze")

    def test_select_kde_theme_uses_package_id_with_lookandfeeltool(self):
        selected = KdeThemeData(
            "Breeze", "org.kde.breeze", "/usr/share/plasma/look-and-feel/org.kde.breeze"
        )
        with (
            patch.object(theme.shutil, "which", return_value="/usr/bin/lookandfeeltool"),
            patch.object(theme, "_run") as run,
        ):
            select_kde_theme(selected)

        run.assert_called_once_with(
            ["/usr/bin/lookandfeeltool", "--apply", "org.kde.breeze"]
        )

    def test_select_kde_theme_reports_missing_kde_tool(self):
        selected = KdeThemeData("Breeze", "org.kde.breeze", "/theme")
        with (
            patch.object(theme.shutil, "which", return_value=None),
            self.assertRaisesRegex(RuntimeError, "lookandfeeltool is not installed"),
        ):
            select_kde_theme(selected)

    def test_select_kde_theme_does_not_expose_raw_process_errors(self):
        selected = KdeThemeData("Breeze", "org.kde.breeze", "/theme")
        with (
            patch.object(theme.shutil, "which", return_value="/usr/bin/lookandfeeltool"),
            patch.object(theme, "_run", side_effect=FileNotFoundError(2, "missing tool")),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "Check that KDE Plasma is available"
            ) as raised:
                select_kde_theme(selected)

        self.assertNotIn("[Errno 2]", str(raised.exception))

    def test_select_kde_theme_rejects_invalid_package_id(self):
        selected = KdeThemeData("Bad", "../escape", "/theme")
        with self.assertRaisesRegex(ValueError, "Invalid KDE theme name"):
            select_kde_theme(selected)


if __name__ == "__main__":
    unittest.main()
