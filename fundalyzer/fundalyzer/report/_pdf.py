"""PDF export for the deep-dive Markdown document.

Strategy: invoke pandoc if it is available on PATH.
If pandoc is not found, emit a clear installation message rather than
failing silently or importing a heavy optional dependency.

Pandoc can be installed system-wide (brew install pandoc / apt install pandoc)
or via the Python wrapper: pip install pandoc.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def export_pdf(markdown_path: Path, pdf_path: Path | None = None) -> Path:
    """Convert *markdown_path* to PDF and return the PDF path.

    Requires pandoc to be available on PATH.  Uses the LaTeX pipeline
    (xelatex) for best typography; falls back to wkhtmltopdf if xelatex
    is not found.

    Args:
        markdown_path: path to the Markdown file to convert.
        pdf_path:      desired output path.  Defaults to the same
                       directory and stem as *markdown_path* with `.pdf`.

    Returns:
        Path to the generated PDF.

    Raises:
        RuntimeError: if pandoc is not installed or conversion fails.
    """
    if pdf_path is None:
        pdf_path = markdown_path.with_suffix(".pdf")

    pandoc = shutil.which("pandoc")
    if pandoc is None:
        raise RuntimeError(
            "pandoc is not installed. Install it with:\n"
            "  macOS:   brew install pandoc\n"
            "  Ubuntu:  sudo apt install pandoc texlive-xetex\n"
            "  pip:     pip install pandoc\n\n"
            f"Markdown report saved to: {markdown_path}"
        )

    # Prefer xelatex (handles Unicode); fall back to pdflatex or wkhtmltopdf.
    latex_engine = "xelatex" if shutil.which("xelatex") else "pdflatex"
    has_latex = shutil.which(latex_engine) is not None

    cmd: list[str]
    if has_latex:
        cmd = [
            pandoc,
            str(markdown_path),
            "--output", str(pdf_path),
            f"--pdf-engine={latex_engine}",
            "--variable", "geometry:margin=2.5cm",
            "--variable", "colorlinks=true",
            "--toc",
        ]
    elif shutil.which("wkhtmltopdf"):
        cmd = [
            pandoc,
            str(markdown_path),
            "--output", str(pdf_path),
            "--pdf-engine=wkhtmltopdf",
        ]
    else:
        raise RuntimeError(
            "pandoc is installed but no PDF engine was found.\n"
            "Install one of:\n"
            "  xelatex:     sudo apt install texlive-xetex  (or brew install texlive)\n"
            "  wkhtmltopdf: sudo apt install wkhtmltopdf\n\n"
            f"Markdown report saved to: {markdown_path}"
        )

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"pandoc failed (exit {result.returncode}):\n{result.stderr}\n\n"
            f"Markdown report saved to: {markdown_path}"
        )

    return pdf_path
