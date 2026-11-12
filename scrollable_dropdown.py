import sys
import tkinter
from typing import Any

import customtkinter as ctk


_UNSET = object()


def _calculate_popup_geometry(
    root_bounds: tuple[int, int, int, int],
    screen_bounds: tuple[int, int],
    widget_bounds: tuple[int, int, int, int],
    desired_height: int,
) -> tuple[int, int, int, int]:
    """Return (x, y, width, height) in screen pixels for a popup that stays
    inside both the root window and the screen, preferring to open below."""
    root_x, root_y, root_width, root_height = root_bounds
    screen_width, screen_height = screen_bounds
    widget_x, widget_y, widget_width, widget_height = widget_bounds
    left = max(0, root_x)
    top = max(0, root_y)
    right = min(screen_width, root_x + root_width)
    bottom = min(screen_height, root_y + root_height)
    if right <= left:
        left, right = 0, screen_width
    if bottom <= top:
        top, bottom = 0, screen_height

    popup_width = max(1, min(widget_width, right - left))
    popup_x = min(max(widget_x, left), right - popup_width)
    below = max(0, bottom - (widget_y + widget_height))
    above = max(0, widget_y - top)

    if below >= desired_height:
        popup_height = desired_height
        popup_y = widget_y + widget_height
    elif above >= desired_height:
        popup_height = desired_height
        popup_y = widget_y - desired_height
    elif above > below:
        popup_height = above
        popup_y = widget_y - above
    else:
        popup_height = below
        popup_y = widget_y + widget_height

    popup_height = max(1, popup_height)
    popup_y = min(max(popup_y, top), bottom - popup_height)
    return popup_x, popup_y, popup_width, popup_height


def _rounded_points(
    x1: float, y1: float, x2: float, y2: float, radius: float
) -> list[float]:
    """Polygon points that draw a rounded rectangle when used with smooth=True."""
    r = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]


