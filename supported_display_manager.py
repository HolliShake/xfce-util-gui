import configparser
import enum
import os
from dataclasses import dataclass
from pathlib import Path


class DisplayManagerEnum(enum.Enum):
    LightDM = enum.auto()
    LigthDM = LightDM
    SDDM = enum.auto()
    GDM = enum.auto()


@dataclass(frozen=True)
class DisplayManagerSetting:
    name: str
    description: str


@dataclass(frozen=True)
class DisplayManagerSettingValue:
    value: str
    source: str


@dataclass(frozen=True)
class DisplayManagerInfo:
    manager: DisplayManagerEnum
    name: str
    config_path: str | None
    section: str | None
    summary: str
    settings: tuple[DisplayManagerSetting, ...]
    note: str = ""


_DISPLAY_MANAGERS = {
    DisplayManagerEnum.LightDM: DisplayManagerInfo(
        manager=DisplayManagerEnum.LightDM,
        name="LightDM (GTK Greeter)",
        config_path=None,
        section="[greeter]",
        summary=(
            "When LightDM uses lightdm-gtk-greeter, these options control the greeter's "
            "appearance and font rendering."
        ),
        settings=(
            DisplayManagerSetting("theme-name", "GTK theme name."),
            DisplayManagerSetting("icon-theme-name", "Icon theme name."),
            DisplayManagerSetting("cursor-theme-name", "Cursor theme name."),
            DisplayManagerSetting("cursor-theme-size", "Cursor size."),
            DisplayManagerSetting("font-name", "Font name."),
            DisplayManagerSetting("background", "Background image path or color."),
            DisplayManagerSetting(
                "user-background", "Whether to display the user's background image."
            ),
            DisplayManagerSetting(
                "xft-antialias", "Enable or disable font anti-aliasing."
            ),
            DisplayManagerSetting("xft-hintstyle", "Font hinting style."),
            DisplayManagerSetting("xft-rgba", "Subpixel rendering order."),
            DisplayManagerSetting("xft-dpi", "Font rendering DPI."),
        ),
        note=(
            "The greeter loads configuration from GLib's system data directories, "
            "system config directories, and its compiled config location. Values shown "
            "above reflect this merge order and identify the file that supplied each value."
        ),
    ),
    DisplayManagerEnum.SDDM: DisplayManagerInfo(
        manager=DisplayManagerEnum.SDDM,
        name="SDDM",
        config_path="/etc/sddm.conf",
        section="[Theme]",
        summary="SDDM configures the greeter theme and related display settings here.",
        settings=(
            DisplayManagerSetting(
                "Current", "Theme name, matching a folder in the SDDM themes directory."
            ),
            DisplayManagerSetting(
                "ThemeDir", "Directory containing SDDM themes; defaults to /usr/share/sddm/themes."
            ),
            DisplayManagerSetting("FacesDir", "Directory used for user avatar files."),
            DisplayManagerSetting(
                "CursorTheme", "Cursor theme set before the display server starts."
            ),
            DisplayManagerSetting(
                "CursorSize", "Cursor size set before the display server starts."
            ),
            DisplayManagerSetting(
                "Font", "Font set before the display server starts; a theme may override it."
            ),
            DisplayManagerSetting("EnableAvatars", "Enable or disable avatar display."),
        ),
        note=(
            "Effective values are merged from /usr/lib/sddm/sddm.conf.d, then "
            "/etc/sddm.conf.d in filename order, and finally /etc/sddm.conf, which has "
            "the highest precedence."
        ),
    ),
    DisplayManagerEnum.GDM: DisplayManagerInfo(
        manager=DisplayManagerEnum.GDM,
        name="GDM",
        config_path="/etc/gdm/custom.conf",
        section="[greeter] (legacy)",
        summary=(
            "GDM's supported configuration focuses on general login behavior rather than "
            "a standalone greeter-theme selector."
        ),
        settings=(
            DisplayManagerSetting(
                "GraphicalTheme",
                "Legacy greeter theme value; modern GDM does not support this as a reliable theme switch.",
            ),
            DisplayManagerSetting(
                "GraphicalThemeDir",
                "Legacy greeter theme directory; modern GDM does not support this as a reliable theme switch.",
            ),
        ),
        note=(
            "Modern GNOME integrates the login screen with GNOME Shell and does not provide "
            "a supported, user-friendly standalone theme switch. GraphicalTheme and "
            "GraphicalThemeDir are legacy references, not reliable runtime options."
        ),
    ),
}


