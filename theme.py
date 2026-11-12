import configparser
import errno
import io
import os
import shutil
import stat
import subprocess
import sys
import uuid
import warnings
from contextlib import ExitStack
from functools import lru_cache
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree


class ThemeError(Exception):
    """Custom exception for theme-related errors."""
    pass


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #

class ThemeData:
    """Class to hold theme metadata."""
    def __init__(self, name: str, absolute_path: str, gtk2: bool, gtk3: bool, gtk4: bool, xfwm4: bool, icon: str|None, cursor: str|None, libAdwaita: bool = False):
        self.name = name
        self.absolute_path = absolute_path
        self.gtk2 = gtk2
        self.gtk3 = gtk3
        self.gtk4 = gtk4
        self.xfwm4 = xfwm4
        self.libAdwaita = libAdwaita
        self.icon = icon
        self.cursor = cursor

    def __str__(self) -> str:
        return (
            f"{self.name}\n"
            f"  Path: {self.absolute_path}\n"
            f"  GTK 2: {'Yes' if self.gtk2 else 'No'}\n"
            f"  GTK 3: {'Yes' if self.gtk3 else 'No'}\n"
            f"  GTK 4: {'Yes' if self.gtk4 else 'No'}\n"
            f"  XFWM4: {'Yes' if self.xfwm4 else 'No'}\n"
            f"  libAdwaita override CSS: {'Available' if self.libAdwaita else 'Not available'}\n"
            f"  Icon theme: {self.icon if self.icon is not None else 'Not specified'}\n"
            f"  Cursor theme: {self.cursor if self.cursor is not None else 'Not specified'}"
        )


class WindowData:
    """Installed XFWM4 window theme and a title-bar sample image."""
    def __init__(self, name: str, absolute_path: str, model_path: str | None = None):
        self.name = name
        self.absolute_path = absolute_path
        self.model_path = model_path

    def __str__(self) -> str:
        return (
            f"{self.name}\n"
            f"  Path: {self.absolute_path}\n"
            f"  Sample image: {self.model_path if self.model_path else 'Unavailable'}"
        )


class IconData:
    """Installed icon theme and image paths used for its preview."""
    def __init__(
        self,
        name: str,
        absolute_path: str,
        model_path: str | None,
        sample_paths: tuple[str | None, ...] | None = None,
    ):
        self.name = name
        self.absolute_path = absolute_path
        self.model_path = model_path
        self.sample_paths = sample_paths if sample_paths is not None else (model_path,)

    def __str__(self) -> str:
        return f"{self.name}\n  Path: {self.absolute_path}\n  Sample image: {self.model_path}"


class CursorData:
    """Installed cursor theme and an optional Xcursor image sample."""
    def __init__(self, name: str, absolute_path: str, model_path: str | None = None):
        self.name = name
        self.absolute_path = absolute_path
        self.model_path = model_path

    def __str__(self) -> str:
        return (
            f"{self.name}\n"
            f"  Path: {self.absolute_path}\n"
            f"  Sample cursor: {self.model_path if self.model_path else 'Unavailable'}"
        )


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #

_GNOME_IFACE = "org.gnome.desktop.interface"
_GNOME_WM = "org.gnome.desktop.wm.preferences"


def _validate_name(name: str, kind: str) -> None:
    if (
        not name
        or Path(name).name != name
        or name in (".", "..")
        or any(char in name for char in "\r\n\0")
    ):
        raise ValueError(f"Invalid {kind} theme name: {name!r}")


def _xdg_data_dirs() -> list[Path]:
    data_home = os.environ.get("XDG_DATA_HOME", "")
    if not os.path.isabs(data_home):
        data_home = str(Path.home() / ".local/share")
    data_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    return [
        Path(directory)
        for directory in [data_home, *data_dirs.split(":")]
        if directory and os.path.isabs(directory)
    ]


def _theme_roots() -> list[Path]:
    return list(dict.fromkeys([Path.home() / ".themes", *(d / "themes" for d in _xdg_data_dirs())]))


def _icon_theme_roots() -> list[Path]:
    return [
        Path.home() / ".icons",
        *(directory / "icons" for directory in _xdg_data_dirs()),
        Path("/usr/share/pixmaps"),
    ]


def _cursor_theme_roots() -> list[Path]:
    cursor_path = os.environ.get("XCURSOR_PATH")
    if cursor_path:
        roots = [Path(directory).expanduser() for directory in cursor_path.split(":") if directory]
    else:
        roots = _icon_theme_roots()[:-1]
    return list(dict.fromkeys(roots))


@lru_cache(maxsize=None)
def _read_index(directory: Path) -> configparser.ConfigParser | None:
    """Parse ``directory/index.theme`` once; None if it does not exist."""
    metadata = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        with (directory / "index.theme").open(encoding="utf-8") as file:
            metadata.read_file(file)
    except FileNotFoundError:
        return None
    return metadata


