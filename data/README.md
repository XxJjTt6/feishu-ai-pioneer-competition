# 数据说明

系统按 `category` 加载数据：优先 `data/processed/*.jsonl`，没有处理后文件时回退到
`data/sample/*.jsonl`。本项目的目标品牌是 `MINISO`，演示竞品是 `POP MART / DAISO /
MUJI / Flying Tiger`。

## 1. 合成演示样本

```bash
python3 data/make_sample.py
```

生成器使用固定种子 `20260719`，输出 400 条 `interest_goods` 评论，其中 MINISO 140 条、
四个竞品各 65 条。每条记录都有稳定的 `demo-*` ID、`demo://synthetic/*` URL 和
`data_provenance=synthetic_demo` 标签。

**这些样本完全由模板和伪随机数合成，只用于离线演示与测试，不是真实用户评论，不是
MINISO 或任何竞品的企业数据，也不能用于推断品牌实际表现。** 各品牌的情感概率只为让
ABSA 和竞品分析产生可观察差异。

## 2. 可选公开评论

调用方在确认网站条款、授权、隐私与研究用途后，可提供公开 JSON/JSONL URL：

```bash
PYTHONPATH=backend python3 -m miniso_studio.infrastructure.data.retail_reviews \
  --source-url 'https://example.org/licensed-open-reviews.jsonl' \
  --brand MINISO --max-reviews 800
```

连接器只下载调用方明确指定的 URL，并标准化常见字段。输出到 `data/processed` 不意味着
数据完整、具有代表性或来自品牌内部；报告必须保留原始 URL、采集日期和许可说明。

## 3. 统一字段

每行 JSONL 至少包含：

```json
{"source_id":"demo-miniso-0001","source_type":"review","brand":"MINISO",
 "product":"IP联名毛绒挂件","category":"interest_goods","rating":4,
 "text":"IP联名设计很可爱。","date":"2026","helpful_votes":12,
 "url":"demo://synthetic/miniso/0001","data_provenance":"synthetic_demo"}
```

`loader.py` 会忽略品牌大小写、规范化五个已配置品牌，并只加载请求的 `category`。加载后
统一转换为 `common/models.py` 中的 `Evidence`，Agent 通过 `source_id` 追溯证据。

## 4. 离线趋势公开来源

- 2026-05-26，MINISO 官方 2026 年一季度未经审计业绩：
  <https://ir.miniso.com/2026-05-26-MINISO-Group-Announces-March-Quarter-2026-Unaudited-Financial-Results>
- 2026-04-24 发布的 MINISO 2025 年年报：
  <https://ir.miniso.com/image/Annual+Report+2025+US.pdf>

趋势连接器把“IP 联名、情绪价值、社交传播、全球本地化”作为基于公开材料的产品研究
信号；其中解释性趋势是待验证假设，不应被写成官方结论。