class DisplayManagerConfigError(RuntimeError):
    """Raised when a display-manager configuration cannot be parsed."""


_LIGHTDM_SETTINGS = tuple(
    setting.name for setting in _DISPLAY_MANAGERS[DisplayManagerEnum.LightDM].settings
)
_SDDM_SETTINGS = tuple(
    setting.name for setting in _DISPLAY_MANAGERS[DisplayManagerEnum.SDDM].settings
)
_GDM_SETTINGS = tuple(
    setting.name for setting in _DISPLAY_MANAGERS[DisplayManagerEnum.GDM].settings
)


def _read_config_values(
    path: Path, section: str, keys: tuple[str, ...], manager: str
) -> dict[str, DisplayManagerSettingValue]:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        with path.open(encoding="utf-8") as config_file:
            parser.read_file(config_file)
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError, configparser.Error) as error:
        raise DisplayManagerConfigError(
            f"Could not read {manager} configuration at {path}."
        ) from error

    if not parser.has_section(section):
        return {}
    return {
        key: DisplayManagerSettingValue(parser.get(section, key), str(path))
        for key in keys
        if parser.has_option(section, key)
    }


def parse_lightdm_greeter_config(
    path: str | Path = "/etc/lightdm/lightdm-gtk-greeter.conf",
    system_data_dirs: tuple[str | Path, ...] | None = None,
    system_config_dirs: tuple[str | Path, ...] | None = None,
) -> dict[str, DisplayManagerSettingValue]:
    """Parse GTK greeter values using GLib's XDG directory order and merge rules."""
    if system_data_dirs is None:
        system_data_dirs = _xdg_system_directories(
            "XDG_DATA_DIRS", "/usr/local/share:/usr/share"
        )
    if system_config_dirs is None:
        system_config_dirs = _xdg_system_directories("XDG_CONFIG_DIRS", "/etc/xdg")

    roots = [*(Path(directory) for directory in system_data_dirs)]
    roots.extend(Path(directory) for directory in system_config_dirs)
    roots.append(Path(path).parent.parent)

    values: dict[str, DisplayManagerSettingValue] = {}
    for index, root in enumerate(roots):
        config_dir = root / "lightdm"
        for file in _dropin_files(
            config_dir / "lightdm-gtk-greeter.conf.d", "LightDM GTK greeter"
        ):
            values.update(_read_config_values(
                file, "greeter", _LIGHTDM_SETTINGS, "LightDM GTK greeter"
            ))
        config_file = (
            Path(path)
            if index == len(roots) - 1
            else config_dir / "lightdm-gtk-greeter.conf"
        )
        values.update(
            _read_config_values(config_file, "greeter", _LIGHTDM_SETTINGS, "LightDM GTK greeter")
        )
    return values


def _xdg_system_directories(variable: str, fallback: str) -> tuple[Path, ...]:
    directories = os.environ.get(variable, fallback)
    return tuple(
        Path(directory)
        for directory in directories.split(os.pathsep)
        if directory and Path(directory).is_absolute()
    )


def _dropin_files(directory: Path, manager: str) -> list[Path]:
    try:
        return sorted(
            (
                entry
                for entry in directory.iterdir()
                if entry.name.endswith(".conf") and entry.is_file()
            ),
            key=lambda entry: entry.name,
        )
    except FileNotFoundError:
        return []
    except OSError as error:
        raise DisplayManagerConfigError(
            f"Could not list {manager} configuration directory {directory}."
        ) from error


def _sddm_config_paths(
    system_dropin_dir: str | Path,
    local_dropin_dir: str | Path,
    config_file: str | Path,
) -> list[Path]:
    paths: list[Path] = []
    for directory in (Path(system_dropin_dir), Path(local_dropin_dir)):
        paths.extend(_dropin_files(directory, "SDDM"))
    paths.append(Path(config_file))
    return paths