def _inherits(metadata: configparser.ConfigParser) -> list[str]:
    result = []
    for parent in metadata.get("Icon Theme", "Inherits", fallback="").split(","):
        parent = parent.strip()
        if parent and Path(parent).name == parent and parent not in (".", ".."):
            result.append(parent)
    return result


# --------------------------------------------------------------------------- #
# Reading / writing the live session settings (xfconf + gsettings)
# --------------------------------------------------------------------------- #

def _run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, check=True)


def _describe(error: Exception) -> str:
    stderr = getattr(error, "stderr", None)
    return stderr.strip() if isinstance(stderr, str) and stderr.strip() else str(error)


def _xfconf_set(channel: str, property_name: str, value: str) -> bool:
    if shutil.which("xfconf-query") is None:
        return False
    # --create makes the call work even if the property does not exist yet.
    _run(["xfconf-query", "-c", channel, "-p", property_name,
          "--create", "-t", "string", "-s", value])
    return True


def _gsettings_set(schema: str, key: str, value: str) -> bool:
    """Return False when gsettings or this schema/key is not available."""
    if shutil.which("gsettings") is None:
        return False
    try:
        _run(["gsettings", "writable", schema, key])
    except (OSError, subprocess.CalledProcessError):
        return False
    _run(["gsettings", "set", schema, key, value])
    return True


def _get_theme_name(channel: str, property_name: str, theme_kind: str,
                    schema: str, key: str) -> str:
    errors = []
    if shutil.which("xfconf-query"):
        try:
            value = _run(["xfconf-query", "-c", channel, "-p", property_name]).stdout.strip()
            if value:
                return value
        except (OSError, subprocess.CalledProcessError) as e:
            errors.append(f"xfconf-query: {_describe(e)}")
    if shutil.which("gsettings"):
        try:
            value = _run(["gsettings", "get", schema, key]).stdout.strip().strip("'\"")
            if value:
                return value
        except (OSError, subprocess.CalledProcessError) as e:
            errors.append(f"gsettings: {_describe(e)}")
    detail = "; ".join(errors) or "neither xfconf-query nor gsettings returned a value"
    raise RuntimeError(f"Failed to get {theme_kind} theme name: {detail}")


def get_gtk_theme_name() -> str:
    """Get the current GTK theme name."""
    return _get_theme_name("xsettings", "/Net/ThemeName", "GTK", _GNOME_IFACE, "gtk-theme")


def get_window_theme_name() -> str:
    """Get the current window theme name."""
    return _get_theme_name("xfwm4", "/general/theme", "window", _GNOME_WM, "theme")


def get_icon_theme_name() -> str:
    """Get the current icon theme name."""
    return _get_theme_name("xsettings", "/Net/IconThemeName", "icon", _GNOME_IFACE, "icon-theme")


def get_cursor_theme_name() -> str:
    """Get the current cursor theme name."""
    return _get_theme_name("xsettings", "/Gtk/CursorThemeName", "cursor",
                           _GNOME_IFACE, "cursor-theme")


def _set_related_theme(kind: str, name: str, channel: str, property_name: str,
                       schema: str, key: str) -> None:
    """Apply a theme to xfconf AND gsettings, whichever of them are available.

    gsettings (or its schema) being absent is not an error. It is an error only
    if neither backend could be updated.
    """
    applied = []
    errors = []
    for tool, setter in (
        ("xfconf-query", lambda: _xfconf_set(channel, property_name, name)),
        ("gsettings", lambda: _gsettings_set(schema, key, name)),
    ):
        try:
            if setter():
                applied.append(tool)
        except (OSError, subprocess.CalledProcessError) as e:
            errors.append(f"{tool}: {_describe(e)}")
    if not applied:
        detail = "; ".join(errors) or "neither xfconf-query nor gsettings is available"
        raise RuntimeError(f"Failed to set {kind} theme '{name}': {detail}")
    for message in errors:
        warnings.warn(f"Partially set {kind} theme '{name}' ({message})", stacklevel=3)


# --------------------------------------------------------------------------- #
# GTK / XFWM4 theme discovery
# --------------------------------------------------------------------------- #

