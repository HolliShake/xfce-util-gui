import os
import ctypes
import ctypes.util
from collections import Counter
from pathlib import Path
from tkinter import BooleanVar, messagebox

import customtkinter as ctk

from scrollable_dropdown import ScrollableComboBox
from PIL import Image

from theme import CursorData, get_available_cursor_themes, get_cursor_theme_name, select_cursor_theme

_ACCENT = ("#2563eb", "#3b82f6")
_ACCENT_HOVER = ("#1d4ed8", "#2563eb")
_ACCENT_TINT = ("#dbeafe", "#1f2f57")
_ACCENT_TINT_HOVER = ("#bfdbfe", "#29407a")
_ACCENT_TEXT = ("#1d4ed8", "#9bb8ff")
_SURFACE = ("#ffffff", "#1b1e25")
_SURFACE_ALT = ("#f3f5f8", "#252932")
_BORDER = ("#e2e6ec", "#323845")
_TEXT = ("#111827", "#e8eaf0")
_MUTED = ("#667085", "#98a2b3")
_OK_BG = ("#dcfce7", "#12351f")
_OK_TEXT = ("#15803d", "#4ade80")
_WARN_TEXT = ("#b45309", "#fbbf24")
_ERR_TEXT = ("#dc2626", "#f87171")
_OFF_BG = ("#e8ebf0", "#2b303b")
_OFF_TEXT = ("#667085", "#8b95a7")
_PAD = 20
_PREVIEW_SIZE = 144


class _XcursorImage(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_uint),
        ("size", ctypes.c_uint),
        ("width", ctypes.c_uint),
        ("height", ctypes.c_uint),
        ("xhot", ctypes.c_uint),
        ("yhot", ctypes.c_uint),
        ("delay", ctypes.c_uint),
        ("pixels", ctypes.POINTER(ctypes.c_uint32)),
    ]


def _load_cursor_preview(path: str, size: int = 64) -> Image.Image:
    library_name = ctypes.util.find_library("Xcursor")
    if library_name is None:
        raise RuntimeError("The Xcursor library is unavailable")
    library = ctypes.CDLL(library_name)
    library.XcursorFilenameLoadImage.argtypes = [ctypes.c_char_p, ctypes.c_int]
    library.XcursorFilenameLoadImage.restype = ctypes.POINTER(_XcursorImage)
    library.XcursorImageDestroy.argtypes = [ctypes.POINTER(_XcursorImage)]
    cursor = library.XcursorFilenameLoadImage(os.fsencode(path), size)
    if not cursor:
        raise ValueError(f"Could not read cursor image: {path}")
    try:
        width = cursor.contents.width
        height = cursor.contents.height
        if not width or not height or width * height > 1024 * 1024:
            raise ValueError(f"Invalid cursor image dimensions: {width}x{height}")
        pixels = cursor.contents.pixels
        rgba = bytearray()
        for index in range(width * height):
            pixel = pixels[index]
            rgba.extend((
                (pixel >> 16) & 0xFF,
                (pixel >> 8) & 0xFF,
                pixel & 0xFF,
                (pixel >> 24) & 0xFF,
            ))
        return Image.frombytes("RGBA", (width, height), bytes(rgba))
    finally:
        library.XcursorImageDestroy(cursor)


