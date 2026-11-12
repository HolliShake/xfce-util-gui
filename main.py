import io
import sys
from pathlib import Path

import cairosvg
import customtkinter as ctk
from PIL import Image, ImageTk

from cursor_theme_tab import create_cursor_tab
from display_manager_theme_tab import create_display_manager_theme_tab
from gtk_theme_tab import GtkThemeTab
from icon_theme_tab import create_icon_theme_tab
from kde_theme_tab import create_kde_theme_tab
from window_theme_tab import create_window_tab


class XfceUtilApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__(className="Xfceutil")
        self.withdraw()
        self.title("XFCE Utility")
        self._set_window_icon()
        self.geometry("760x760")
        self.minsize(600, 600)

        tabs = ctk.CTkTabview(self)
        tabs.pack(fill="both", expand=True, padx=16, pady=16)
        self.display_manager_theme_tab = create_display_manager_theme_tab(
            tabs.add("Display Manager")
        )
        self.gtk_theme_tab = GtkThemeTab(tabs.add("GTK Theme"))
        self.kde_theme_tab = create_kde_theme_tab(tabs.add("KDE Theme"))
        self.window_theme_tab = create_window_tab(tabs.add("Window"))
        self.icon_tab = create_icon_theme_tab(tabs.add("Icon"))
        self.cursor_theme_tab = create_cursor_tab(tabs.add("Cursor"))
        self.update_idletasks()
        self.deiconify()

    def _set_window_icon(self) -> None:
        icon_paths = (
            Path("/usr/local/share/icons/hicolor/scalable/apps/xfce-util.svg"),
            Path(sys.prefix) / "share/icons/hicolor/scalable/apps/xfce-util.svg",
            Path(__file__).resolve().parent / "xfce-util.svg",
        )
        icon_path = next((path for path in icon_paths if path.is_file()), None)
        if icon_path is None:
            return
        png_data = cairosvg.svg2png(
            url=str(icon_path), output_width=128, output_height=128
        )
        with Image.open(io.BytesIO(png_data)) as image:
            self._window_icon = ImageTk.PhotoImage(image)
        self.iconphoto(True, self._window_icon)


def main() -> None:
    XfceUtilApp().mainloop()


if __name__ == "__main__":
    main()
