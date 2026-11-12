from collections.abc import Mapping
import logging
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from theme import (
    get_available_cursor_themes,
    get_available_icon_themes,
    get_available_themes,
)
from supported_display_manager import (
    DisplayManagerConfigError,
    DisplayManagerEnum,
    DisplayManagerInfo,
    DisplayManagerSetting,
    DisplayManagerSettingValue,
    get_display_manager,
    get_display_manager_info,
    parse_display_manager_settings,
    save_display_manager_settings,
)

# ── Palette ──────────────────────────────────────────────────────────────
_ACCENT = ("#2563eb", "#3b82f6")
_ACCENT_HOVER = ("#1d4ed8", "#2563eb")
_ACCENT_SOFT = ("#dbeafe", "#1e3a5f")
_SURFACE = ("#ffffff", "#1b1e25")
_SURFACE_ALT = ("#f8fafc", "#22262f")
_SURFACE_INPUT = ("#ffffff", "#161a21")
_BORDER = ("#e2e6ec", "#323845")
_BORDER_SUBTLE = ("#eef1f5", "#2a2f3a")
_BORDER_INPUT = ("#d0d5dd", "#3a4050")
_TEXT = ("#111827", "#e8eaf0")
_TEXT_SECONDARY = ("#374151", "#c4c9d4")
_MUTED = ("#667085", "#98a2b3")
_OK_BG = ("#dcfce7", "#12351f")
_OK_TEXT = ("#15803d", "#4ade80")
_OK_BORDER = ("#bbf7d0", "#1a4d2e")
_OFF_BG = ("#f1f3f6", "#2b303b")
_OFF_TEXT = ("#667085", "#8b95a7")
_OFF_BORDER = ("#e5e7eb", "#3a4050")
_ERROR_BG = ("#fef2f2", "#3b1219")
_ERROR_TEXT = ("#b91c1c", "#f87171")
_ERROR_BORDER = ("#fecaca", "#5c1a1a")

_PAD = 20
_RADIUS_CARD = 14
_RADIUS_CHIP = 11
_RADIUS_INPUT = 8

_LOGGER = logging.getLogger(__name__)
_THEME_SETTING_KINDS = {
    "theme-name": "gtk",
    "icon-theme-name": "icon",
    "cursor-theme-name": "cursor",
    "CursorTheme": "cursor",
}


