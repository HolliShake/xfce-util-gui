import warnings
from collections import Counter
from tkinter import BooleanVar, messagebox

import customtkinter as ctk

from theme import ThemeData, get_available_themes, get_gtk_theme_name, select_gtk_theme

# ── Design tokens ────────────────────────────────────────────────────────────
# Every color is a (light, dark) tuple so the tab follows the appearance mode.
_ACCENT = ("#2563eb", "#3b82f6")
_ACCENT_HOVER = ("#1d4ed8", "#2563eb")
_ACCENT_TINT = ("#dbeafe", "#1f2f57")
_ACCENT_TINT_HOVER = ("#bfdbfe", "#29407a")
_ACCENT_TEXT = ("#1d4ed8", "#9bb8ff")

_SURFACE = ("#ffffff", "#1b1e25")  # cards
_SURFACE_ALT = ("#f3f5f8", "#252932")  # rows / inset fields
_BORDER = ("#e2e6ec", "#323845")
_TEXT = ("#111827", "#e8eaf0")
_MUTED = ("#667085", "#98a2b3")

_OK_BG = ("#dcfce7", "#12351f")
_OK_TEXT = ("#15803d", "#4ade80")
_WARN_BG = ("#fef3c7", "#3d2e00")
_WARN_TEXT = ("#b45309", "#fbbf24")
_ERR_TEXT = ("#dc2626", "#f87171")
_OFF_BG = ("#e8ebf0", "#2b303b")
_OFF_TEXT = ("#667085", "#8b95a7")

_PAD = 20
_CARD_RADIUS = 14

_TOOLKITS = (("GTK2", "gtk2"), ("GTK3", "gtk3"), ("GTK4", "gtk4"))
_EXTRAS = (("XFWM4", "xfwm4"), ("libAdwaita", "libAdwaita"))
_EXTRA_LABEL = {"XFWM4": "XFWM4", "libAdwaita": "libAdwaita CSS"}


