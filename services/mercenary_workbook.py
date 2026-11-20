"""Read the original mercenary workbook into plain text rows using openpyxl."""

from pathlib import Path

from openpyxl import load_workbook


def read_mercenary_sheets(path: str | Path) -> dict[str, list[list[str]]]:
    """Return worksheet rows as strings, matching legacy loader expectations.

    Empty spreadsheet rows are omitted, but column indices are preserved so
    header-driven consumers can recognize sparse workbook layouts.

    Args:
        path: Existing XLSX workbook path.

    Returns:
        Mapping of worksheet titles to nonempty rows, with cell values as text.

    Raises:
        OSError: The workbook cannot be read from disk.
        zipfile.BadZipFile: The file is not a valid XLSX archive.
    """
    workbook = load_workbook(filename=path, read_only=True, data_only=True)
    try:
        sheets: dict[str, list[list[str]]] = {}
        for worksheet in workbook.worksheets:
            rows: list[list[str]] = []
            for cells in worksheet.iter_rows(values_only=True):
                values = [str(cell).strip() if cell is not None else "" for cell in cells]
                if not any(values):
                    continue
                while values and not values[-1]:
                    values.pop()
                rows.append(values)
            sheets[worksheet.title] = rows
        return sheets
    finally:
        workbook.close()
