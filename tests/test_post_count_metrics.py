"""Per-message statistics preserve distinct message and occurrence counts."""

from services.post_count_metrics import pc_apply_content, pc_empty_result
from services.post_count_templates import PC_DRP, PC_GM


def test_repeated_template_counts_one_message_but_two_occurrences() -> None:
    families = [PC_GM, PC_DRP]
    result = pc_empty_result("Канал", families, 17)
    pc_apply_content(
        result, "гмпост#Роза гмпост#Роза", None, families,
        message_id=1, channel_id=17, guild_id=2,
    )
    assert result["scanned"] == 1
    assert result["matched"] == 1
    assert result["families"][PC_GM]["messages"] == 1
    assert result["families"][PC_GM]["occurrences"] == 2
    assert result["families"][PC_GM]["groups"]["роза"]["messages"] == 1
    assert result["lengths"]["short"] == 1
    assert len(result["template_messages"]) == 1


def test_long_gm_post_counts_as_long() -> None:
    result = pc_empty_result("Канал", [PC_GM], 17)
    pc_apply_content(result, "гмпост#Роза " + "а" * 310, None, [PC_GM])
    assert result["lengths"] == {"long": 1, "short": 0}
    assert result["families"][PC_GM]["long"] == 1


def test_drp_length_not_counted_by_default() -> None:
    result = pc_empty_result("Канал", [PC_DRP], 17)
    pc_apply_content(result, "дрпвердикт#Тест " + "а" * 400, None, [PC_DRP])
    assert result["matched"] == 1
    assert result["lengths"] == {"long": 0, "short": 0}


def test_unmatched_message_only_increments_scanned() -> None:
    result = pc_empty_result("Канал", [PC_GM], 17)
    pc_apply_content(result, "текст без метки", None, [PC_GM])
    assert result["scanned"] == 1
    assert result["matched"] == 0
    assert result["template_messages"] == []
