"""
gtk3_toolbar.py — GTK3 toolbar construction + styling for NotebookWindow.

A **mixin** combined into NotebookWindow in gtk3_window.py. GTK3-specific; relies
on handlers/attributes defined across the window and its other mixins.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from .settings import TOOLBAR_TEXT_BESIDE


class ToolbarMixin:
    """Toolbar construction + style for NotebookWindow (see module docstring)."""
    def _build_toolbar(self):
        toolbar = Gtk.Toolbar()
        self.toolbar = toolbar
        toolbar.set_style(self._toolbar_style_enum())

        btn_new = Gtk.ToolButton(icon_name="document-new")
        btn_new.set_label("New note")
        btn_new.set_tooltip_text("Create a new note in the selected folder")
        btn_new.connect("clicked", self.on_new_note)
        toolbar.insert(btn_new, -1)

        self.btn_save = Gtk.ToolButton(icon_name="document-save")
        self.btn_save.set_label("Save note")
        self.btn_save.set_tooltip_text("Save the current note")
        self.btn_save.set_sensitive(False)  # enabled only when dirty
        self.btn_save.connect("clicked", self.on_save_note)
        toolbar.insert(self.btn_save, -1)

        # Refresh note: reload the current note from disk (e.g. edited elsewhere).
        self.btn_refresh = Gtk.ToolButton(icon_name="view-refresh")
        self.btn_refresh.set_label("Refresh note")
        self.btn_refresh.set_tooltip_text(
            "Reload the current note from disk")
        self.btn_refresh.set_sensitive(False)  # enabled only with a note open
        self.btn_refresh.connect("clicked", self.on_refresh_note)
        toolbar.insert(self.btn_refresh, -1)

        # Slugify: rename the active note from its level-1 heading. Enabled only
        # when the active tab's first line is a short (<32 char) H1.
        self.btn_slugify = Gtk.ToolButton(icon_name="insert-link")
        self.btn_slugify.set_label("Slugify")
        self.btn_slugify.set_tooltip_text(
            "Rename this note from its level-1 heading")
        self.btn_slugify.set_sensitive(False)
        self.btn_slugify.connect("clicked", self.on_slugify)
        toolbar.insert(self.btn_slugify, -1)

        toolbar.insert(self._toolbar_separator(), -1)

        # Card view toggle: when active, pane 2 shows each note as a small card
        # (bold title + date + first body line). Off by default.
        self.btn_cardview = Gtk.ToggleToolButton()
        self.btn_cardview.set_icon_name("mail-attachment")
        self.btn_cardview.set_label("Card view")
        self.btn_cardview.set_tooltip_text(
            "Show notes as cards (title, date, first line)")
        self.btn_cardview.set_active(False)
        # "Important" items keep their label beside the icon in BOTH_HORIZ mode.
        self.btn_cardview.set_is_important(True)
        self.btn_cardview.connect("toggled", self.on_toggle_card_view)
        toolbar.insert(self.btn_cardview, -1)

        toolbar.insert(self._toolbar_separator(), -1)

        # Read-only toggle. Pressed-in (active) means read-only; releasing it
        # enters edit mode. Applies across all tabs.
        self.btn_readonly = Gtk.ToggleToolButton()
        self.btn_readonly.set_icon_name("changes-prevent-symbolic")
        self.btn_readonly.set_label("Read-only")
        self.btn_readonly.set_tooltip_text(
            "Read-only mode (release to edit)")
        self.btn_readonly.set_active(True)  # default: read-only
        self.btn_readonly.set_is_important(True)
        self._readonly_handler = self.btn_readonly.connect(
            "toggled", self.on_toggle_read_only)
        toolbar.insert(self.btn_readonly, -1)

        # Preview toggle: when active, all tabs show rendered markdown (read-only)
        # and the Read-only button is disabled. Applies across all tabs.
        self.btn_preview = Gtk.ToggleToolButton()
        self.btn_preview.set_icon_name("document-page-setup")
        self.btn_preview.set_label("Preview")
        self.btn_preview.set_tooltip_text(
            "Preview rendered markdown (read-only)")
        self.btn_preview.set_active(False)
        self.btn_preview.set_is_important(True)
        self.btn_preview.connect("toggled", self.on_toggle_preview)
        toolbar.insert(self.btn_preview, -1)

        # Outline toggle: show/hide the headings-outline pane (pane 4).
        self.btn_outline = Gtk.ToggleToolButton()
        self.btn_outline.set_icon_name("view-list")
        self.btn_outline.set_label("Outline")
        self.btn_outline.set_tooltip_text(
            "Show the headings outline of the current note")
        self.btn_outline.set_active(False)
        self.btn_outline.set_is_important(True)
        self.btn_outline.connect("toggled", self.on_toggle_outline)
        toolbar.insert(self.btn_outline, -1)

        return toolbar

    @staticmethod
    def _toolbar_separator():
        sep = Gtk.SeparatorToolItem()
        sep.set_draw(True)  # ensure the divider line is actually drawn
        return sep

    def _toolbar_style_enum(self):
        if self.settings.toolbar_style == TOOLBAR_TEXT_BESIDE:
            return Gtk.ToolbarStyle.BOTH_HORIZ
        return Gtk.ToolbarStyle.BOTH

    def _apply_toolbar_style(self):
        self.toolbar.set_style(self._toolbar_style_enum())
