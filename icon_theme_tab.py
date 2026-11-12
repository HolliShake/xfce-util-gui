import io
from pathlib import Path
from tkinter import BooleanVar, messagebox
from xml.etree.ElementTree import ParseError

import cairocffi
import cairosvg
import customtkinter as ctk
from defusedxml.common import DefusedXmlException
from PIL import Image

from theme import IconData, get_available_icon_themes, get_icon_theme_name, select_icon_theme

# ── Design tokens (shared look with the GTK tab) ─────────────────────────────
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
_CARD_RADIUS = 14

# Preview: a 2x2 grid of sample icons. CTkImage handles HiDPI, so the image is
# drawn at its display size instead of being upscaled (which looked blurry).
_TILE = 72
_GAP = 8
_CANVAS = _GAP * 3 + _TILE * 2
_POSITIONS = ((_GAP, _GAP), (_GAP * 2 + _TILE, _GAP), (_GAP, _GAP * 2 + _TILE), (_GAP * 2 + _TILE, _GAP * 2 + _TILE))
_NO_PREVIEW = "No preview\navailable"


class IconThemeTab:
    def __init__(self, parent: ctk.CTkFrame) -> None:
        self._parent = parent
        self._themes: dict[str, IconData] = {}
        self._current: str | None = None
        self._current_error: str | None = None
        self._preview_image: ctk.CTkImage | None = None
        self._loading = False
        self._all_users = BooleanVar(master=parent, value=False)

        self._f_title = ctk.CTkFont(size=26, weight="bold")
        self._f_name = ctk.CTkFont(size=20, weight="bold")
        self._f_body = ctk.CTkFont(size=13)
        self._f_small = ctk.CTkFont(size=12)
        self._f_chip = ctk.CTkFont(size=12, weight="bold")
        self._f_mono = ctk.CTkFont(family="monospace", size=12)

        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1, minsize=280)

        self._build_header()
        self._build_picker()
        self._build_preview()
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
        # Solid tinted button: a transparent "outline" button repaints its rounded
        # corners from the parent color and falls back to blue theme hover colors.
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

    # ──────────────────────────────────────────────────────────────── header
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self._parent, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=_PAD, pady=(_PAD, 14))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header, text="Icon Theme", font=self._f_title, anchor="w").grid(
            row=0, column=0, sticky="w"
        )
        ctk.CTkLabel(
            header, text="Preview an installed icon theme before applying it.",
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
        self._picker = ctk.CTkComboBox(
            card, values=[], state="disabled", command=self._show_theme,
            height=38, corner_radius=10, border_width=1, border_color=_BORDER,
            fg_color=_SURFACE_ALT, text_color=_TEXT, font=self._f_body,
            button_color=_ACCENT, button_hover_color=_ACCENT_HOVER,
            dropdown_fg_color=_SURFACE, dropdown_hover_color=_ACCENT_TINT,
            dropdown_text_color=_TEXT, dropdown_font=self._f_body, bg_color=_SURFACE,
        )
        self._picker.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 16))

    # ─────────────────────────────────────────────────────────────- preview
    def _build_preview(self) -> None:
        card = self._card(2, sticky="nsew")
        card.grid_rowconfigure(1, weight=1)
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text="PREVIEW", font=self._f_chip, text_color=_MUTED, anchor="w").grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 0)
        )

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.grid(row=1, column=0, sticky="ew", padx=16, pady=14)  # centered vertically by the weighted row
        body.grid_columnconfigure(1, weight=1)

        # Inset preview tile
        side = _CANVAS + 24
        inset = ctk.CTkFrame(body, width=side, height=side, corner_radius=14, fg_color=_SURFACE_ALT)
        inset.grid(row=0, column=0, padx=(0, 20), sticky="n")
        inset.grid_propagate(False)
        self._preview = ctk.CTkLabel(
            inset, text=_NO_PREVIEW, text_color=_MUTED, font=self._f_small,
            justify="center", fg_color="transparent",
        )
        self._preview.place(relx=0.5, rely=0.5, anchor="center")

        # Info column
        info = ctk.CTkFrame(body, fg_color="transparent")
        info.grid(row=0, column=1, sticky="new")
        info.grid_columnconfigure(0, weight=1)

        title = ctk.CTkFrame(info, fg_color="transparent")
        title.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self._d_name = ctk.CTkLabel(title, text="—", font=self._f_name, anchor="w")
        self._d_name.grid(row=0, column=0, sticky="w")
        self._active_badge = self._chip(title, "● Active", width=72)
        self._active_badge.configure(fg_color=_OK_BG, text_color=_OK_TEXT)

        ctk.CTkLabel(info, text="PATH", font=self._f_chip, text_color=_MUTED, anchor="w").grid(
            row=1, column=0, sticky="w", pady=(0, 4)
        )
        path_box = ctk.CTkFrame(info, fg_color=_SURFACE_ALT, corner_radius=10)
        path_box.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        path_box.grid_columnconfigure(0, weight=1)
        self._d_path = ctk.CTkLabel(
            path_box, text="", text_color=_MUTED, anchor="w", justify="left",
            wraplength=300, font=self._f_mono,
        )
        self._d_path.grid(row=0, column=0, sticky="w", padx=(12, 6), pady=8)
        self._copy_button = self._tonal_button(
            path_box, "⧉  Copy", self._copy_path, width=88, height=28, bg=_SURFACE_ALT
        )
        self._copy_button.grid(row=0, column=1, padx=(0, 8), pady=6)

        ctk.CTkLabel(info, text="FOLDER SAMPLE", font=self._f_chip, text_color=_MUTED, anchor="w").grid(
            row=3, column=0, sticky="w", pady=(0, 4)
        )
        self._d_sample = ctk.CTkLabel(
            info, text="—", text_color=_MUTED, anchor="w", justify="left",
            wraplength=300, font=self._f_mono,
        )
        self._d_sample.grid(row=4, column=0, sticky="w")

        card.bind("<Configure>", self._on_card_resize)

    def _on_card_resize(self, event) -> None:
        wrap = max(180, event.width - (_CANVAS + 24) - 120)
        self._d_path.configure(wraplength=wrap)
        self._d_sample.configure(wraplength=wrap + 60)

    # ───────────────────────────────────────────────────────────────- footer
    def _build_options(self) -> None:
        card = self._card(3, pady=(0, 12))
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

    def _on_all_users_toggle(self) -> None:
        self._refresh_all_users_hint()
        self._update_apply_state()

    def _refresh_all_users_hint(self) -> None:
        if self._all_users.get():
            self._all_users_hint.configure(
                text="⚠  Updates GTK and XFCE icon settings in every directory under /home. "
                     "Existing files are backed up; elevated permissions may be required.",
                text_color=_WARN_TEXT,
            )
        else:
            self._all_users_hint.configure(
                text="Applies to your account only. Desktop settings change for this session.",
                text_color=_MUTED,
            )

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self._parent, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", padx=_PAD, pady=(0, _PAD))
        footer.grid_columnconfigure(0, weight=1)

        self._status = ctk.CTkLabel(
            footer, text="", anchor="w", justify="left", font=self._f_small, wraplength=480
        )
        self._status.grid(row=0, column=0, sticky="ew", padx=(2, 12))
        footer.bind("<Configure>", lambda e: self._status.configure(wraplength=max(200, e.width - 240)))

        self._apply_button = ctk.CTkButton(
            footer, text="Apply Icon Theme", width=172, height=42, corner_radius=12,
            font=ctk.CTkFont(size=14, weight="bold"), state="disabled",
            fg_color=_SURFACE_ALT, hover_color=_ACCENT_HOVER, text_color=("white", "white"),
            text_color_disabled=_MUTED, command=self._apply_theme,
        )
        self._apply_button.grid(row=0, column=1, sticky="e")

    def _bind_shortcuts(self) -> None:
        # Every tab binds on the same window, so only react while this tab is visible.
        top = self._parent.winfo_toplevel()
        top.bind("<Control-r>", lambda _e: self._shortcut(self._load_themes), add="+")
        top.bind("<Control-Return>", lambda _e: self._shortcut(self._apply_theme), add="+")

    def _shortcut(self, action) -> None:
        if self._parent.winfo_ismapped():
            action()

    # ─────────────────────────────────────────────────────────────── helpers
    def _set_status(self, text: str, kind: str = "info") -> None:
        color = {"ok": _OK_TEXT, "warn": _WARN_TEXT, "error": _ERR_TEXT}.get(kind, _MUTED)
        self._status.configure(text=text, text_color=color)

    def _selected_theme(self) -> IconData | None:
        return self._themes.get(self._picker.get())

    def _set_apply(self, enabled: bool, text: str) -> None:
        self._apply_button.configure(
            state="normal" if enabled else "disabled",
            text=text,
            fg_color=_ACCENT if enabled else _SURFACE_ALT,
        )

    def _update_apply_state(self) -> None:
        theme = self._selected_theme()
        if theme is None:
            self._set_apply(False, "Apply Icon Theme")
            return
        already = theme.name == self._current and not self._all_users.get()
        self._set_apply(not already, "Already Active" if already else "Apply Icon Theme")

    def _clear_preview(self, text: str = _NO_PREVIEW) -> None:
        self._preview.configure(image="", text=text)
        self._preview_image = None

    def _clear_info(self) -> None:
        self._d_name.configure(text="—")
        self._d_path.configure(text="")
        self._d_sample.configure(text="—")
        self._active_badge.grid_forget()

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

    # ──────────────────────────────────────────────────────────────- loading
    def _load_themes(self) -> None:
        if self._loading:
            return
        self._loading = True
        self._refresh_button.configure(state="disabled", text="⟳  Refreshing…")
        self._set_status("Loading icon themes…")
        self._parent.update_idletasks()
        try:
            self._load_themes_impl()
        finally:
            self._loading = False
            self._refresh_button.configure(state="normal", text="⟳  Refresh")

    def _load_themes_impl(self) -> None:
        previous = self._picker.get()
        try:
            self._current = get_icon_theme_name()
            self._current_error = None
        except RuntimeError as error:
            self._current = None
            self._current_error = str(error)
        self._set_current(self._current)

        try:
            themes = get_available_icon_themes()
        except RuntimeError as error:
            self._themes = {}
            self._picker.configure(values=[], state="disabled")
            self._picker.set("")
            self._clear_info()
            self._clear_preview()
            self._update_apply_state()
            self._set_status(f"Unable to load icon themes: {error}", "error")
            return

        self._themes = {theme.name: theme for theme in sorted(themes, key=lambda t: t.name.lower())}
        if not self._themes:
            self._picker.configure(values=[], state="disabled")
            self._picker.set("")
            self._clear_info()
            self._clear_preview()
            self._update_apply_state()
            self._set_status("No installed icon themes found.", "warn")
            return

        values = list(self._themes)
        selected = previous if previous in self._themes else self._current if self._current in self._themes else values[0]
        self._picker.configure(values=values, state="readonly")
        self._picker.set(selected)
        self._show_theme(selected)

        summary = f"{len(values)} icon theme{'s' if len(values) != 1 else ''} available."
        if self._current_error and not self._status.cget("text").startswith("Could not load preview"):
            self._set_status(f"{summary} Couldn't read the active theme: {self._current_error}", "warn")
        elif not self._status.cget("text").startswith("Could not load preview"):
            self._set_status(summary)

    # ─────────────────────────────────────────────────────────────- selection
    def _show_theme(self, name: str) -> None:
        theme = self._themes[name]
        self._d_name.configure(text=theme.name)
        self._d_path.configure(text=str(theme.absolute_path))
        self._d_sample.configure(text=str(theme.model_path or "Unavailable"))
        if theme.name == self._current:
            self._active_badge.grid(row=0, column=1, padx=(10, 0))
        else:
            self._active_badge.grid_forget()
        self._update_apply_state()

        self._clear_preview()
        self._set_status("")
        if not any(theme.sample_paths):
            return
        try:
            image = self._compose_preview(theme)
            self._preview_image = ctk.CTkImage(
                light_image=image, dark_image=image, size=(_CANVAS, _CANVAS)
            )
            self._preview.configure(image=self._preview_image, text="")
        except (OSError, ValueError, ParseError, DefusedXmlException, cairocffi.CairoError) as error:
            self._clear_preview("Preview\nunavailable")
            self._set_status(f"Could not load preview: {error}", "error")

    @staticmethod
    def _compose_preview(theme: IconData) -> Image.Image:
        preview = Image.new("RGBA", (_CANVAS, _CANVAS), (0, 0, 0, 0))
        for path_value, (x, y) in zip(theme.sample_paths, _POSITIONS):
            if path_value is None:
                continue
            path = Path(path_value)
            if path.suffix.lower() == ".svg":
                png = cairosvg.svg2png(
                    bytestring=path.read_bytes(), output_width=_TILE, output_height=_TILE
                )
                with Image.open(io.BytesIO(png)) as image:
                    image.load()
                    icon = image.convert("RGBA")
            else:
                with Image.open(path) as image:
                    image.load()
                    icon = image.convert("RGBA")
            icon.thumbnail((_TILE, _TILE))
            # centre smaller icons inside their tile
            preview.alpha_composite(
                icon, (x + (_TILE - icon.width) // 2, y + (_TILE - icon.height) // 2)
            )
        return preview

    # ───────────────────────────────────────────────────────────────── apply
    def _apply_theme(self) -> None:
        theme = self._selected_theme()
        if theme is None or str(self._apply_button.cget("state")) == "disabled":
            return
        all_users = self._all_users.get()
        if all_users and not messagebox.askyesno(
            "Apply icon theme for all users",
            "Set this icon theme in every directory under /home?\n\n"
            "Existing GTK and XFCE settings will be backed up. "
            "Elevated permissions may be required.",
            icon="warning",
            parent=self._parent,
        ):
            return
        self._set_apply(False, "Applying…")
        self._set_status(f"Applying {theme.name}…")
        self._parent.update_idletasks()
        try:
            select_icon_theme(theme, applyToAllUser=all_users)
        except (RuntimeError, ValueError, OSError) as error:
            self._set_status(f"Could not apply {theme.name}: {error}", "error")
            messagebox.showerror("Could not apply icon theme", str(error), parent=self._parent)
            self._update_apply_state()
            return
        self._current = theme.name
        self._set_current(theme.name)
        self._active_badge.grid(row=0, column=1, padx=(10, 0))
        scope = " for all users" if all_users else ""
        self._set_status(f"✓  Applied {theme.name}{scope}.", "ok")
        self._update_apply_state()


def create_icon_theme_tab(parent: ctk.CTkFrame) -> IconThemeTab:
    return IconThemeTab(parent)