class CursorThemeTab:
    def __init__(self, parent: ctk.CTkFrame) -> None:
        self._parent = parent
        self._themes: dict[str, CursorData] = {}
        self._current: str | None = None
        self._current_error: str | None = None
        self._loading = False
        self._preview_image: ctk.CTkImage | None = None
        self._preview_error: str | None = None
        self._all_users = BooleanVar(master=parent, value=False)

        self._f_title = ctk.CTkFont(size=26, weight="bold")
        self._f_body = ctk.CTkFont(size=13)
        self._f_small = ctk.CTkFont(size=12)
        self._f_chip = ctk.CTkFont(size=12, weight="bold")

        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)
        self._build_header()
        self._build_picker()
        self._build_details()
        self._build_options()
        self._build_footer()
        self._bind_shortcuts()
        self._load_themes()

    def _card(self, row: int, *, sticky: str = "ew") -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            self._parent, fg_color=_SURFACE, border_width=1,
            border_color=_BORDER, corner_radius=14,
        )
        card.grid(row=row, column=0, sticky=sticky, padx=_PAD, pady=(0, 12))
        card.grid_columnconfigure(0, weight=1)
        return card

    def _chip(self, master, text: str) -> ctk.CTkLabel:
        return ctk.CTkLabel(
            master, text=text, height=24, corner_radius=12,
            font=self._f_chip, fg_color=_OFF_BG, text_color=_OFF_TEXT,
        )

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self._parent, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=_PAD, pady=(_PAD, 14))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Cursor Theme", font=self._f_title, anchor="w").grid(
            row=0, column=0, sticky="w"
        )
        ctk.CTkLabel(
            header,
            text="Choose an installed Xcursor theme for your desktop.",
            font=self._f_small,
            text_color=_MUTED,
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.grid(row=0, column=1, rowspan=2, sticky="e")
        self._current_chip = self._chip(right, "Active: loading…")
        self._current_chip.grid(row=0, column=0, padx=(0, 10))
        self._refresh_button = ctk.CTkButton(
            right, text="⟳  Refresh", width=104, height=34, corner_radius=8,
            border_width=0, font=self._f_chip, fg_color=_ACCENT_TINT,
            hover_color=_ACCENT_TINT_HOVER, text_color=_ACCENT_TEXT,
            command=self._load_themes,
        )
        self._refresh_button.grid(row=0, column=1)

    def _set_current(self, name: str | None) -> None:
        if name:
            self._current_chip.configure(
                text=f"●  Active: {name}", fg_color=_OK_BG, text_color=_OK_TEXT
            )
        else:
            self._current_chip.configure(
                text="Active theme unknown", fg_color=_OFF_BG, text_color=_OFF_TEXT
            )

    def _build_picker(self) -> None:
        card = self._card(1)
        ctk.CTkLabel(
            card, text="CURSOR THEME", font=self._f_chip, text_color=_MUTED, anchor="w"
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 4))
        self._theme_picker = ScrollableComboBox(
            card, values=[], state="disabled", command=self._on_select,
            height=38, corner_radius=10, border_width=1, border_color=_BORDER,
            fg_color=_SURFACE_ALT, text_color=_TEXT, font=self._f_body,
            button_color=_ACCENT, button_hover_color=_ACCENT_HOVER,
            dropdown_fg_color=_SURFACE, dropdown_hover_color=_ACCENT_TINT,
            dropdown_text_color=_TEXT, dropdown_font=self._f_body, bg_color=_SURFACE,
        )
        self._theme_picker.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))

    def _build_details(self) -> None:
        card = self._card(2, sticky="nsew")
        card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            card, text="SELECTED THEME", font=self._f_chip, text_color=_MUTED, anchor="w"
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 4))

        preview_frame = ctk.CTkFrame(
            card, width=_PREVIEW_SIZE + 24, height=_PREVIEW_SIZE + 24,
            corner_radius=12, fg_color=_SURFACE_ALT,
        )
        preview_frame.grid(row=1, column=0, rowspan=3, padx=(16, 20), pady=(4, 14), sticky="n")
        preview_frame.grid_propagate(False)
        self._preview = ctk.CTkLabel(
            preview_frame, text="No preview available", text_color=_MUTED,
            font=self._f_small, justify="center", fg_color="transparent",
        )
        self._preview.place(relx=0.5, rely=0.5, anchor="center")

        details = ctk.CTkFrame(card, fg_color="transparent")
        details.grid(row=1, column=1, rowspan=3, sticky="nsew", padx=(0, 16), pady=(4, 14))
        details.grid_columnconfigure(0, weight=1)
        self._name = ctk.CTkLabel(
            details, text="—", font=ctk.CTkFont(size=18, weight="bold"), anchor="w"
        )
        self._name.grid(row=0, column=0, sticky="w")
        self._path = ctk.CTkLabel(
            details, text="", font=ctk.CTkFont(family="monospace", size=12),
            text_color=_MUTED, anchor="w", justify="left", wraplength=560,
        )
        self._path.grid(row=1, column=0, sticky="ew", pady=(4, 8))
        self._sample_path = ctk.CTkLabel(
            details, text="Sample image: unavailable", font=self._f_small,
            text_color=_MUTED, anchor="w", justify="left", wraplength=420,
        )
        self._sample_path.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self._active_badge = self._chip(details, "ACTIVE")
        self._active_badge.grid(row=0, column=1, sticky="e", padx=(8, 0))
        self._active_badge.grid_remove()
        ctk.CTkLabel(
            details,
            text="Cursor themes may inherit cursor assets from another installed theme.",
            font=self._f_small,
            text_color=_MUTED,
            anchor="w",
            justify="left",
        ).grid(row=3, column=0, columnspan=2, sticky="ew")
        card.bind(
            "<Configure>",
            lambda event: self._on_details_resize(event.width),
        )

    def _on_details_resize(self, width: int) -> None:
        wrap = max(180, width - _PREVIEW_SIZE - 80)
        self._path.configure(wraplength=wrap)
        self._sample_path.configure(wraplength=wrap)

    def _build_options(self) -> None:
        card = self._card(3)
        self._all_users_switch = ctk.CTkSwitch(
            card, text="Also apply to all users in /home", variable=self._all_users,
            command=self._on_all_users_toggle, font=self._f_body, bg_color=_SURFACE,
            progress_color=_ACCENT, button_hover_color=_ACCENT_HOVER,
            switch_width=40, switch_height=20,
        )
        self._all_users_switch.grid(row=0, column=0, sticky="w", padx=16, pady=(14, 4))
        self._all_users_hint = ctk.CTkLabel(
            card, text="", text_color=_MUTED, justify="left", anchor="w",
            font=self._f_small, wraplength=600,
        )
        self._all_users_hint.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))
        card.bind(
            "<Configure>",
            lambda event: self._all_users_hint.configure(wraplength=max(200, event.width - 40)),
        )
        self._refresh_all_users_hint()

    def _refresh_all_users_hint(self) -> None:
        if self._all_users.get():
            self._all_users_hint.configure(
                text="⚠  Updates GTK and XFCE cursor settings for every home under /home. "
                     "Existing files are backed up; GNOME settings change only for this session. "
                     "Elevated permissions may be required.",
                text_color=_WARN_TEXT,
            )
        else:
            self._all_users_hint.configure(
                text="Applies to your account and current desktop session.",
                text_color=_MUTED,
            )

    def _on_all_users_toggle(self) -> None:
        self._refresh_all_users_hint()
        self._update_apply_state()

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self._parent, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", padx=_PAD, pady=(0, _PAD))
        footer.grid_columnconfigure(0, weight=1)
        self._status = ctk.CTkLabel(
            footer, text="", anchor="w", justify="left", font=self._f_small, wraplength=440
        )
        self._status.grid(row=0, column=0, sticky="ew", padx=(2, 12))
        footer.bind(
            "<Configure>",
            lambda event: self._status.configure(wraplength=max(200, event.width - 220)),
        )
        self._apply_button = ctk.CTkButton(
            footer, text="Apply Cursor Theme", width=190, height=42, corner_radius=12,
            font=ctk.CTkFont(size=14, weight="bold"), state="disabled",
            fg_color=_SURFACE_ALT, hover_color=_ACCENT_HOVER, text_color=("white", "white"),
            text_color_disabled=_MUTED, command=self._apply_theme,
        )
        self._apply_button.grid(row=0, column=1, sticky="e")

    def _bind_shortcuts(self) -> None:
        top = self._parent.winfo_toplevel()
        top.bind("<Control-r>", lambda _event: self._shortcut(self._load_themes), add="+")
        top.bind("<Control-Return>", lambda _event: self._shortcut(self._apply_theme), add="+")

    def _shortcut(self, action) -> None:
        if self._parent.winfo_ismapped():
            action()

    def _set_status(self, text: str, kind: str = "info") -> None:
        color = {"ok": _OK_TEXT, "warn": _WARN_TEXT, "error": _ERR_TEXT}.get(kind, _MUTED)
        self._status.configure(text=text, text_color=color)

    def _selected_theme(self) -> CursorData | None:
        return self._themes.get(self._theme_picker.get())

    def _update_apply_state(self) -> None:
        theme = self._selected_theme()
        already_active = theme is not None and theme.name == self._current
        if already_active and not self._all_users.get():
            self._apply_button.configure(
                state="disabled", text="Already Active", fg_color=_SURFACE_ALT
            )
        elif theme is not None:
            self._apply_button.configure(
                state="normal", text="Apply Cursor Theme", fg_color=_ACCENT
            )
        else:
            self._apply_button.configure(
                state="disabled", text="Apply Cursor Theme", fg_color=_SURFACE_ALT
            )

    def _load_themes(self) -> None:
        if self._loading:
            return
        self._loading = True
        self._refresh_button.configure(state="disabled", text="⟳  Refreshing…")
        self._set_status("Loading cursor themes…")
        self._parent.update_idletasks()
        try:
            self._load_themes_impl()
        finally:
            self._loading = False
            self._refresh_button.configure(state="normal", text="⟳  Refresh")

    def _load_themes_impl(self) -> None:
        previous = self._theme_picker.get() if self._themes else None
        try:
            self._current = get_cursor_theme_name()
            self._current_error = None
        except RuntimeError as error:
            self._current = None
            self._current_error = str(error)
        self._set_current(self._current)

        try:
            themes = get_available_cursor_themes()
        except RuntimeError as error:
            self._themes = {}
            self._theme_picker.configure(values=[], state="disabled")
            self._theme_picker.set("")
            self._name.configure(text="Unable to load cursor themes")
            self._path.configure(text=str(error))
            self._sample_path.configure(text="Sample image: unavailable")
            self._clear_preview()
            self._active_badge.grid_remove()
            self._set_status("Press Refresh to retry.", "error")
            self._update_apply_state()
            return

        counts = Counter(theme.name for theme in themes)
        labels = [
            theme.name if counts[theme.name] == 1 else f"{theme.name} ({theme.absolute_path})"
            for theme in themes
        ]
        self._themes = dict(zip(labels, themes))
        if not self._themes:
            self._theme_picker.configure(values=[], state="disabled")
            self._theme_picker.set("")
            self._name.configure(text="No installed cursor themes found")
            self._path.configure(text="Install a cursor theme, then press Refresh.")
            self._sample_path.configure(text="Sample image: unavailable")
            self._clear_preview()
            self._active_badge.grid_remove()
            self._set_status("No cursor themes found.", "warn")
            self._update_apply_state()
            return

        values = list(self._themes)
        selected = previous if previous in self._themes else next(
            (label for label, theme in self._themes.items() if theme.name == self._current),
            values[0],
        )
        self._theme_picker.configure(values=values, state="readonly")
        self._theme_picker.set(selected)
        self._on_select(selected)

        summary = f"{len(values)} cursor theme{'s' if len(values) != 1 else ''} available."
        if self._preview_error:
            self._set_status(f"Could not load preview: {self._preview_error}", "error")
        elif self._current_error:
            self._set_status(
                f"{summary} Could not read the active theme: {self._current_error}", "warn"
            )
        else:
            self._set_status(summary)

    def _on_select(self, label: str) -> None:
        theme = self._themes.get(label)
        if theme is None:
            return
        self._name.configure(text=theme.name)
        self._path.configure(text=theme.absolute_path)
        self._sample_path.configure(text=f"Sample image: {theme.model_path or 'Unavailable'}")
        if theme.name == self._current:
            self._active_badge.grid(row=0, column=1, sticky="e", padx=(8, 0))
        else:
            self._active_badge.grid_remove()
        self._show_preview(theme)
        self._update_apply_state()

    def _clear_preview(self, text: str = "No preview available") -> None:
        self._preview.configure(image="", text=text)
        self._preview_image = None

    def _show_preview(self, theme: CursorData) -> None:
        had_preview_error = self._preview_error is not None
        self._preview_error = None
        self._clear_preview()
        if theme.model_path is None:
            return
        try:
            image = _load_cursor_preview(theme.model_path)
        except (OSError, RuntimeError, ValueError) as error:
            self._preview_error = str(error)
            self._clear_preview("Preview unavailable")
            self._set_status(f"Could not load preview: {error}", "error")
            return
        self._preview_image = ctk.CTkImage(
            light_image=image,
            dark_image=image,
            size=(_PREVIEW_SIZE, _PREVIEW_SIZE),
        )
        self._preview.configure(image=self._preview_image, text="")
        if had_preview_error and self._status.cget("text").startswith("Could not load preview"):
            self._set_status("")

    def _apply_theme(self) -> None:
        theme = self._selected_theme()
        if theme is None or str(self._apply_button.cget("state")) == "disabled":
            return
        all_users = self._all_users.get()
        if all_users and not messagebox.askyesno(
            "Apply cursor theme for all users",
            "Set this cursor theme in the GTK and XFCE configuration for every home "
            "directory under /home?\n\nExisting files will be backed up. GNOME settings "
            "will change only for this session.",
            icon="warning",
            parent=self._parent,
        ):
            return

        self._apply_button.configure(state="disabled", text="Applying…")
        self._set_status(f"Applying {theme.name}…")
        self._parent.update_idletasks()
        try:
            select_cursor_theme(theme, applyToAllUser=all_users)
        except (RuntimeError, ValueError, OSError) as error:
            self._set_status(f"Could not apply {theme.name}: {error}", "error")
            messagebox.showerror("Could not apply cursor theme", str(error), parent=self._parent)
            self._update_apply_state()
            return

        self._current = theme.name
        self._set_current(theme.name)
        self._on_select(self._theme_picker.get())
        scope = " for all users" if all_users else ""
        self._set_status(f"✓  Applied {theme.name}{scope}.", "ok")
        self._update_apply_state()


def create_cursor_tab(parent: ctk.CTkFrame) -> CursorThemeTab:
    return CursorThemeTab(parent)
