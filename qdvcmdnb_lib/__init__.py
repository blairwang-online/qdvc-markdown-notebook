"""
qdvcmdnb_lib — internal package for QDVC Markdown Notebook.

Modules:
    config       Constants and shared sentinels.
    model        Pure-Python data layer (no GTK): notes + file I/O.
    highlighter  MarkdownHighlighter (GTK TextBuffer tagging).
    window       NotebookWindow (view + controller).
"""

__all__ = ["config", "model", "highlighter", "window"]
