# -*- coding: utf-8 -*-
"""
Notebook renderer package.

Public API is wired in ``notebook.facade`` (assembled pages, schematics, export).
Submodules under ``assemble/``, ``export/``, ``html/``, ``mpl/`` hold internals.
"""
from notebook.constants import _BOT_EXPORT_DPI
from notebook.facade import (
    build_beam_schematic_figure,
    build_cantilever_page_html,
    build_cantilever_schematic_figure,
    build_page_html,
    _fig_to_png_bytes,
    _pdf_to_png_bytes,
)
from notebook.html.math_format import clean_math_signs
from notebook.export.pdf import _html_to_pdf_bytes, _stamp_notebook_grid_on_pdf

__all__ = [
    "build_page_html",
    "build_cantilever_page_html",
    "build_beam_schematic_figure",
    "build_cantilever_schematic_figure",
    "clean_math_signs",
    "_html_to_pdf_bytes",
    "_pdf_to_png_bytes",
    "_fig_to_png_bytes",
    "_stamp_notebook_grid_on_pdf",
    "_BOT_EXPORT_DPI",
]
