"""
gtk3_actions.py — GTK3 user-action handlers for NotebookWindow.

A **mixin** combined into NotebookWindow in gtk3_window.py. Holds the signal
handlers and the operations they drive: note/file actions, the right-click and
tab context menus, search, workspace open/close/refresh, preferences/about,
session save, and the shared confirm/error dialogs. Business logic and disk I/O
are delegated to qdvcmdnb_lib.model and .settings. GTK3-specific; relies on
attributes/widgets defined across the window and its other mixins.
"""

import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib  # noqa: E402

from . import model
from .config import (
    APP_NAME,
    NODE_ALL_NOTES,
    NODE_SUBFOLDERS,
    NODE_SUBFOLDER,
)
from .settings import icon_set_files, APP_ICON_NAME
from .gtk3_preferences import PreferencesDialog


class ActionsMixin:
    """User-action handlers for NotebookWindow (see module docstring)."""

    # --------------------------------------------------------- handlers -- #
    def on_sidebar_selection_changed(self, selection):
        model_, treeiter = selection.get_selected()
        if treeiter is None:
            return
        node_kind = model_[treeiter][2]
        self.current_node = node_kind
        if node_kind == NODE_SUBFOLDER:
            self.current_subfolder = model_[treeiter][3]
        else:
            self.current_subfolder = None

        if node_kind == NODE_SUBFOLDERS:
            # The "Subfolders" parent itself has no note list: show placeholders
            # in both the note list (pane 2) and the editor (pane 3).
            self._show_notelist_placeholder()
            tab = self._active_tab()
            if tab:
                tab.clear()
        else:
            self._reload_notelist()

    def on_note_selection_changed(self, selection):
        if self._note_select_guard:
            return
        model_, treeiter = selection.get_selected()
        if treeiter is None:
            return
        # Default behaviour: open (replace) in the active tab.
        tab = self._active_tab()
        if tab and self._maybe_warn_unsaved(tab) is False:
            # User cancelled; revert the selection to the tab's current note.
            self._reselect_active_note()
            return
        path = model_[treeiter][1]
        self._load_note_in_active_tab(model.Note(path))

    def on_notelist_button_press(self, _widget, event):
        # Right-click (button 3) opens the context menu on the row under it,
        # WITHOUT changing the current selection (so right-clicking doesn't open
        # the note in the active tab).
        if event.button != 3:
            return False
        path_info = self.note_view.get_path_at_pos(int(event.x), int(event.y))
        if path_info is None:
            return False
        path, _col, _cx, _cy = path_info
        treeiter = self.note_store.get_iter(path)
        note_path = self.note_store[treeiter][1]

        menu = self._build_note_context_menu(note_path, include_locate=False)
        menu.popup_at_pointer(event)
        return True

    def _on_tab_context_menu(self, tab, event):
        """
        Right-click on a tab label: show the same context menu as a pane-2
        right-click, plus a "Locate in subfolders" item at the top. No-op for a
        tab with no note open (guarded in EditorTab).
        """
        if tab.note is None:
            return
        menu = self._build_note_context_menu(
            tab.note.path, include_locate=True, tab=tab)
        menu.popup_at_pointer(event)

    def _build_note_context_menu(self, note_path, include_locate=False,
                                 tab=None):
        """
        Build the shared context menu for a note (used by both pane-2 right-click
        and tab right-click). Several items carry leading icons. When
        `include_locate` is True an extra "Locate in subfolders" item is added at
        the top (used from a tab, where `tab` is that EditorTab) which reveals
        the note in panes 1 and 2.
        """
        menu = Gtk.Menu()

        if include_locate:
            item_locate = self._icon_menu_item("Locate in subfolders",
                                                "edit-find")
            item_locate.connect(
                "activate",
                lambda _i: self._locate_note_in_panes(note_path))
            menu.append(item_locate)
            menu.append(Gtk.SeparatorMenuItem())

        item_open = self._icon_menu_item("Open in new tab", "tab-new")
        item_open.connect(
            "activate",
            lambda _i: self._load_note_in_new_tab(model.Note(note_path)))
        menu.append(item_open)

        # "Move to subfolder" → a submenu listing every subfolder of the
        # workspace (plus the top level). Confirms before moving.
        item_move = self._icon_menu_item("Move to subfolder", "folder-move")
        item_move.set_submenu(self._build_move_submenu(note_path, tab))
        # Only meaningful with a workspace open.
        item_move.set_sensitive(bool(self.root_folder))
        menu.append(item_move)

        menu.append(Gtk.SeparatorMenuItem())

        item_copy = self._icon_menu_item("Copy full path", "edit-copy")
        item_copy.connect("activate",
                          lambda _i: self._copy_path_to_clipboard(note_path))
        menu.append(item_copy)

        item_browse = self._icon_menu_item("Show in file browser",
                                           "system-file-manager")
        item_browse.connect("activate",
                            lambda _i: self._show_in_file_browser(note_path))
        menu.append(item_browse)

        menu.show_all()
        return menu

    def _build_move_submenu(self, note_path, tab):
        """Submenu of destination subfolders for "Move to subfolder"."""
        submenu = Gtk.Menu()
        if not self.root_folder:
            mi = Gtk.MenuItem(label="(open a workspace first)")
            mi.set_sensitive(False)
            submenu.append(mi)
            submenu.show_all()
            return submenu

        cur_dir = os.path.abspath(os.path.dirname(note_path))
        for rel in model.all_subfolders(self.root_folder):
            dest = (self.root_folder if rel == ""
                    else os.path.join(self.root_folder, rel))
            label = "(top level)" if rel == "" else rel
            mi = Gtk.MenuItem(label=label)
            # Disable the folder the note already lives in.
            if os.path.abspath(dest) == cur_dir:
                mi.set_sensitive(False)
            else:
                mi.connect(
                    "activate",
                    lambda _i, d=dest, lbl=label: self._move_note_to(
                        note_path, d, lbl, tab))
            submenu.append(mi)
        submenu.show_all()
        return submenu

    def _move_note_to(self, note_path, dest_folder, label, tab):
        """Confirm, then move the note into `dest_folder` and refresh UI."""
        name = os.path.basename(note_path)
        if not self._confirm(
                "Move this note?",
                f"\u201c{name}\u201d will be moved to \u201c{label}\u201d."):
            return
        # Find every open tab that points at this note (by old path) so we can
        # update them to the new location after the move. Comparing by path
        # rather than object identity is important: a tab may hold its own
        # throwaway Note for the same file.
        old_abs = os.path.abspath(note_path)
        owning_tabs = [t for t in self._tabs
                       if t.note is not None
                       and os.path.abspath(t.note.path) == old_abs]

        # Move on disk via a single Note (reused by the first owning tab if any,
        # so its in-place path/name update is reflected there too).
        note = owning_tabs[0].note if owning_tabs else model.Note(note_path)
        try:
            new_path = model.move_note(note, dest_folder)
        except OSError as exc:
            self._error_dialog(f"Could not move note:\n{exc}")
            return

        # Point every owning tab at the new path and refresh its title. The
        # buffer content is unchanged by a move, so we don't reload from disk
        # (which also avoids any read at the now-nonexistent old path).
        for t in owning_tabs:
            t.note.path = new_path
            t.note.name = os.path.basename(new_path)
            t._refresh_title()

        # Rebuild panes. Guard the note-list reselection so it does not trigger
        # a reload of the active tab (which could otherwise read a stale path).
        self._reload_sidebar()
        self._note_select_guard = True
        try:
            self._reload_notelist(select_path=new_path)
        finally:
            self._note_select_guard = False
        self.update_status()
        self._refresh_outline()

    def _locate_note_in_panes(self, note_path):
        """
        Reveal `note_path` in the sidebar (pane 1) and note list (pane 2):
        select the subfolder that contains it (or All Notes if it sits at the
        workspace root or outside any immediate subfolder), then select the row.
        """
        if not self.root_folder:
            return
        note_dir = os.path.abspath(os.path.dirname(note_path))
        root = os.path.abspath(self.root_folder)
        # Determine the immediate subfolder (first path component under root)
        # that contains the note, if any.
        target_node = NODE_ALL_NOTES
        target_sub = None
        try:
            rel = os.path.relpath(note_dir, root)
        except ValueError:
            rel = ""
        if rel and not rel.startswith(".."):
            first = rel.split(os.sep)[0]
            if first and first != ".":
                target_sub = first
                target_node = NODE_SUBFOLDER

        # Select the matching sidebar row (which reloads the note list via its
        # selection handler), then select the note row in pane 2.
        self._select_sidebar_node(target_node, target_sub)
        self._reload_notelist(select_path=note_path)

    def _copy_path_to_clipboard(self, path):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(path, -1)
        clipboard.store()

    def _show_in_file_browser(self, path):
        """Open the file's containing folder in the default file manager."""
        folder = os.path.dirname(path)
        uri = GLib.filename_to_uri(folder, None)
        try:
            Gtk.show_uri_on_window(self, uri, Gdk.CURRENT_TIME)
        except GLib.Error as exc:
            self._error_dialog(f"Could not open file browser:\n{exc}")

    def on_new_note(self, _widget):
        if self.read_only:
            self._error_dialog(
                "Read-only mode is on. Release the Read-only button to make "
                "changes.")
            return
        if not self.root_folder:
            self._error_dialog("Open a working folder first (Ctrl+O).")
            return
        # Target folder = the selected subfolder if one is selected, else root.
        if self.current_node == NODE_SUBFOLDER and self.current_subfolder:
            target_dir = os.path.join(self.root_folder, self.current_subfolder)
        else:
            target_dir = self.root_folder

        try:
            path = model.create_empty_note(target_dir)
        except OSError as exc:
            self._error_dialog(f"Could not create note:\n{exc}")
            return
        self._reload_notelist(select_path=path)
        self._load_note_in_active_tab(model.Note(path))
        tab = self._active_tab()
        if tab:
            tab.text_view.grab_focus()

    def on_save_note(self, _widget):
        self._save_active()

    def on_refresh_note(self, _widget):
        """Reload the active tab's note from disk (e.g. changed elsewhere).
        If the tab has unsaved changes, warn first (same prompt as closing)."""
        tab = self._active_tab()
        if tab is None or tab.note is None:
            return
        if self._maybe_warn_unsaved(tab) is False:
            return  # user cancelled
        note = model.Note(tab.note.path)
        if not tab.load_note(note):
            self._error_dialog(f"Could not reload note:\n{note.path}")
            return
        tab.highlight_search(self.search_query)
        self.update_status()

    def on_slugify(self, _widget):
        tab = self._active_tab()
        if tab is None or tab.note is None:
            return
        heading = model.heading_for_slug(tab.get_content())
        if heading is None:
            return
        slug = model.slugify(heading)
        if not slug:
            return

        old_name = tab.note.name
        new_name = slug + ".md"
        if not self._confirm(
                "Rename this note?",
                f"\u201c{old_name}\u201d will be renamed to \u201c{new_name}\u201d."):
            return

        try:
            new_path = model.rename_note(tab.note, slug)
        except OSError as exc:
            self._error_dialog(f"Could not rename note:\n{exc}")
            return
        # tab.note was updated in place by rename_note; refresh title + list.
        tab._refresh_title()
        self._reload_notelist(select_path=new_path)
        self.update_status()

    def on_open_folder(self, _widget):
        dialog = Gtk.FileChooserDialog(
            title="Open Working Folder",
            parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dialog.add_buttons(
            "_Cancel", Gtk.ResponseType.CANCEL,
            "_Open", Gtk.ResponseType.OK,
        )
        if self.root_folder:
            dialog.set_current_folder(self.root_folder)
        if dialog.run() == Gtk.ResponseType.OK:
            folder = dialog.get_filename()
            dialog.destroy()
            self.open_folder(folder)
        else:
            dialog.destroy()

    def on_open_recent(self, _widget, folder):
        if not os.path.isdir(folder):
            self._error_dialog(f"Folder no longer exists:\n{folder}")
            # Drop the dead entry and refresh.
            self.settings.recent_folders = [
                f for f in self.settings.recent_folders if f != folder
            ]
            self.settings.save()
            self._rebuild_recent_menu()
            return
        if self._maybe_warn_unsaved(self._active_tab()) is False:
            return
        self.open_folder(folder)

    def on_preferences(self, _widget):
        dialog = PreferencesDialog(self, self.settings,
                                   on_apply=self._apply_preferences)
        dialog.run_modal()

    def _apply_preferences(self):
        """Re-theme tabs and toolbar after a preferences change."""
        self._apply_editor_font()
        self._apply_code_font()
        self._apply_preview_font()
        self._apply_line_spacing()
        self._apply_toolbar_style()
        self._apply_tab_title_length()
        self._apply_icon_set()

    def on_about(self, _widget):
        dialog = Gtk.AboutDialog(transient_for=self, modal=True)
        dialog.set_program_name(APP_NAME)
        dialog.set_comments(
            "A three-pane markdown notebook for the MATE / GNOME2-era desktop.")
        self._set_about_logo(dialog)
        dialog.run()
        dialog.destroy()

    def _set_about_logo(self, dialog):
        """
        Give the About dialog the same icon the app is using: the custom icon
        set when one is configured (a large PNG/SVG loaded as a pixbuf), the
        installed themed name as a fallback, else the stock icon name.
        """
        files = icon_set_files(self.settings.icon_set_dir)
        if files:
            from gi.repository import GdkPixbuf
            # Prefer the SVG, then the largest PNG, rendered at 64px.
            source = files.get("scalable")
            if source is None:
                for size in sorted((k for k in files if isinstance(k, int)),
                                   reverse=True):
                    source = files[size]
                    break
            if source is not None:
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                        source, 64, 64)
                    dialog.set_logo(pixbuf)
                    return
                except GLib.Error:
                    pass
            # Pixbuf load failed but a set exists: use the themed name we install.
            dialog.set_logo_icon_name(APP_ICON_NAME)
            return
        dialog.set_logo_icon_name("accessories-text-editor")

    def on_sort_changed(self, widget, mode):
        if widget.get_active():
            self.sort_mode = mode
            # Persist the choice when "remember sort order" is enabled.
            if self.settings.remember_sort:
                self.settings.set_sort_mode(mode)
                self.settings.save()
            tab = self._active_tab()
            keep = tab.note.path if (tab and tab.note) else None
            self._reload_notelist(select_path=keep)

    def _reselect_active_note(self):
        """
        After a cancelled note switch, restore the list selection to whatever
        the active tab currently holds (or clear it). Guarded so the
        selection-changed handler does not re-trigger a load.
        """
        tab = self._active_tab()
        target = tab.note.path if (tab and tab.note) else None
        self._note_select_guard = True
        try:
            sel = self.note_view.get_selection()
            sel.unselect_all()
            if target:
                for row in self.note_store:
                    if row[1] == target:
                        sel.select_iter(row.iter)
                        break
        finally:
            self._note_select_guard = False

    def on_quit(self, _widget):
        if self._confirm_close_all() is False:
            return
        self._save_session()
        Gtk.main_quit()

    def _on_delete_event(self, _widget, _event):
        if self._confirm_close_all() is False:
            return True  # cancel close
        self._save_session()
        return False

    def _save_session(self):
        """
        Persist the current workspace, the set of open notes, and the sidebar /
        note-list selection so they can be restored next launch (only meaningful
        when "restore session" is on, but we record it regardless so toggling the
        option later just works).
        """
        open_notes = [tab.note.path for tab in self._tabs
                      if tab.note is not None]
        # Current pane-2 selection (path), if any.
        sel = self.note_view.get_selection()
        _m, it = sel.get_selected()
        selected_note = self.note_store[it][1] if it is not None else None
        self.settings.set_last_session(
            self.root_folder, open_notes,
            node=self.current_node,
            subfolder=self.current_subfolder,
            selected_note=selected_note)
        self.settings.save()

    def _confirm_close_all(self):
        """Prompt for every dirty tab before quitting. False cancels the quit."""
        for tab in list(self._tabs):
            if self._maybe_warn_unsaved(tab) is False:
                return False
        return True


    # ---------------------------------------------------------- dialogs -- #
    def _maybe_warn_unsaved(self, tab):
        """
        If `tab` has unsaved changes, ask the user. Returns False if the pending
        action should be cancelled, True otherwise. A None tab is treated as
        clean (nothing to lose).
        """
        if tab is None or not tab.dirty or not tab.note:
            return True
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text=f"Save changes to \u201c{tab.note.display_name()}\u201d?",
        )
        dialog.add_buttons(
            "Discard", Gtk.ResponseType.NO,
            "_Cancel", Gtk.ResponseType.CANCEL,
            "_Save", Gtk.ResponseType.YES,
        )
        resp = dialog.run()
        dialog.destroy()
        if resp == Gtk.ResponseType.YES:
            tab.save()
            return True
        if resp == Gtk.ResponseType.NO:
            tab.dirty = False
            return True
        return False  # cancelled

    def _error_dialog(self, message):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=message,
        )
        dialog.run()
        dialog.destroy()

    def _confirm(self, primary, secondary=None):
        """Yes/No confirmation dialog. Returns True if the user confirmed."""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=primary,
        )
        if secondary:
            dialog.format_secondary_text(secondary)
        resp = dialog.run()
        dialog.destroy()
        return resp == Gtk.ResponseType.OK

    def on_refresh_workspace(self, _widget):
        """
        Re-scan the working folder from disk and rebuild panes 1 and 2, keeping
        the current sidebar selection (and the pane-2 note selection) where
        possible. Open tabs are left untouched. No-op without a workspace.
        """
        if not self.root_folder:
            self._error_dialog("Open a working folder first (Ctrl+O).")
            return
        if not os.path.isdir(self.root_folder):
            self._error_dialog(
                f"Working folder no longer exists:\n{self.root_folder}")
            return
        # Preserve the pane-2 selection by path across the rebuild.
        sel = self.note_view.get_selection()
        _m, it = sel.get_selected()
        keep = self.note_store[it][1] if it is not None else None
        # Rebuilding the sidebar with preserve_selection reloads pane 2 via the
        # selection handler; then restore the note selection.
        self._reload_sidebar(preserve_selection=True)
        self._reload_notelist(select_path=keep)
        self.update_status()

    def on_close_workspace(self, _widget):
        """Close the current workspace, returning to the empty initial state."""
        if self._confirm_close_all() is False:
            return
        self.root_folder = None
        self.current_node = NODE_ALL_NOTES
        self.current_subfolder = None
        self.search_query = None
        self._search_no_results = False
        self.search_entry.set_text("")
        self.set_title(APP_NAME)
        self.sidebar_store.clear()
        self.note_store.clear()
        self.notelist_stack.set_visible_child_name("list")
        for tab in self._tabs:
            tab.clear()
        self.update_status()


    # ------------------------------------------------------- view toggles -- #
    def on_toggle_toolbar(self, item):
        self.toolbar.set_visible(item.get_active())

    def on_toggle_statusbar(self, item):
        self.statusbar_box.set_visible(item.get_active())


    # ------------------------------------------------------------ search -- #
    def on_search(self, _widget):
        """Run the search from the entry's current text (ENTER or button)."""
        text = self.search_entry.get_text().strip()
        # An empty box means no filter.
        self.search_query = text or None
        self._reload_notelist()
        self._apply_search_highlight()

    def on_search_icon_press(self, entry, icon_pos, _event):
        """Clear icon pressed: empty the box and drop the filter."""
        if icon_pos == Gtk.EntryIconPosition.SECONDARY:
            entry.set_text("")
            self.search_query = None
            self._reload_notelist()
            self._apply_search_highlight()

    def _apply_search_highlight(self):
        """(#5) Highlight the current search term in the active tab's document.
        A cleared search removes the highlight."""
        tab = self._active_tab()
        if tab is not None:
            tab.highlight_search(self.search_query)


    # ----------------------------------------------------------- editor -- #
    def _load_note_in_active_tab(self, note):
        tab = self._active_tab()
        if tab is None:
            tab = self._new_tab(focus=True)
        if not tab.load_note(note):
            self._error_dialog(f"Could not open note:\n{note.path}")
            return
        tab.highlight_search(self.search_query)
        self.update_status()
        self._refresh_outline()

    def _load_note_in_new_tab(self, note):
        tab = self._new_tab(focus=True)
        if not tab.load_note(note):
            self._error_dialog(f"Could not open note:\n{note.path}")
            return
        tab.highlight_search(self.search_query)
        self.update_status()
        self._refresh_outline()

    def _save_active(self):
        tab = self._active_tab()
        if tab is None or not tab.note:
            return False
        if not tab.save():
            self._error_dialog(f"Could not save note:\n{tab.note.path}")
            return False
        self.update_status()
        return True