def get_available_themes() -> list[ThemeData]:
    """List installed GTK and XFWM themes, including their component metadata.

    Themes with the same name in different directories are listed separately.
    Icon and cursor names come from the theme's optional metatheme metadata.
    libAdwaita indicates GTK 4 CSS available for an override, not verified compatibility.
    """
    _read_index.cache_clear()
    themes = []
    try:
        for root in _theme_roots():
            try:
                entries = sorted(root.iterdir(), key=lambda path: path.name)
            except FileNotFoundError:
                continue
            for entry in entries:
                if not entry.is_dir():
                    continue
                gtk2 = (entry / "gtk-2.0" / "gtkrc").is_file()
                gtk3 = (entry / "gtk-3.0" / "gtk.css").is_file()
                gtk4 = (entry / "gtk-4.0" / "gtk.css").is_file()
                xfwm4 = (entry / "xfwm4" / "themerc").is_file()
                if not any((gtk2, gtk3, gtk4, xfwm4)):
                    continue
                try:
                    metadata = _read_index(entry)
                except (UnicodeError, configparser.Error):
                    metadata = None  # a broken index.theme must not hide the theme
                themes.append(ThemeData(
                    name=entry.name,
                    absolute_path=str(entry.absolute()),
                    gtk2=gtk2,
                    gtk3=gtk3,
                    gtk4=gtk4,
                    xfwm4=xfwm4,
                    libAdwaita=gtk4,
                    icon=metadata.get("X-GNOME-Metatheme", "IconTheme", fallback=None) if metadata else None,
                    cursor=metadata.get("X-GNOME-Metatheme", "CursorTheme", fallback=None) if metadata else None,
                ))
    except OSError as e:
        raise RuntimeError(f"Failed to get available themes: {e}") from e
    return themes


def _window_theme_model_path(xfwm4_path: Path) -> str | None:
    for stem in ("title-3-active", "title-1-active", "title-2-active", "top-active"):
        for extension in (".png", ".xpm"):
            candidate = xfwm4_path / f"{stem}{extension}"
            if candidate.is_file():
                return str(candidate.absolute())
    return None


def get_available_window_themes() -> list[WindowData]:
    """List installed themes that provide XFWM4 window decorations."""
    try:
        return [
            WindowData(
                theme.name,
                theme.absolute_path,
                _window_theme_model_path(Path(theme.absolute_path) / "xfwm4"),
            )
            for theme in get_available_themes()
            if theme.xfwm4
        ]
    except OSError as error:
        raise RuntimeError(f"Failed to get available window themes: {error}") from error


# --------------------------------------------------------------------------- #
# Icon themes
# --------------------------------------------------------------------------- #

_ICON_PREVIEW_NAMES = ("folder", "go-down", "audio-volume-high", "web-browser")


def _icon_file(directory: Path, icon_name: str) -> Path | None:
    for extension in (".png", ".svg", ".xpm"):
        candidate = directory / (icon_name + extension)
        if candidate.is_file():
            return candidate
    return None


def _find_theme_icon(
    name: str,
    icon_name: str,
    roots: list[Path],
    visited: set[str],
    size: int = 16,
) -> str | None:
    if name in visited:
        return None
    visited.add(name)
    parents: list[str] = []
    for root in roots:
        directory = root / name
        metadata = _read_index(directory)
        if metadata is None:
            continue
        section = "Icon Theme"
        dirs = (
            metadata.get(section, "Directories", fallback="").split(",")
            + metadata.get(section, "ScaledDirectories", fallback="").split(",")
        )
        matches = []
        for index, value in enumerate(dict.fromkeys(item.strip() for item in dirs)):
            path = Path(value)
            if not value or path.is_absolute() or ".." in path.parts:
                continue
            if not metadata.has_section(value):
                continue
            try:
                directory_size = metadata.getint(value, "Size")
                scale = metadata.getint(value, "Scale", fallback=1)
                kind = metadata.get(value, "Type", fallback="Threshold").lower()
                minimum = metadata.getint(value, "MinSize", fallback=directory_size)
                maximum = metadata.getint(value, "MaxSize", fallback=directory_size)
                threshold = metadata.getint(value, "Threshold", fallback=2)
            except ValueError:
                continue
            if scale != 1:
                continue
            if kind == "fixed":
                if size != directory_size:
                    continue
                distance = 0
            elif kind == "scalable":
                if not minimum <= size <= maximum:
                    continue
                distance = 0
            elif kind == "threshold":
                if abs(size - directory_size) > threshold:
                    continue
                distance = abs(size - directory_size)
            else:
                continue
            candidate = _icon_file(directory / path, icon_name)
            if candidate is not None:
                matches.append((distance, index, candidate))
        if matches:
            candidate = min(matches, key=lambda match: (match[0], match[1]))[2]
            return str(candidate.absolute())
        parents.extend(_inherits(metadata))
    for parent in parents:
        result = _find_theme_icon(parent, icon_name, roots, visited, size)
        if result:
            return result
    return None


