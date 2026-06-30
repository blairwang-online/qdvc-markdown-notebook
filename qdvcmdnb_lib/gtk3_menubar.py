"""
gtk3_menubar.py — GTK3 menu-bar construction for NotebookWindow.

This is a **mixin**: it holds only the menu-building methods, factored out of the
window for readability. It is combined into NotebookWindow in gtk3_window.py and
relies on attributes/handlers defined there and in the other mixins (e.g.
self.on_new_note, self.settings). No standalone behaviour; GTK3-specific.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk  # noqa: E402

from .config import SORT_ALPHA, SORT_DATE_NEW, SORT_DATE_OLD


class MenuBarMixin:
    """Menu-bar construction for NotebookWindow (see module docstring)."""
    def _build_menubar(self):
        menubar = Gtk.MenuBar()
        accel = Gtk.AccelGroup()
        self.add_accel_group(accel)
        self._accel_group = accel

        # ---- File menu ----
        file_menu = Gtk.Menu()
        file_item = Gtk.MenuItem.new_with_mnemonic("_File")
        file_item.set_submenu(file_menu)

        mi_new = self._icon_menu_item("New note", "document-new")
        mi_new.add_accelerator("activate", accel, Gdk.KEY_n,
                               Gdk.ModifierType.CONTROL_MASK,
                               Gtk.AccelFlags.VISIBLE)
        mi_new.connect("activate", self.on_new_note)
        file_menu.append(mi_new)

        mi_save = self._icon_menu_item("Save note", "document-save")
        mi_save.add_accelerator("activate", accel, Gdk.KEY_s,
                                Gdk.ModifierType.CONTROL_MASK,
                                Gtk.AccelFlags.VISIBLE)
        mi_save.connect("activate", self.on_save_note)
        file_menu.append(mi_save)

        # Refresh note — mirrors the toolbar button; Ctrl+R. Disabled until a
        # note is open (kept in sync in _update_save_sensitivity).
        self.mi_refresh = self._icon_menu_item("Refresh note", "view-refresh")
        self.mi_refresh.add_accelerator("activate", accel, Gdk.KEY_r,
                                        Gdk.ModifierType.CONTROL_MASK,
                                        Gtk.AccelFlags.VISIBLE)
        self.mi_refresh.set_sensitive(False)
        self.mi_refresh.connect("activate", self.on_refresh_note)
        file_menu.append(self.mi_refresh)

        file_menu.append(Gtk.SeparatorMenuItem())

        mi_open = self._icon_menu_item("Open workspace", "folder-open")
        mi_open.add_accelerator("activate", accel, Gdk.KEY_o,
                                Gdk.ModifierType.CONTROL_MASK,
                                Gtk.AccelFlags.VISIBLE)
        mi_open.connect("activate", self.on_open_folder)
        file_menu.append(mi_open)

        # Refresh workspace — re-scan the working folder and rebuild panes 1+2
        # from disk. Same icon as Refresh note. Ctrl+Shift+R.
        self.mi_refresh_ws = self._icon_menu_item("Refresh workspace",
                                                  "view-refresh")
        self.mi_refresh_ws.add_accelerator(
            "activate", accel, Gdk.KEY_r,
            Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK,
            Gtk.AccelFlags.VISIBLE)
        self.mi_refresh_ws.connect("activate", self.on_refresh_workspace)
        file_menu.append(self.mi_refresh_ws)

        mi_close_ws = Gtk.MenuItem(label="Close workspace")
        mi_close_ws.connect("activate", self.on_close_workspace)
        file_menu.append(mi_close_ws)

        # "Open recent workspace" submenu, populated dynamically from settings.
        self.recent_menu_item = self._icon_menu_item(
            "Open recent workspace", "document-open-recent")
        self.recent_menu = Gtk.Menu()
        self.recent_menu_item.set_submenu(self.recent_menu)
        file_menu.append(self.recent_menu_item)

        file_menu.append(Gtk.SeparatorMenuItem())

        mi_new_tab = self._icon_menu_item("New tab", "tab-new")
        mi_new_tab.add_accelerator("activate", accel, Gdk.KEY_t,
                                   Gdk.ModifierType.CONTROL_MASK,
                                   Gtk.AccelFlags.VISIBLE)
        mi_new_tab.connect("activate", self.on_new_tab)
        file_menu.append(mi_new_tab)

        mi_close_tab = Gtk.MenuItem(label="Close tab")
        mi_close_tab.add_accelerator("activate", accel, Gdk.KEY_w,
                                     Gdk.ModifierType.CONTROL_MASK,
                                     Gtk.AccelFlags.VISIBLE)
        mi_close_tab.connect("activate", self.on_close_tab)
        file_menu.append(mi_close_tab)

        file_menu.append(Gtk.SeparatorMenuItem())

        mi_quit = self._icon_menu_item("Quit", "application-exit")
        # Note: the spec listed Ctrl+S for Quit; that collides with Save,
        # so Quit is bound to the conventional Ctrl+Q instead. See MAINTENANCE.md.
        mi_quit.add_accelerator("activate", accel, Gdk.KEY_q,
                                Gdk.ModifierType.CONTROL_MASK,
                                Gtk.AccelFlags.VISIBLE)
        mi_quit.connect("activate", self.on_quit)
        file_menu.append(mi_quit)

        menubar.append(file_item)

        # ---- Edit menu ----
        edit_menu = Gtk.Menu()
        edit_item = Gtk.MenuItem.new_with_mnemonic("_Edit")
        edit_item.set_submenu(edit_menu)

        mi_prefs = self._icon_menu_item("Preferences\u2026", "preferences-system")
        mi_prefs.connect("activate", self.on_preferences)
        edit_menu.append(mi_prefs)

        menubar.append(edit_item)

        # ---- View menu ----
        view_menu = Gtk.Menu()
        view_item = Gtk.MenuItem.new_with_mnemonic("_View")
        view_item.set_submenu(view_menu)

        self.mi_toolbar = Gtk.CheckMenuItem(label="Toolbar")
        self.mi_toolbar.set_active(True)
        self.mi_toolbar.connect("toggled", self.on_toggle_toolbar)
        view_menu.append(self.mi_toolbar)

        self.mi_statusbar = Gtk.CheckMenuItem(label="Statusbar")
        self.mi_statusbar.set_active(True)
        self.mi_statusbar.connect("toggled", self.on_toggle_statusbar)
        view_menu.append(self.mi_statusbar)

        view_menu.append(Gtk.SeparatorMenuItem())

        # Mode toggles that mirror the toolbar's toggle buttons. A guard flag
        # (_syncing_view_toggles) prevents the menu↔toolbar sync from looping.
        self._syncing_view_toggles = False

        self.mi_readonly = Gtk.CheckMenuItem(label="Read-only")
        self.mi_readonly.set_active(True)
        self.mi_readonly.add_accelerator("activate", accel, Gdk.KEY_e,
                                         Gdk.ModifierType.CONTROL_MASK,
                                         Gtk.AccelFlags.VISIBLE)
        self.mi_readonly.connect("toggled", self.on_menu_toggle_read_only)
        view_menu.append(self.mi_readonly)

        self.mi_cardview = Gtk.CheckMenuItem(label="Card view")
        self.mi_cardview.add_accelerator("activate", accel, Gdk.KEY_d,
                                         Gdk.ModifierType.CONTROL_MASK,
                                         Gtk.AccelFlags.VISIBLE)
        self.mi_cardview.connect("toggled", self.on_menu_toggle_card_view)
        view_menu.append(self.mi_cardview)

        self.mi_preview = Gtk.CheckMenuItem(label="Preview")
        self.mi_preview.add_accelerator("activate", accel, Gdk.KEY_grave,
                                        Gdk.ModifierType.CONTROL_MASK,
                                        Gtk.AccelFlags.VISIBLE)
        self.mi_preview.connect("toggled", self.on_menu_toggle_preview)
        view_menu.append(self.mi_preview)

        self.mi_outline = Gtk.CheckMenuItem(label="Headings outline")
        self.mi_outline.add_accelerator("activate", accel, Gdk.KEY_o,
                                        Gdk.ModifierType.CONTROL_MASK
                                        | Gdk.ModifierType.SHIFT_MASK,
                                        Gtk.AccelFlags.VISIBLE)
        self.mi_outline.connect("toggled", self.on_menu_toggle_outline)
        view_menu.append(self.mi_outline)

        view_menu.append(Gtk.SeparatorMenuItem())

        mi_alpha = Gtk.RadioMenuItem(label="Sort: Alphabetical", group=None)
        mi_alpha.set_active(True)
        mi_alpha.connect("toggled", self.on_sort_changed, SORT_ALPHA)
        view_menu.append(mi_alpha)

        mi_new_first = Gtk.RadioMenuItem(label="Sort: Date, newest first",
                                         group=mi_alpha)
        mi_new_first.connect("toggled", self.on_sort_changed, SORT_DATE_NEW)
        view_menu.append(mi_new_first)

        mi_old_first = Gtk.RadioMenuItem(label="Sort: Date, oldest first",
                                         group=mi_alpha)
        mi_old_first.connect("toggled", self.on_sort_changed, SORT_DATE_OLD)
        view_menu.append(mi_old_first)

        # Keep references so a restored/persisted sort mode can be reflected.
        self._sort_items = {
            SORT_ALPHA: mi_alpha,
            SORT_DATE_NEW: mi_new_first,
            SORT_DATE_OLD: mi_old_first,
        }

        menubar.append(view_item)

        # ---- Help menu ----
        help_menu = Gtk.Menu()
        help_item = Gtk.MenuItem.new_with_mnemonic("_Help")
        help_item.set_submenu(help_menu)

        mi_about = self._icon_menu_item("About", "help-about")
        mi_about.connect("activate", self.on_about)
        help_menu.append(mi_about)

        menubar.append(help_item)
        return menubar

    @staticmethod
    def _icon_menu_item(label, icon_name):
        """
        Build a menu item with a leading icon, GNOME2/MATE style.

        Uses Gtk.ImageMenuItem (deprecated in GTK3 but the idiomatic way to get
        icons in menus, and a good fit for this app's MATE-era look). Falls back
        to a plain MenuItem if ImageMenuItem is unavailable.
        """
        try:
            item = Gtk.ImageMenuItem(label=label)
            img = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
            item.set_image(img)
            item.set_always_show_image(True)
            return item
        except (AttributeError, TypeError):
            return Gtk.MenuItem(label=label)
