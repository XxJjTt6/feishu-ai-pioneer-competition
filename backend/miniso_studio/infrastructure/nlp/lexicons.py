"""兴趣消费品领域词典。

词典同时覆盖中文演示评论与可选公开英文评论，供确定性 ABSA 使用。
"""
from __future__ import annotations

from typing import Dict, List


ASPECT_LEXICON: Dict[str, List[str]] = {
    "IP/设计吸引力": [
        "ip", "联名", "设计", "可爱", "颜值", "造型", "design", "cute", "character",
    ],
    "品质/耐用性": [
        "质量", "品质", "耐用", "做工", "坏", "破损", "quality", "durable", "broken", "build",
    ],
    "价格/价值": [
        "价格", "性价比", "贵", "便宜", "划算", "不值", "物有所值",
        "price", "prices", "value", "expensive", "worth",
    ],
    "实用性": [
        "实用", "功能", "好用", "收纳", "useful", "practical", "function",
    ],
    "礼赠性": [
        "礼物", "送人", "送礼", "礼赠", "gift", "gifts", "present",
    ],
    "收藏性": [
        "收藏", "系列", "隐藏款", "盲盒", "collect", "collection", "series", "blind box",
    ],
    "包装": [
        "包装", "开箱", "盒子", "package", "packages", "packaging", "unboxing",
    ],
    "门店可得性": [
        "缺货", "门店", "库存", "断货", "sold out", "out of stock",
        "store", "stores", "availability",
    ],
    "本地化": [
        "本地", "文化", "地域", "城市限定", "local", "localized", "regional", "culture",
    ],
}

POSITIVE_WORDS: List[str] = [
    "great", "good", "excellent", "amazing", "love", "best", "perfect", "comfortable",
    "clear", "impressive", "solid", "worth", "happy", "recommend", "fantastic", "crisp",
    "cute", "durable", "useful", "practical", "beautiful", "好", "很好", "棒", "优秀",
    "喜欢", "完美", "清晰", "值", "值得", "推荐", "舒适", "稳定", "精美", "可爱",
    "耐用", "实用", "好用", "惊喜",
]

NEGATIVE_WORDS: List[str] = [
    "bad", "poor", "terrible", "awful", "hate", "worst", "disappointing", "disappointed",
    "uncomfortable", "muffled", "weak", "drop", "drops", "broke", "broken", "expensive",
    "fail", "fails", "annoying", "laggy", "lag", "useless", "cheap", "issue", "issues",
    "problem", "sold out", "out of stock", "差", "很差", "糟", "失望", "弱", "坏", "贵",
    "问题", "故障", "缺货", "断货", "破损", "粗糙", "不值",
]

NEGATORS: List[str] = [
    "not", "no", "never", "hardly", "lack", "without", "n't",
    "不", "不是", "并不", "没", "没有", "未", "无",
]