def get_available_icon_themes() -> list[IconData]:
    """List icon themes and resolve XFCE's four preview icons to image paths.

    The first theme of a given name follows the icon search path precedence.
    Icons may be resolved through the theme's inherited themes. ``model_path``
    is the image path for the first (folder) preview icon.
    """
    _read_index.cache_clear()
    roots = list(dict.fromkeys(_icon_theme_roots()))
    themes: dict[str, IconData] = {}
    try:
        for root in roots:
            try:
                entries = sorted(root.iterdir(), key=lambda entry: entry.name.casefold())
            except FileNotFoundError:
                continue
            for entry in entries:
                if entry.name in themes or not entry.is_dir():
                    continue
                try:
                    metadata = _read_index(entry)
                except (UnicodeError, configparser.Error):
                    continue
                if (
                    metadata is None
                    or not metadata.has_option("Icon Theme", "Directories")
                    or metadata.getboolean("Icon Theme", "Hidden", fallback=False)
                ):
                    continue
                missing = None
                samples = []
                for icon_name in _ICON_PREVIEW_NAMES:
                    path = _find_theme_icon(entry.name, icon_name, roots, set())
                    if path is None:
                        if missing is None:
                            missing = _find_theme_icon(entry.name, "image-missing", roots, set())
                        path = missing
                    samples.append(path)
                themes[entry.name] = IconData(
                    entry.name, str(entry.absolute()), samples[0], tuple(samples)
                )
    except (OSError, UnicodeError, configparser.Error) as e:
        raise RuntimeError(f"Failed to get available icon themes: {e}") from e
    return list(themes.values())


def select_icon_theme(theme: IconData, applyToAllUser: bool = False) -> None:
    """Set the current icon theme in XFCE and gsettings, optionally for every home under /home.

    All-user mode backs up existing GTK and XFCE settings before replacing
    them. Live session settings are still changed only for the current user.
    """
    if not isinstance(theme, IconData):
        raise TypeError("theme must be an instance of IconData")
    _validate_name(theme.name, "icon")
    if applyToAllUser:
        _apply_all_users_with_authentication("icon", theme)
    _set_related_theme("icon", theme.name, "xsettings", "/Net/IconThemeName",
                       _GNOME_IFACE, "icon-theme")


# --------------------------------------------------------------------------- #
# Cursor themes
# --------------------------------------------------------------------------- #

def _cursor_theme_available(name: str, roots: list[Path], seen: set[str]) -> bool:
    if name in seen:
        return False
    seen.add(name)
    for root in roots:
        directory = root / name
        if (directory / "cursors").is_dir():
            return True
        metadata = _read_index(directory)
        if metadata is None:
            continue
        if any(_cursor_theme_available(parent, roots, seen) for parent in _inherits(metadata)):
            return True
    return False


_PREFERRED_CURSORS = ("left_ptr", "default", "top_left_arrow", "arrow", "pointer")


def _find_cursor_model_path(name: str, roots: list[Path], seen: set[str]) -> str | None:
    if name in seen:
        return None
    seen.add(name)
    parents: list[str] = []
    for root in roots:
        directory = root / name
        cursors = directory / "cursors"
        if cursors.is_dir():
            try:
                files = sorted(
                    (path for path in cursors.iterdir() if path.is_file()),
                    key=lambda path: path.name.casefold(),
                )
            except FileNotFoundError:
                files = []
            by_name = {path.name: path for path in files}
            sample = next((by_name[c] for c in _PREFERRED_CURSORS if c in by_name), None)
            if sample is None and files:
                sample = files[0]
            if sample is not None:
                return str(sample.absolute())
        metadata = _read_index(directory)
        if metadata is not None:
            parents.extend(_inherits(metadata))
    for parent in parents:
        result = _find_cursor_model_path(parent, roots, seen)
        if result:
            return result
    return None


def get_available_cursor_themes() -> list[CursorData]:
    """List installed cursor themes, including themes resolved by inheritance."""
    _read_index.cache_clear()
    roots = _cursor_theme_roots()
    themes: dict[str, CursorData] = {}
    try:
        for root in roots:
            try:
                entries = sorted(root.iterdir(), key=lambda entry: entry.name.casefold())
            except FileNotFoundError:
                continue
            for entry in entries:
                if entry.name in themes or not entry.is_dir():
                    continue
                try:
                    if _cursor_theme_available(entry.name, roots, set()):
                        themes[entry.name] = CursorData(
                            entry.name,
                            str(entry.absolute()),
                            _find_cursor_model_path(entry.name, roots, set()),
                        )
                except (UnicodeError, configparser.Error):
                    continue
    except OSError as error:
        raise RuntimeError(f"Failed to get available cursor themes: {error}") from error
    return list(themes.values())


def select_cursor_theme(theme: CursorData, applyToAllUser: bool = False) -> None:
    """Set the current cursor theme in XFCE and gsettings, optionally for every home under /home."""
    if not isinstance(theme, CursorData):
        raise TypeError("theme must be an instance of CursorData")
    _validate_name(theme.name, "cursor")
    if applyToAllUser:
        _apply_all_users_with_authentication("cursor", theme)
    _set_related_theme("cursor", theme.name, "xsettings", "/Gtk/CursorThemeName",
                       _GNOME_IFACE, "cursor-theme")


