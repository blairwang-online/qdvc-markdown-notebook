"""
window.py — NotebookWindow: the view + controller for QDVC Markdown Notebook.

GTK and controller logic live together here, which is idiomatic for GTK (signal
handlers are wired directly to widgets). All filesystem and business logic is
delegated to qdvcmdnb_lib.model so this layer never touches disk directly.
"""

import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango  # noqa: E402

from . import model
from .config import (
    APP_NAME,
    SORT_ALPHA,
    SORT_DATE_NEW,
    SORT_DATE_OLD,
    ALL_NOTES,
)
from .highlighter import MarkdownHighlighter
from .settings import Settings


class NotebookWindow(Gtk.Window):

    def __init__(self, root_folder=None):
        super().__init__(title=APP_NAME)
        self.set_default_size(1000, 640)

        self.settings = Settings.load()

        self.root_folder = None
        self.current_note = None          # Note currently open in editor
        self.current_subfolder = ALL_NOTES
        self.sort_mode = SORT_ALPHA
        self._dirty = False
        self._loading = False             # guard against spurious "changed"

        self._build_ui()
        self._apply_editor_font()
        self._rebuild_recent_menu()

        if root_folder:
            self.open_folder(os.path.abspath(root_folder))

        self.connect("destroy", Gtk.main_quit)
        self.connect("delete-event", self._on_delete_event)

    # ----------------------------------------------------------------- UI -- #
    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(vbox)

        vbox.pack_start(self._build_menubar(), False, False, 0)
        vbox.pack_start(self._build_toolbar(), False, False, 0)

        # Three-pane layout via nested GtkPaned.
        outer = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        inner = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)

        outer.pack1(self._build_sidebar(), resize=False, shrink=False)
        outer.pack2(inner, resize=True, shrink=False)
        inner.pack1(self._build_notelist(), resize=False, shrink=False)
        inner.pack2(self._build_editor(), resize=True, shrink=False)

        outer.set_position(200)
        inner.set_position(280)

        vbox.pack_start(outer, True, True, 0)
        vbox.pack_start(self._build_statusbar(), False, False, 0)

    def _build_menubar(self):
        menubar = Gtk.MenuBar()
        accel = Gtk.AccelGroup()
        self.add_accel_group(accel)

        # ---- File menu ----
        file_menu = Gtk.Menu()
        file_item = Gtk.MenuItem(label="File")
        file_item.set_submenu(file_menu)

        mi_new = Gtk.MenuItem(label="New")
        mi_new.add_accelerator("activate", accel, Gdk.KEY_n,
                               Gdk.ModifierType.CONTROL_MASK,
                               Gtk.AccelFlags.VISIBLE)
        mi_new.connect("activate", self.on_new_note)
        file_menu.append(mi_new)

        mi_save = Gtk.MenuItem(label="Save")
        mi_save.add_accelerator("activate", accel, Gdk.KEY_s,
                                Gdk.ModifierType.CONTROL_MASK,
                                Gtk.AccelFlags.VISIBLE)
        mi_save.connect("activate", self.on_save_note)
        file_menu.append(mi_save)

        mi_open = Gtk.MenuItem(label="Open Working Folder")
        mi_open.add_accelerator("activate", accel, Gdk.KEY_o,
                                Gdk.ModifierType.CONTROL_MASK,
                                Gtk.AccelFlags.VISIBLE)
        mi_open.connect("activate", self.on_open_folder)
        file_menu.append(mi_open)

        # "Open Recent" submenu, populated dynamically from settings.
        self.recent_menu_item = Gtk.MenuItem(label="Open Recent")
        self.recent_menu = Gtk.Menu()
        self.recent_menu_item.set_submenu(self.recent_menu)
        file_menu.append(self.recent_menu_item)

        file_menu.append(Gtk.SeparatorMenuItem())

        mi_quit = Gtk.MenuItem(label="Quit")
        # Note: the spec listed Ctrl+S for Quit; that collides with Save,
        # so Quit is bound to the conventional Ctrl+Q instead. See MAINTENANCE.md.
        mi_quit.add_accelerator("activate", accel, Gdk.KEY_q,
                                Gdk.ModifierType.CONTROL_MASK,
                                Gtk.AccelFlags.VISIBLE)
        mi_quit.connect("activate", self.on_quit)
        file_menu.append(mi_quit)

        menubar.append(file_item)

        # ---- View menu ----
        view_menu = Gtk.Menu()
        view_item = Gtk.MenuItem(label="View")
        view_item.set_submenu(view_menu)

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

        view_menu.append(Gtk.SeparatorMenuItem())

        mi_font = Gtk.MenuItem(label="Set Editor Font\u2026")
        mi_font.connect("activate", self.on_choose_font)
        view_menu.append(mi_font)

        menubar.append(view_item)
        return menubar

    def _build_toolbar(self):
        toolbar = Gtk.Toolbar()
        toolbar.set_style(Gtk.ToolbarStyle.BOTH)

        btn_new = Gtk.ToolButton(icon_name="document-new")
        btn_new.set_label("New note")
        btn_new.set_tooltip_text("Create a new note in the selected folder")
        btn_new.connect("clicked", self.on_new_note)
        toolbar.insert(btn_new, -1)

        btn_save = Gtk.ToolButton(icon_name="document-save")
        btn_save.set_label("Save note")
        btn_save.set_tooltip_text("Save the current note")
        btn_save.connect("clicked", self.on_save_note)
        toolbar.insert(btn_save, -1)

        return toolbar

    def _build_sidebar(self):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        # Columns: display label (str), folder name or "" for All Notes (str),
        #          is_all_notes (bool)
        self.sidebar_store = Gtk.TreeStore(str, str, bool)
        self.sidebar_view = Gtk.TreeView(model=self.sidebar_store)
        self.sidebar_view.set_headers_visible(False)

        renderer = Gtk.CellRendererText()
        col = Gtk.TreeViewColumn("Folders", renderer, text=0)
        self.sidebar_view.append_column(col)

        self.sidebar_view.get_selection().connect(
            "changed", self.on_sidebar_selection_changed)

        scroll.add(self.sidebar_view)
        return scroll

    def _build_notelist(self):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        # Columns: display name (str), full path (str), mtime (float)
        self.note_store = Gtk.ListStore(str, str, float)
        self.note_view = Gtk.TreeView(model=self.note_store)
        self.note_view.set_headers_visible(False)

        renderer = Gtk.CellRendererText()
        renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
        col = Gtk.TreeViewColumn("Notes", renderer, text=0)
        self.note_view.append_column(col)

        self.note_view.get_selection().connect(
            "changed", self.on_note_selection_changed)

        scroll.add(self.note_view)
        return scroll

    def _build_editor(self):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.text_buffer = Gtk.TextBuffer()
        self.text_view = Gtk.TextView(buffer=self.text_buffer)
        self.text_view.set_monospace(True)
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text_view.set_left_margin(8)
        self.text_view.set_right_margin(8)
        self.text_view.set_top_margin(8)
        self.text_view.set_bottom_margin(8)

        # The actual font is applied by _apply_editor_font() from settings,
        # called once after the UI is built and again when the user changes it.

        self.highlighter = MarkdownHighlighter(self.text_buffer)
        self.text_buffer.connect("changed", self.on_text_changed)

        scroll.add(self.text_view)
        return scroll

    def _build_statusbar(self):
        self.statusbar = Gtk.Statusbar()
        self._status_ctx = self.statusbar.get_context_id("main")
        return self.statusbar

    # ----------------------------------------------------------- settings -- #
    def _apply_editor_font(self):
        """Apply the editor font from settings to the TextView."""
        font = Pango.FontDescription(self.settings.editor_font)
        self.text_view.override_font(font)

    def _rebuild_recent_menu(self):
        """Repopulate the File > Open Recent submenu from settings."""
        for child in self.recent_menu.get_children():
            self.recent_menu.remove(child)

        recents = self.settings.recent_folders
        if not recents:
            placeholder = Gtk.MenuItem(label="(none)")
            placeholder.set_sensitive(False)
            self.recent_menu.append(placeholder)
        else:
            for folder in recents:
                item = Gtk.MenuItem(label=folder)
                item.connect("activate", self.on_open_recent, folder)
                self.recent_menu.append(item)
        self.recent_menu.show_all()

    def _remember_folder(self, folder):
        """Record a folder as recent, persist, and refresh the menu."""
        self.settings.add_recent_folder(folder)
        self.settings.save()
        self._rebuild_recent_menu()

    # -------------------------------------------------------- status bar -- #
    def update_status(self):
        count = len(self.note_store)
        if self.current_note:
            sel = self.current_note.display_name()
        else:
            sel = "none"
        msg = f"{count} item(s)  |  Selected: {sel}"
        if self._dirty:
            msg += "  *"
        self.statusbar.pop(self._status_ctx)
        self.statusbar.push(self._status_ctx, msg)

    # ------------------------------------------------------ folder logic -- #
    def open_folder(self, folder):
        if not folder or not os.path.isdir(folder):
            self._error_dialog(f"Not a folder:\n{folder}")
            return
        self.root_folder = folder
        self.set_title(f"{APP_NAME} \u2014 {folder}")
        self.current_subfolder = ALL_NOTES
        self.current_note = None
        self._reload_sidebar()
        self._reload_notelist()
        self._clear_editor()
        self.update_status()
        self._remember_folder(folder)

    def _reload_sidebar(self):
        self.sidebar_store.clear()
        # Top segment: "All Notes".
        self.sidebar_store.append(None, ["All Notes", "", True])
        # Bottom segment: immediate subfolders.
        if self.root_folder:
            for sub in model.immediate_subfolders(self.root_folder):
                self.sidebar_store.append(None, [sub, sub, False])
        # Select "All Notes" by default.
        self.sidebar_view.get_selection().select_path(Gtk.TreePath.new_first())

    def _notes_for_current_subfolder(self):
        if not self.root_folder:
            return []
        if self.current_subfolder is ALL_NOTES:
            return model.collect_notes(self.root_folder)
        folder = os.path.join(self.root_folder, self.current_subfolder)
        return model.collect_notes(folder)

    def _reload_notelist(self, select_path=None):
        self.note_store.clear()
        notes = model.sort_notes(
            self._notes_for_current_subfolder(), self.sort_mode)
        for n in notes:
            self.note_store.append([n.display_name(), n.path, n.mtime])

        if select_path:
            # Re-select a specific note by its file path after reload.
            for row in self.note_store:
                if row[1] == select_path:
                    self.note_view.get_selection().select_iter(row.iter)
                    break
        self.update_status()

    # ----------------------------------------------------------- editor -- #
    def _clear_editor(self):
        self._loading = True
        self.text_buffer.set_text("")
        self._loading = False
        self._dirty = False

    def _load_note(self, note):
        try:
            content = model.read_note(note)
        except (OSError, UnicodeDecodeError) as exc:
            self._error_dialog(f"Could not open note:\n{exc}")
            return
        self._loading = True
        self.text_buffer.set_text(content)
        self._loading = False
        self.current_note = note
        self._dirty = False
        self.highlighter.highlight()
        self.update_status()

    def _save_current(self):
        if not self.current_note:
            return False
        start = self.text_buffer.get_start_iter()
        end = self.text_buffer.get_end_iter()
        content = self.text_buffer.get_text(start, end, True)
        try:
            model.write_note(self.current_note, content)
        except OSError as exc:
            self._error_dialog(f"Could not save note:\n{exc}")
            return False
        self._dirty = False
        self.update_status()
        return True

    # --------------------------------------------------------- handlers -- #
    def on_sidebar_selection_changed(self, selection):
        model_, treeiter = selection.get_selected()
        if treeiter is None:
            return
        is_all = model_[treeiter][2]
        if is_all:
            self.current_subfolder = ALL_NOTES
        else:
            self.current_subfolder = model_[treeiter][1]
        self.current_note = None
        self._clear_editor()
        self._reload_notelist()

    def on_note_selection_changed(self, selection):
        model_, treeiter = selection.get_selected()
        if treeiter is None:
            return
        if self._maybe_warn_unsaved() is False:
            return
        path = model_[treeiter][1]
        self._load_note(model.Note(path))

    def on_text_changed(self, _buffer):
        if self._loading:
            return
        self._dirty = True
        self.highlighter.highlight()
        self.update_status()

    def on_new_note(self, _widget):
        if not self.root_folder:
            self._error_dialog("Open a working folder first (Ctrl+O).")
            return
        # Target folder = currently selected subfolder, else the root.
        if self.current_subfolder is ALL_NOTES:
            target_dir = self.root_folder
        else:
            target_dir = os.path.join(self.root_folder, self.current_subfolder)

        try:
            path = model.create_empty_note(target_dir)
        except OSError as exc:
            self._error_dialog(f"Could not create note:\n{exc}")
            return
        self._reload_notelist(select_path=path)
        self._load_note(model.Note(path))
        self.text_view.grab_focus()

    def on_save_note(self, _widget):
        self._save_current()

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
        if self._maybe_warn_unsaved() is False:
            return
        self.open_folder(folder)

    def on_choose_font(self, _widget):
        dialog = Gtk.FontChooserDialog(title="Set Editor Font", parent=self)
        dialog.set_font(self.settings.editor_font)
        # Only the markdown editor is themed; a sample hints at the use.
        dialog.set_preview_text("# Heading\nBody text 0123 *italic* `code`")
        if dialog.run() == Gtk.ResponseType.OK:
            chosen = dialog.get_font()
            if chosen:
                self.settings.set_editor_font(chosen)
                self.settings.save()
                self._apply_editor_font()
        dialog.destroy()

    def on_sort_changed(self, widget, mode):
        if widget.get_active():
            self.sort_mode = mode
            keep = self.current_note.path if self.current_note else None
            self._reload_notelist(select_path=keep)

    def on_quit(self, _widget):
        if self._maybe_warn_unsaved() is False:
            return
        Gtk.main_quit()

    def _on_delete_event(self, _widget, _event):
        if self._maybe_warn_unsaved() is False:
            return True  # cancel close
        return False

    # ---------------------------------------------------------- dialogs -- #
    def _maybe_warn_unsaved(self):
        """
        If there are unsaved changes, ask the user. Returns False if the
        pending action should be cancelled, True otherwise.
        """
        if not self._dirty or not self.current_note:
            return True
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text="Save changes to the current note?",
        )
        dialog.add_buttons(
            "Discard", Gtk.ResponseType.NO,
            "_Cancel", Gtk.ResponseType.CANCEL,
            "_Save", Gtk.ResponseType.YES,
        )
        resp = dialog.run()
        dialog.destroy()
        if resp == Gtk.ResponseType.YES:
            self._save_current()
            return True
        if resp == Gtk.ResponseType.NO:
            self._dirty = False
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
