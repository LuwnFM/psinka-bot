"""Post-count reports preserve cross-channel and cross-message aggregation."""

from services.post_count_metrics import pc_apply_content, pc_empty_result
from services.post_count_reporting import pc_merge_lengths, pc_merge_stats, pc_percent
from services.post_count_templates import PC_GM


def test_cross_result_aggregation_and_length_counts() -> None:
    results = []
    for channel in (12, 13):
        item = pc_empty_result(f"Канал {channel}", [PC_GM], channel)
        pc_apply_content(item, "гмпост#Арка " + "а" * 310, None, [PC_GM], channel_id=channel)
        results.append(item)
    merged = pc_merge_stats(results, [PC_GM])
    assert merged[PC_GM]["messages"] == 2
    assert merged[PC_GM]["occurrences"] == 2
    assert merged[PC_GM]["groups"]["арка"]["messages"] == 2
    assert pc_merge_lengths(results) == {"long": 2, "short": 0}


def test_percentage_has_existing_numeric_semantics() -> None:
    assert pc_percent(5, 10) == 50.0
