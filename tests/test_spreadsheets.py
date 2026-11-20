"""Auction Excel output remains usable and preserves existing sanitization."""

from io import BytesIO

from openpyxl import load_workbook

from services.spreadsheets import clean_xlsx_value, make_xlsx_file, sanitize_sheet_name


def test_invalid_excel_sheet_characters_are_replaced() -> None:
    assert sanitize_sheet_name("Лоты / новые?") == "Лоты _ новые_"
    assert sanitize_sheet_name("") == "Лист"
    assert len(sanitize_sheet_name("a" * 40)) == 31


def test_cells_keep_numeric_types_and_control_characters_are_removed() -> None:
    assert clean_xlsx_value(None) == ""
    assert clean_xlsx_value(123) == 123
    assert clean_xlsx_value(1.25) == 1.25
    assert clean_xlsx_value("a\x00b\x1fc") == "abc"


def test_written_xlsx_is_valid_and_discord_ready() -> None:
    stream = make_xlsx_file(
        [("Лоты / новые?", [["Название", "Цена"], ["Лот", 1234], ["Заметка", "A\x00B"]])],
        "auction.xlsx",
    )
    assert isinstance(stream, BytesIO)
    assert stream.name == "auction.xlsx"
    assert stream.tell() == 0
    workbook = load_workbook(stream, read_only=True, data_only=True)
    try:
        sheet = workbook["Лоты _ новые_"]
        assert list(sheet.values) == [("Название", "Цена"), ("Лот", 1234), ("Заметка", "AB")]
    finally:
        workbook.close()


def test_overlong_cells_are_truncated_like_original() -> None:
    cell = clean_xlsx_value("x" * 40000)
    assert cell.startswith("x" * 32700)
    assert "обрезано" in cell
