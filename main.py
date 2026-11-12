import customtkinter as ctk

from cursor_theme_tab import create_cursor_tab
from gtk_theme_tab import GtkThemeTab
from icon_theme_tab import create_icon_theme_tab
from kde_theme_tab import create_kde_theme_tab
from window_theme_tab import create_window_tab


class XfceUtilApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("XFCE Utility")
        self.geometry("760x760")
        self.minsize(600, 600)

        tabs = ctk.CTkTabview(self)
        tabs.pack(fill="both", expand=True, padx=16, pady=16)
        self.gtk_theme_tab = GtkThemeTab(tabs.add("GTK Theme"))
        create_kde_theme_tab(tabs.add("KDE Theme"))
        self.window_theme_tab = create_window_tab(tabs.add("Window"))
        self.icon_tab = create_icon_theme_tab(tabs.add("Icon"))
        self.cursor_theme_tab = create_cursor_tab(tabs.add("Cursor"))


def main() -> None:
    XfceUtilApp().mainloop()


if __name__ == "__main__":
    main()
