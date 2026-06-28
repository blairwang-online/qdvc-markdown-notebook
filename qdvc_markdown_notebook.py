#!/usr/bin/env python3
"""
qdvc_markdown_notebook.py

A three-pane markdown notebook viewer/editor for the MATE / GNOME2-era
desktop, built with GTK 3 via PyGObject.

Usage:
    python3 qdvc_markdown_notebook.py /path/to/markdown/data
    python3 qdvc_markdown_notebook.py        # start empty, open folder via Ctrl+O

This file is a thin entry point. Application logic lives in the qdvcmdnb_lib
package (config, model, highlighter, window). See MAINTENANCE.md.
"""

import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from qdvcmdnb_lib.window import NotebookWindow


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else None
    win = NotebookWindow(root_folder=root)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
