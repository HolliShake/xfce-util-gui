from collections.abc import Mapping

import customtkinter as ctk

from supported_display_manager import (
    DisplayManagerConfigError,
    DisplayManagerEnum,
    DisplayManagerInfo,
    DisplayManagerSettingValue,
    get_display_manager,
    get_display_manager_info,
    parse_display_manager_settings,
)

# ── Palette ──────────────────────────────────────────────────────────────
_ACCENT = ("#2563eb", "#3b82f6")
_ACCENT_SOFT = ("#dbeafe", "#1e3a5f")
_SURFACE = ("#ffffff", "#1b1e25")
_SURFACE_ALT = ("#f8fafc", "#22262f")
_BORDER = ("#e2e6ec", "#323845")
_BORDER_SUBTLE = ("#eef1f5", "#2a2f3a")
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


class DisplayManagerThemeTab:
    """Show appearance-related configuration options for the configured display manager."""

    def __init__(self, parent: ctk.CTkFrame) -> None:
        self._parent = parent
        self._f_title = ctk.CTkFont(size=26, weight="bold")
        self._f_heading = ctk.CTkFont(size=17, weight="bold")
        self._f_body = ctk.CTkFont(size=13)
        self._f_small = ctk.CTkFont(size=12)
        self._f_chip = ctk.CTkFont(size=11, weight="bold")
        self._f_mono = ctk.CTkFont(family="monospace", size=12)
        self._f_mono_bold = ctk.CTkFont(family="monospace", size=12, weight="bold")
        self._f_icon = ctk.CTkFont(size=14, weight="bold")

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
        content = ctk.CTkScrollableFrame(
            self._parent,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=_BORDER,
            scrollbar_button_hover_color=_MUTED,
        )
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
                "This tab is informational; XFCE Utility does not edit display-manager "
                "configuration files. Changes generally affect the greeter after the "
                "display manager is restarted."
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

    # ── Individual setting row ────────────────────────────────────────────
    def _build_setting_row(
        self,
        parent: ctk.CTkFrame,
        index: int,
        total: int,
        setting,
        parsed_value: DisplayManagerSettingValue | None,
        config_error: str | None,
    ) -> None:
        if config_error:
            value_text = "Unavailable — configuration could not be read."
            value_color = _ERROR_TEXT
            is_set: bool | None = None
        elif parsed_value is None:
            value_text = "Not explicitly set · manager default applies"
            value_color = _OFF_TEXT
            is_set = False
        else:
            value_text = parsed_value.value if parsed_value.value else "(empty)"
            value_color = _TEXT
            is_set = True

        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.grid(row=index, column=0, sticky="ew")
        row_frame.grid_columnconfigure(1, weight=1)

        if is_set is None:
            dot_color, dot_char = _ERROR_TEXT, "✕"
        elif is_set:
            dot_color, dot_char = _OK_TEXT, "●"
        else:
            dot_color, dot_char = _OFF_TEXT, "○"

        ctk.CTkLabel(
            row_frame,
            text=dot_char,
            font=ctk.CTkFont(size=9),
            text_color=dot_color,
            width=16,
        ).grid(row=0, column=0, padx=(0, 6), pady=(10, 0), sticky="n")

        ctk.CTkLabel(
            row_frame,
            text=setting.name,
            font=self._f_mono_bold,
            text_color=_ACCENT,
            anchor="nw",
        ).grid(row=0, column=1, sticky="nw", pady=(8, 0))

        ctk.CTkLabel(
            row_frame,
            text=value_text,
            font=self._f_mono if is_set else self._f_small,
            text_color=value_color,
            anchor="ne",
            justify="right",
            wraplength=320,
        ).grid(row=0, column=2, sticky="ne", padx=(12, 0), pady=(8, 0))

        next_row = 1
        if is_set and parsed_value.source:
            ctk.CTkLabel(
                row_frame,
                text=f"source: {parsed_value.source}",
                font=ctk.CTkFont(size=10),
                text_color=_MUTED,
                anchor="e",
            ).grid(row=1, column=2, sticky="e", padx=(12, 0), pady=(0, 2))
            next_row = 2

        ctk.CTkLabel(
            row_frame,
            text=setting.description,
            font=self._f_small,
            text_color=_MUTED,
            anchor="w",
            justify="left",
            wraplength=560,
        ).grid(
            row=next_row,
            column=0,
            columnspan=3,
            sticky="ew",
            padx=(22, 0),
            pady=(0, 10),
        )

        if index < total - 1:
            ctk.CTkFrame(
                row_frame, height=1, fg_color=_BORDER_SUBTLE
            ).grid(
                row=next_row + 1,
                column=0,
                columnspan=3,
                sticky="ew",
            )


def create_display_manager_theme_tab(parent: ctk.CTkFrame) -> DisplayManagerThemeTab:
    return DisplayManagerThemeTab(parent)