"""
model.py — pure-Python data layer for QDVC Markdown Notebook.

No GTK imports here. Everything in this module is testable without a display.
It covers the Note value object, filesystem discovery (subfolders, note
collection), sorting, and all disk read/write/create operations.
"""

import os
import time

from .config import (
    MARKDOWN_EXTENSIONS,
    SORT_ALPHA,
    SORT_DATE_NEW,
    SORT_DATE_OLD,
)


class Note:
    """A single markdown file on disk."""

    __slots__ = ("path", "name", "mtime")

    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        try:
            self.mtime = os.path.getmtime(path)
        except OSError:
            self.mtime = 0.0

    def display_name(self):
        base = self.name
        for ext in MARKDOWN_EXTENSIONS:
            if base.lower().endswith(ext):
                return base[: -len(ext)]
        return base


def is_markdown(filename):
    return filename.lower().endswith(MARKDOWN_EXTENSIONS)


def collect_notes(folder):
    """
    Return a list of Note objects for all markdown files at any depth under
    `folder`. Used for "All Notes" and for an aggregated subfolder view.
    """
    notes = []
    for root, _dirs, files in os.walk(folder):
        for f in files:
            if is_markdown(f):
                notes.append(Note(os.path.join(root, f)))
    return notes


def immediate_subfolders(root):
    """Return sorted list of immediate subfolder names of `root`."""
    try:
        entries = os.listdir(root)
    except OSError:
        return []
    subs = [
        e for e in entries
        if os.path.isdir(os.path.join(root, e)) and not e.startswith(".")
    ]
    return sorted(subs, key=str.lower)


def sort_notes(notes, sort_mode):
    """Return a new list of notes ordered according to `sort_mode`."""
    if sort_mode == SORT_ALPHA:
        return sorted(notes, key=lambda n: n.display_name().lower())
    if sort_mode == SORT_DATE_NEW:
        return sorted(notes, key=lambda n: n.mtime, reverse=True)
    if sort_mode == SORT_DATE_OLD:
        return sorted(notes, key=lambda n: n.mtime)
    return list(notes)


# --------------------------------------------------------------------------- #
# Disk I/O
#
# These functions raise OSError / UnicodeDecodeError on failure; the caller
# (the window) is responsible for presenting errors to the user. Keeping the
# I/O here means the view never touches the filesystem directly.
# --------------------------------------------------------------------------- #
def read_note(note):
    """Read and return the text content of `note`. May raise."""
    with open(note.path, "r", encoding="utf-8") as fh:
        return fh.read()


def write_note(note, content):
    """
    Write `content` to `note` on disk and refresh its mtime. May raise.

    Writes are not atomic; see MAINTENANCE.md for the os.replace upgrade path.
    """
    with open(note.path, "w", encoding="utf-8") as fh:
        fh.write(content)
    note.mtime = time.time()


def unique_note_path(folder, base="Untitled", ext=".md"):
    """
    Return a path inside `folder` for a new note that does not collide with an
    existing file: 'Untitled.md', 'Untitled 1.md', 'Untitled 2.md', ...
    """
    candidate = os.path.join(folder, base + ext)
    i = 1
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{base} {i}{ext}")
        i += 1
    return candidate


def create_empty_note(folder, base="Untitled", ext=".md"):
    """Create a new empty note file in `folder` and return its path. May raise."""
    path = unique_note_path(folder, base=base, ext=ext)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("")
    return path
