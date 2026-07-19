"""兴趣消费趋势连接器。

网络或可选依赖不可用时返回带官方出处和明确发布日期的离线趋势信号。趋势是
对公开材料的产品研究解读，不把演示评论冒充企业内部数据。
"""
from __future__ import annotations

from typing import List

from miniso_studio.common.logging import log
from miniso_studio.common.models import Evidence, SourceType, TrendSignal

Q1_RESULTS_URL = (
    "https://ir.miniso.com/2026-05-26-MINISO-Group-Announces-"
    "March-Quarter-2026-Unaudited-Financial-Results"
)
ANNUAL_REPORT_2025_URL = "https://ir.miniso.com/image/Annual+Report+2025+US.pdf"

_OFFLINE_TRENDS: List[TrendSignal] = [
    TrendSignal(
        name="IP联名",
        direction="up",
        summary="授权 IP 与原创设计共同增强兴趣商品的辨识度，适合用系列化上新验证联名热度。",
        evidence_ids=["trend-miniso-q1-2026-ip"],
    ),
    TrendSignal(
        name="情绪价值",
        direction="up",
        summary=(
            "研究假设：可爱设计、惊喜感和低门槛自我奖励可能增强兴趣消费购买动机，"
            "需用公开内容数据与试购继续验证。"
        ),
        evidence_ids=["trend-miniso-annual-2025-emotion"],
    ),
    TrendSignal(
        name="社交传播",
        direction="up",
        summary=(
            "研究假设：系列化、开箱和可展示设计可能增强分享意愿，"
            "需通过公开内容数据继续验证。"
        ),
        evidence_ids=["trend-miniso-annual-2025-social"],
    ),
    TrendSignal(
        name="全球本地化",
        direction="up",
        summary="海外门店扩张需要全球 IP 资产与区域文化、节日和城市限定商品协同。",
        evidence_ids=["trend-miniso-q1-2026-global"],
    ),
]

_OFFLINE_TREND_EVIDENCE: List[Evidence] = [
    Evidence(
        source_id="trend-miniso-q1-2026-ip",
        source_type=SourceType.TREND,
        brand="MINISO",
        date="2026-05-26",
        text=(
            "名创优品官方于 2026-05-26 发布 2026 年一季度未经审计业绩：集团收入同比增长 "
            "28.5%，IP 授权费用同比增长 42.0%；公司说明该增长与持续投入 IP 发展有关。"
            "官方同时将品牌定义为提供具有鲜明 IP 设计的潮流生活方式产品的全球零售商。"
        ),
        url=Q1_RESULTS_URL,
        data_provenance="public",
    ),
    Evidence(
        source_id="trend-miniso-q1-2026-global",
        source_type=SourceType.TREND,
        brand="MINISO",
        date="2026-05-26",
        text=(
            "名创优品官方 2026-05-26 一季度业绩显示：截至 2026-03-31，MINISO 门店 "
            "8,210 家，其中海外 3,617 家；过去十二个月新增 MINISO 门店约 56% 位于海外。"
        ),
        url=Q1_RESULTS_URL,
        data_provenance="public",
    ),
    Evidence(
        source_id="trend-miniso-annual-2025-emotion",
        source_type=SourceType.TREND,
        brand="MINISO",
        date="2026-04-24",
        text=(
            "名创优品官方于 2026-04-24 发布 2025 年年报。年报披露平均每月推出约 1,600 个 SKU；"
            "本趋势将高频上新解读为测试设计吸引力与情绪价值的公开经营信号。"
        ),
        url=ANNUAL_REPORT_2025_URL,
        data_provenance="public",
    ),
    Evidence(
        source_id="trend-miniso-annual-2025-social",
        source_type=SourceType.TREND,
        brand="MINISO",
        date="2026-04-24",
        text=(
            "名创优品 2025 年年报于 2026-04-24 发布，并披露海外收入占比 44.2%。"
            "系列化、开箱和社交分享属于基于公开品牌与商品策略形成的待验证产品研究假设。"
        ),
        url=ANNUAL_REPORT_2025_URL,
        data_provenance="public",
    ),
]


def fetch_trends(keywords: List[str]) -> "tuple[List[TrendSignal], List[Evidence]]":
    """返回可复现的趋势信号及其官方公开 Evidence。"""
    try:
        from pytrends.request import TrendReq  # type: ignore  # noqa: F401

        log.bind(node="trends").info("pytrends 可用；仍返回带固定日期的离线趋势以保证复现。")
    except Exception:  # noqa: BLE001
        log.bind(node="trends").info("pytrends 不可用，使用带官方出处的离线趋势信号。")
    return list(_OFFLINE_TRENDS), list(_OFFLINE_TREND_EVIDENCE)
