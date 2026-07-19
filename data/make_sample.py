#!/usr/bin/env python3
"""生成可复现的兴趣消费合成演示评论。

这些记录只用于离线流程、ABSA 与竞品拆解演示，不是真实企业数据，也不代表任何品牌
的实际消费者评价。公开评论接入见 ``miniso_studio.infrastructure.data.retail_reviews``。
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Dict, List

OUT = Path(__file__).resolve().parent / "sample"
RANDOM_SEED = 20260719
YEARS = ["2024", "2025", "2026"]

PHRASES: Dict[str, Dict[str, List[str]]] = {
    "design": {
        "pos": ["IP联名设计很可爱，颜值让人惊喜。", "The character design is cute and distinctive."],
        "neg": ["联名图案有点普通，设计缺少新意。", "The design feels generic rather than collectible."],
    },
    "quality": {
        "pos": ["做工细致，材质结实耐用。", "The build quality feels solid and durable."],
        "neg": ["做工很差，刚用不久就坏了。", "The item arrived broken and the quality is poor."],
    },
    "value": {
        "pos": ["价格友好，性价比很高。", "Good value for the price and worth buying."],
        "neg": ["价格偏贵，这个品质不值。", "It is expensive and not worth the price."],
    },
    "practical": {
        "pos": ["收纳功能很实用，日常很好用。", "The product is practical and useful every day."],
        "neg": ["功能不实用，用起来很麻烦。", "It looks nice but is not very practical."],
    },
    "gift": {
        "pos": ["作为小礼物送人很合适。", "It makes a cute and affordable gift."],
        "neg": ["包装破损，不适合送礼。", "I would not present this as a gift."],
    },
    "collect": {
        "pos": ["整个系列很值得收藏，还想继续集齐。", "The series is fun to collect and display."],
        "neg": ["系列重复度高，没有继续收藏的动力。", "The series has too many repeats to collect."],
    },
    "package": {
        "pos": ["包装精美，开箱过程很有惊喜。", "The packaging is beautiful and unboxing feels special."],
        "neg": ["包装盒粗糙，到手时还有破损。", "The package was damaged and poorly finished."],
    },
    "availability": {
        "pos": ["附近门店库存充足，很容易买到。", "The item was available at my local store."],
        "neg": ["热门款总是缺货，跑了几家门店都没库存。", "It was sold out in every store nearby."],
    },
    "localization": {
        "pos": ["本地文化元素自然，城市限定很有记忆点。", "The regional design feels thoughtfully localized."],
        "neg": ["本地化只是换了文字，文化表达比较生硬。", "The local edition does not feel genuinely regional."],
    },
}

BRAND_COUNTS = {
    "MINISO": 140,
    "POP MART": 65,
    "DAISO": 65,
    "MUJI": 65,
    "Flying Tiger": 65,
}

# 仅为合成数据制造可观察差异，不是对品牌真实表现的判断。
BRAND_NEGATIVE_BASE = {
    "MINISO": 0.34,
    "POP MART": 0.38,
    "DAISO": 0.36,
    "MUJI": 0.29,
    "Flying Tiger": 0.40,
}

PRODUCTS = {
    "MINISO": ["IP联名毛绒挂件", "角色收纳盒", "城市限定水杯", "香氛礼盒"],
    "POP MART": ["角色盲盒", "收藏手办", "毛绒挂件", "限定系列摆件"],
    "DAISO": ["桌面收纳盒", "便携水杯", "文具礼盒", "旅行用品"],
    "MUJI": ["亚克力收纳盒", "旅行分装瓶", "香氛用品", "文具套装"],
    "Flying Tiger": ["派对礼物", "趣味文具", "创意家居摆件", "季节限定杯具"],
}


def _slug(brand: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", brand.lower()).strip("-")


def generate_brand(brand: str, count: int, rng: random.Random) -> List[dict]:
    rows: List[dict] = []
    aspects = list(PHRASES)
    brand_slug = _slug(brand)
    for index in range(count):
        chosen_aspects = rng.sample(aspects, rng.choice([1, 2, 2, 3]))
        texts: List[str] = []
        has_negative = False
        for aspect in chosen_aspects:
            negative = rng.random() < BRAND_NEGATIVE_BASE[brand]
            has_negative = has_negative or negative
            texts.append(rng.choice(PHRASES[aspect]["neg" if negative else "pos"]))
        rows.append(
            {
                "source_id": f"demo-{brand_slug}-{index:04d}",
                "source_type": "review" if brand == "MINISO" else "competitor",
                "brand": brand,
                "product": rng.choice(PRODUCTS[brand]),
                "category": "interest_goods",
                "rating": rng.choice([1, 2, 3]) if has_negative else rng.choice([4, 5, 5]),
                "text": " ".join(texts),
                "date": rng.choice(YEARS),
                "helpful_votes": rng.randint(0, 40),
                "url": f"demo://synthetic/{brand_slug}/{index:04d}",
                "data_provenance": "synthetic_demo",
            }
        )
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old_file in OUT.glob("*.jsonl"):
        old_file.unlink()

    rng = random.Random(RANDOM_SEED)
    for brand, count in BRAND_COUNTS.items():
        rows = generate_brand(brand, count, rng)
        path = OUT / f"{brand.replace(' ', '_')}.jsonl"
        with path.open("w", encoding="utf-8") as fp:
            for row in rows:
                fp.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"wrote {len(rows)} synthetic demo rows -> {path}")


if __name__ == "__main__":
    main()
