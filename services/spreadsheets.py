"""Write valid Excel auction reports using openpyxl instead of hand-authored XML."""

import io
import re
from typing import Any

from openpyxl import Workbook


def clean_xlsx_value(value: Any) -> Any:
    """Sanitize cell contents while retaining the original numeric cell types."""
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    text = str(value)
    text = re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]", "", text)
    if len(text) > 32700:
        text = text[:32700] + "\n...[обрезано из-за лимита Excel на ячейку]"
    return text


def sanitize_sheet_name(name: str) -> str:
    """Keep the bot's original Excel worksheet name normalization."""
    name = re.sub(r"[\[\]:*?/\\]", "_", name)
    return name[:31] or "Лист"


def make_xlsx_file(sheets: list[tuple[str, list[list[Any]]]], filename: str) -> io.BytesIO:
    """Serialize an XLSX stream consumable by the existing Discord attachment API."""
    workbook = Workbook()
    initial_sheet = workbook.active
    if initial_sheet is not None:
        workbook.remove(initial_sheet)
    for title, rows in sheets:
        worksheet = workbook.create_sheet(title=sanitize_sheet_name(title))
        for row in rows:
            worksheet.append([clean_xlsx_value(value) for value in row])
    file_obj = io.BytesIO()
    workbook.save(file_obj)
    file_obj.seek(0)
    file_obj.name = filename
    return file_obj