def parse_sddm_config(
    config_file: str | Path = "/etc/sddm.conf",
    system_dropin_dir: str | Path = "/usr/lib/sddm/sddm.conf.d",
    local_dropin_dir: str | Path = "/etc/sddm.conf.d",
) -> dict[str, DisplayManagerSettingValue]:
    """Parse effective SDDM theme settings, honoring documented file precedence."""
    values: dict[str, DisplayManagerSettingValue] = {}
    for path in _sddm_config_paths(system_dropin_dir, local_dropin_dir, config_file):
        values.update(_read_config_values(path, "Theme", _SDDM_SETTINGS, "SDDM"))
    return values


def parse_gdm_config(
    path: str | Path = "/etc/gdm/custom.conf",
) -> dict[str, DisplayManagerSettingValue]:
    """Read legacy GDM greeter-theme keys when present in custom.conf."""
    return _read_config_values(Path(path), "greeter", _GDM_SETTINGS, "GDM")


def parse_display_manager_settings(
    manager: DisplayManagerEnum,
) -> dict[str, DisplayManagerSettingValue]:
    """Parse configuration values for a specific display manager."""
    parsers = {
        DisplayManagerEnum.LightDM: parse_lightdm_greeter_config,
        DisplayManagerEnum.SDDM: parse_sddm_config,
        DisplayManagerEnum.GDM: parse_gdm_config,
    }
    try:
        parser = parsers[manager]
    except KeyError:
        raise ValueError(f"Unsupported display manager: {manager!r}") from None
    return parser()


def _display_manager_from_identifier(identifier: str) -> DisplayManagerEnum | None:
    normalized = identifier.casefold()
    if "lightdm" in normalized:
        return DisplayManagerEnum.LightDM
    if "sddm" in normalized:
        return DisplayManagerEnum.SDDM
    if "gdm" in normalized:
        return DisplayManagerEnum.GDM
    return None


def get_display_manager(
    config_path: str | Path = "/etc/X11/default-display-manager",
    systemd_service_paths: tuple[str | Path, ...] = (
        "/etc/systemd/system/display-manager.service",
        "/run/systemd/system/display-manager.service",
        "/usr/lib/systemd/system/display-manager.service",
    ),
) -> DisplayManagerEnum:
    """Detect the configured display manager using common distro mechanisms."""
    path = Path(config_path)
    configured_identifier: str | None = None
    try:
        configured_identifier = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        pass
    except (OSError, UnicodeError) as error:
        raise RuntimeError("Could not read the configured display manager.") from error

    if configured_identifier:
        detected = _display_manager_from_identifier(configured_identifier)
        if detected is not None:
            return detected

    for service_path in systemd_service_paths:
        try:
            service_target = Path(service_path).resolve(strict=True)
        except FileNotFoundError:
            continue
        except OSError as error:
            raise RuntimeError("Could not inspect the system display-manager service.") from error
        detected = _display_manager_from_identifier(
            f"{Path(service_path).name} {service_target.name}"
        )
        if detected is not None:
            return detected

    if configured_identifier:
        raise ValueError(f"Unknown display manager: {configured_identifier}")
    raise FileNotFoundError("Display manager could not be detected.")


def get_display_manager_info(
    manager: DisplayManagerEnum | None = None,
) -> DisplayManagerInfo:
    """Return display and configuration details for one supported manager."""
    selected = manager if manager is not None else get_display_manager()
    try:
        return _DISPLAY_MANAGERS[selected]
    except KeyError:
        raise ValueError(f"Unsupported display manager: {selected!r}") from None


def get_supported_display_managers() -> tuple[DisplayManagerInfo, ...]:
    """Return the configuration overview for every supported display manager."""
    return tuple(_DISPLAY_MANAGERS.values())


__all__ = [
    "DisplayManagerEnum",
    "DisplayManagerInfo",
    "DisplayManagerSetting",
    "DisplayManagerSettingValue",
    "DisplayManagerConfigError",
    "get_display_manager",
    "get_display_manager_info",
    "get_supported_display_managers",
    "parse_lightdm_greeter_config",
    "parse_sddm_config",
    "parse_gdm_config",
    "parse_display_manager_settings",
]


if __name__ == "__main__":
    try:
        info = get_display_manager_info()
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        raise SystemExit(str(error)) from error
    print(f"Display Manager: {info.name}")
    print(f"Configuration: {info.config_path}")
