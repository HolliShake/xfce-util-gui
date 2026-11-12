import configparser
import enum
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


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
            DisplayManagerSetting("xft-dpi", "Font rendering DPI (50-300)."),
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
_DISPLAY_MANAGER_IDS = {
    DisplayManagerEnum.LightDM: "lightdm",
    DisplayManagerEnum.SDDM: "sddm",
    DisplayManagerEnum.GDM: "gdm",
}
_DISPLAY_MANAGER_CONFIGS = {
    DisplayManagerEnum.LightDM: (
        Path("/etc/lightdm/lightdm-gtk-greeter.conf"),
        "greeter",
        _LIGHTDM_SETTINGS,
    ),
    DisplayManagerEnum.SDDM: (
        Path("/etc/sddm.conf"),
        "Theme",
        _SDDM_SETTINGS,
    ),
    DisplayManagerEnum.GDM: (
        Path("/etc/gdm/custom.conf"),
        "greeter",
        _GDM_SETTINGS,
    ),
}


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


def _validate_display_manager_updates(
    manager: DisplayManagerEnum, updates: Mapping[str, str]
) -> None:
    if manager not in _DISPLAY_MANAGER_CONFIGS:
        raise ValueError(f"Unsupported display manager: {manager!r}")
    if not updates:
        raise ValueError("No display-manager settings were provided.")
    allowed_settings = _DISPLAY_MANAGER_CONFIGS[manager][2]
    for key, value in updates.items():
        if key not in allowed_settings:
            raise ValueError(f"Unsupported setting for {manager.name}: {key!r}")
        if not isinstance(value, str):
            raise ValueError(f"Invalid value for display-manager setting {key!r}.")
        if len(value) > 4096 or any(char in value for char in "\r\n\0"):
            raise ValueError(f"Invalid value for display-manager setting {key!r}.")


def _section_header(line: str) -> str | None:
    stripped = line.strip()
    if not stripped.startswith("[") or "]" not in stripped:
        return None
    closing = stripped.index("]")
    suffix = stripped[closing + 1 :].strip()
    if suffix and not suffix.startswith(("#", ";")):
        return None
    return stripped[1:closing].strip()


def _update_ini_content(
    content: str, section: str, updates: Mapping[str, str]
) -> str:
    lines = content.splitlines(keepends=True)
    section_ranges: list[tuple[int, int]] = []
    current_section: str | None = None
    current_start = 0
    for index, line in enumerate(lines):
        header = _section_header(line)
        if header is not None:
            if current_section == section:
                section_ranges.append((current_start, index))
            current_section = header
            current_start = index
    if current_section == section:
        section_ranges.append((current_start, len(lines)))

    newline = "\r\n" if "\r\n" in content else "\n"
    if not section_ranges:
        if content and not content.endswith(("\n", "\r")):
            content += newline
        suffix = "".join(f"{key}={value}{newline}" for key, value in updates.items())
        separator = newline if content else ""
        return f"{content}{separator}[{section}]{newline}{suffix}"

    key_pattern = re.compile(
        r"^\s*(" + "|".join(re.escape(key) for key in updates) + r")\s*[=:]"
    )
    remove_indices: set[int] = set()
    for start, end in section_ranges:
        for index in range(start + 1, end):
            stripped = lines[index].lstrip()
            if stripped.startswith(("#", ";")):
                continue
            if key_pattern.match(lines[index]):
                remove_indices.add(index)

    last_section_end = section_ranges[-1][1]
    insertion_index = last_section_end - sum(
        index < last_section_end for index in remove_indices
    )
    filtered = [line for index, line in enumerate(lines) if index not in remove_indices]
    if insertion_index > 0 and not filtered[insertion_index - 1].endswith(("\n", "\r")):
        filtered[insertion_index - 1] += newline
    rendered = [f"{key}={value}{newline}" for key, value in updates.items()]
    filtered[insertion_index:insertion_index] = rendered
    return "".join(filtered)


def _write_ini_settings(
    path: Path, section: str, updates: Mapping[str, str]
) -> None:
    try:
        original_stat = path.lstat()
    except FileNotFoundError:
        original_stat = None
    else:
        if not stat.S_ISREG(original_stat.st_mode):
            raise RuntimeError(f"Refusing to edit a non-regular configuration file: {path}")

    try:
        content = path.read_text(encoding="utf-8") if original_stat else ""
    except (OSError, UnicodeError) as error:
        raise RuntimeError(f"Could not read configuration file {path}.") from error
    if content:
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        parser.optionxform = str
        try:
            parser.read_string(content)
        except configparser.Error as error:
            raise RuntimeError(f"Could not parse configuration file {path}.") from error

    updated = _update_ini_content(content, section, updates)
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        parser.read_string(updated)
    except configparser.Error as error:
        raise RuntimeError(f"Could not validate updated configuration file {path}.") from error

    mode = stat.S_IMODE(original_stat.st_mode) if original_stat else 0o644
    backup_path: Path | None = None
    if original_stat:
        backup_path = path.with_name(f"{path.name}.backup-{os.getpid()}-{os.stat(path).st_mtime_ns}")
        try:
            shutil.copy2(path, backup_path)
        except OSError as error:
            raise RuntimeError(f"Could not back up configuration file {path}.") from error

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as output:
            output.write(updated)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
    except OSError as error:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        if backup_path is not None:
            try:
                backup_path.unlink()
            except FileNotFoundError:
                pass
        raise RuntimeError(f"Could not save configuration file {path}.") from error


