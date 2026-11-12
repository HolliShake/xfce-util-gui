import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from supported_display_manager import (
    DisplayManagerEnum,
    DisplayManagerConfigError,
    get_display_manager,
    get_display_manager_info,
    get_supported_display_managers,
    parse_gdm_config,
    parse_lightdm_greeter_config,
    parse_sddm_config,
)


class SupportedDisplayManagerTests(unittest.TestCase):
    def test_detects_supported_managers_case_insensitively(self):
        examples = (
            ("/usr/sbin/lightdm", DisplayManagerEnum.LightDM),
            ("/usr/bin/sddm", DisplayManagerEnum.SDDM),
            ("/usr/sbin/gdm3", DisplayManagerEnum.GDM),
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "default-display-manager"
            for value, expected in examples:
                with self.subTest(value=value):
                    path.write_text(value.upper(), encoding="utf-8")
                    self.assertIs(get_display_manager(path), expected)

    def test_missing_and_unknown_managers_have_clear_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "missing"
            with self.assertRaisesRegex(
                FileNotFoundError, "Display manager could not be detected"
            ):
                get_display_manager(path, systemd_service_paths=())

            path.write_text("/usr/bin/otherdm", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unknown display manager"):
                get_display_manager(path, systemd_service_paths=())

    def test_detects_manager_from_systemd_service_alias_when_default_file_is_absent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "missing-default-display-manager"
            service_target = root / "usr" / "lib" / "systemd" / "system" / "sddm.service"
            service_target.parent.mkdir(parents=True)
            service_target.touch()
            service_alias = root / "etc" / "systemd" / "system" / "display-manager.service"
            service_alias.parent.mkdir(parents=True)
            service_alias.symlink_to(service_target)

            self.assertIs(
                get_display_manager(path, (service_alias,)),
                DisplayManagerEnum.SDDM,
            )

    def test_all_manager_details_include_requested_settings_and_gdm_caveat(self):
        details = {info.manager: info for info in get_supported_display_managers()}
        lightdm = details[DisplayManagerEnum.LightDM]
        sddm = details[DisplayManagerEnum.SDDM]
        gdm = details[DisplayManagerEnum.GDM]

        self.assertIsNone(lightdm.config_path)
        self.assertEqual(lightdm.section, "[greeter]")
        self.assertTrue(
            {
                "theme-name",
                "icon-theme-name",
                "cursor-theme-name",
                "cursor-theme-size",
                "font-name",
                "background",
                "user-background",
                "xft-antialias",
                "xft-hintstyle",
                "xft-rgba",
                "xft-dpi",
            }.issubset({setting.name for setting in lightdm.settings})
        )

        self.assertEqual(sddm.config_path, "/etc/sddm.conf")
        self.assertEqual(sddm.section, "[Theme]")
        self.assertTrue(
            {
                "Current",
                "ThemeDir",
                "FacesDir",
                "CursorTheme",
                "CursorSize",
                "Font",
                "EnableAvatars",
            }.issubset({setting.name for setting in sddm.settings})
        )

        self.assertEqual(gdm.config_path, "/etc/gdm/custom.conf")
        self.assertEqual(
            {setting.name for setting in gdm.settings},
            {"GraphicalTheme", "GraphicalThemeDir"},
        )
        self.assertIn("legacy", gdm.note)

    def test_lightdm_parser_reads_only_greeter_settings_and_reports_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "etc" / "lightdm" / "lightdm-gtk-greeter.conf"
            path.parent.mkdir(parents=True)
            path.write_text(
                "[greeter]\n"
                "theme-name=Adwaita\n"
                "background=/usr/share/backgrounds/login.png\n"
                "\n[other]\n"
                "theme-name=Ignored\n",
                encoding="utf-8",
            )

            values = parse_lightdm_greeter_config(
                path,
                system_data_dirs=(),
                system_config_dirs=(),
            )

        self.assertEqual(values["theme-name"].value, "Adwaita")
        self.assertEqual(values["theme-name"].source, str(path))
        self.assertEqual(
            values["background"].value,
            "/usr/share/backgrounds/login.png",
        )
        self.assertNotIn("xft-dpi", values)

    def test_lightdm_parser_merges_sorted_system_and_local_dropins(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            system_data_root = base / "usr" / "share"
            system_dir = (
                system_data_root / "lightdm" / "lightdm-gtk-greeter.conf.d"
            )
            config_data_root = base / "etc" / "xdg"
            local_dir = (
                config_data_root / "lightdm" / "lightdm-gtk-greeter.conf.d"
            )
            system_dir.mkdir(parents=True)
            local_dir.mkdir(parents=True)
            (system_dir / "01-default.conf").write_text(
                "[greeter]\ntheme-name=Ubuntu\nfont-name=System Font\n",
                encoding="utf-8",
            )
            (system_dir / "30-desktop.conf").write_text(
                "[greeter]\ntheme-name=Greybird\n",
                encoding="utf-8",
            )
            (local_dir / "99-custom.conf").write_text(
                "[greeter]\ntheme-name=Vimix\n",
                encoding="utf-8",
            )
            main_config = (
                base / "etc" / "lightdm" / "lightdm-gtk-greeter.conf"
            )
            main_config.parent.mkdir(parents=True)
            main_config.write_text(
                "[greeter]\nfont-name=Local Font\n",
                encoding="utf-8",
            )

            with patch.dict(
                "os.environ",
                {
                    "XDG_DATA_DIRS": str(system_data_root),
                    "XDG_CONFIG_DIRS": str(config_data_root),
                },
            ):
                values = parse_lightdm_greeter_config(path=main_config)

        self.assertEqual(values["theme-name"].value, "Vimix")
        self.assertEqual(
            values["theme-name"].source, str(local_dir / "99-custom.conf")
        )
        self.assertEqual(values["font-name"].value, "Local Font")
        self.assertEqual(values["font-name"].source, str(main_config))

    def test_sddm_parser_applies_dropin_and_main_file_precedence(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            system_dir = base / "usr" / "sddm.conf.d"
            local_dir = base / "etc" / "sddm.conf.d"
            system_dir.mkdir(parents=True)
            local_dir.mkdir(parents=True)
            (system_dir / "10-theme.conf").write_text(
                "[Theme]\nCurrent=SystemTheme\nCursorSize=24\n",
                encoding="utf-8",
            )
            (local_dir / "20-theme.conf").write_text(
                "[Theme]\nCurrent=LocalTheme\n",
                encoding="utf-8",
            )
            main_config = base / "sddm.conf"
            main_config.write_text(
                "[Theme]\nCurrent=MainTheme\nEnableAvatars=false\n",
                encoding="utf-8",
            )

            values = parse_sddm_config(
                config_file=main_config,
                system_dropin_dir=system_dir,
                local_dropin_dir=local_dir,
            )

        self.assertEqual(values["Current"].value, "MainTheme")
        self.assertEqual(values["Current"].source, str(main_config))
        self.assertEqual(values["CursorSize"].value, "24")
        self.assertEqual(values["CursorSize"].source, str(system_dir / "10-theme.conf"))
        self.assertEqual(values["EnableAvatars"].value, "false")

    def test_gdm_parser_reads_only_legacy_greeter_theme_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "custom.conf"
            path.write_text(
                "[daemon]\nWaylandEnable=false\n"
                "\n[greeter]\n"
                "GraphicalTheme=OldTheme\n"
                "GraphicalThemeDir=/usr/share/gdm/themes\n",
                encoding="utf-8",
            )

            values = parse_gdm_config(path)

        self.assertEqual(values["GraphicalTheme"].value, "OldTheme")
        self.assertEqual(
            values["GraphicalThemeDir"].value, "/usr/share/gdm/themes"
        )
        self.assertNotIn("WaylandEnable", values)

    def test_parser_reports_invalid_configuration_without_raw_parse_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lightdm.conf"
            path.write_text("not a section\n", encoding="utf-8")
            with self.assertRaisesRegex(
                DisplayManagerConfigError, "Could not read LightDM GTK greeter configuration"
            ):
                parse_lightdm_greeter_config(path)

    def test_legacy_lightdm_enum_name_remains_an_alias(self):
        self.assertIs(DisplayManagerEnum.LigthDM, DisplayManagerEnum.LightDM)
        self.assertIs(
            get_display_manager_info(DisplayManagerEnum.LigthDM).manager,
            DisplayManagerEnum.LightDM,
        )


if __name__ == "__main__":
    unittest.main()