class ScrollableComboBox(ctk.CTkComboBox):
    """A CustomTkinter combo box with a root-bounded, scrollable popup.

    The popup is a rounded frame holding a lightweight canvas list, so rows
    never poke out of the rounded corners, the scrollbar only appears when
    needed, and the list stays fast with many values.

    NOTE: CTkComboBox owns attributes such as ``_canvas``, ``_entry``,
    ``_values`` and ``_state``. All popup-specific attributes below are
    prefixed with ``_popup_`` so they never collide with the parent class.
    """

    _MAX_POPUP_HEIGHT = 320  # logical px (scaled for DPI automatically)
    _OPTION_HEIGHT = 32
    _MAX_CORNER_RADIUS = 12

    # Class-level defaults so methods are safe even if CTk calls configure()
    # or destroy() before our __init__ body has run.
    _popup: tkinter.Toplevel | None = None
    _popup_container: Any = None
    _popup_canvas: tkinter.Canvas | None = None
    _popup_scrollbar: Any = None
    _popup_key: str | None = None
    _popup_dismiss_bindings: tuple = ()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        initial_values = [str(v) for v in (kwargs.get("values") or ())]
        variable = kwargs.get("variable")
        kwargs["values"] = []

        self._popup = None
        self._popup_container = None
        self._popup_canvas = None
        self._popup_scrollbar = None
        self._popup_key = None
        self._popup_dismiss_bindings = []

        super().__init__(*args, **kwargs)

        self._values = initial_values

        self._popup_row_px = 1
        self._popup_pad_px = 4
        self._popup_draw_width = 0
        self._popup_hover_index: int | None = None
        self._popup_selected_index: int | None = None
        self._popup_hover_item: int | None = None
        self._popup_selected_item: int | None = None
        self._popup_accent_item: int | None = None

        for sequence, handler in (
            ("<Down>", self._on_key_down),
            ("<Up>", self._on_key_up),
            ("<Return>", self._on_key_return),
            ("<Escape>", self._on_key_escape),
        ):
            try:
                self._entry.bind(sequence, handler, add="+")
            except Exception:
                pass

        if variable is None:
            self.set(self._values[0] if self._values else "")

    # ------------------------------------------------------------------ API

    def configure(self, require_redraw: bool = False, **kwargs: Any) -> None:
        values = kwargs.pop("values", _UNSET)
        if values is not _UNSET:
            kwargs["values"] = []
        if values is not _UNSET or "state" in kwargs:
            self._close_popup()
        super().configure(require_redraw=require_redraw, **kwargs)
        if values is not _UNSET:
            self._values = [str(v) for v in (values or ())]

    def cget(self, attribute_name: str) -> Any:
        if attribute_name == "values":
            return list(self._values)
        return super().cget(attribute_name)

    # -------------------------------------------------------------- opening

    def _is_open(self) -> bool:
        return self._popup is not None and bool(self._popup.winfo_viewable())

    def _clicked(self, event: Any = None) -> None:
        if self._is_open():
            self._close_popup()
        elif self._state != tkinter.DISABLED and self._values:
            self._open_dropdown_menu()

    def _scaled(self, value: float) -> int:
        return int(round(self._apply_widget_scaling(value)))

    def _open_dropdown_menu(self) -> None:
        popup = self._ensure_popup()
        canvas = self._popup_canvas
        scrollbar = self._popup_scrollbar
        assert canvas is not None and scrollbar is not None
        self._apply_popup_theme()

        row = max(1, self._scaled(self._OPTION_HEIGHT))
        radius = min(self.cget("corner_radius"), self._MAX_CORNER_RADIUS)
        # Padding keeps rows clear of the rounded corners and the border.
        pad = max(4, self._scaled(radius) // 2 + 3)
        self._popup_row_px = row
        self._popup_pad_px = pad

        content_height = len(self._values) * row
        max_height = self._scaled(self._MAX_POPUP_HEIGHT)
        desired = min(content_height + 2 * pad, max_height)

        root = self.winfo_toplevel()
        root.update_idletasks()
        x, y, width, height = _calculate_popup_geometry(
            (
                root.winfo_rootx(),
                root.winfo_rooty(),
                root.winfo_width(),
                root.winfo_height(),
            ),
            (root.winfo_screenwidth(), root.winfo_screenheight()),
            (
                self.winfo_rootx(),
                self.winfo_rooty(),
                self.winfo_width(),
                self.winfo_height(),
            ),
            desired,
        )

        needs_scroll = content_height > height - 2 * pad
        canvas.configure(yscrollincrement=row)
        if needs_scroll:
            canvas.grid_configure(padx=(pad, 2), pady=pad)
            scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, pad), pady=pad)
        else:
            canvas.grid_configure(padx=pad, pady=pad)
            scrollbar.grid_remove()

        popup.geometry(f"{width}x{height}+{x}+{y}")
        popup.deiconify()
        popup.lift()
        popup.update_idletasks()

        self._popup_selected_index = self._index_of(self.get())
        self._popup_hover_index = self._popup_selected_index
        canvas.yview_moveto(0)
        self._redraw()
        if self._popup_selected_index is not None:
            self._ensure_visible(self._popup_selected_index)
        self._bind_dismiss()

    def _index_of(self, value: str) -> int | None:
        try:
            return self._values.index(value)
        except ValueError:
            return None

    # ---------------------------------------------------------------- popup

    def _ensure_popup(self) -> tkinter.Toplevel:
        if self._popup is not None:
            return self._popup

        root = self.winfo_toplevel()
        popup = tkinter.Toplevel(root)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.transient(root)
        popup.bind("<Escape>", lambda _e: self._close_popup())

        # Make the area outside the rounded frame see-through where possible,
        # so the corners never show a square background.
        self._popup_key = None
        try:
            if sys.platform.startswith("win"):
                popup.configure(bg="#010101")
                popup.attributes("-transparentcolor", "#010101")
                self._popup_key = "#010101"
            elif sys.platform == "darwin":
                popup.attributes("-transparent", True)
                popup.configure(bg="systemTransparent")
                self._popup_key = "systemTransparent"
        except tkinter.TclError:
            self._popup_key = None

        container = ctk.CTkFrame(popup, border_width=1)
        container.pack(fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        canvas = tkinter.Canvas(
            container, highlightthickness=0, borderwidth=0, takefocus=0
        )
        canvas.grid(row=0, column=0, sticky="nsew")

        scrollbar = ctk.CTkScrollbar(container, width=10, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.bind("<Motion>", self._on_motion)
        canvas.bind("<Leave>", self._on_leave)
        canvas.bind("<Button-1>", self._on_canvas_click)
        canvas.bind("<MouseWheel>", self._on_wheel)
        canvas.bind("<Button-4>", self._on_wheel)
        canvas.bind("<Button-5>", self._on_wheel)
        canvas.bind("<Configure>", self._on_canvas_configure)

        self._popup = popup
        self._popup_container = container
        self._popup_canvas = canvas
        self._popup_scrollbar = scrollbar
        return popup

    def _apply_popup_theme(self) -> None:
        popup = self._popup
        container = self._popup_container
        canvas = self._popup_canvas
        scrollbar = self._popup_scrollbar
        assert popup and container and canvas and scrollbar

        dropdown_bg = self.cget("dropdown_fg_color")
        outer_bg = self._popup_key or self._apply_appearance_mode(self._bg_color)

        popup.configure(bg=outer_bg)
        container.configure(
            corner_radius=min(self.cget("corner_radius"), self._MAX_CORNER_RADIUS),
            fg_color=dropdown_bg,
            border_color=self.cget("border_color"),
            bg_color=outer_bg,
        )
        canvas.configure(bg=self._apply_appearance_mode(dropdown_bg))
        scrollbar.configure(
            fg_color="transparent",
            button_color=self.cget("button_color"),
            button_hover_color=self.cget("button_hover_color"),
        )

    # -------------------------------------------------------------- drawing

    def _row_rect(self, index: int) -> list[float]:
        inset = max(2, self._scaled(3))
        y1 = index * self._popup_row_px + 1
        y2 = (index + 1) * self._popup_row_px - 1
        return _rounded_points(
            inset,
            y1,
            max(inset + 1, self._popup_draw_width - inset),
            y2,
            self._scaled(6),
        )

    def _redraw(self) -> None:
        canvas = self._popup_canvas
        if canvas is None:
            return
        canvas.delete("all")
        row = self._popup_row_px
        self._popup_draw_width = max(1, canvas.winfo_width())
        canvas.configure(
            scrollregion=(0, 0, self._popup_draw_width, len(self._values) * row)
        )

        font = self._apply_font_scaling(self.cget("dropdown_font"))
        text_color = self._apply_appearance_mode(self.cget("dropdown_text_color"))
        hover_color = self._apply_appearance_mode(self.cget("dropdown_hover_color"))
        accent_color = self._apply_appearance_mode(self.cget("button_color"))

        dummy = _rounded_points(0, 0, 10, 10, 3)
        self._popup_selected_item = canvas.create_polygon(
            dummy, smooth=True, fill=hover_color, outline="", state="hidden"
        )
        self._popup_hover_item = canvas.create_polygon(
            dummy, smooth=True, fill=hover_color, outline="", state="hidden"
        )
        self._popup_accent_item = canvas.create_polygon(
            dummy, smooth=True, fill=accent_color, outline="", state="hidden"
        )

        text_x = max(8, self._scaled(12))
        for i, value in enumerate(self._values):
            canvas.create_text(
                text_x,
                i * row + row / 2,
                text=value,
                anchor="w",
                font=font,
                fill=text_color,
            )

        if self._popup_selected_index is not None:
            canvas.coords(
                self._popup_selected_item, *self._row_rect(self._popup_selected_index)
            )
            canvas.itemconfigure(self._popup_selected_item, state="normal")
            bar_w = max(2, self._scaled(3))
            top = self._popup_selected_index * row + row * 0.28
            bottom = (self._popup_selected_index + 1) * row - row * 0.28
            left = max(2, self._scaled(3)) + 1
            canvas.coords(
                self._popup_accent_item,
                *_rounded_points(left, top, left + bar_w, bottom, bar_w / 2),
            )
            canvas.itemconfigure(self._popup_accent_item, state="normal")
        self._set_hover(self._popup_hover_index)

    def _set_hover(self, index: int | None) -> None:
        canvas = self._popup_canvas
        if canvas is None or self._popup_hover_item is None:
            return
        self._popup_hover_index = index
        if index is None or not 0 <= index < len(self._values):
            canvas.itemconfigure(self._popup_hover_item, state="hidden")
            return
        canvas.coords(self._popup_hover_item, *self._row_rect(index))
        canvas.itemconfigure(self._popup_hover_item, state="normal")
        # Keep the highlights underneath the text.
        canvas.tag_lower(self._popup_hover_item)
        if self._popup_selected_item is not None:
            canvas.tag_lower(self._popup_selected_item)

    def _ensure_visible(self, index: int) -> None:
        canvas = self._popup_canvas
        total = len(self._values) * self._popup_row_px
        if canvas is None or total <= 0:
            return
        view_top = canvas.canvasy(0)
        view_bottom = canvas.canvasy(canvas.winfo_height())
        row_top = index * self._popup_row_px
        row_bottom = row_top + self._popup_row_px
        if row_top < view_top:
            canvas.yview_moveto(row_top / total)
        elif row_bottom > view_bottom:
            canvas.yview_moveto((row_bottom - canvas.winfo_height()) / total)

    # --------------------------------------------------------------- events

    def _index_at(self, event: Any) -> int | None:
        canvas = self._popup_canvas
        assert canvas is not None
        index = int(canvas.canvasy(event.y) // self._popup_row_px)
        return index if 0 <= index < len(self._values) else None

    def _on_motion(self, event: Any) -> None:
        index = self._index_at(event)
        if index != self._popup_hover_index:
            self._set_hover(index)

    def _on_leave(self, _event: Any = None) -> None:
        self._set_hover(None)

    def _on_canvas_click(self, event: Any) -> str:
        index = self._index_at(event)
        if index is not None:
            self._select_value(self._values[index])
        return "break"

    def _on_wheel(self, event: Any) -> str:
        canvas = self._popup_canvas
        if canvas is None:
            return "break"
        if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
            step = -1
        else:
            step = 1
        canvas.yview_scroll(step, "units")
        return "break"

    def _on_canvas_configure(self, event: Any) -> None:
        if event.width != self._popup_draw_width and self._is_open():
            self._redraw()

    # ------------------------------------------------------------- keyboard

    def _move_highlight(self, delta: int) -> None:
        count = len(self._values)
        if not count:
            return
        current = self._popup_hover_index
        if current is None:
            new = 0 if delta > 0 else count - 1
        else:
            new = min(max(current + delta, 0), count - 1)
        self._set_hover(new)
        self._ensure_visible(new)

    def _on_key_down(self, _event: Any = None) -> str | None:
        if self._is_open():
            self._move_highlight(1)
            return "break"
        if self._state != tkinter.DISABLED and self._values:
            self._open_dropdown_menu()
            return "break"
        return None

    def _on_key_up(self, _event: Any = None) -> str | None:
        if self._is_open():
            self._move_highlight(-1)
            return "break"
        return None

    def _on_key_return(self, _event: Any = None) -> str | None:
        if self._is_open():
            if self._popup_hover_index is not None:
                self._select_value(self._values[self._popup_hover_index])
            else:
                self._close_popup()
            return "break"
        return None

    def _on_key_escape(self, _event: Any = None) -> str | None:
        if self._is_open():
            self._close_popup()
            return "break"
        return None

    # ------------------------------------------------------------ selecting

    def _select_value(self, value: str) -> None:
        self._close_popup()
        self._dropdown_callback(value)

    # -------------------------------------------------------------- dismiss

    def _bind_dismiss(self) -> None:
        if self._popup_dismiss_bindings:
            return
        root = self.winfo_toplevel()
        for sequence, handler in (
            ("<Button-1>", self._on_root_click),
            ("<Configure>", self._on_root_configure),
            ("<Unmap>", self._on_root_unmap),
            ("<FocusOut>", self._on_root_focus_out),
        ):
            funcid = root.bind(sequence, handler, add="+")
            self._popup_dismiss_bindings.append((sequence, funcid))

    def _unbind_dismiss(self) -> None:
        if not self._popup_dismiss_bindings:
            return
        root = self.winfo_toplevel()
        for sequence, funcid in self._popup_dismiss_bindings:
            try:
                script = str(root.tk.call("bind", root._w, sequence))
                kept = [
                    line
                    for line in script.split("\n")
                    if line and funcid not in line
                ]
                root.tk.call("bind", root._w, sequence, "\n".join(kept))
                root.deletecommand(funcid)
            except tkinter.TclError:
                continue
        self._popup_dismiss_bindings.clear()

    def _on_root_click(self, event: Any) -> None:
        if not self._is_open():
            return
        widget = event.widget
        if isinstance(widget, tkinter.Misc) and self._is_descendant(widget, self):
            return  # the combo box's own click handler toggles the popup
        self._close_popup()

    def _on_root_configure(self, event: Any) -> None:
        # Root moved or resized: the popup position would be stale.
        if event.widget is self.winfo_toplevel() and self._is_open():
            self._close_popup()

    def _on_root_unmap(self, event: Any) -> None:
        if event.widget is self.winfo_toplevel():
            self._close_popup()

    def _on_root_focus_out(self, _event: Any = None) -> None:
        if self._popup is not None:
            self.after_idle(self._close_if_root_inactive)

    def _close_if_root_inactive(self) -> None:
        if not self._is_open():
            return
        root = self.winfo_toplevel()
        try:
            focused = root.focus_displayof()
        except (tkinter.TclError, KeyError):
            focused = None
        if focused is None:
            self._close_popup()
            return
        focused_toplevel = focused.winfo_toplevel()
        if focused_toplevel is not root and focused_toplevel is not self._popup:
            self._close_popup()

    @staticmethod
    def _is_descendant(widget: tkinter.Misc | None, parent: tkinter.Misc) -> bool:
        while widget is not None:
            if widget is parent:
                return True
            widget = widget.master
        return False

    def _close_popup(self) -> None:
        if self._popup is not None:
            try:
                self._popup.withdraw()
            except tkinter.TclError:
                pass
        self._popup_hover_index = None
        self._unbind_dismiss()

    def destroy(self) -> None:
        try:
            self._close_popup()
        except tkinter.TclError:
            pass
        if self._popup is not None:
            try:
                self._popup.destroy()
            except tkinter.TclError:
                pass
            self._popup = None
            self._popup_container = None
            self._popup_canvas = None
            self._popup_scrollbar = None
        super().destroy()