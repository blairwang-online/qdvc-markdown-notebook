"""
config.py — shared constants and sentinels for QDVC Markdown Notebook.

This module has no GTK or filesystem dependencies, so it can be imported
freely from any layer.
"""

APP_NAME = "QDVC Markdown Notebook"

# Filename extensions treated as markdown notes.
MARKDOWN_EXTENSIONS = (".md", ".markdown", ".mdown", ".mkd", ".txt")

# Sort modes for the note list.
SORT_ALPHA = "alpha"
SORT_DATE_NEW = "date_new"
SORT_DATE_OLD = "date_old"

# Sentinel object representing the "All Notes" virtual folder in the sidebar.
# Compare with `is`, never `==`.
ALL_NOTES = object()
