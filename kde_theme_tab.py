import logging
from collections import Counter
from tkinter import BooleanVar, messagebox

import customtkinter as ctk

from scrollable_dropdown import ScrollableComboBox
from theme import (
    KdeThemeData,
    get_available_kde_themes,
    get_kde_theme_name,
    select_kde_theme,
)

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
_LOGGER = logging.getLogger(__name__)


class KdeThemeTab:
    def __init__(self, parent: ctk.CTkFrame) -> None:
        self._parent = parent
        self._themes: dict[str, KdeThemeData] = {}
        self._current: str | None = None
        self._current_error: str | None = None
        self._loading = False
        self._all_users = BooleanVar(master=parent, value=False)

        self._f_title = ctk.CTkFont(size=26, weight="bold")
        self._f_name = ctk.CTkFont(size=20, weight="bold")
        self._f_body = ctk.CTkFont(size=13)
        self._f_small = ctk.CTkFont(size=12)
        self._f_chip = ctk.CTkFont(size=12, weight="bold")
        self._f_mono = ctk.CTkFont(family="monospace", size=12)

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
            self._parent,
            fg_color=_SURFACE,
            border_width=1,
            border_color=_BORDER,
            corner_radius=14,
        )
        card.grid(row=row, column=0, sticky=sticky, padx=_PAD, pady=(0, 12))
        card.grid_columnconfigure(0, weight=1)
        return card

    def _chip(self, master, text: str) -> ctk.CTkLabel:
        return ctk.CTkLabel(
            master,
            text=text,
            height=24,
            corner_radius=12,
            font=self._f_chip,
            fg_color=_OFF_BG,
            text_color=_OFF_TEXT,
        )

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self._parent, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=_PAD, pady=(_PAD, 14))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header, text="KDE Theme", font=self._f_title, anchor="w"
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="Browse and apply installed KDE Plasma global themes.",
            font=self._f_small,
            text_color=_MUTED,
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.grid(row=0, column=1, rowspan=2, sticky="e")
        self._current_chip = self._chip(right, "Active: loading…")
        self._current_chip.grid(row=0, column=0, padx=(0, 10))
        self._refresh_button = ctk.CTkButton(
            right,
            text="⟳  Refresh",
            width=104,
            height=34,
            corner_radius=8,
            border_width=0,
            font=self._f_chip,
            fg_color=_ACCENT_TINT,
            hover_color=_ACCENT_TINT_HOVER,
            text_color=_ACCENT_TEXT,
            command=self._load_themes,
        )
        self._refresh_button.grid(row=0, column=1)

    def _set_current(self, package_id: str | None) -> None:
        if package_id:
            self._current_chip.configure(
                text=f"●  Active: {package_id}",
                fg_color=_OK_BG,
                text_color=_OK_TEXT,
            )
        else:
            self._current_chip.configure(
                text="Active KDE theme unknown",
                fg_color=_OFF_BG,
                text_color=_OFF_TEXT,
            )

    def _build_picker(self) -> None:
        card = self._card(1)
        ctk.CTkLabel(
            card,
            text="KDE GLOBAL THEME",
            font=self._f_chip,
            text_color=_MUTED,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 4))
        self._theme_picker = ScrollableComboBox(
            card,
            values=[],
            state="disabled",
            command=self._on_select,
            height=38,
            corner_radius=10,
            border_width=1,
            border_color=_BORDER,
            fg_color=_SURFACE_ALT,
            text_color=_TEXT,
            font=self._f_body,
            button_color=_ACCENT,
            button_hover_color=_ACCENT_HOVER,
            dropdown_fg_color=_SURFACE,
            dropdown_hover_color=_ACCENT_TINT,
            dropdown_text_color=_TEXT,
            dropdown_font=self._f_body,
            bg_color=_SURFACE,
        )
        self._theme_picker.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))

    def _build_details(self) -> None:
        card = self._card(2, sticky="nsew")
        ctk.CTkLabel(
            card,
            text="SELECTED THEME",
            font=self._f_chip,
            text_color=_MUTED,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 4))

        self._name = ctk.CTkLabel(
            card, text="—", font=self._f_name, anchor="w", justify="left"
        )
        self._name.grid(row=1, column=0, sticky="w", padx=16)
        self._active_badge = self._chip(card, "● Active")
        self._active_badge.grid(row=1, column=1, sticky="e", padx=16)
        self._active_badge.configure(fg_color=_OK_BG, text_color=_OK_TEXT)
        self._active_badge.grid_remove()

        ctk.CTkLabel(
            card, text="PACKAGE ID", font=self._f_chip, text_color=_MUTED, anchor="w"
        ).grid(row=2, column=0, sticky="w", padx=16, pady=(16, 4))
        self._package_id = ctk.CTkLabel(
            card, text="", font=self._f_mono, text_color=_MUTED, anchor="w"
        )
        self._package_id.grid(row=3, column=0, columnspan=2, sticky="ew", padx=16)

        ctk.CTkLabel(
            card, text="DESCRIPTION", font=self._f_chip, text_color=_MUTED, anchor="w"
        ).grid(row=4, column=0, sticky="w", padx=16, pady=(14, 4))
        self._description = ctk.CTkLabel(
            card,
            text="",
            font=self._f_body,
            text_color=_TEXT,
            justify="left",
            anchor="w",
            wraplength=560,
        )
        self._description.grid(row=5, column=0, columnspan=2, sticky="ew", padx=16)

        ctk.CTkLabel(
            card, text="PATH", font=self._f_chip, text_color=_MUTED, anchor="w"
        ).grid(row=6, column=0, sticky="w", padx=16, pady=(14, 4))
        self._path = ctk.CTkLabel(
            card,
            text="",
            font=self._f_mono,
            text_color=_MUTED,
            justify="left",
            anchor="w",
            wraplength=560,
        )
        self._path.grid(row=7, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 16))
        card.bind("<Configure>", lambda event: self._on_details_resize(event.width))

    def _on_details_resize(self, width: int) -> None:
        wraplength = max(200, width - 40)
        self._description.configure(wraplength=wraplength)
        self._path.configure(wraplength=wraplength)

    def _build_options(self) -> None:
        card = self._card(3)
        self._all_users_switch = ctk.CTkSwitch(
            card,
            text="Also apply to all users in /home",
            variable=self._all_users,
            command=self._on_all_users_toggle,
            font=self._f_body,
            bg_color=_SURFACE,
            progress_color=_ACCENT,
            button_hover_color=_ACCENT_HOVER,
            switch_width=40,
            switch_height=20,
        )
        self._all_users_switch.grid(row=0, column=0, sticky="w", padx=16, pady=(14, 4))
        self._all_users_hint = ctk.CTkLabel(
            card,
            text="",
            text_color=_MUTED,
            justify="left",
            anchor="w",
            font=self._f_small,
            wraplength=600,
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
                text="⚠  Updates kdeglobals for homes under /home and backs up existing files. "
                     "The theme must be installed system-wide. Other users' running KDE "
                     "sessions will not change live; authentication may be requested.",
                text_color=_WARN_TEXT,
            )
        else:
            self._all_users_hint.configure(
                text="Applies to your KDE user and current session.",
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
            footer,
            text="",
            anchor="w",
            justify="left",
            font=self._f_small,
            wraplength=440,
        )
        self._status.grid(row=0, column=0, sticky="ew", padx=(2, 12))
        footer.bind(
            "<Configure>",
            lambda event: self._status.configure(wraplength=max(200, event.width - 220)),
        )
        self._apply_button = ctk.CTkButton(
            footer,
            text="Apply KDE Theme",
            width=190,
            height=42,
            corner_radius=12,
            font=ctk.CTkFont(size=14, weight="bold"),
            state="disabled",
            fg_color=_SURFACE_ALT,
            hover_color=_ACCENT_HOVER,
            text_color=("white", "white"),
            text_color_disabled=_MUTED,
            command=self._apply_theme,
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

    def _selected_theme(self) -> KdeThemeData | None:
        return self._themes.get(self._theme_picker.get())

    def _update_apply_state(self) -> None:
        theme = self._selected_theme()
        already_active = (
            theme is not None
            and theme.package_id == self._current
            and not self._all_users.get()
        )
        if already_active:
            self._apply_button.configure(
                state="disabled", text="Already Active", fg_color=_SURFACE_ALT
            )
        elif theme is not None:
            self._apply_button.configure(
                state="normal", text="Apply KDE Theme", fg_color=_ACCENT
            )
        else:
            self._apply_button.configure(
                state="disabled", text="Apply KDE Theme", fg_color=_SURFACE_ALT
            )

    def _load_themes(self) -> None:
        if self._loading:
            return
        self._loading = True
        self._refresh_button.configure(state="disabled", text="⟳  Refreshing…")
        self._set_status("Loading KDE Plasma themes…")
        self._parent.update_idletasks()
        try:
            self._load_themes_impl()
        finally:
            self._loading = False
            self._refresh_button.configure(state="normal", text="⟳  Refresh")

    def _load_themes_impl(self) -> None:
        previous = self._theme_picker.get() if self._themes else None
        try:
            self._current = get_kde_theme_name()
            self._current_error = None
        except RuntimeError as error:
            self._current = None
            self._current_error = str(error)
        self._set_current(self._current)

        try:
            themes = get_available_kde_themes()
        except RuntimeError as error:
            self._themes = {}
            self._theme_picker.configure(values=[], state="disabled")
            self._theme_picker.set("")
            self._show_empty_state("Unable to load KDE themes", str(error))
            self._set_status("Could not load KDE themes. Press Refresh to retry.", "error")
            self._update_apply_state()
            return

        counts = Counter(theme.name for theme in themes)
        labels = [
            theme.name if counts[theme.name] == 1 else f"{theme.name} ({theme.package_id})"
            for theme in themes
        ]
        self._themes = dict(zip(labels, themes))
        if not self._themes:
            detail = "Install a KDE Plasma global theme, then press Refresh."
            if self._current_error:
                detail += f"\n\n{self._current_error}"
            self._theme_picker.configure(values=[], state="disabled")
            self._theme_picker.set("")
            self._show_empty_state("No KDE Plasma themes found", detail)
            self._set_status("No KDE Plasma themes found.", "warn")
            self._update_apply_state()
            return

        values = list(self._themes)
        selected = previous if previous in self._themes else next(
            (
                label
                for label, theme in self._themes.items()
                if theme.package_id == self._current
            ),
            values[0],
        )
        self._theme_picker.configure(values=values, state="readonly")
        self._theme_picker.set(selected)
        self._on_select(selected)

        summary = f"{len(values)} KDE global theme{'s' if len(values) != 1 else ''} available."
        if self._current_error:
            self._set_status(
                f"{summary} Could not read the active KDE theme: {self._current_error}",
                "warn",
            )
        else:
            self._set_status(summary)

    def _show_empty_state(self, title: str, detail: str) -> None:
        self._name.configure(text=title)
        self._package_id.configure(text="")
        self._description.configure(text=detail)
        self._path.configure(text="")
        self._active_badge.grid_remove()

    def _on_select(self, label: str) -> None:
        theme = self._themes.get(label)
        if theme is None:
            return
        self._name.configure(text=theme.name)
        self._package_id.configure(text=theme.package_id)
        self._description.configure(
            text=theme.description or "No description provided by this theme."
        )
        self._path.configure(text=theme.absolute_path)
        if theme.package_id == self._current:
            self._active_badge.grid(row=1, column=1, sticky="e", padx=16)
        else:
            self._active_badge.grid_remove()
        self._update_apply_state()

    def _apply_theme(self) -> None:
        theme = self._selected_theme()
        if theme is None or str(self._apply_button.cget("state")) == "disabled":
            return
        apply_to_all_users = self._all_users.get()
        if apply_to_all_users and not messagebox.askyesno(
            "Apply KDE theme for all users",
            "Set this KDE Plasma global theme for every home directory under /home?\n\n"
            "The theme must be installed under /usr/share/plasma/look-and-feel or "
            "/usr/local/share/plasma/look-and-feel. Existing kdeglobals files will be "
            "backed up. Other users' running sessions will not change live.",
            icon="warning",
            parent=self._parent,
        ):
            return
        self._apply_button.configure(state="disabled", text="Applying…")
        self._set_status(f"Applying {theme.name}…")
        self._parent.update_idletasks()
        try:
            select_kde_theme(theme, applyToAllUser=apply_to_all_users)
        except (RuntimeError, ValueError, OSError) as error:
            _LOGGER.exception("Could not apply KDE theme %s", theme.package_id)
            if apply_to_all_users:
                message = (
                    "Could not apply this theme for all users. Check that it is installed "
                    "system-wide and that Polkit authorization succeeded."
                )
            elif isinstance(error, (RuntimeError, ValueError)):
                message = str(error)
            else:
                message = "Could not apply this KDE theme. Check KDE Plasma availability and retry."
            self._set_status(message, "error")
            messagebox.showerror("Could not apply KDE theme", message, parent=self._parent)
            self._update_apply_state()
            return

        self._current = theme.package_id
        self._set_current(theme.package_id)
        self._on_select(self._theme_picker.get())
        scope = " for all users" if apply_to_all_users else " to the current KDE user"
        self._set_status(f"✓  Applied {theme.name}{scope}.", "ok")
        self._update_apply_state()


def create_kde_theme_tab(parent: ctk.CTkFrame) -> KdeThemeTab:
    return KdeThemeTab(parent)
