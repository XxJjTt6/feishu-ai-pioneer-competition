"""中英文确定性 ABSA 的词组和否定回归测试。"""
from __future__ import annotations

import pytest

from miniso_studio.common.models import Evidence
from miniso_studio.infrastructure.nlp.absa import analyze


def _evidence(source_id: str, text: str) -> Evidence:
    return Evidence(source_id=source_id, brand="MINISO", text=text, rating=None)


def test_unrated_chinese_multicharacter_sentiment_terms_are_matched():
    stats = analyze(
        [
            _evidence("positive", "包装精美、设计很可爱"),
            _evidence("negative", "做工很差、刚用就坏了"),
        ]
    )

    assert stats["包装"].positive == 1
    assert stats["IP/设计吸引力"].positive == 1
    assert stats["品质/耐用性"].negative == 1


def test_simple_chinese_negation_does_not_turn_durability_positive():
    stats = analyze([_evidence("negated", "这个杯子不是很耐用")])

    assert stats["品质/耐用性"].mentions == 1
    assert stats["品质/耐用性"].positive == 0
    assert stats["品质/耐用性"].negative == 1


@pytest.mark.parametrize(
    ("text", "expected_aspect"),
    [
        ("颜值让人惊喜", "IP/设计吸引力"),
        ("值得收藏", "收藏性"),
    ],
)
def test_chinese_aspect_keywords_do_not_leak_into_price(text, expected_aspect):
    stats = analyze([_evidence("aspect-isolation", text)])

    assert stats[expected_aspect].mentions == 1
    assert stats["价格/价值"].mentions == 0


def test_ascii_aspect_keyword_requires_english_word_boundaries():
    stats = analyze([_evidence("shipping", "Shipping was slow")])

    assert stats["IP/设计吸引力"].mentions == 0
    assert all(stat.mentions == 0 for stat in stats.values())


@pytest.mark.parametrize(
    ("text", "expected_aspect"),
    [
        ("Prices are high.", "价格/价值"),
        ("I bought these as gifts.", "礼赠性"),
        ("The stores nearby had stock.", "门店可得性"),
        ("The packages look beautiful.", "包装"),
    ],
)
def test_common_english_aspect_plurals_are_explicitly_supported(text, expected_aspect):
    stats = analyze([_evidence("plural-aspect", text)])

    assert stats[expected_aspect].mentions == 1


def test_english_word_matching_and_negation_behavior_is_preserved():
    stats = analyze(
        [
            _evidence("not-good", "The design is not good."),
            _evidence("not-bad", "The quality is not bad."),
            _evidence("boundary", "The store said goodbye."),
        ]
    )

    assert stats["IP/设计吸引力"].negative == 1
    assert stats["品质/耐用性"].positive == 1
    assert stats["门店可得性"].mentions == 1
    assert stats["门店可得性"].positive == 0
    assert stats["门店可得性"].negative == 0


@pytest.mark.parametrize("term", ["comfortable", "crisp"])
def test_unrated_legacy_english_positive_terms_are_preserved(term):
    stats = analyze([_evidence(f"legacy-positive-{term}", f"The quality is {term}.")])

    assert stats["品质/耐用性"].positive == 1
    assert stats["品质/耐用性"].negative == 0


@pytest.mark.parametrize(
    "term",
    ["uncomfortable", "muffled", "drop", "drops", "laggy", "lag"],
)
def test_unrated_legacy_english_negative_terms_are_preserved(term):
    stats = analyze([_evidence(f"legacy-negative-{term}", f"The quality is {term}.")])

    assert stats["品质/耐用性"].positive == 0
    assert stats["品质/耐用性"].negative == 1
