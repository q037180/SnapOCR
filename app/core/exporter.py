"""文本导出：按扩展名将识别/翻译结果保存为 txt / docx / pdf / xlsx / md。

pdf 走 PySide6 自带的 QPrinter（中文渲染无障碍）；
docx 走 python-docx（延迟导入，未安装时给出友好提示）；
xlsx 走 openpyxl（表格识别结果）；
md 为 Markdown 纯文本输出（参考 MinerU / PaddleOCR-VL 的文档化输出）。
"""
from __future__ import annotations

import os
import re

# XML 1.0 不允许的控制字符：python-docx / QTextDocument 遇到会报
# "All strings must be XML compatible"（实测 NUL 直接让导出失败）
_XML_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _xml_safe(text: str) -> str:
    """去掉 XML/HTML 不接受的控制字符，保留 \\t \\n \\r。"""
    return _XML_ILLEGAL.sub("", text)


def ensure_text_suffix(path: str, selected_filter: str = "") -> str:
    """用户没写扩展名时按所选过滤器补一个。

    Windows 原生保存框通常会补，但非原生/某些平台不会：以前会直接
    抛「不支持的导出格式：」，用户只看到导出失败。
    """
    if os.path.splitext(path)[1]:
        return path
    f = (selected_filter or "").lower()
    for ext in (".docx", ".pdf", ".md", ".txt"):
        if ext in f:
            return path + ext
    return path + ".txt"


def ensure_xlsx_suffix(path: str) -> str:
    return path if os.path.splitext(path)[1] else path + ".xlsx"


def export_text(path: str, text: str) -> None:
    """按扩展名导出文本。支持 .txt / .docx / .pdf / .md。"""
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".txt", ".docx", ".pdf", ".md"):
        raise ValueError(f"不支持的导出格式：{ext or '（没有扩展名）'}")
    if not (text or "").strip():
        # 空内容不落盘：否则会生成 1 页空白 PDF / 空文档，用户以为导出成功了
        raise ValueError("没有可导出的内容")
    text = _xml_safe(text)
    if ext == ".txt":
        _save_txt(path, text)
    elif ext == ".docx":
        _save_docx(path, text)
    elif ext == ".pdf":
        _save_pdf(path, text)
    else:
        _save_md(path, text)


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
        if row is None:
            continue
        # openpyxl 不接受 None 单元格；统一转成空串，避免整次导出失败
        vals = [_xml_safe("" if c is None else str(c)) for c in row]
        ws.append(vals)
        # openpyxl 会把以 "=" 开头的字符串当成公式写入（Excel 打开变 #NAME?
        # 或直接计算），OCR 出代码/公式样文本时就是数据损坏。强制回文本类型。
        excel_row = ws.max_row
        for col, v in enumerate(vals, 1):
            if v.startswith("="):
                ws.cell(row=excel_row, column=col).data_type = "s"
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
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
    except ImportError as exc:
        raise RuntimeError(
            "导出 docx 需要 python-docx：请先执行 pip install python-docx"
        ) from exc
    doc = Document()
    body = doc.element.body
    sect = body.find(qn("w:sectPr"))  # 节属性必须是 body 的最后一个元素
    # 逐行 append <w:p><w:r><w:t>；不用 doc.add_paragraph：它内部是
    # O(n) 插入，10 万行实测 419 秒（本写法 1.5 秒 / 5 万行，线性）
    for line in text.splitlines():
        p = OxmlElement("w:p")
        run = OxmlElement("w:r")
        t = OxmlElement("w:t")
        t.text = line
        t.set(qn("xml:space"), "preserve")  # 保留行首/行尾空格
        run.append(t)
        p.append(run)
        if sect is not None:
            sect.addprevious(p)
        else:
            body.append(p)
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
