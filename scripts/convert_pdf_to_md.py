"""Convert scanned PDF to clean Markdown using rapidocr-onnxruntime.

Usage:
    uv run python scripts/convert_pdf_to_md.py            # 全量转换
    uv run python scripts/convert_pdf_to_md.py --test      # 仅前 3 页测试
    uv run python scripts/convert_pdf_to_md.py --pages 20  # 前 20 页

This is a one-time conversion utility for the student handbook PDF.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import fitz  # pymupdf
import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

PDF_PATH = (
    Path(__file__).resolve().parent.parent
    / "cli_campus"
    / "data"
    / "resources"
    / "东南大学大学生手册2025.pdf"
)
DEFAULT_OUTPUT = PDF_PATH.parent / "student_handbook.md"

# OCR engine (singleton)
ocr = RapidOCR()

# ---------------------------------------------------------------------------
# Noise filters — remove PDF.js viewer artifacts and sidebar fragments
# ---------------------------------------------------------------------------

# Regex patterns matching lines that should be dropped entirely
_NOISE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^https?://"),  # URLs
    re.compile(r"^\d+/\d+$"),  # page numbers like "3/114"
    re.compile(r"^PDF\.?js\s*viewer$", re.I),  # PDF.js viewer header
    re.compile(r"^\d{4}/\d{1,2}/\d{1,2}"),  # date stamps like "2026/4/4 11:44"
]

# Short sidebar fragments commonly leaked from page edges.
# These are partial section headers that appear vertically on the page margin.
_SIDEBAR_FRAGMENTS: set[str] = {
    "学",
    "理",
    "籍管",
    "教学与学铺",
    "教学与学籍",
    "第一部分",
    "第二部分",
    "第三部分",
    "第四部分",
    "第五部分",
    "第六部分",
    "第七部分",
    "第八部分",
    "学生管理",
    "奖励与处分",
    "资助管理",
    "日常管理",
    "心理健康",
    "校园文化",
}


def _is_noise(text: str) -> bool:
    """Return True if *text* is a known noise fragment to skip."""
    s = text.strip()
    if not s or len(s) <= 1:
        return True
    if s in _SIDEBAR_FRAGMENTS:
        return True
    return any(p.match(s) for p in _NOISE_PATTERNS)


# ---------------------------------------------------------------------------
# Core conversion helpers
# ---------------------------------------------------------------------------


def pdf_page_to_image(page: fitz.Page, dpi: int = 300) -> np.ndarray:
    """Render a PDF page to a numpy RGB array at given DPI."""
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return np.array(img)


def ocr_page(img: np.ndarray) -> list[tuple[list, str, float]]:
    """Run OCR on a page image, return list of (box, text, confidence)."""
    result, _ = ocr(img)
    return result or []


def page_ocr_to_text(ocr_results: list, page_width: int) -> str:
    """Convert OCR results from a single page to plain text.

    Handles two-column layouts by splitting into left/right halves
    at the page midpoint, then reading left column top-to-bottom
    before right column.
    """
    if not ocr_results:
        return ""

    # Build item list: (y_center, x_center, width, text)
    items: list[tuple[float, float, float, str]] = []
    for box, text, _conf in ocr_results:
        text = text.strip()
        if _is_noise(text):
            continue
        y_center = (box[0][1] + box[2][1]) / 2
        x_left = box[0][0]
        x_right = box[2][0]
        x_center = (x_left + x_right) / 2
        box_width = x_right - x_left
        items.append((y_center, x_center, box_width, text))

    if not items:
        return ""

    # Detect two-column layout: check if most items sit in either left or right half
    mid_x = page_width / 2
    left_items = [(y, x, w, t) for y, x, w, t in items if x < mid_x * 0.9]
    right_items = [(y, x, w, t) for y, x, w, t in items if x >= mid_x * 0.9]

    # Wide items (spanning > 60% of page width) are full-width (headers, etc.)
    wide_threshold = page_width * 0.6
    wide_items = [(y, x, w, t) for y, x, w, t in items if w > wide_threshold]

    # Two-column detected if both halves have significant content
    is_two_col = len(left_items) > 5 and len(right_items) > 5

    if is_two_col:
        # Process wide items first (these span both columns, usually headers)
        # Then left column, then right column
        narrow_left = [(y, x, w, t) for y, x, w, t in left_items if w <= wide_threshold]
        narrow_right = [
            (y, x, w, t) for y, x, w, t in right_items if w <= wide_threshold
        ]

        ordered = []
        # Wide items by y
        for y, x, w, t in sorted(wide_items, key=lambda i: i[0]):
            ordered.append((y, t))
        # Left column by y
        for y, x, w, t in sorted(narrow_left, key=lambda i: i[0]):
            ordered.append((y + 0.001, t))  # slight offset to keep wide items first
        # Right column after left
        max_left_y = max((y for y, *_ in narrow_left), default=0)
        for y, x, w, t in sorted(narrow_right, key=lambda i: i[0]):
            ordered.append((max_left_y + y + 1, t))

        return "\n".join(t for _, t in sorted(ordered, key=lambda i: i[0]))
    else:
        # Single-column: group into lines by vertical proximity
        items.sort(key=lambda t: (t[0], t[1]))
        lines: list[list[tuple[float, str]]] = []
        current_line: list[tuple[float, str]] = []
        last_y = -999.0

        for y, x, _w, text in items:
            if abs(y - last_y) > 20:  # new line threshold
                if current_line:
                    lines.append(current_line)
                current_line = [(x, text)]
                last_y = y
            else:
                current_line.append((x, text))

        if current_line:
            lines.append(current_line)

        result_lines = []
        for line in lines:
            line.sort(key=lambda t: t[0])
            merged = " ".join(seg[1] for seg in line)
            result_lines.append(merged)

        return "\n".join(result_lines)


def convert_pdf(
    pdf_path: Path,
    max_pages: int | None = None,
    dpi: int = 300,
) -> str:
    """Convert entire PDF to text, page by page."""
    doc = fitz.open(str(pdf_path))
    total = len(doc)
    if max_pages:
        total = min(total, max_pages)

    all_text: list[str] = []
    for i in range(total):
        page = doc[i]
        print(f"  Processing page {i + 1}/{total}...", end=" ", flush=True)
        img = pdf_page_to_image(page, dpi=dpi)

        # Get page width in pixels at this DPI for column detection
        page_width = img.shape[1]

        results = ocr_page(img)
        text = page_ocr_to_text(results, page_width)
        char_count = len(text.replace(" ", "").replace("\n", ""))
        print(f"({char_count} chars)")
        if text.strip():
            all_text.append(f"<!-- Page {i + 1} -->\n{text}")

    doc.close()
    return "\n\n---\n\n".join(all_text)


def post_process_markdown(raw_text: str) -> str:
    """Post-process OCR text into clean Markdown with headings."""
    lines = raw_text.split("\n")
    processed = []

    for line in lines:
        stripped = line.strip()

        # Preserve structural markers
        if stripped.startswith("<!-- Page") or stripped.startswith("---"):
            processed.append(line)
            continue

        # Skip empty lines but preserve them
        if not stripped:
            processed.append("")
            continue

        # Detect chapter/section headings (common Chinese handbook patterns)
        if re.match(r"^第[一二三四五六七八九十百千\d]+[章编]", stripped):
            processed.append(f"\n## {stripped}")
        elif re.match(r"^第[一二三四五六七八九十百千\d]+[节]", stripped):
            processed.append(f"\n### {stripped}")
        elif re.match(r"^第[一二三四五六七八九十百千\d]+条\b", stripped):
            processed.append(f"\n**{stripped}**")
        elif re.match(r"^[一二三四五六七八九十]+[、.]", stripped):
            processed.append(f"\n### {stripped}")
        elif re.match(r"^[（(][一二三四五六七八九十\d]+[）)]", stripped):
            processed.append(f"- {stripped}")
        elif re.match(r"^\d+[、.]", stripped):
            processed.append(f"- {stripped}")
        else:
            processed.append(stripped)

    text = "\n".join(processed)

    # Clean up excessive blank lines
    text = re.sub(r"\n{4,}", "\n\n\n", text)

    return text


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert scanned PDF to Markdown")
    parser.add_argument(
        "--pages", type=int, default=None, help="Max pages to process (default: all)"
    )
    parser.add_argument("--output", type=str, default=None, help="Output file path")
    parser.add_argument(
        "--dpi", type=int, default=300, help="Rendering DPI (default: 300)"
    )
    parser.add_argument(
        "--test", action="store_true", help="Test mode: process first 3 pages only"
    )
    args = parser.parse_args()

    if args.test:
        args.pages = 3

    output_path = Path(args.output) if args.output else DEFAULT_OUTPUT

    print(f"PDF: {PDF_PATH}")
    print(f"Output: {output_path}")
    print(f"DPI: {args.dpi}")
    print(f"Pages: {args.pages or 'all'}")
    print()

    raw = convert_pdf(PDF_PATH, max_pages=args.pages, dpi=args.dpi)
    markdown = post_process_markdown(raw)

    # Add header
    header = (
        "# 东南大学大学生手册 2025\n\n"
        "> 本文档由 OCR 自动识别生成，可能存在少量识别误差。\n"
        "> 原始文档来源：https://yingxin.seu.edu.cn/2025/0809/c27744a536204/page.htm\n\n"
        "---\n\n"
    )
    final = header + markdown

    output_path.write_text(final, encoding="utf-8")
    size_kb = output_path.stat().st_size / 1024
    print(f"\nDone! Output: {output_path} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