# --------------------------------------------------------------------------- #
# Per-home (all users) file helpers
# --------------------------------------------------------------------------- #

def _open_directory(parent_fd: int, name: str, owner: os.stat_result,
                    stack: ExitStack, create: bool = False) -> int:
    created = False
    if create:
        try:
            os.mkdir(name, 0o755, dir_fd=parent_fd)
            created = True
        except FileExistsError:
            pass
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    stack.callback(os.close, fd)
    if created and os.geteuid() == 0:
        os.fchown(fd, owner.st_uid, owner.st_gid)
    return fd


def _backup_existing(directory_fd: int, name: str) -> None:
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    backup = f"{name}.backup-{uuid.uuid4().hex}"
    os.rename(name, backup, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)


def _read_home_file(directory_fd: int, name: str) -> tuple[bytes | None, int]:
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    except FileNotFoundError:
        return None, 0o600
    with os.fdopen(fd, "rb") as file:
        info = os.fstat(file.fileno())
        return file.read(), stat.S_IMODE(info.st_mode)


def _replace_home_file(
    directory_fd: int,
    name: str,
    contents: bytes,
    owner: os.stat_result,
    mode: int,
    old_contents: bytes | None,
) -> None:
    if old_contents == contents:
        return
    temporary = f".{name}.tmp-{uuid.uuid4().hex}"
    fd = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        mode,
        dir_fd=directory_fd,
    )
    try:
        with os.fdopen(fd, "wb") as file:
            if os.geteuid() == 0:
                os.fchown(file.fileno(), owner.st_uid, owner.st_gid)
            file.write(contents)
            file.flush()
            os.fsync(file.fileno())
        _backup_existing(directory_fd, name)
        os.rename(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass


def _gtk_theme_settings_ini(old_contents: bytes | None, key: str, name: str) -> bytes:
    settings = configparser.ConfigParser(interpolation=None)
    settings.optionxform = str
    if old_contents:
        settings.read_string(old_contents.decode("utf-8"))
    if not settings.has_section("Settings"):
        settings.add_section("Settings")
    settings.set("Settings", key, name)
    output = io.StringIO()
    settings.write(output)
    return output.getvalue().encode("utf-8")


def _xfconf_xml(old_contents: bytes | None, channel: str, group_name: str,
                property_name: str, name: str) -> bytes:
    """Return xfconf perchannel XML with ``group_name/property_name`` set to ``name``."""
    if old_contents:
        root = ElementTree.fromstring(
            old_contents,
            parser=ElementTree.XMLParser(target=ElementTree.TreeBuilder(insert_comments=True)),
        )
        if root.tag != "channel" or root.get("name") != channel:
            raise ValueError(f"Existing XFCE {channel} configuration has an unexpected root")
    else:
        root = ElementTree.Element("channel", {"name": channel, "version": "1.0"})
    group = root.find(f"./property[@name='{group_name}']")
    if group is None:
        group = ElementTree.SubElement(root, "property", {"name": group_name, "type": "empty"})
    else:
        group.set("type", "empty")
    setting = group.find(f"./property[@name='{property_name}']")
    if setting is None:
        setting = ElementTree.SubElement(group, "property", {"name": property_name})
    setting.attrib.clear()
    setting.attrib.update({"name": property_name, "type": "string", "value": name})
    ElementTree.indent(root, space="  ")
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"


_HomeAction = Callable[[int, os.stat_result, ExitStack], None]


def _for_each_home(homes_root: Path, what: str, action: _HomeAction) -> None:
    """Run ``action(home_fd, owner_stat, stack)`` for each home; collect errors."""
    errors = []
    with ExitStack() as stack:
        root_fd = os.open(homes_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        stack.callback(os.close, root_fd)
        for home_name in sorted(os.listdir(root_fd)):
            try:
                info = os.stat(home_name, dir_fd=root_fd, follow_symlinks=False)
                if not stat.S_ISDIR(info.st_mode):
                    continue
                with ExitStack() as home_stack:
                    home_fd = _open_directory(root_fd, home_name, info, home_stack)
                    action(home_fd, info, home_stack)
            except (OSError, UnicodeError, configparser.Error,
                    ElementTree.ParseError, ValueError) as e:
                errors.append(f"{homes_root / home_name}: {e}")
    if errors:
        raise RuntimeError(
            f"Failed to apply {what} to some homes; earlier settings may already have changed: "
            + "; ".join(errors)
        )


def _write_xfconf_value(home_fd: int, info: os.stat_result, stack: ExitStack,
                        channel: str, group: str, prop: str, name: str) -> None:
    fd = _open_directory(home_fd, ".config", info, stack, create=True)
    for part in ("xfce4", "xfconf", "xfce-perchannel-xml"):
        fd = _open_directory(fd, part, info, stack, create=True)
    filename = f"{channel}.xml"
    old_xml, mode = _read_home_file(fd, filename)
    xml = _xfconf_xml(old_xml, channel, group, prop, name)
    _replace_home_file(fd, filename, xml, info, mode, old_xml)


def _write_gtk_ini_value(home_fd: int, info: os.stat_result, stack: ExitStack,
                         key: str, name: str) -> None:
    config_fd = _open_directory(home_fd, ".config", info, stack, create=True)
    for version in ("gtk-3.0", "gtk-4.0"):
        gtk_fd = _open_directory(config_fd, version, info, stack, create=True)
        old_ini, mode = _read_home_file(gtk_fd, "settings.ini")
        ini = _gtk_theme_settings_ini(old_ini, key, name)
        _replace_home_file(gtk_fd, "settings.ini", ini, info, mode, old_ini)


def _apply_xsettings_theme_to_homes(
    name: str,
    homes_root: Path,
    kind: str,
    gtk_key: str,
    xfconf_group: str,
    xfconf_property: str,
) -> None:
    _validate_name(name, kind)

    def action(home_fd: int, info: os.stat_result, stack: ExitStack) -> None:
        _write_gtk_ini_value(home_fd, info, stack, gtk_key, name)
        _write_xfconf_value(home_fd, info, stack, "xsettings", xfconf_group, xfconf_property, name)

    _for_each_home(homes_root, f"{kind} theme", action)


def _apply_window_theme_to_homes(theme: WindowData, homes_root: Path) -> None:
    def action(home_fd: int, info: os.stat_result, stack: ExitStack) -> None:
        _write_xfconf_value(home_fd, info, stack, "xfwm4", "general", "theme", theme.name)

    _for_each_home(homes_root, "window theme", action)


def _apply_theme_to_homes(theme: ThemeData, homes_root: Path) -> None:
    source = Path(theme.absolute_path).resolve(strict=True)
    components = [
        source / version for version, available in (
            ("gtk-3.0", theme.gtk3), ("gtk-4.0", theme.gtk4)
        ) if available
    ]
    if not theme.gtk2 and not components:
        raise RuntimeError(f"Theme '{theme.name}' has no GTK assets to apply")
    for component in components:
        if not (component / "gtk.css").is_file():
            raise RuntimeError(f"Missing theme stylesheet: {component / 'gtk.css'}")
    gtk2_file = source / "gtk-2.0" / "gtkrc"
    if theme.gtk2 and not gtk2_file.is_file():
        raise RuntimeError(f"Missing theme stylesheet: {gtk2_file}")
    if theme.gtk2 and any(char in str(gtk2_file) for char in "\r\n"):
        raise ValueError("GTK 2 theme path cannot contain a newline")
    _validate_name(theme.name, "GTK")

    # Directory listings are the same for every home: read them once.
    assets = {component: sorted(component.iterdir()) for component in components}

    def action(home_fd: int, info: os.stat_result, stack: ExitStack) -> None:
        if theme.gtk2:
            escaped = str(gtk2_file).replace("\\", "\\\\").replace('"', '\\"')
            contents = f'include "{escaped}"\n'.encode("utf-8")
            _backup_existing(home_fd, ".gtkrc-2.0")
            fd = os.open(".gtkrc-2.0", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o644, dir_fd=home_fd)
            with os.fdopen(fd, "wb") as file:
                if os.geteuid() == 0:
                    os.fchown(file.fileno(), info.st_uid, info.st_gid)
                file.write(contents)
        if components:
            config_fd = _open_directory(home_fd, ".config", info, stack, create=True)
            for component in components:
                target_fd = _open_directory(config_fd, component.name, info, stack, create=True)
                for asset in assets[component]:
                    if asset.name in ("settings.ini", "thumbnail.png"):
                        continue
                    try:
                        existing = os.readlink(asset.name, dir_fd=target_fd)
                    except FileNotFoundError:
                        existing = None
                    except OSError as e:
                        if e.errno != errno.EINVAL:
                            raise
                        existing = None
                    if existing == str(asset):
                        continue
                    _backup_existing(target_fd, asset.name)
                    os.symlink(str(asset), asset.name, dir_fd=target_fd)
                    if os.geteuid() == 0:
                        os.chown(asset.name, info.st_uid, info.st_gid,
                                 dir_fd=target_fd, follow_symlinks=False)

    _for_each_home(homes_root, "GTK overrides", action)

    # Also make each user's own settings (XFCE xsettings + GTK settings.ini)
    # point at the theme, so the override assets actually get used.
    _apply_xsettings_theme_to_homes(
        theme.name, homes_root, "GTK", "gtk-theme-name", "Net", "ThemeName"
    )


def _require_trusted_root_path(path: Path, description: str) -> Path:
    resolved = path.resolve(strict=True)
    info = resolved.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise RuntimeError(
            "All-user changes require a root-owned system installation; reinstall with "
            f"the system-wide installation instructions ({description})."
        )
    for directory in resolved.parents:
        directory_info = directory.stat()
        if (
            not stat.S_ISDIR(directory_info.st_mode)
            or directory_info.st_uid != 0
            or directory_info.st_mode & 0o022
        ):
            raise RuntimeError(
                "All-user changes require a root-owned system installation; reinstall with "
                f"the system-wide installation instructions ({description})."
            )
    return resolved


def _require_trusted_theme_tree(path: Path) -> None:
    pending = [path]
    while pending:
        current = pending.pop()
        info = current.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or info.st_uid != 0
            or info.st_mode & 0o022
            or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))
        ):
            raise RuntimeError(
                f"Refusing privileged GTK theme access to untrusted asset: {current}"
            )
        if stat.S_ISDIR(info.st_mode):
            pending.extend(current.iterdir())


