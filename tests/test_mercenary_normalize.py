"""Original mercenary normalization and synonym aliases stay deterministic."""

from services.mercenary_normalize import (
    _clean_profession_targets,
    _rows_to_dicts,
    dedupe_preserve_order,
    normalize_lookup_text,
    split_multi_field,
)


def test_name_normalization_removes_numeric_suffix_only() -> None:
    assert normalize_lookup_text("  Гвардеец — 2 ") == "гвардеец"
    assert normalize_lookup_text("РЫЦАРЬ-СТРАЖ") == "рыцарь страж"
    assert normalize_lookup_text("Ёжик, чародей!") == "ежик чародей"


def test_preserve_first_spelling_and_remove_alias_duplicates() -> None:
    assert dedupe_preserve_order(["Ёж", "еж", "Лучник", "ЛУЧНИК"]) == ["Ёж", "Лучник"]
    assert split_multi_field("Страж, Гвардеец; страж\n Лучник") == [
        "Страж", "Гвардеец", "Лучник"
    ]


def test_mercenary_excel_table_keeps_sparse_columns() -> None:
    rows = [["Заметки"], ["Профессия", "", "Профессия код"], ["Страж", "", "23"]]
    assert _rows_to_dicts(rows, "Профессия") == [
        {"Профессия": "Страж", "Профессия код": "23"}
    ]


def test_unrecognized_specialization_targets_are_not_added() -> None:
    pool = {"Гвардеец": ["Меч"], "Работник": ["Ремесло"]}
    assert _clean_profession_targets(["гвардеец", "Несуществующий", "ГВАРДЕЕЦ"], pool) == [
        "Гвардеец"
    ]
