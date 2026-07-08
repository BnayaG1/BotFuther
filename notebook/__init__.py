"""
Notebook renderer package.

Internal refactor of `beam_notebook.py`. Public API remains in `beam_notebook.py`
for backwards compatibility; new code may import from submodules directly.
"""

from notebook.assemble.cantilever import build_cantilever_page_html
from notebook.assemble.page import build_page_html
from notebook.export.pdf import _html_to_pdf_bytes, _stamp_notebook_grid_on_pdf
from notebook.export.png import _fig_to_png_bytes, _pdf_to_png_bytes
from notebook.html.math_format import clean_math_signs

__all__ = [
    "build_page_html",
    "build_cantilever_page_html",
    "clean_math_signs",
    "_html_to_pdf_bytes",
    "_pdf_to_png_bytes",
    "_fig_to_png_bytes",
    "_stamp_notebook_grid_on_pdf",
]