def _system_gtk_theme_for_all_users(name: str, absolute_path: str) -> ThemeData:
    _validate_name(name, "GTK")
    selected = Path(absolute_path)
    if selected.name != name:
        raise ValueError("GTK theme name and path do not match")

    source = None
    for root in (Path("/usr/local/share/themes"), Path("/usr/share/themes")):
        try:
            trusted_root = root.resolve(strict=True)
        except FileNotFoundError:
            continue
        root_info = trusted_root.stat()
        if (
            not stat.S_ISDIR(root_info.st_mode)
            or root_info.st_uid != 0
            or root_info.st_mode & 0o022
        ):
            continue
        try:
            if selected.parent.resolve(strict=True) == trusted_root:
                candidate = trusted_root / name
                candidate_info = candidate.lstat()
                if (
                    not stat.S_ISDIR(candidate_info.st_mode)
                    or candidate_info.st_uid != 0
                    or candidate_info.st_mode & 0o022
                ):
                    raise RuntimeError(f"GTK theme directory is not trusted: {candidate}")
                source = candidate
                break
        except FileNotFoundError:
            continue
    if source is None:
        raise ValueError(
            "All-user GTK changes require a theme installed under "
            "/usr/share/themes or /usr/local/share/themes."
        )

    components: dict[str, Path] = {}
    for version in ("gtk-2.0", "gtk-3.0", "gtk-4.0"):
        component = source / version
        try:
            component.lstat()
        except FileNotFoundError:
            continue
        _require_trusted_theme_tree(component)
        components[version] = component

    return ThemeData(
        name=name,
        absolute_path=str(source),
        gtk2=(components.get("gtk-2.0", source / "gtk-2.0") / "gtkrc").is_file(),
        gtk3=(components.get("gtk-3.0", source / "gtk-3.0") / "gtk.css").is_file(),
        gtk4=(components.get("gtk-4.0", source / "gtk-4.0") / "gtk.css").is_file(),
        xfwm4=False,
        icon=None,
        cursor=None,
    )