def _require_trusted_root_path(path: Path, description: str) -> Path:
    resolved = path.resolve(strict=True)
    current = resolved
    while True:
        info = current.stat()
        if (
            info.st_uid != 0
            or info.st_mode & 0o022
            or (current == resolved and not stat.S_ISREG(info.st_mode))
            or (current != resolved and not stat.S_ISDIR(info.st_mode))
        ):
            raise RuntimeError(
                "Display-manager changes require a root-owned system installation "
                f"({description})."
            )
        if current == current.parent:
            break
        current = current.parent
    return resolved


def _trusted_helper_application() -> Path:
    module_name = Path(__file__).name
    candidates = [Path(__file__)]
    candidates.extend(
        Path(entry) / module_name for entry in sys.path if entry
    )
    candidates.extend(
        Path("/opt/xfceutil/venv/lib").glob(
            f"python*/site-packages/{module_name}"
        )
    )

    checked: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
            if resolved in checked:
                continue
            checked.add(resolved)
            return _require_trusted_root_path(resolved, "application files")
        except (OSError, RuntimeError):
            continue
    raise RuntimeError(
        "Saving display-manager settings requires the root-owned system "
        "installation. Launch the installed XFCE Utility or install it first."
    )


def _write_display_manager_settings(
    manager: DisplayManagerEnum, updates: Mapping[str, str]
) -> None:
    _validate_display_manager_updates(manager, updates)
    path, section, _ = _DISPLAY_MANAGER_CONFIGS[manager]
    try:
        for directory in path.parents:
            info = directory.lstat()
            if (
                not stat.S_ISDIR(info.st_mode)
                or stat.S_ISLNK(info.st_mode)
                or info.st_uid != 0
                or info.st_mode & 0o022
            ):
                raise RuntimeError(f"Refusing to edit configuration under {directory}.")
        try:
            target_stat = path.lstat()
        except FileNotFoundError:
            target_stat = None
        if target_stat is not None and (
            not stat.S_ISREG(target_stat.st_mode)
            or stat.S_ISLNK(target_stat.st_mode)
            or target_stat.st_uid != 0
            or target_stat.st_mode & 0o022
        ):
            raise RuntimeError(f"Refusing to edit untrusted configuration file {path}.")
        _write_ini_settings(path, section, updates)
    except OSError as error:
        raise RuntimeError("Could not save display-manager configuration.") from error


def _save_display_manager_settings_as_root(arguments: list[str]) -> int:
    if os.geteuid() != 0:
        print("Display-manager settings must be saved through Polkit.", file=sys.stderr)
        return 1
    if len(arguments) != 2:
        print("Invalid display-manager helper arguments.", file=sys.stderr)
        return 2
    manager_id, encoded_updates = arguments
    managers = {
        identifier: manager for manager, identifier in _DISPLAY_MANAGER_IDS.items()
    }
    try:
        manager = managers[manager_id]
        updates = json.loads(encoded_updates)
        if not isinstance(updates, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in updates.items()
        ):
            raise ValueError
        _write_display_manager_settings(manager, updates)
    except (KeyError, json.JSONDecodeError, TypeError, ValueError, OSError, RuntimeError) as error:
        print(f"Could not save display-manager settings: {error}", file=sys.stderr)
        return 1
    return 0


def save_display_manager_settings(
    manager: DisplayManagerEnum, updates: Mapping[str, str]
) -> None:
    """Save selected active-manager settings after Polkit authorization."""
    _validate_display_manager_updates(manager, updates)
    if os.geteuid() == 0:
        _write_display_manager_settings(manager, updates)
        return

    pkexec = shutil.which("pkexec")
    if pkexec is None:
        raise RuntimeError(
            "Polkit is unavailable. Install pkexec and a desktop authentication agent."
        )
    interpreter = _require_trusted_root_path(Path(sys.executable), "Python interpreter")
    application = _trusted_helper_application()
    pkexec_path = _require_trusted_root_path(Path(pkexec), "Polkit executable")
    encoded_updates = json.dumps(dict(updates), separators=(",", ":"))
    command = [
        str(pkexec_path),
        str(interpreter),
        "-I",
        str(application),
        "--save-display-manager-settings",
        _DISPLAY_MANAGER_IDS[manager],
        encoded_updates,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as error:
        raise RuntimeError("Could not start Polkit authorization.") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        if not detail:
            detail = "Authorization was cancelled or the privileged save failed."
        raise RuntimeError(f"Could not save display-manager settings: {detail}")


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
    "save_display_manager_settings",
]


if __name__ == "__main__":
    if sys.argv[1:2] == ["--save-display-manager-settings"]:
        raise SystemExit(_save_display_manager_settings_as_root(sys.argv[2:]))
    try:
        info = get_display_manager_info()
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        raise SystemExit(str(error)) from error
    print(f"Display Manager: {info.name}")
    print(f"Configuration: {info.config_path}")
