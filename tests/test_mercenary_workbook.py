"""Compatibility tests for the mercenary Excel database reader."""

import ast
from pathlib import Path

from openpyxl import Workbook

from services.mercenary_workbook import read_mercenary_sheets


def test_mercenary_reader_preserves_headers_columns_and_numeric_values(tmp_path) -> None:
    path = tmp_path / "mercenaries.xlsx"
    workbook = Workbook()
    main = workbook.active
    main.title = "01_Профессии"
    main.append(["Профессия", "Навык 1", "Цена"])
    main.append(["Наемник", None, 150])
    main.append([None, None, None])
    main.append(["Страж", "Меч", 200])
    extras = workbook.create_sheet("02_Синонимы")
    extras.append(["Тип", "Значение"])
    extras.append(["alias", "Гвардеец"])
    workbook.save(path)

    sheets = read_mercenary_sheets(path)
    assert sheets["01_Профессии"] == [
        ["Профессия", "Навык 1", "Цена"],
        ["Наемник", "", "150"],
        ["Страж", "Меч", "200"],
    ]
    assert sheets["02_Синонимы"] == [["Тип", "Значение"], ["alias", "Гвардеец"]]


def test_mercenary_catalog_is_not_loaded_during_module_import() -> None:
    tree = ast.parse(Path("psinkamain.py").read_text(encoding="utf-8"))
    calls = [
        (statement, node)
        for statement in tree.body
        for node in ast.walk(statement)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "load_mercenary_database_from_xlsx"
    ]
    assert len(calls) == 1
    assert isinstance(calls[0][0], ast.If)
    assert "__main__" in ast.unparse(calls[0][0].test)