class GtkThemeTab:
    def __init__(self, parent: ctk.CTkFrame) -> None:
        self._parent = parent
        self._themes: dict[str, ThemeData] = {}
        self._current: str | None = None
        self._current_error: str | None = None
        self._loading = False
        self._raw_open = False
        self._all_users = BooleanVar(master=parent, value=False)
        self._rows: dict[str, ctk.CTkLabel] = {}
        self._strip: dict[str, ctk.CTkLabel] = {}

        self._f_title = ctk.CTkFont(size=26, weight="bold")
        self._f_h2 = ctk.CTkFont(size=13, weight="bold")
        self._f_body = ctk.CTkFont(size=13)
        self._f_small = ctk.CTkFont(size=12)
        self._f_chip = ctk.CTkFont(size=12, weight="bold")
        self._f_mono = ctk.CTkFont(family="monospace", size=12)

        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1, minsize=330)

        self._build_header()
        self._build_picker()
        self._build_details()
        self._build_options()
        self._build_footer()
        self._bind_shortcuts()
        self._load_themes()

    # ──────────────────────────────────────────────────────────── factories
    def _card(self, row: int, *, pady=(0, 12), sticky="ew") -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            self._parent, fg_color=_SURFACE, border_width=1, border_color=_BORDER,
            corner_radius=_CARD_RADIUS,
        )
        card.grid(row=row, column=0, sticky=sticky, padx=_PAD, pady=pady)
        card.grid_columnconfigure(0, weight=1)
        return card

    def _tonal_button(self, master, text: str, command, *, width=100, height=32, bg="transparent"):
        """Solid, softly tinted button.

        Used instead of an outlined button: a transparent fg_color has to repaint
        its rounded corners from the parent color, which shows artifacts on cards,
        and an outline without hover/border colors falls back to the blue theme.
        """
        return ctk.CTkButton(
            master, text=text, command=command, width=width, height=height,
            corner_radius=8, border_width=0, bg_color=bg, font=self._f_chip,
            fg_color=_ACCENT_TINT, hover_color=_ACCENT_TINT_HOVER,
            text_color=_ACCENT_TEXT, text_color_disabled=_MUTED,
        )

    def _chip(self, master, text="", *, width=0, bg="transparent") -> ctk.CTkLabel:
        return ctk.CTkLabel(
            master, text=text, width=width, height=24, corner_radius=12,
            font=self._f_chip, fg_color=_OFF_BG, text_color=_OFF_TEXT, bg_color=bg,
        )

    @staticmethod
    def _style_chip(chip: ctk.CTkLabel, on: bool, text: str) -> None:
        chip.configure(
            text=text,
            fg_color=_OK_BG if on else _OFF_BG,
            text_color=_OK_TEXT if on else _OFF_TEXT,
        )

    # ──────────────────────────────────────────────────────────────── header
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self._parent, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=_PAD, pady=(_PAD, 14))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header, text="GTK Theme", font=self._f_title, anchor="w").grid(
            row=0, column=0, sticky="w"
        )
        ctk.CTkLabel(
            header, text="Pick an installed theme and apply it to your desktop session.",
            font=self._f_small, text_color=_MUTED, anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.grid(row=0, column=1, rowspan=2, sticky="e")
        self._current_chip = self._chip(right, "Active: loading…")
        self._current_chip.grid(row=0, column=0, padx=(0, 10))
        self._refresh_button = self._tonal_button(
            right, "⟳  Refresh", self._load_themes, width=104, height=34
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

    # ───────────────────────────────────────────────────────────────- picker
    def _build_picker(self) -> None:
        card = self._card(1)
        ctk.CTkLabel(card, text="THEME", font=self._f_chip, text_color=_MUTED, anchor="w").grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 4)
        )
        self._theme_picker = ctk.CTkComboBox(
            card, values=[], state="disabled", command=self._on_select,
            height=38, corner_radius=10, border_width=1, border_color=_BORDER,
            fg_color=_SURFACE_ALT, text_color=_TEXT, font=self._f_body,
            button_color=_ACCENT, button_hover_color=_ACCENT_HOVER,
            dropdown_fg_color=_SURFACE, dropdown_hover_color=_ACCENT_TINT,
            dropdown_text_color=_TEXT, dropdown_font=self._f_body, bg_color=_SURFACE,
        )
        self._theme_picker.grid(row=1, column=0, sticky="ew", padx=16)

        strip = ctk.CTkFrame(card, fg_color="transparent")
        strip.grid(row=2, column=0, sticky="w", padx=16, pady=(10, 14))
        for col, (key, _attr) in enumerate(_TOOLKITS):
            chip = self._chip(strip, f"✕ {key}", width=76, bg=_SURFACE)
            chip.grid(row=0, column=col, padx=(0, 6))
            self._strip[key] = chip

    def _update_strip(self, theme: ThemeData | None) -> None:
        for key, attr in _TOOLKITS:
            on = bool(theme and getattr(theme, attr, False))
            self._style_chip(self._strip[key], on, f"{'✓' if on else '✕'} {key}")

    # ──────────────────────────────────────────────────────────────- details
    def _build_details(self) -> None:
        card = self._card(2, sticky="nsew")
        card.grid_rowconfigure(1, weight=1)
        self._details_card = card

        ctk.CTkLabel(card, text="DETAILS", font=self._f_chip, text_color=_MUTED, anchor="w").grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 0)
        )
        scroll = ctk.CTkScrollableFrame(
            card, height=260, corner_radius=0, fg_color="transparent",
            scrollbar_fg_color="transparent", scrollbar_button_color=_BORDER,
            scrollbar_button_hover_color=_MUTED,
        )
        scroll.grid(row=1, column=0, sticky="nsew", padx=(8, 4), pady=(4, 8))
        scroll.grid_columnconfigure(0, weight=1)

        self._message = ctk.CTkLabel(
            scroll, text="", text_color=_MUTED, justify="left", anchor="w",
            font=self._f_body, wraplength=520,
        )

        content = ctk.CTkFrame(scroll, fg_color="transparent")
        content.grid_columnconfigure(0, weight=1)
        self._content = content

        # Title row
        title = ctk.CTkFrame(content, fg_color="transparent")
        title.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self._d_name = ctk.CTkLabel(
            title, text="", font=ctk.CTkFont(size=18, weight="bold"), anchor="w"
        )
        self._d_name.grid(row=0, column=0, sticky="w")
        self._active_badge = self._chip(title, "● Active", width=72)
        self._style_chip(self._active_badge, True, "● Active")

        # Path field + copy
        path_box = ctk.CTkFrame(content, fg_color=_SURFACE_ALT, corner_radius=10)
        path_box.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        path_box.grid_columnconfigure(0, weight=1)
        self._d_path = ctk.CTkLabel(
            path_box, text="", text_color=_MUTED, anchor="w", justify="left",
            wraplength=420, font=self._f_mono,
        )
        self._d_path.grid(row=0, column=0, sticky="w", padx=(12, 6), pady=8)
        self._copy_button = self._tonal_button(
            path_box, "⧉  Copy", self._copy_path, width=88, height=28, bg=_SURFACE_ALT
        )
        self._copy_button.grid(row=0, column=1, padx=(0, 8), pady=6)

        # Extras (GTK 2/3/4 are already shown as chips under the picker)
        extras = ctk.CTkFrame(content, fg_color="transparent")
        extras.grid(row=2, column=0, sticky="w", pady=(0, 8))
        for col, (key, _attr) in enumerate(_EXTRAS):
            chip = self._chip(extras, width=140, bg=_SURFACE)
            chip.grid(row=0, column=col, padx=(0, 6))
            self._rows[key] = chip

        # Icon / cursor
        meta_row = 3
        meta = ctk.CTkFrame(content, fg_color=_SURFACE_ALT, corner_radius=10)
        meta.grid(row=meta_row, column=0, sticky="ew")
        meta.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(meta, text="Icon theme", anchor="w", font=self._f_h2, width=100).grid(
            row=0, column=0, padx=(12, 4), pady=(8, 2), sticky="w"
        )
        self._d_icon = ctk.CTkLabel(meta, text="", anchor="w", text_color=_MUTED, font=self._f_body)
        self._d_icon.grid(row=0, column=1, sticky="ew", pady=(8, 2))
        ctk.CTkLabel(meta, text="Cursor theme", anchor="w", font=self._f_h2, width=100).grid(
            row=1, column=0, padx=(12, 4), pady=(2, 8), sticky="w"
        )
        self._d_cursor = ctk.CTkLabel(meta, text="", anchor="w", text_color=_MUTED, font=self._f_body)
        self._d_cursor.grid(row=1, column=1, sticky="ew", pady=(2, 8))

        # Warnings
        self._warn_row = meta_row + 1
        self._warn_frame = ctk.CTkFrame(content, fg_color=_WARN_BG, corner_radius=10)
        self._warn_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self._warn_frame, text="⚠  Warnings", text_color=_WARN_TEXT, anchor="w", font=self._f_h2
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 0))
        self._warn_text = ctk.CTkLabel(
            self._warn_frame, text="", anchor="w", justify="left", font=self._f_small,
            text_color=_TEXT, wraplength=480,
        )
        self._warn_text.grid(row=1, column=0, sticky="w", padx=12, pady=(2, 10))

        # Raw details
        self._raw_toggle_row = meta_row + 2
        self._raw_toggle = ctk.CTkButton(
            content, text="▸  Raw details", anchor="w", width=120, height=28,
            corner_radius=8, border_width=0, fg_color="transparent", bg_color=_SURFACE,
            hover_color=_SURFACE_ALT, text_color=_MUTED, font=self._f_small,
            command=self._toggle_raw,
        )
        self._raw_toggle.grid(row=self._raw_toggle_row, column=0, sticky="w", pady=(10, 0))
        self._raw = ctk.CTkTextbox(
            content, height=120, wrap="word", corner_radius=10, border_width=0,
            fg_color=_SURFACE_ALT, text_color=_TEXT, font=ctk.CTkFont(family="monospace", size=11),
            scrollbar_button_color=_BORDER, scrollbar_button_hover_color=_MUTED,
        )
        self._raw.configure(state="disabled")

        card.bind("<Configure>", self._on_card_resize)

    def _on_card_resize(self, event) -> None:
        width = max(260, event.width - 70)
        self._message.configure(wraplength=width)
        self._d_path.configure(wraplength=max(200, width - 110))
        self._warn_text.configure(wraplength=max(200, width - 30))

    def _show_message(self, text: str) -> None:
        self._update_strip(None)
        self._content.grid_forget()
        self._message.configure(text=text)
        self._message.grid(row=0, column=0, sticky="w", padx=8, pady=8)

    def _render_details(self, theme: ThemeData, notes: list[str] | None = None) -> None:
        self._message.grid_forget()
        self._content.grid(row=0, column=0, sticky="nsew", padx=6, pady=4)

        self._d_name.configure(text=theme.name)
        if theme.name == self._current:
            self._active_badge.grid(row=0, column=1, padx=(10, 0))
        else:
            self._active_badge.grid_forget()
        self._d_path.configure(text=str(theme.absolute_path))
        self._d_icon.configure(text=theme.icon or "Not specified")
        self._d_cursor.configure(text=theme.cursor or "Not specified")

        for key, attr in _EXTRAS:
            on = bool(getattr(theme, attr, False))
            self._style_chip(self._rows[key], on, f"{'✓' if on else '✕'} {_EXTRA_LABEL[key]}")

        if notes:
            self._warn_text.configure(text="\n".join(f"•  {n}" for n in notes))
            self._warn_frame.grid(row=self._warn_row, column=0, sticky="ew", pady=(8, 0))
        else:
            self._warn_frame.grid_forget()

        self._raw.configure(state="normal")
        self._raw.delete("1.0", "end")
        self._raw.insert("1.0", str(theme))
        self._raw.configure(state="disabled")

    def _toggle_raw(self) -> None:
        self._raw_open = not self._raw_open
        if self._raw_open:
            self._raw_toggle.configure(text="▾  Raw details")
            self._raw.grid(row=self._raw_toggle_row + 1, column=0, sticky="ew", pady=(4, 0))
        else:
            self._raw_toggle.configure(text="▸  Raw details")
            self._raw.grid_forget()

    def _copy_path(self) -> None:
        theme = self._selected_theme()
        if theme is None:
            return
        top = self._parent.winfo_toplevel()
        top.clipboard_clear()
        top.clipboard_append(str(theme.absolute_path))
        top.update()  # keeps the clipboard content alive on X11 after focus changes
        self._copy_button.configure(
            text="✓  Copied", fg_color=_OK_BG, hover_color=_OK_BG, text_color=_OK_TEXT
        )
        self._parent.after(1500, self._reset_copy_button)

    def _reset_copy_button(self) -> None:
        try:
            self._copy_button.configure(
                text="⧉  Copy", fg_color=_ACCENT_TINT, hover_color=_ACCENT_TINT_HOVER,
                text_color=_ACCENT_TEXT,
            )
        except Exception:  # widget may be gone if the tab was closed
            pass

    # ──────────────────────────────────────────────────────────────- options
    def _build_options(self) -> None:
        card = self._card(3)
        self._all_users_switch = ctk.CTkSwitch(
            card, text="Also install for all users in /home", variable=self._all_users,
            command=self._on_all_users_toggle, font=self._f_body, bg_color=_SURFACE,
            progress_color=_ACCENT, button_hover_color=_ACCENT_HOVER,
            switch_width=40, switch_height=20,
        )
        self._all_users_switch.grid(row=0, column=0, sticky="w", padx=16, pady=(14, 4))
        self._hint = ctk.CTkLabel(
            card, text="", text_color=_MUTED, justify="left", anchor="w",
            font=self._f_small, wraplength=600,
        )
        self._hint.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))
        card.bind("<Configure>", lambda e: self._hint.configure(wraplength=max(200, e.width - 40)))
        self._refresh_hint()

    def _on_all_users_toggle(self) -> None:
        self._refresh_hint()
        self._update_apply_state()

    def _refresh_hint(self) -> None:
        if self._all_users.get():
            self._hint.configure(
                text="⚠  Overrides will be written to every home under /home. Existing files "
                     "are backed up and elevated permissions may be required.",
                text_color=_WARN_TEXT,
            )
        else:
            self._hint.configure(
                text="Applies to your account only. Desktop settings change for this session.",
                text_color=_MUTED,
            )

    # ───────────────────────────────────────────────────────────────- footer
    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self._parent, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", padx=_PAD, pady=(0, _PAD))
        footer.grid_columnconfigure(0, weight=1)

        self._status = ctk.CTkLabel(
            footer, text="", anchor="w", justify="left", font=self._f_small, wraplength=480
        )
        self._status.grid(row=0, column=0, sticky="ew", padx=(2, 12))
        footer.bind("<Configure>", lambda e: self._status.configure(wraplength=max(200, e.width - 220)))

        self._apply_button = ctk.CTkButton(
            footer, text="Apply Theme", width=156, height=42, corner_radius=12,
            font=ctk.CTkFont(size=14, weight="bold"), state="disabled",
            fg_color=_SURFACE_ALT, hover_color=_ACCENT_HOVER, text_color=("white", "white"),
            text_color_disabled=_MUTED, command=self._apply_theme,
        )
        self._apply_button.grid(row=0, column=1, sticky="e")

    def _bind_shortcuts(self) -> None:
        top = self._parent.winfo_toplevel()
        top.bind("<Control-r>", lambda _e: self._load_themes(), add="+")
        top.bind("<Control-Return>", lambda _e: self._apply_theme(), add="+")

    # ─────────────────────────────────────────────────────────────── helpers
    def _set_status(self, text: str, kind: str = "info") -> None:
        color = {"ok": _OK_TEXT, "warn": _WARN_TEXT, "error": _ERR_TEXT}.get(kind, _MUTED)
        self._status.configure(text=text, text_color=color)

    def _selected_theme(self) -> ThemeData | None:
        return self._themes.get(self._theme_picker.get())

    def _set_apply(self, enabled: bool, text: str) -> None:
        self._apply_button.configure(
            state="normal" if enabled else "disabled",
            text=text,
            fg_color=_ACCENT if enabled else _SURFACE_ALT,
        )

    def _update_apply_state(self) -> None:
        theme = self._selected_theme()
        if theme is None:
            self._set_apply(False, "Apply Theme")
            return
        already = theme.name == self._current and not self._all_users.get()
        self._set_apply(not already, "Already Active" if already else "Apply Theme")

    # ──────────────────────────────────────────────────────────────- loading
    def _load_themes(self) -> None:
        if self._loading:
            return
        self._loading = True
        self._refresh_button.configure(state="disabled", text="⟳  Refreshing…")
        self._set_status("Loading themes…")
        self._parent.update_idletasks()
        try:
            self._load_themes_impl()
        finally:
            self._loading = False
            self._refresh_button.configure(state="normal", text="⟳  Refresh")

    def _load_themes_impl(self) -> None:
        previous = self._theme_picker.get() if self._themes else None

        try:
            self._current = get_gtk_theme_name()
            self._current_error = None
        except RuntimeError as error:
            self._current = None
            self._current_error = str(error)
        self._set_current(self._current)

        try:
            themes = get_available_themes()
        except RuntimeError as error:
            self._themes = {}
            self._theme_picker.configure(values=[], state="disabled")
            self._theme_picker.set("")
            self._show_message(f"Unable to load themes:\n{error}")
            self._set_status("Could not load themes. Press Refresh to retry.", "error")
            self._update_apply_state()
            return

        usable = sorted(
            (t for t in themes if t.gtk2 or t.gtk3 or t.gtk4), key=lambda t: t.name.lower()
        )
        counts = Counter(t.name for t in usable)

        def label(t: ThemeData) -> str:
            # Path is only added when two themes share a name.
            return t.name if counts[t.name] == 1 else f"{t.name} ({t.absolute_path})"

        self._themes = {label(t): t for t in usable}
        if not self._themes:
            self._theme_picker.configure(values=[], state="disabled")
            self._theme_picker.set("")
            self._show_message("No installed GTK themes found.\n\nInstall a theme, then press Refresh.")
            self._set_status("No themes found.", "warn")
            self._update_apply_state()
            return

        values = list(self._themes)
        selected = (
            previous if previous in self._themes
            else next((l for l, t in self._themes.items() if t.name == self._current), values[0])
        )
        self._theme_picker.configure(values=values, state="readonly")
        self._theme_picker.set(selected)
        self._on_select(selected)

        summary = f"{len(values)} theme{'s' if len(values) != 1 else ''} available."
        if self._current_error:
            self._set_status(f"{summary} Couldn't read the active theme: {self._current_error}", "warn")
        else:
            self._set_status(summary)

    def _on_select(self, label: str) -> None:
        theme = self._themes[label]
        self._update_strip(theme)
        self._render_details(theme)
        self._update_apply_state()

    # ───────────────────────────────────────────────────────────────── apply
    def _apply_theme(self) -> None:
        theme = self._selected_theme()
        if theme is None or str(self._apply_button.cget("state")) == "disabled":
            return
        all_users = self._all_users.get()
        if all_users and not messagebox.askyesno(
            "Apply for all users",
            "Install GTK overrides in every home under /home?\n\n"
            "Existing files will be backed up. This may require elevated permissions. "
            "Desktop settings only change for this session.",
            icon="warning",
            parent=self._parent,
        ):
            return

        self._set_apply(False, "Applying…")
        self._set_status(f"Applying {theme.name}…")
        self._parent.update_idletasks()

        caught: list[warnings.WarningMessage] = []
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", UserWarning)
                select_gtk_theme(theme, applyToAllUser=all_users)
        except (RuntimeError, ValueError, OSError) as error:
            extra = "\n".join(str(item.message) for item in caught)
            self._set_status(f"Could not apply {theme.name}: {error}", "error")
            messagebox.showerror(
                "Could not apply theme", f"{error}\n{extra}".strip(), parent=self._parent
            )
            self._update_apply_state()
            return

        self._current = theme.name
        self._set_current(theme.name)
        notes = [str(item.message) for item in caught]
        self._render_details(theme, notes)
        if notes:
            self._set_status(f"Applied {theme.name} with {len(notes)} warning(s). See details.", "warn")
        else:
            self._set_status(f"✓  Applied {theme.name}.", "ok")
        self._update_apply_state()