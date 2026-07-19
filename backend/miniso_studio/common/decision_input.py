"""Trend2SKU 的结构化决策输入契约。"""
from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ProductCategory = Literal[
    "plush",
    "fragrance_accessory",
    "stationery",
    "home_storage",
    "beauty_tool",
    "digital_accessory",
    "other",
]
TargetSegment = Literal[
    "student",
    "young_professional",
    "ip_fan",
    "gift",
    "family",
    "collector",
]
TargetMarket = Literal[
    "china",
    "southeast_asia",
    "japan_korea",
    "europe_america",
    "middle_east",
    "global",
]
PriceBand = Literal["entry", "mid", "premium"]
IPStrategy = Literal["original", "licensed", "none", "evaluate"]
Objective = Literal[
    "emotional",
    "social",
    "margin",
    "supply_chain",
    "localization",
]


class DecisionInput(BaseModel):
    """跨 API、Runner 与 checkpoint 持久化的规范化输入。"""

    model_config = ConfigDict(extra="forbid")

    brief: str = Field(min_length=1, max_length=500)
    product_category: ProductCategory = "fragrance_accessory"
    custom_category: str = Field(default="", max_length=40)
    target_segment: TargetSegment = "young_professional"
    target_market: TargetMarket = "global"
    price_band: PriceBand = "mid"
    ip_strategy: IPStrategy = "original"
    objectives: list[Objective] = Field(
        default_factory=lambda: ["emotional", "social"]
    )
    constraints: str = Field(default="", max_length=300)

    _CATEGORY_LABELS: ClassVar[dict[str, str]] = {
        "plush": "毛绒",
        "fragrance_accessory": "香氛配饰",
        "stationery": "文创文具",
        "home_storage": "家居收纳",
        "beauty_tool": "美妆工具",
        "digital_accessory": "数码配件",
        "other": "其他",
    }
    _SEGMENT_LABELS: ClassVar[dict[str, str]] = {
        "student": "学生",
        "young_professional": "年轻职场人",
        "ip_fan": "IP 粉丝",
        "gift": "礼赠人群",
        "family": "亲子家庭",
        "collector": "收藏爱好者",
    }
    _MARKET_LABELS: ClassVar[dict[str, str]] = {
        "china": "中国市场",
        "southeast_asia": "东南亚市场",
        "japan_korea": "日韩市场",
        "europe_america": "欧美市场",
        "middle_east": "中东市场",
        "global": "全球市场",
    }
    _PRICE_LABELS: ClassVar[dict[str, str]] = {
        "entry": "入门价格带",
        "mid": "中端价格带",
        "premium": "高端价格带",
    }
    _IP_STRATEGY_LABELS: ClassVar[dict[str, str]] = {
        "original": "原创 IP",
        "licensed": "授权 IP",
        "none": "无 IP",
        "evaluate": "待评估",
    }
    _OBJECTIVE_LABELS: ClassVar[dict[str, str]] = {
        "emotional": "情绪价值",
        "social": "社交传播",
        "margin": "毛利潜力",
        "supply_chain": "供应链可行性",
        "localization": "本地化适配",
    }

    @field_validator("brief", "custom_category", "constraints", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("objectives")
    @classmethod
    def normalize_objectives(cls, values: list[Objective]) -> list[Objective]:
        normalized = list(dict.fromkeys(values))
        if not 1 <= len(normalized) <= 4:
            raise ValueError("objectives 去重后必须包含 1-4 项")
        return normalized

    @model_validator(mode="after")
    def normalize_custom_category(self) -> "DecisionInput":
        if self.product_category == "other":
            if not self.custom_category:
                raise ValueError("product_category 为 other 时必须填写 custom_category")
        else:
            self.custom_category = ""
        return self

    @property
    def category_label(self) -> str:
        if self.product_category == "other":
            return self.custom_category
        return self._CATEGORY_LABELS[self.product_category]

    @property
    def segment_label(self) -> str:
        return self._SEGMENT_LABELS[self.target_segment]

    @property
    def target_segment_label(self) -> str:
        """兼容使用字段全名的调用方。"""
        return self.segment_label

    @property
    def market_label(self) -> str:
        return self._MARKET_LABELS[self.target_market]

    @property
    def target_market_label(self) -> str:
        """兼容使用字段全名的调用方。"""
        return self.market_label

    @property
    def price_label(self) -> str:
        return self._PRICE_LABELS[self.price_band]

    @property
    def price_band_label(self) -> str:
        """兼容使用字段全名的调用方。"""
        return self.price_label

    @property
    def ip_strategy_label(self) -> str:
        return self._IP_STRATEGY_LABELS[self.ip_strategy]

    @property
    def objective_labels(self) -> list[str]:
        return [self._OBJECTIVE_LABELS[value] for value in self.objectives]
