"""快速拖放轉換的規則表與轉換邏輯（不含畫面）。

源自 GUI__QuickConverter.py；畫面在 gui/tabs/quick_tab.py。
"""

import os
import uuid

from core.image_converter import (
    convert_image,
    SUPPORTED_INPUT_EXTENSIONS as IMG_INPUT_EXT,
    SUPPORTED_OUTPUT_FORMATS as IMG_OUTPUT_FMTS,
)
from core.video_converter import (
    convert_video,
    INPUT_VIDEO_EXTENSIONS as VID_INPUT_EXT,
    VIDEO_FORMATS as VID_OUTPUT_FMTS,
)
from core.table_converter import excel_to_format, tables_to_excel
from core.pdf_extractor import pdf_to_text, pdf_to_docx, pdf_to_pptx
from core.pdf_maker import images_to_pdf, SUPPORTED_EXTENSIONS as PDF_IMG_EXT

# ═════════════════════════════════════════════════════════════════════════════
# Presets registry
# ═════════════════════════════════════════════════════════════════════════════

PRESETS: dict[str, dict] = {}

_CATEGORY_LABELS = {
    "image":          "🖼 圖片",
    "image_to_pdf":   "🖼 圖片",
    "video":          "🎬 影片 / 音訊",
    "excel_to_table": "📊 表格",
    "table_to_excel": "📊 表格",
    "pdf_extract":    "📋 PDF",
}


def _register_presets():
    for fmt, info in IMG_OUTPUT_FMTS.items():
        PRESETS[f"圖片 → {fmt} ({info['ext']})"] = {
            "input_ext": IMG_INPUT_EXT, "output_fmt": fmt, "category": "image",
        }
    PRESETS["圖片 → PDF"] = {
        "input_ext": PDF_IMG_EXT, "output_fmt": "PDF", "category": "image_to_pdf",
    }
    for fmt, info in VID_OUTPUT_FMTS.items():
        PRESETS[f"影片 → {fmt} ({info['ext']})"] = {
            "input_ext": VID_INPUT_EXT, "output_fmt": fmt, "category": "video",
        }
    PRESETS["Excel → CSV"] = {
        "input_ext": {".xlsx", ".xls"}, "output_fmt": "csv", "category": "excel_to_table",
    }
    PRESETS["Excel → Parquet"] = {
        "input_ext": {".xlsx", ".xls"}, "output_fmt": "parquet", "category": "excel_to_table",
    }
    PRESETS["CSV/Parquet → Excel"] = {
        "input_ext": {".csv", ".parquet"}, "output_fmt": "xlsx", "category": "table_to_excel",
    }
    PRESETS["PDF → TXT"] = {
        "input_ext": {".pdf"}, "output_fmt": "txt", "category": "pdf_extract",
    }
    PRESETS["PDF → DOCX"] = {
        "input_ext": {".pdf"}, "output_fmt": "docx", "category": "pdf_extract",
    }
    PRESETS["PDF → PPTX"] = {
        "input_ext": {".pdf"}, "output_fmt": "pptx", "category": "pdf_extract",
    }


_register_presets()

# ═════════════════════════════════════════════════════════════════════════════
# Conversion helpers
# ═════════════════════════════════════════════════════════════════════════════


def _get_output_ext(preset: dict) -> str:
    cat, fmt = preset["category"], preset["output_fmt"]
    if cat == "image":          return IMG_OUTPUT_FMTS[fmt]["ext"]
    if cat == "video":          return VID_OUTPUT_FMTS[fmt]["ext"]
    if cat == "excel_to_table": return ""
    if cat == "table_to_excel": return ".xlsx"
    if cat == "pdf_extract":    return f".{fmt}"
    if cat == "image_to_pdf":   return ".pdf"
    return ""


def _resolve_output_path(input_path: str, ext: str, overwrite: bool) -> str:
    base = os.path.splitext(input_path)[0]
    out = base + ext
    if os.path.exists(out) and not overwrite:
        out = f"{base}_{uuid.uuid4().hex[:6]}{ext}"
    return out


def convert_single(input_path: str, preset: dict, overwrite: bool) -> list[str]:
    """Convert one file using *preset*. Returns list of output paths."""
    cat, fmt = preset["category"], preset["output_fmt"]
    out_dir = os.path.dirname(input_path)

    if cat == "image":
        ext = IMG_OUTPUT_FMTS[fmt]["ext"]
        out = _resolve_output_path(input_path, ext, overwrite)
        result = convert_image(input_path, out_dir, fmt)
        if result != out:
            if os.path.exists(out):
                os.remove(out)
            os.rename(result, out)
        return [out]

    if cat == "image_to_pdf":
        out = _resolve_output_path(input_path, ".pdf", overwrite)
        images_to_pdf([input_path], out)
        return [out]

    if cat == "video":
        ext = VID_OUTPUT_FMTS[fmt]["ext"]
        out = _resolve_output_path(input_path, ext, overwrite)
        result = convert_video(input_path, out_dir, fmt)
        if result != out:
            if os.path.exists(out):
                os.remove(out)
            os.rename(result, out)
        return [out]

    if cat == "excel_to_table":
        return excel_to_format(input_path, out_dir, fmt)

    if cat == "table_to_excel":
        return tables_to_excel([input_path], out_dir)

    if cat == "pdf_extract":
        out = _resolve_output_path(input_path, f".{fmt}", overwrite)
        {"txt": pdf_to_text, "docx": pdf_to_docx, "pptx": pdf_to_pptx}[fmt](input_path, out)
        return [out]

    return []