def _apply_all_users_as_root(arguments: list[str]) -> int:
    if os.geteuid() != 0:
        print("The all-user helper must be run through Polkit.", file=sys.stderr)
        return 1
    if len(arguments) not in (2, 3):
        print("Invalid all-user helper arguments.", file=sys.stderr)
        return 2

    kind, name = arguments[:2]
    try:
        _validate_name(name, kind)
        if kind == "gtk" and len(arguments) == 3:
            theme = _system_gtk_theme_for_all_users(name, arguments[2])
            _apply_theme_to_homes(theme, Path("/home"))
        elif kind == "window" and len(arguments) == 2:
            _apply_window_theme_to_homes(WindowData(name, ""), Path("/home"))
        elif kind == "icon" and len(arguments) == 2:
            _apply_xsettings_theme_to_homes(
                name, Path("/home"), "icon", "gtk-icon-theme-name", "Net", "IconThemeName"
            )
        elif kind == "cursor" and len(arguments) == 2:
            _apply_xsettings_theme_to_homes(
                name, Path("/home"), "cursor", "gtk-cursor-theme-name", "Gtk", "CursorThemeName"
            )
        else:
            print("Invalid all-user helper operation.", file=sys.stderr)
            return 2
    except (OSError, RuntimeError, ValueError, UnicodeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


def _apply_all_users_with_authentication(
    kind: str, theme: ThemeData | WindowData | IconData | CursorData
) -> None:
    pkexec = shutil.which("pkexec")
    if pkexec is None:
        raise RuntimeError(
            "Polkit is unavailable. Install policykit-1 and an XFCE Polkit authentication agent."
        )

    interpreter = _require_trusted_root_path(Path(sys.executable), "Python interpreter")
    application = _require_trusted_root_path(Path(__file__), "application files")
    pkexec_path = _require_trusted_root_path(Path(pkexec), "Polkit executable")
    arguments = [
        str(pkexec_path),
        str(interpreter),
        "-I",
        str(application),
        "--apply-all-users",
        kind,
        theme.name,
    ]
    if kind == "gtk":
        if not isinstance(theme, ThemeData):
            raise TypeError("GTK all-user operation requires ThemeData")
        arguments.append(theme.absolute_path)

    result = subprocess.run(arguments, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        if not detail:
            detail = "Authentication was cancelled or the privileged operation failed."
        raise RuntimeError(f"Could not apply theme for all users: {detail}")


# --------------------------------------------------------------------------- #
# Public selectors for GTK / window themes
# --------------------------------------------------------------------------- #

def _icon_theme_installed(name: str, roots: list[Path]) -> bool:
    return any((root / name / "index.theme").is_file() for root in roots)


def select_gtk_theme(theme: ThemeData, applyToAllUser: bool = False) -> None:
    """Set GTK and installed related themes in XFCE and GNOME (gsettings) settings.

    Every setting is written to xfconf and, when available, to gsettings.
    A failure can leave earlier settings changed. Missing icon or cursor
    themes referenced by metadata are skipped with a warning.
    All-user mode installs GTK overrides under directories in /home, backing
    up conflicts. Theme files must be accessible to each user; session
    settings still apply only to the current session.
    """
    if not isinstance(theme, ThemeData):
        raise TypeError("theme must be an instance of ThemeData")
    _validate_name(theme.name, "GTK")
    if applyToAllUser:
        _apply_all_users_with_authentication("gtk", theme)

    _set_related_theme("GTK", theme.name, "xsettings", "/Net/ThemeName",
                       _GNOME_IFACE, "gtk-theme")

    if theme.xfwm4:
        _set_related_theme("window", theme.name, "xfwm4", "/general/theme",
                           _GNOME_WM, "theme")

    icon_roots = _icon_theme_roots()
    cursor_roots = _cursor_theme_roots()
    for kind, name, property_name, key in (
        ("icon", theme.icon, "/Net/IconThemeName", "icon-theme"),
        ("cursor", theme.cursor, "/Gtk/CursorThemeName", "cursor-theme"),
    ):
        if not name:
            continue
        try:
            _validate_name(name, kind)
        except ValueError as e:
            raise ValueError(f"{e}; earlier settings may already have changed") from e
        try:
            available = (
                _icon_theme_installed(name, icon_roots)
                if kind == "icon" else _cursor_theme_available(name, cursor_roots, set())
            )
        except (OSError, UnicodeError, configparser.Error) as e:
            raise RuntimeError(
                f"Failed to check {kind} theme '{name}'; earlier settings may already have changed: {e}"
            ) from e
        if not available:
            warnings.warn(f"{kind.capitalize()} theme '{name}' is not installed; skipping it", stacklevel=2)
            continue
        _set_related_theme(kind, name, "xsettings", property_name, _GNOME_IFACE, key)


def select_window_theme(theme: WindowData, applyToAllUser: bool = False) -> None:
    """Set an installed XFWM4 theme in XFCE and GNOME (gsettings) settings.

    All-user mode updates each home directory's XFCE xfwm4 configuration,
    backing up existing files. Live settings still apply only to this session.
    """
    if not isinstance(theme, WindowData):
        raise TypeError("theme must be an instance of WindowData")
    _validate_name(theme.name, "window")
    if applyToAllUser:
        _apply_all_users_with_authentication("window", theme)

    _set_related_theme("window", theme.name, "xfwm4", "/general/theme", _GNOME_WM, "theme")


__all__ = [
    "ThemeError",
    "ThemeData",
    "IconData",
    "WindowData",
    "CursorData",
    "get_gtk_theme_name",
    "get_window_theme_name",
    "get_icon_theme_name",
    "get_cursor_theme_name",
    "get_available_themes",
    "get_available_window_themes",
    "get_available_icon_themes",
    "get_available_cursor_themes",
    "select_icon_theme",
    "select_gtk_theme",
    "select_window_theme",
    "select_cursor_theme",
]

if __name__ == "__main__":
    if sys.argv[1:2] == ["--apply-all-users"]:
        raise SystemExit(_apply_all_users_as_root(sys.argv[2:]))
    print(f"GTK Theme: {get_gtk_theme_name()}")
    print(f"Window Theme: {get_window_theme_name()}")
    print(f"Icon Theme: {get_icon_theme_name()}")
    print(f"Cursor Theme: {get_cursor_theme_name()}")
    print("\nAvailable Themes:")
    for theme in get_available_themes():
        print(f"\n{theme}")
    print("\nAvailable Icon Themes:")
    for theme in get_available_icon_themes():
        print(f"\n{theme}")