class DisplayManagerThemeTab:
    """Show appearance-related configuration options for the configured display manager."""

    def __init__(self, parent: ctk.CTkFrame) -> None:
        self._parent = parent
        self._f_title = ctk.CTkFont(size=26, weight="bold")
        self._f_heading = ctk.CTkFont(size=17, weight="bold")
        self._f_body = ctk.CTkFont(size=13)
        self._f_small = ctk.CTkFont(size=12)
        self._f_chip = ctk.CTkFont(size=11, weight="bold")
        self._f_label = ctk.CTkFont(size=13, weight="bold")
        self._f_mono = ctk.CTkFont(family="monospace", size=12)
        self._f_mono_bold = ctk.CTkFont(family="monospace", size=12, weight="bold")
        self._f_meta = ctk.CTkFont(family="monospace", size=10)
        self._f_icon = ctk.CTkFont(size=14, weight="bold")
        self._installed_theme_names: dict[str, tuple[str, ...] | None] = {}

        try:
            self._detected: DisplayManagerEnum | None = get_display_manager()
        except (FileNotFoundError, RuntimeError, ValueError):
            self._detected = None

        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)
        self._build_header()
        self._build_detection_status()
        self._build_information()

    # ── Header (unchanged from original) ─────────────────────────────────
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self._parent, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=_PAD, pady=(_PAD, 12))
        ctk.CTkLabel(
            header, text="Display Manager", font=self._f_title, anchor="w"
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="Review appearance options for your configured Linux login greeter.",
            font=self._f_small,
            text_color=_MUTED,
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

    # ── Detection status banner ───────────────────────────────────────────
    def _build_detection_status(self) -> None:
        if self._detected is None:
            bg, text_color, border, icon, text = (
                _ERROR_BG,
                _ERROR_TEXT,
                _ERROR_BORDER,
                "⚠",
                "Could not detect the configured display manager.",
            )
        else:
            info = get_display_manager_info(self._detected)
            bg, text_color, border, icon, text = (
                _OK_BG,
                _OK_TEXT,
                _OK_BORDER,
                "✓",
                f"Detected display manager: {info.name}",
            )

        status = ctk.CTkFrame(
            self._parent,
            fg_color=bg,
            border_width=1,
            border_color=border,
            corner_radius=_RADIUS_CARD,
        )
        status.grid(row=1, column=0, sticky="ew", padx=_PAD, pady=(0, 12))
        status.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            status,
            text=icon,
            font=self._f_icon,
            text_color=text_color,
            width=28,
            height=28,
        ).grid(row=0, column=0, padx=(14, 10), pady=12)

        ctk.CTkLabel(
            status,
            text=text,
            font=self._f_body,
            text_color=text_color,
            anchor="w",
            justify="left",
            wraplength=600,
        ).grid(row=0, column=1, sticky="ew", padx=(0, 16), pady=12)

    # ── Information area ──────────────────────────────────────────────────
    def _build_information(self) -> None:
        if hasattr(self, "_content"):
            self._content.destroy()
        content = ctk.CTkScrollableFrame(
            self._parent,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=_BORDER,
            scrollbar_button_hover_color=_MUTED,
        )
        self._content = content
        content.grid(row=2, column=0, sticky="nsew", padx=_PAD, pady=(0, _PAD))
        content.grid_columnconfigure(0, weight=1)

        if self._detected is None:
            self._build_empty_state(content)
            return

        info = get_display_manager_info(self._detected)
        try:
            values = parse_display_manager_settings(self._detected)
            config_error = None
        except DisplayManagerConfigError as error:
            values = {}
            config_error = str(error)

        self._build_manager_card(content, 0, info, values, config_error)

        note_frame = ctk.CTkFrame(
            content,
            fg_color=_SURFACE_ALT,
            border_width=1,
            border_color=_BORDER_SUBTLE,
            corner_radius=10,
        )
        note_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        note_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            note_frame,
            text="ⓘ",
            font=self._f_icon,
            text_color=_ACCENT,
            width=24,
        ).grid(row=0, column=0, padx=(14, 6), pady=10, sticky="n")
        ctk.CTkLabel(
            note_frame,
            text=(
                "Saving changes edits the active display manager's system configuration "
                "and requests administrator authorization. Changes generally take effect "
                "after the display manager is restarted."
            ),
            font=self._f_small,
            text_color=_MUTED,
            anchor="w",
            justify="left",
            wraplength=620,
        ).grid(row=0, column=1, sticky="ew", padx=(0, 14), pady=10)

    def _build_empty_state(self, parent: ctk.CTkScrollableFrame) -> None:
        empty = ctk.CTkFrame(
            parent,
            fg_color=_SURFACE_ALT,
            border_width=1,
            border_color=_BORDER_SUBTLE,
            corner_radius=_RADIUS_CARD,
        )
        empty.grid(row=0, column=0, sticky="ew", pady=(4, 8))
        empty.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            empty,
            text="—",
            font=ctk.CTkFont(size=36, weight="bold"),
            text_color=_MUTED,
        ).grid(row=0, column=0, pady=(24, 6))
        ctk.CTkLabel(
            empty,
            text="No display manager detected",
            font=self._f_heading,
            text_color=_TEXT,
        ).grid(row=1, column=0, pady=(0, 4))
        ctk.CTkLabel(
            empty,
            text="Display-manager settings are unavailable until detection succeeds.",
            font=self._f_body,
            text_color=_MUTED,
            wraplength=420,
            justify="center",
        ).grid(row=2, column=0, pady=(0, 24), padx=20)

    # ── Manager card ──────────────────────────────────────────────────────
    def _build_manager_card(
        self,
        parent: ctk.CTkScrollableFrame,
        row: int,
        info: DisplayManagerInfo,
        values: Mapping[str, DisplayManagerSettingValue],
        config_error: str | None,
    ) -> None:
        self._setting_entries: dict[
            str, ctk.CTkEntry | ctk.CTkComboBox | ctk.CTkSwitch
        ] = {}
        self._setting_initial: dict[str, str | None] = {}
        self._setting_initial_switches: dict[str, bool] = {}
        card = ctk.CTkFrame(
            parent,
            fg_color=_SURFACE,
            border_width=1,
            border_color=_BORDER,
            corner_radius=_RADIUS_CARD,
        )
        card.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        card.grid_columnconfigure(0, weight=1)

        # ── Card header ────────────────────────────────────────────────
        heading = ctk.CTkFrame(card, fg_color="transparent")
        heading.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 4))
        heading.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            heading,
            text=info.name,
            font=self._f_heading,
            text_color=_TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        badges = ctk.CTkFrame(heading, fg_color="transparent")
        badges.grid(row=1, column=0, sticky="w", pady=(6, 0))

        if info.manager == self._detected:
            ctk.CTkLabel(
                badges,
                text="●  IN USE",
                height=22,
                corner_radius=_RADIUS_CHIP,
                font=self._f_chip,
                fg_color=_OK_BG,
                text_color=_OK_TEXT,
                padx=10,
            ).pack(side="left", padx=(0, 6))

        if info.section:
            ctk.CTkLabel(
                badges,
                text=f"§  {info.section}",
                height=22,
                corner_radius=_RADIUS_CHIP,
                font=self._f_chip,
                fg_color=_ACCENT_SOFT,
                text_color=_ACCENT,
                padx=10,
            ).pack(side="left", padx=(0, 6))
        else:
            ctk.CTkLabel(
                badges,
                text="No supported theme section",
                height=22,
                corner_radius=_RADIUS_CHIP,
                font=self._f_chip,
                fg_color=_OFF_BG,
                text_color=_OFF_TEXT,
                padx=10,
            ).pack(side="left", padx=(0, 6))

        details_row = 1

        # ── Config path ───────────────────────────────────────────────
        if info.config_path is not None:
            path_frame = ctk.CTkFrame(
                card,
                fg_color=_SURFACE_ALT,
                corner_radius=8,
                border_width=1,
                border_color=_BORDER_SUBTLE,
            )
            path_frame.grid(
                row=details_row, column=0, sticky="ew", padx=18, pady=(10, 8)
            )
            path_frame.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                path_frame,
                text="›",
                font=self._f_icon,
                text_color=_MUTED,
                width=20,
            ).grid(row=0, column=0, padx=(10, 2), pady=6)
            ctk.CTkLabel(
                path_frame,
                text=info.config_path,
                font=self._f_mono,
                text_color=_MUTED,
                anchor="w",
                justify="left",
                wraplength=560,
            ).grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=6)
            details_row += 1

        # ── Summary ───────────────────────────────────────────────────
        ctk.CTkLabel(
            card,
            text=info.summary,
            font=self._f_body,
            text_color=_TEXT_SECONDARY,
            anchor="w",
            justify="left",
            wraplength=600,
        ).grid(row=details_row, column=0, sticky="ew", padx=18, pady=(0, 10))
        details_row += 1

        # ── Config error banner ───────────────────────────────────────
        if config_error:
            err = ctk.CTkFrame(
                card,
                fg_color=_ERROR_BG,
                border_width=1,
                border_color=_ERROR_BORDER,
                corner_radius=8,
            )
            err.grid(row=details_row, column=0, sticky="ew", padx=18, pady=(0, 10))
            err.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                err,
                text="⚠",
                font=self._f_icon,
                text_color=_ERROR_TEXT,
                width=20,
            ).grid(row=0, column=0, padx=(10, 4), pady=8)
            ctk.CTkLabel(
                err,
                text=config_error,
                font=self._f_small,
                text_color=_ERROR_TEXT,
                anchor="w",
                justify="left",
                wraplength=540,
            ).grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=8)
            details_row += 1

        # ── Settings section ──────────────────────────────────────────
        if info.settings:
            settings_header = ctk.CTkFrame(card, fg_color="transparent")
            settings_header.grid(
                row=details_row, column=0, sticky="ew", padx=18, pady=(4, 2)
            )
            settings_header.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                settings_header,
                text="SETTINGS",
                font=self._f_chip,
                text_color=_MUTED,
                anchor="w",
            ).grid(row=0, column=0, sticky="w")
            ctk.CTkFrame(
                settings_header,
                height=1,
                fg_color=_BORDER_SUBTLE,
            ).grid(row=1, column=0, sticky="ew", pady=(4, 0))
            details_row += 1

            settings = ctk.CTkFrame(card, fg_color="transparent")
            settings.grid(row=details_row, column=0, sticky="ew", padx=18)
            settings.grid_columnconfigure(0, weight=1)
            details_row += 1

            for idx, setting in enumerate(info.settings):
                parsed_value = values.get(setting.name)
                self._build_setting_row(
                    settings,
                    idx,
                    len(info.settings),
                    setting,
                    parsed_value,
                    config_error,
                )

        # ── Save bar ──────────────────────────────────────────────────
        save_bar = ctk.CTkFrame(card, fg_color="transparent")
        save_bar.grid(row=details_row, column=0, sticky="ew", padx=18, pady=(12, 4))
        save_bar.grid_columnconfigure(0, weight=1)
        self._save_hint = ctk.CTkLabel(
            save_bar,
            text="No unsaved changes",
            font=self._f_small,
            text_color=_MUTED,
            anchor="w",
        )
        self._save_hint.grid(row=0, column=0, sticky="w")

        save_button = ctk.CTkButton(
            save_bar,
            text="Save changes",
            command=self._save_settings,
            state="disabled" if config_error else "normal",
            fg_color=_ACCENT,
            hover_color=_ACCENT_HOVER,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        save_button.grid(row=0, column=1, sticky="e")
        self._save_button = save_button
        self._save_requires_auth_hint = ctk.CTkLabel(
            save_bar,
            text="Requires administrator authentication",
            font=self._f_small,
            text_color=_MUTED,
            anchor="e",
        )
        self._save_requires_auth_hint.grid(row=1, column=1, sticky="e", pady=(4, 0))
        details_row += 1

        # ── Note ──────────────────────────────────────────────────────
        if info.note:
            note = ctk.CTkFrame(
                card,
                fg_color=_SURFACE_ALT,
                corner_radius=8,
                border_width=1,
                border_color=_BORDER_SUBTLE,
            )
            note.grid(
                row=details_row, column=0, sticky="ew", padx=18, pady=(8, 16)
            )
            note.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                note,
                text="ⓘ",
                font=self._f_icon,
                text_color=_MUTED,
                width=20,
            ).grid(row=0, column=0, padx=(10, 4), pady=8, sticky="n")
            ctk.CTkLabel(
                note,
                text=info.note,
                font=self._f_small,
                text_color=_OFF_TEXT,
                anchor="w",
                justify="left",
                wraplength=560,
            ).grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=8)
        else:
            card.grid_rowconfigure(details_row, minsize=16)

        self._sync_save_state()

    # ── Individual setting row ────────────────────────────────────────────
    def _build_setting_row(
        self,
        parent: ctk.CTkFrame,
        index: int,
        total: int,
        setting: DisplayManagerSetting,
        parsed_value: DisplayManagerSettingValue | None,
        config_error: str | None,
    ) -> None:
        if config_error:
            is_set: bool | None = None
        elif parsed_value is None:
            is_set = False
        else:
            is_set = True

        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.grid(row=index, column=0, sticky="ew", pady=(0, 2))
        row_frame.grid_columnconfigure(0, weight=1)

        # Status dot + key line
        label_line = ctk.CTkFrame(row_frame, fg_color="transparent")
        label_line.grid(row=0, column=0, sticky="ew", pady=(10, 2))
        label_line.grid_columnconfigure(1, weight=1)

        if is_set is None:
            dot_color, dot_char = _ERROR_TEXT, "✕"
        elif is_set:
            dot_color, dot_char = _OK_TEXT, "●"
        else:
            dot_color, dot_char = _OFF_TEXT, "○"

        ctk.CTkLabel(
            label_line,
            text=dot_char,
            font=ctk.CTkFont(size=9),
            text_color=dot_color,
            width=16,
        ).grid(row=0, column=0, padx=(0, 6), sticky="n")

        ctk.CTkLabel(
            label_line,
            text=setting.name,
            font=self._f_mono_bold,
            text_color=_ACCENT,
            anchor="w",
        ).grid(row=0, column=1, sticky="w")

        if is_set:
            ctk.CTkLabel(
                label_line,
                text="SET",
                font=ctk.CTkFont(size=9, weight="bold"),
                text_color=_OK_TEXT,
                fg_color=_OK_BG,
                corner_radius=_RADIUS_CHIP,
                padx=8,
                height=18,
            ).grid(row=0, column=2, sticky="e")
        elif is_set is False:
            ctk.CTkLabel(
                label_line,
                text="DEFAULT",
                font=ctk.CTkFont(size=9, weight="bold"),
                text_color=_OFF_TEXT,
                fg_color=_OFF_BG,
                corner_radius=_RADIUS_CHIP,
                padx=8,
                height=18,
            ).grid(row=0, column=2, sticky="e")
        else:
            ctk.CTkLabel(
                label_line,
                text="UNAVAILABLE",
                font=ctk.CTkFont(size=9, weight="bold"),
                text_color=_ERROR_TEXT,
                fg_color=_ERROR_BG,
                corner_radius=_RADIUS_CHIP,
                padx=8,
                height=18,
            ).grid(row=0, column=2, sticky="e")

        # Description (clean, muted, full width)
        ctk.CTkLabel(
            row_frame,
            text=setting.description,
            font=self._f_small,
            text_color=_MUTED,
            anchor="w",
            justify="left",
            wraplength=560,
        ).grid(row=1, column=0, sticky="ew", padx=(22, 0), pady=(0, 8))

        # Source (meta line, only if present)
        if is_set and parsed_value.source:
            ctk.CTkLabel(
                row_frame,
                text=f"source: {parsed_value.source}",
                font=self._f_meta,
                text_color=_MUTED,
                anchor="w",
            ).grid(row=2, column=0, sticky="ew", padx=(22, 0), pady=(0, 8))

        # Input field
        theme_kind = _THEME_SETTING_KINDS.get(setting.name)
        browse_background = setting.name == "background"
        if setting.name == "user-background":
            initial_enabled = (
                parsed_value.value.strip().casefold() not in ("false", "0", "no", "off")
                if parsed_value is not None
                else True
            )
            value_entry = ctk.CTkSwitch(
                row_frame,
                text="Enabled",
                font=self._f_body,
                height=32,
                state="disabled" if config_error else "normal",
                fg_color=_BORDER_INPUT,
                progress_color=_ACCENT,
                button_color=_SURFACE,
                button_hover_color=_ACCENT_HOVER,
                text_color=_TEXT,
                command=self._sync_save_state,
            )
            if initial_enabled:
                value_entry.select()
            else:
                value_entry.deselect()
            self._setting_initial_switches[setting.name] = initial_enabled
        elif theme_kind is not None:
            choices = self._get_installed_theme_names(theme_kind)
            if choices is not None and parsed_value is not None:
                choices = tuple(dict.fromkeys((parsed_value.value, *choices)))
            combo_values = list(choices or ())
            if choices is not None and parsed_value is None:
                combo_values.insert(0, "")
            value_entry = ctk.CTkComboBox(
                row_frame,
                values=combo_values,
                font=self._f_mono,
                height=32,
                state=(
                    "disabled"
                    if config_error
                    else "readonly"
                    if choices
                    else "normal"
                ),
                border_color=_BORDER_INPUT,
                border_width=1,
                fg_color=_SURFACE_INPUT,
                text_color=_TEXT,
                button_color=_ACCENT,
                button_hover_color=_ACCENT_HOVER,
                dropdown_fg_color=_SURFACE,
                dropdown_hover_color=("#dbeafe", "#1f2f57"),
                dropdown_text_color=_TEXT,
                corner_radius=_RADIUS_INPUT,
            )
            value_entry.set(parsed_value.value if parsed_value is not None else "")
        else:
            value_entry = ctk.CTkEntry(
                row_frame,
                font=self._f_mono,
                height=32,
                placeholder_text="Not set",
                state="disabled" if config_error else "normal",
                border_color=_BORDER_INPUT,
                border_width=1,
                fg_color=_SURFACE_INPUT,
                text_color=_TEXT,
                corner_radius=_RADIUS_INPUT,
            )
            if parsed_value is not None:
                value_entry.insert(0, parsed_value.value)

        value_entry.grid(row=3, column=0, sticky="ew", padx=(22, 0), pady=(0, 2))
        if browse_background:
            ctk.CTkButton(
                row_frame,
                text="Choose image…",
                width=120,
                height=28,
                font=self._f_meta,
                fg_color=_SURFACE_INPUT,
                hover_color=_ACCENT_HOVER,
                text_color=_TEXT,
                border_width=1,
                border_color=_BORDER_INPUT,
                corner_radius=_RADIUS_INPUT,
                state="disabled" if config_error else "normal",
                command=lambda entry=value_entry: self._choose_background_file(entry),
            ).grid(row=4, column=0, sticky="e", padx=(22, 0), pady=(0, 8))
        elif theme_kind is not None and self._installed_theme_names.get(theme_kind) is None:
            # Show a small helper note under the input
            ctk.CTkLabel(
                row_frame,
                text="Installed theme choices are unavailable; enter a value manually.",
                font=self._f_meta,
                text_color=_OFF_TEXT,
                anchor="w",
                justify="left",
                wraplength=560,
            ).grid(row=4, column=0, sticky="ew", padx=(22, 0), pady=(0, 8))
        elif setting.name != "user-background":
            value_entry.grid_configure(pady=(0, 8))

        self._setting_entries[setting.name] = value_entry
        self._setting_initial[setting.name] = (
            parsed_value.value if parsed_value is not None else None
        )
        self._attach_change_tracking(setting.name, value_entry)

        if index < total - 1:
            ctk.CTkFrame(
                row_frame, height=1, fg_color=_BORDER_SUBTLE
            ).grid(row=5, column=0, sticky="ew", pady=(2, 0))

    # ── Change tracking ───────────────────────────────────────────────────
    def _attach_change_tracking(self, name: str, widget) -> None:
        try:
            if isinstance(widget, ctk.CTkComboBox):
                widget.configure(command=lambda _value: self._sync_save_state())
            elif isinstance(widget, ctk.CTkSwitch):
                widget.configure(command=self._sync_save_state)
            else:
                widget.bind("<KeyRelease>", lambda _e: self._sync_save_state(), add="+")
        except Exception:
            _LOGGER.debug("Could not attach change tracking for %s", name, exc_info=True)

    def _current_updates(self) -> dict[str, str]:
        updates: dict[str, str] = {}
        for key, entry in self._setting_entries.items():
            if isinstance(entry, ctk.CTkSwitch):
                current_state = bool(entry.get())
                if current_state != self._setting_initial_switches[key]:
                    updates[key] = "true" if current_state else "false"
                continue
            value = entry.get()
            if not isinstance(value, str):
                continue
            if value != (self._setting_initial[key] or ""):
                updates[key] = value
        return updates

    def _choose_background_file(self, entry: ctk.CTkEntry) -> None:
        initial_directory = Path.home()
        current_value = entry.get().strip()
        if current_value and not current_value.startswith("#"):
            candidate = Path(current_value).expanduser()
            if candidate.is_dir():
                initial_directory = candidate.resolve()
            elif candidate.is_absolute() or candidate.exists() or candidate.suffix:
                if candidate.parent.is_dir():
                    initial_directory = candidate.parent.resolve()
        path = filedialog.askopenfilename(
            parent=self._parent,
            title="Choose greeter background image",
            initialdir=str(initial_directory),
            filetypes=(
                ("Image files", "*.png *.jpg *.jpeg *.bmp *.webp *.gif"),
                ("All files", "*.*"),
            ),
        )
        if not path:
            return
        entry.delete(0, "end")
        entry.insert(0, path)
        self._sync_save_state()

    def _sync_save_state(self) -> None:
        if not hasattr(self, "_save_button"):
            return
        if getattr(self, "_save_button", None) is None:
            return
        if getattr(self, "_save_requires_auth_hint", None) is not None:
            if getattr(self, "_save_disabled_for_error", False):
                return
        updates = self._current_updates()
        disabled = getattr(self, "_config_error_active", False)
        if updates:
            self._save_button.configure(state="normal" if not disabled else "disabled")
            if hasattr(self, "_save_hint"):
                count = len(updates)
                self._save_hint.configure(
                    text=(
                        f"{count} unsaved change{'s' if count != 1 else ''}"
                    ),
                    text_color=_TEXT_SECONDARY,
                )
        else:
            self._save_button.configure(state="disabled")
            if hasattr(self, "_save_hint"):
                self._save_hint.configure(text="No unsaved changes", text_color=_MUTED)

    # ── Theme choices ─────────────────────────────────────────────────────
    def _get_installed_theme_names(self, kind: str) -> tuple[str, ...] | None:
        if kind in self._installed_theme_names:
            return self._installed_theme_names[kind]
        try:
            if kind == "gtk":
                names = (
                    theme.name
                    for theme in get_available_themes()
                    if theme.gtk2 or theme.gtk3 or theme.gtk4
                )
            elif kind == "icon":
                names = (theme.name for theme in get_available_icon_themes())
            elif kind == "cursor":
                names = (theme.name for theme in get_available_cursor_themes())
            else:
                raise ValueError(f"Unknown display-manager theme kind: {kind!r}")
            result = tuple(sorted(set(names), key=str.casefold))
        except RuntimeError:
            _LOGGER.warning(
                "Could not load installed %s themes for the display-manager editor",
                kind,
                exc_info=True,
            )
            self._installed_theme_names[kind] = None
            return None
        self._installed_theme_names[kind] = result
        return result

    # ── Save ──────────────────────────────────────────────────────────────
    def _save_settings(self) -> None:
        if self._detected is None:
            return
        updates = self._current_updates()
        if not updates:
            messagebox.showinfo(
                "No changes",
                "Change at least one setting before saving.",
                parent=self._parent,
            )
            return
        try:
            save_display_manager_settings(self._detected, updates)
        except (RuntimeError, ValueError) as error:
            messagebox.showerror(
                "Could not save display-manager settings",
                str(error),
                parent=self._parent,
            )
            return
        messagebox.showinfo(
            "Settings saved",
            "Display-manager settings were saved. Restart the display manager "
            "to apply them.",
            parent=self._parent,
        )
        self._build_information()


def create_display_manager_theme_tab(parent: ctk.CTkFrame) -> DisplayManagerThemeTab:
    return DisplayManagerThemeTab(parent)