"""确定性 Aspect-Based Sentiment Analysis（Infrastructure 层）。

输入一批 Evidence（评论），按 aspect 统计提及量、负面率、代表性引用。
情感判定使用子句级中英文词典、简单否定翻转与评分兜底，不调用 LLM。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Sequence, Tuple

from miniso_studio.common.models import Evidence
from miniso_studio.infrastructure.nlp.lexicons import (
    ASPECT_LEXICON,
    NEGATIVE_WORDS,
    NEGATORS,
    POSITIVE_WORDS,
)

_CLAUSE_SPLIT = re.compile(r"[.!?;,\n。！？；，]")
_CHINESE = re.compile(r"[\u4e00-\u9fff]")
_ENGLISH_TOKEN = re.compile(r"[a-zA-Z]+(?:'[a-zA-Z]+)?")
_CHINESE_NEGATORS = tuple(item for item in NEGATORS if _CHINESE.search(item))
_ENGLISH_NEGATORS = {item for item in NEGATORS if not _CHINESE.search(item)}


@dataclass
class AspectStat:
    aspect: str
    mentions: int = 0
    negative: int = 0
    positive: int = 0
    evidence_ids: List[str] = field(default_factory=list)
    negative_evidence_ids: List[str] = field(default_factory=list)

    @property
    def negative_rate(self) -> float:
        return round(self.negative / self.mentions, 4) if self.mentions else 0.0

    @property
    def positive_rate(self) -> float:
        return round(self.positive / self.mentions, 4) if self.mentions else 0.0


def _term_matches(text: str, terms: Iterable[str], polarity: int) -> List[Tuple[int, int, int]]:
    """返回词典命中的位置；中文按词组，英文按单词边界匹配。"""
    matches: List[Tuple[int, int, int]] = []
    for term in terms:
        needle = term.lower()
        if _CHINESE.search(needle):
            start = text.find(needle)
            while start >= 0:
                matches.append((start, start + len(needle), polarity))
                start = text.find(needle, start + 1)
            continue
        pattern = re.compile(rf"(?<![a-z]){re.escape(needle)}(?![a-z])")
        matches.extend((match.start(), match.end(), polarity) for match in pattern.finditer(text))
    return matches


def _is_negated(text: str, start: int) -> bool:
    prefix = text[:start]
    if _CHINESE.search(text[start:]):
        chinese_window = prefix[-6:]
        if any(negator in chinese_window for negator in _CHINESE_NEGATORS):
            return True

    previous_words = _ENGLISH_TOKEN.findall(prefix.lower())[-3:]
    return any(
        word in _ENGLISH_NEGATORS or word.endswith("n't")
        for word in previous_words
    )


def _clause_sentiment(clause: str, rating) -> str:
    """返回 ``pos``、``neg`` 或 ``neu``。"""
    text = clause.lower()
    matches = _term_matches(text, POSITIVE_WORDS, 1)
    matches.extend(_term_matches(text, NEGATIVE_WORDS, -1))

    # 同位置可能同时命中长短词（例如“差”与“很差”），只保留最长项。
    by_start: Dict[int, Tuple[int, int, int]] = {}
    for match in matches:
        previous = by_start.get(match[0])
        if previous is None or match[1] - match[0] > previous[1] - previous[0]:
            by_start[match[0]] = match

    score = 0
    for start, _end, polarity in sorted(by_start.values()):
        score += -polarity if _is_negated(text, start) else polarity
    if score > 0:
        return "pos"
    if score < 0:
        return "neg"

    if rating is not None:
        try:
            numeric_rating = float(rating)
            if numeric_rating <= 2:
                return "neg"
            if numeric_rating >= 4:
                return "pos"
        except (TypeError, ValueError):
            return "neu"
    return "neu"


def _match_aspects(clause: str) -> List[str]:
    text = clause.lower()

    def matches(keyword: str) -> bool:
        needle = keyword.lower()
        if _CHINESE.search(needle):
            return needle in text
        return re.search(rf"(?<![a-z]){re.escape(needle)}(?![a-z])", text) is not None

    return [
        aspect
        for aspect, keywords in ASPECT_LEXICON.items()
        if any(matches(keyword) for keyword in keywords)
    ]


def analyze(evidences: Sequence[Evidence]) -> Dict[str, AspectStat]:
    """对评论做 ABSA，返回 ``{aspect: AspectStat}``。"""
    stats: Dict[str, AspectStat] = {aspect: AspectStat(aspect=aspect) for aspect in ASPECT_LEXICON}
    for evidence in evidences:
        seen_aspects: Dict[str, str] = {}
        for clause in _CLAUSE_SPLIT.split(evidence.text):
            clause = clause.strip()
            if len(clause) < 3:
                continue
            for aspect in _match_aspects(clause):
                sentiment = _clause_sentiment(clause, evidence.rating)
                previous = seen_aspects.get(aspect)
                if previous is None or (sentiment == "neg" and previous != "neg"):
                    seen_aspects[aspect] = sentiment

        for aspect, sentiment in seen_aspects.items():
            stat = stats[aspect]
            stat.mentions += 1
            if evidence.source_id not in stat.evidence_ids:
                stat.evidence_ids.append(evidence.source_id)
            if sentiment == "neg":
                stat.negative += 1
                stat.negative_evidence_ids.append(evidence.source_id)
            elif sentiment == "pos":
                stat.positive += 1
    return stats
