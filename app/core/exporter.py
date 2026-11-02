"""文本导出：按扩展名将识别/翻译结果保存为 txt / docx / pdf / xlsx / md。

pdf 走 PySide6 自带的 QPrinter（中文渲染无障碍）；
docx 走 python-docx（延迟导入，未安装时给出友好提示）；
xlsx 走 openpyxl（表格识别结果）；
md 为 Markdown 纯文本输出（参考 MinerU / PaddleOCR-VL 的文档化输出）。
"""
from __future__ import annotations

import os


def export_text(path: str, text: str) -> None:
    """按扩展名导出文本。支持 .txt / .docx / .pdf / .md。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".txt":
        _save_txt(path, text)
    elif ext == ".docx":
        _save_docx(path, text)
    elif ext == ".pdf":
        _save_pdf(path, text)
    elif ext == ".md":
        _save_md(path, text)
    else:
        raise ValueError(f"不支持的导出格式：{ext}")


def export_xlsx(path: str, rows: list[list[str]]) -> None:
    """表格识别结果（行列矩阵）导出为 Excel。"""
    try:
        from openpyxl import Workbook
    except ImportError as exc:
        raise RuntimeError(
            "导出 xlsx 需要 openpyxl：请先执行 pip install openpyxl"
        ) from exc
    wb = Workbook()
    ws = wb.active
    ws.title = "OCR表格"
    for row in rows:
        ws.append(row)
    # 简单列宽自适应（按前 30 个字符估计）
    for col_idx, col in enumerate(ws.columns, 1):
        width = max((len(str(c.value)) for c in col if c.value), default=8)
        ws.column_dimensions[ws.cell(1, col_idx).column_letter].width = min(
            max(width * 1.6 + 2, 8), 60
        )
    wb.save(path)


def _save_md(path: str, text: str) -> None:
    # Markdown 纯文本：内容原样输出，多行按段落分隔，可用任意 Markdown 阅读器打开
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _save_txt(path: str, text: str) -> None:
    # utf-8-sig：带 BOM，Windows 记事本/Word 打开不乱码
    with open(path, "w", encoding="utf-8-sig") as f:
        f.write(text)


def _save_docx(path: str, text: str) -> None:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError(
            "导出 docx 需要 python-docx：请先执行 pip install python-docx"
        ) from exc
    doc = Document()
    for line in text.splitlines():
        doc.add_paragraph(line)
    doc.save(path)


def _save_pdf(path: str, text: str) -> None:
    from PySide6.QtGui import QTextDocument
    from PySide6.QtPrintSupport import QPrinter

    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(path)
    doc = QTextDocument()
    html = "".join(
        (line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") or "<br>")
        + "<br>"
        for line in text.splitlines()
    )
    doc.setHtml(html)
    doc.print_(printer)
