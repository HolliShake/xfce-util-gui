import unittest
from unittest.mock import Mock, patch

import main


class MainWindowTests(unittest.TestCase):
    def test_window_is_shown_after_all_tabs_are_created(self):
        events = []
        tabs = Mock()
        tabs.add.side_effect = lambda name: events.append(name) or object()
        with (
            patch.object(
                main.ctk.CTk,
                "__init__",
                autospec=True,
                side_effect=lambda self, **kwargs: events.append("init"),
            ),
            patch.object(
                main.XfceUtilApp,
                "withdraw",
                autospec=True,
                side_effect=lambda self: events.append("withdraw"),
            ),
            patch.object(main.XfceUtilApp, "title"),
            patch.object(main.XfceUtilApp, "_set_window_icon"),
            patch.object(main.XfceUtilApp, "geometry"),
            patch.object(main.XfceUtilApp, "minsize"),
            patch.object(
                main.XfceUtilApp,
                "update_idletasks",
                autospec=True,
                side_effect=lambda self: events.append("render"),
            ),
            patch.object(
                main.XfceUtilApp,
                "deiconify",
                autospec=True,
                side_effect=lambda self: events.append("show"),
            ),
            patch.object(main.ctk, "CTkTabview", return_value=tabs),
            patch.object(
                main,
                "create_display_manager_theme_tab",
                side_effect=lambda _: events.append("display"),
            ),
            patch.object(
                main,
                "GtkThemeTab",
                side_effect=lambda _: events.append("gtk"),
            ),
            patch.object(
                main, "create_kde_theme_tab", side_effect=lambda _: events.append("kde")
            ),
            patch.object(
                main, "create_window_tab", side_effect=lambda _: events.append("window")
            ),
            patch.object(
                main, "create_icon_theme_tab", side_effect=lambda _: events.append("icon")
            ),
            patch.object(
                main, "create_cursor_tab", side_effect=lambda _: events.append("cursor")
            ),
        ):
            main.XfceUtilApp()

        self.assertLess(events.index("withdraw"), events.index("Display Manager"))
        self.assertEqual(events[-2:], ["render", "show"])


if __name__ == "__main__":
    unittest.main()
