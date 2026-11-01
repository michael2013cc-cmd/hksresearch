# HKEX 公告雷达 — 事件族架构与技能设计

> 版本: 1.0 | 日期: 2026-11-01 | 状态: 已确认，待实施
> 前序文档: `2026-10-29-hkex-daily-radar-design.md`（采集/精读/评分/日报底座）
> 实证样本: 2026-10-30 全量 1,147 条公告、128 份翌日披露报表

---

## 1. 结论摘要

1. **翌日披露报表（NDR）不单独做成 skill。** 它落为 `analyzers/ndr.py`（确定性解析）+ `references/ndr-playbook.md`（判断手册），由总技能引用。
2. **不按交易所 14 个大类拆子项目。** 按 7 个事件族拆分：NDR、资本动作、交易、业绩、治理、股息、停复牌；剩余内幕消息作为兜底分类。所有族共用一个仓库、一套采集与事件库。
3. **只做一个总技能 `hkex-radar`。** 技能负责路由、解读、决策口径与护栏；代码负责抽取与校验。只有出现外部复用或独立发布需求时，才把某个族拆成独立包/技能。
4. **先做 P0 + P1。** P0 建立分析器契约并把 NDR 迁入，行为不变；P1 建事件库、告警与技能 v1。P0/P1 完成后再进入资本动作族。

---

## 2. 背景与实证

### 2.1 复杂度不在抓取，而在语义

采集层已经解决单日 1,000 行上限（双向拉取 + 按 `NEWS_ID` 合并）与时间窗过滤。真正的复杂度是：

1. **标签与内容不一致。** 2026-10-30 的 128 份 NDR 只有两个交易所标签，逐份读正文后实际分成 11 类；“股份購回”标签下有 8 份当日零回购，只是注销旧购回；“其他”标签下藏着配售、供股、内资股转 H 股、股份合并、以股代息、单位发行。
2. **一条事件跨多份文件。** 配售公告 → 上市文件 → 次日 NDR → 月报表；回购公告 → NDR 每日购回 → 注销 → 月报表。按文件分析会丢链路。
3. **同类文件版式不同。** NDR 是稳定表格，适合确定性解析；业绩、交易、内幕消息是叙述 + 表格混合，需要 LLM 抽取 + 引文校验。
4. **影响力需要外部基数。** 回购金额、交易代价必须用市值、成交额、财务基数归一，否则结论系统性偏向大盘股。
5. **修订版、A+H 副本、多柜台、多类别股份、多币种、季节性。** 这些是长期存在的边界条件，必须进入数据模型而不是临时补丁。

### 2.2 2026-10-30 分类证据

| 大类 | 条数 | 占比 | 处理 |
|---|---:|---:|---|
| 公告及通告 | 629 | 54.8% | 拆成交易、业绩、治理、股息、剩余内幕消息 |
| ETF 交易资料 | 151 | 13.2% | 丢弃，仅计数 |
| 翌日披露报表 | 128 | 11.2% | NDR 分析器 |
| 通函 | 71 | 6.2% | 挂靠交易/股东大会事件 |
| 债券及结构性产品 | 67 | 5.8% | 丢弃，仅计数 |
| 财务报告/ESG | 24 | 2.1% | 独立研究产品，不进日报 |
| 委任代表表格 | 23 | 2.0% | 丢弃 |
| 展示文件 | 18 | 1.6% | 丢弃 |
| 上市文件 | 9 | 0.8% | 挂靠资本动作事件 |
| 杠杆及反向产品 | 9 | 0.8% | 丢弃 |
| 月报表 | 8 | 0.7% | 丢弃，可用于股本校验 |
| 宪章文件 | 5 | 0.4% | 丢弃 |
| 公司资料报表 | 4 | 0.3% | 丢弃 |
| 合并守则-交易披露 | 1 | 0.1% | 并入交易族 |

“公告及通告”内部的日量级：内幕消息 104、季度业绩 58、海外监管-营运业绩 44、附属公司业绩 18、更换董事 52、审核委员会 20、关连交易 17、持续关连交易 18、主要交易 15、须予披露交易 14、收购守则相关 16、股息/分派 28、停牌 10、配售 6、根据授权发行 18、股份计划 6、海外监管-证券发行 10。标签可重叠，不能直接相加。

---

## 3. 目标与非目标

### 3.1 目标

- **G1 事件化**：把“文件列表”转成“公司事件时间线”，同一事件的多份文件可关联。
- **G2 可解释**：每个数字带 PDF 页码与原文引文，每个告警带触发规则。
- **G3 可比较**：跨事件族用统一的重大性口径（规模按市值/成交额/财务基数归一）。
- **G4 可扩展**：新增事件族只增加分析器、规则包、金标准样本，不改核心。
- **G5 可运维**：每日批处理可重跑、幂等、失败可定位；LLM 结果缓存。

### 3.2 非目标

- 不做自动交易、不给买卖建议、不预测股价方向。
- 不为 ETF、债券、杠杆产品、月报表、委任代表表格建分析器。
- 不做全量公告的 LLM 摘要；只对路由后的高价值事件定向抽取。
- 不做历史全量回填；只按需回看近 N 天用于校准。
- 不把解析规则写进技能文本。

---

## 4. 设计原则

1. **以事件为中心，不以文件为中心。** 文件是证据，事件才是分析与决策的单位。
2. **代码做确定性，技能做判断性。** 表格解析、数值校验、去重、幂等属于代码；重要性判断、比较、决策口径属于技能。
3. **没有证据的数字不进入结论。** 数字事实必须带页码与原文引文；引文校验失败则丢弃或降置信度。
4. **共享核心，独立分析器。** 采集、归一化、PDF、LLM、证据、事件库只实现一次；每个族只实现“匹配、抽取、解释”。
5. **YAGNI。** 先做 7 个族，不做 14 个；先 SQLite，不上服务；先 P0/P1，不一次性铺开。

---

## 5. 系统架构

```
L1 Collector        全量抓取 + 双向合并 + 原始快照
L2 Normalizer       多柜台/修订版/去重/分类标签归一
L3 Router           taxonomy.yaml：doc_group + tags → 事件族
L4 Analyzers        ndr | capital_actions | transactions | results |
                    governance | dividends | trading_status | inside_info
L5 Evidence/Store   Fact + Event + Link + SQLite 事件库
L6 Market/Financial 收盘价、市值、20 日成交额、财务事实
L7 Scorer/Decision  族内重大性 + 跨族影响 + P0/P1/P2 告警
L8 Reporter         日报、族报、告警清单（Markdown + JSON）
L9 Skill            hkex-radar：路由、解读、决策口径、护栏
```

### 5.1 模块布局

```
hkexradar/
  collector.py            # 现有，保持
  normalizer.py           # 现有，保持
  triage.py               # 现有，逐步降级为“粗筛”
  taxonomy.py             # 新增：加载 taxonomy.yaml，路由
  models.py               # 保留文档/评分模型；新增事件模型可放 analyzers/base.py
  analyzers/
    __init__.py
    base.py               # Fact / Evidence / Event / Analyzer 协议
    ndr.py                # 从 hkexradar/ndr.py 迁入
    capital_actions.py    # P2
    transactions.py       # P3
    results.py            # P4
    governance.py         # P3
    dividends.py          # P5
    trading_status.py     # P1 告警，P3 完整
  store.py                # SQLite 事件库
  marketdata.py           # P2：行情/市值/成交额
  pipeline.py             # 编排：采集 → 路由 → 分析 → 存储 → 报告
  reporter.py             # 现有日报；新增族报/简报模板
  run.py                  # CLI：--family、--date、--from-time
scripts/
  ndr_analysis.py         # 薄封装，保留现有用法
skills/
  hkex-radar/
    SKILL.md
    references/
    scripts/
config/
  taxonomy.yaml
  analyzers/
    ndr.yaml
    capital_actions.yaml
    ...
```

### 5.2 数据流

1. 采集并落原始快照；归一化得到 `Announcement`。
2. 路由为每个公告选择一个或多个族；例行族直接计数丢弃。
3. 分析器按需下载/读取 PDF，产出 `Fact` 与 `Event`。
4. 事件库按 `news_id` 幂等写入；同一公司的事件用 `links` 关联。
5. 评分器读取族内指标与外部基数，产出 `materiality` 与告警级别。
6. 报告器生成日报/族报；技能读取报告与事件库回答追问。

---

## 6. 分类路由

### 6.1 配置示例

```yaml
version: 1
families:
  transactions:
    groups: [公告及通告, 合併守則 - 交易披露]
    tags:
      - 須予披露的交易
      - 主要交易
      - 非常重大收購或出售
      - 關連交易
      - 持續關連交易
      - 《收購守則》所指的要約公司刊發的公告
      - 《收購守則》所指的受要約公司刊發的公告
    priority: 100
  results:
    groups: [公告及通告]
    tags: [季度業績, 中期業績, 末期業績, 全年業績, 盈利警告, 盈利預喜, 海外監管公告-營運業績最新情況, 附屬公司的業績]
    priority: 90
  capital_actions:
    groups: [公告及通告, 上市文件]
    tags: [配售, 供股, 根據一般性授權發行股份, 根據特定授權發行股份, 股份計劃, 可換股債券, 海外監管公告-證券發行及相關事宜]
    priority: 80
  governance:
    groups: [公告及通告]
    tags: [更換董事或重要行政職能或職責的變更, 更換審核委員會成員, 更換薪酬委員會成員, 更換提名委員會成員, 更換公司秘書, 更換核數師, 董事名單和他們的地位和作用]
    priority: 70
  dividends:
    groups: [公告及通告]
    tags: [股息或分派, 股息或分派（公告表格）]
    priority: 60
  trading_status:
    groups: [公告及通告]
    tags: [停牌, 復牌, 短暫停牌]
    priority: 110
  ndr:
    groups: [翌日披露報表]
    tags: [股份購回]
    priority: 50
  inside_info:
    groups: [公告及通告]
    tags: [內幕消息]
    priority: 10
routine:
  groups:
    - 交易所買賣基金的交易資料
    - 債券及結構性產品
    - 槓桿及反向產品的交易資料
    - 月報表
    - 委任代表表格
    - 展示文件
    - 憲章文件
    - 公司資料報表
    - 財務報表/環境、社會及管治資料
```

### 6.2 路由规则

1. 先按 `priority` 从高到低匹配；优先级只决定“主族”与报告顺序，不改变告警时效。
2. 主族顺序：停复牌（110，告警时效最高）→ 交易（100）→ 业绩（90）→ 资本动作（80）→ 治理（70）→ 股息（60）→ NDR（50）→ 剩余内幕消息（10）。
3. 一条公告命中多个族时，除主族外只做轻量关联（如停牌公告同时是重大交易，则交易族仍建链接），不重复 LLM 精读。
4. **海外监管公告按内容标签路由**，不按 `doc_group` 整体丢弃；A+H 公司的副本与主公告做 `same_event` 去重。
5. **通函、上市文件不独立分析**：若标题/标签能关联到已有事件，则挂 `follows`；否则进入“未关联文件”清单。
6. **修订版**：不重复建事件；更新原事件的 `documents` 链接，并在报告中标注“经修订”。
7. **未知标签**：进入 `data/unclassified/YYYY-MM-DD.json`，每周汇总一次，人工决定是否新增族或例行规则；不静默丢弃。
8. 例行组只计数，不下载 PDF；但月报表的已发行股本可用于 NDR 的股本校验，按需单独读取。

---

## 7. 分析器契约

### 7.1 基础模型

```python
class Evidence(BaseModel):
    page: int | None = None
    quote: str

class AnalyzerFact(BaseModel):
    key: str
    value: str
    unit: str | None = None
    currency: str | None = None
    evidence: Evidence
    confidence: float = 1.0

class AnalyzerEvent(BaseModel):
    family: str
    type: str
    code: str
    news_id: str
    effective_date: date | None = None
    direction: Literal["positive", "negative", "neutral", "unclear"] = "unclear"
    materiality: float = 0.0
    confidence: float = 1.0
    summary: str = ""
    facts: list[AnalyzerFact] = []
    links: list[tuple[str, str]] = []   # (type, target_event_id)

class AnalyzerResult(BaseModel):
    analyzer: str
    events: list[AnalyzerEvent]
    warnings: list[str] = []
```

### 7.2 协议

```python
class Analyzer(Protocol):
    family: str
    def matches(self, ann: Announcement) -> bool: ...
    def analyze(self, ann: Announcement, text: str, ctx: "AnalysisContext") -> AnalyzerResult: ...
```

`AnalysisContext` 提供：`root`、`store`、`marketdata`、`llm`、`day_counts`、`is_revision`。分析器不得直接访问网络；下载与缓存由 pipeline 注入。

### 7.3 NDR 适配

现有 `parse_filing` 保留为纯函数，新增 `NdrAnalyzer`：

- `matches`: `doc_group == "翌日披露報表"`。
- `analyze`: 调 `parse_filing`，把 `Filing` 转成 `AnalyzerEvent`：
  - 事件类型 = `filing.category`；子类型 = `subtypes`。
  - 事实 = 购回股数/金额/币种、注销股数、待注销股数、期初/期末股本、发行股数。
  - 证据 = 表格所在页与原文行（PDF 文本带页边界，按行定位）。
- 多类别、多币种、空库存字段等边界继续由现有测试覆盖。
- 纯函数与适配器分离，保证解析逻辑可单测、可回归。

### 7.4 错误处理

- PDF 下载失败：记 `text_status=unavailable`，事件降级为“标题级”，置信度 0.3，不阻断其他族。
- 文本为空/乱码：不调用 LLM；进入质量统计。
- LLM 输出 schema 失败：重试 1 次，再失败降级规则摘要。
- 数字校验失败（如 股数 × 价格 ≠ 金额，期初 + 变动 ≠ 期末）：保留事件但标 `warning`，置信度降低；报告中显式提示。
- 同一 `news_id` 重跑：事件按 `(news_id, family, type)` 幂等覆盖，不重复累计。

---

## 8. 事件库

SQLite，路径 `data/events.db`，开启 WAL。表结构：

```sql
CREATE TABLE documents (
  news_id TEXT PRIMARY KEY,
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  published_at TEXT NOT NULL,
  doc_group TEXT NOT NULL,
  tags TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  pdf_path TEXT,
  text_status TEXT NOT NULL,
  is_revision INTEGER NOT NULL DEFAULT 0,
  revision_of TEXT
);

CREATE TABLE events (
  event_id TEXT PRIMARY KEY,
  family TEXT NOT NULL,
  type TEXT NOT NULL,
  code TEXT NOT NULL,
  news_id TEXT NOT NULL,
  effective_date TEXT,
  direction TEXT NOT NULL,
  materiality REAL NOT NULL,
  confidence REAL NOT NULL,
  summary TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE facts (
  event_id TEXT NOT NULL,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  unit TEXT,
  currency TEXT,
  page INTEGER,
  quote TEXT NOT NULL,
  confidence REAL NOT NULL,
  PRIMARY KEY (event_id, key)
);

CREATE TABLE links (
  from_event TEXT NOT NULL,
  to_event TEXT NOT NULL,
  type TEXT NOT NULL,
  PRIMARY KEY (from_event, to_event, type)
);

CREATE TABLE runs (
  run_id TEXT PRIMARY KEY,
  report_date TEXT NOT NULL,
  window_from TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  counts TEXT NOT NULL,
  errors TEXT NOT NULL
);

CREATE INDEX idx_events_code_date ON events(code, effective_date);
CREATE INDEX idx_events_family ON events(family);
CREATE INDEX idx_documents_date ON documents(published_at);
```

约定：

- `event_id` 使用 `"{news_id}:{family}:{type}"`，天然幂等。
- `documents` 与 `events` 多对多通过 `events.news_id`；同一事件多份文件用 `links(same_event)`。
- 报告与 JSON 仍落 `reports/`，事件库是跨天查询与关联的底座。
- 不存 PDF 二进制；只存路径，PDF 留在 `data/raw/`。

---

## 9. 事件族设计

| 族 | 输入 | 抽取内容 | 关键指标 | 阶段 |
|---|---|---|---|---|
| NDR | 翌日披露报表 PDF | 股份变动、购回成交、待注销、库存股出售 | 回购额/成交额、净摊薄、注销管道、回购目的 | P0–P1 |
| 资本动作 | 配售/供股/可转债/股份计划/上市文件 | 发行股数、价格、折让、募资额、用途、锁定期 | 摊薄 %、折让 %、募资/市值、大股东参与 | P2 |
| 交易 | 须予披露/主要/非常重大/关连交易 | 对手方、代价、标的、四项规模比率、关连属性 | 代价/市值、规模比率、关连交易占比 | P3 |
| 业绩 | 业绩公告/盈警盈喜/营运数据 | 收入、利润、EPS、毛利率、股息、指引 | 同比、超预期、股息变化、指引方向 | P4 |
| 治理 | 董事/CEO/CFO/公司秘书/核数师/委员会 | 离任原因、继任者、生效日、角色 | 角色关键性、是否核数师、继任是否空缺 | P3 |
| 股息 | 股息/分派公告 | 每股股息、总额、除净日、派付日、频率 | 股息率（需股价）、同比、特别股息 | P5 |
| 停复牌 | 停牌/复牌公告 | 原因、时间、复牌条件 | 直接 P0；持续时长 | P1 告警 |
| 剩余内幕消息 | 未被其他族路由的内幕消息 | 事件实质、主体、金额、时间 | 按实质分类后的重大性 | P5 |

### 9.1 NDR 族的最小决策规则（P1）

- 净摊薄 = 新发行股数 / 期初股本。≥10% 记 P0，≥5% 记 P1。
- 注销管道 = 待注销股数 / 期末股本。≥5% 记 P1。
- 当日回购金额 / 当日成交额（P2b 已接入；20 日 ADV 待批量抓取历史行情）。无行情数据时退化为绝对金额并标注“未归一”。
- 回购目的为“拟注销”优先于“库存”；库存股后续出售是潜在反向信号。
- 同日“回购 + 注销 + 发行”并存时，必须分别列出，不合并成单一结论。

阈值放 `config/analyzers/ndr.yaml`，代码只读配置。

---

## 10. 技能设计

### 10.1 一个总技能

目录：

```
skills/hkex-radar/
  SKILL.md
  references/
    taxonomy.md
    ndr-playbook.md
    capital-actions-playbook.md
    transactions-playbook.md
    results-playbook.md
    governance-playbook.md
    decision-rules.md
  scripts/
    run_daily.py
```

`SKILL.md` 结构：

```yaml
---
name: hkex-radar
description: 分析港交所披露易公告，按事件族抽取事实、评估重大性、生成日报/告警。用于查询某日公告、回购、配售、业绩、交易、停牌等。
---
```

正文只写：

1. **触发场景**：港交所/披露易/公告/翌日披露报表/回购/配售/供股/业绩/盈警/停牌/复牌。
2. **标准流程**：确认日期与时间窗 → 运行采集（或回放快照）→ 查看族报告 → 查事件库关联 → 给结论与证据。
3. **命令**：
   ```bash
   python -m hkexradar.run --date 2026-10-30 --from-time 16:00
   PYTHONPATH=. python scripts/ndr_analysis.py --date 2026-10-30
   ```
4. **阅读顺序**：先看告警，再看族内 Top，再看事件链接，最后看明细；每个数字回到 PDF 页码。
5. **硬性护栏**：
   - 所有时间默认 HKT。
   - 单日 API 上限 1,000 行，报告必须说明是否使用双向合并。
   - 交易所标签不等于内容；“股份購回”标签下可能当日零回购。
   - 没有原文引文的数字不得进入结论。
   - 不输出买卖建议；告警是“需关注”，不是“该买/该卖”。

### 10.2 Playbook 的边界

- `ndr-playbook.md` 写：11 类含义、Section 1/2/3/B 怎么读、注销 vs 库存、常见误判、阈值。
- 其他 playbook 在对应族进入开发时再写，不预先生成空文件。
- playbook 只写判断与陷阱，不复制解析代码或正则。

### 10.3 何时拆独立技能/包

满足任一条件才拆：

1. 有外部使用者或其他项目复用；
2. 需要独立发布节奏/版本；
3. 形成完全不同的多步工作流（如 NDR 信号回测）。

拆的时候把 `analyzers/ndr`、测试、CLI 一起抽成包，技能只引用，不复制逻辑。

---

## 11. 评分与决策

### 11.1 两层评分

**族内重大性（0–100）** 由各族规则计算；**跨族影响** 统一为：

```
impact = 100 × 规模分 × 意外度 × 置信度
规模分 = clamp(绝对规模 / 公司基数, 0, 1) 的单调映射
公司基数 = 市值（优先）或 20 日成交额；缺失时用行业中位数并标注
```

输出 P0/P1/P2：

- **P0**：停牌/复牌、核数师辞任、重大交易、摊薄 ≥10%、退市/清盘/违约。
- **P1**：回购额/成交额 ≥10%、注销管道 ≥5%、董事/CFO 变更、配售/供股、摊薄 5–10%。
- **P2**：常规回购、一般治理变更、股息例行公告。

### 11.2 必须补的外部数据

P2b 已实现 `marketdata.py`：

- 港交所官方日行情（主板 + GEM），解析固定宽度报价，缓存到 `data/cache/market/quotes-YYYY-MM-DD.json`；
- 市值(推算) = 股本 × 收市价（停牌/无成交用前收市价）；股本优先取公告披露值，其次 NDR 期末股本或发行比例反推；
- 当前报告用当日成交额做流动性对照；`average_turnover()` 已支持 20 日 ADV，但尚未批量抓取历史行情；
- 所有“未归一”的金额在报告中显式标注，避免把绝对金额当成影响力；H 股 NDR 股本口径需单独提示。

P4 增加财务事实库（收入、利润、资产、股本），用于交易规模比率与业绩同比；在 P4 之前，交易族只输出“代价/市值”近似口径并标注。

### 11.3 决策输出

日报分三层：

1. **今日必看（P0/P1）**：每条一句话 + 关键数字 + 证据页码。
2. **族内摘要**：NDR、资本动作、交易、业绩、治理各 3–5 条。
3. **观察清单**：未达告警阈值但值得跟踪的事件（如注销管道累积）。

不输出买卖建议；不把“方向”当作股价预测。

---

## 12. 实施计划

### P0 — 分析器骨架（0.5–1 天）

1. 新建 `hkexradar/analyzers/base.py`：`Evidence`、`AnalyzerFact`、`AnalyzerEvent`、`AnalyzerResult`、`Analyzer` 协议。
2. 把 `hkexradar/ndr.py` 迁到 `hkexradar/analyzers/ndr.py`，保留全部纯函数；更新 `scripts/ndr_analysis.py`、`tests/test_ndr.py` 的导入。
3. 新增 `NdrAnalyzer` 适配器，把 `Filing` 转成 `AnalyzerEvent` + `AnalyzerFact`；不改变现有报告输出。
4. 现有 81 项测试全绿；10-30 的 NDR 报告逐字节不变（或明确记录差异）。

**验收**：`python -m pytest -q` 全绿；`PYTHONPATH=. python scripts/ndr_analysis.py --date 2026-10-30` 产物与迁移前一致。

### P1 — NDR 事件库 + 告警 + 技能 v1（1–1.5 天）

1. `hkexradar/store.py`：建表、幂等写入、按日/按公司查询；测试用临时 SQLite。
2. NDR 分析后写事件库；新增 `reports/YYYY-MM-DD-ndr-brief.md`（P0/P1 告警 + Top 10 + 质量统计）。
3. 阈值配置 `config/analyzers/ndr.yaml`；告警规则单测。
4. `skills/hkex-radar/`：SKILL.md、taxonomy.md、ndr-playbook.md、decision-rules.md；脚本薄封装。
5. 用 10-30 数据验收：128/128 解析；Top 20 告警人工复核一致；技能能回答“昨天回购最多的三家公司”并给页码。

### P2–P5（后续，逐族交付）

- P2（2–3 天）：`marketdata.py` + `capital_actions.py` + 摊薄监控；验收 10-30 的 2 配售/2 供股/1 换股转换。**P2a（资本动作）与 P2b（行情/市值归一）已完成**。
- P3（3–5 天）：`transactions.py` + `governance.py` + `dividends.py` + 停复牌告警；30 份金标准，数字抽取 ≥90%。
- P4（4–6 天）：`results.py` + 财务事实库；20 份业绩，收入/利润/股息 ≥90%。
- P5（2 天）：`inside_info.py` + 跨族日报 + 定时任务；一页简报 <5 分钟生成。

每阶段独立提交、独立验收；不把多个族绑在一个大版本里。

---

## 13. 测试策略

- **单元测试**：纯解析函数、路由、阈值、SQLite 写入、证据校验；不触网。
- **集成测试**：用 `data/fixtures/` 快照回放全链路；LLM 用假客户端。
- **金标准**：每个族 20–30 份人工标注样本，记录 `news_id`、关键数字、类别、告警级别；比较抽取准确率。
- **回归**：NDR 现有 6 项测试扩展为金标准；P0 迁移前后报告 diff 必须为零。
- **质量门**：数字抽取 ≥95%（NDR）、≥90%（其他族）；告警精确率人工抽检 ≥80%；无证据事实为 0。

---

## 14. 运维

- 每日批处理：采集 → 路由 → 分析 → 入库 → 日报；失败重跑幂等。
- 缓存：LLM 按 `(news_id, prompt_version, model)`；PDF 按 `NEWS_ID`。
- 日志：每次运行写 `runs` 表；采集错误、PDF 失败、未分类标签进入质量统计。
- 备份：`data/events.db` 每日复制；原始快照与 PDF 不覆盖。
- 成本：只对高价值事件调用 LLM；NDR 等确定性族零 LLM。

---

## 15. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 交易所标签/版式变化 | 路由漏判、解析失败 | 未知标签周报；金标准回归；解析失败降级不阻断 |
| LLM 数字幻觉 | 错误结论 | 引文校验 + 算术校验 + 置信度；无证据不入结论 |
| 行情数据缺失/许可 | 影响力偏向大盘股 | 已用港交所日行情 + 本地缓存；失败时标注“未归一”；市值是股本×收市价 proxy |
| 财务基数缺失 | 交易规模比率不准 | P3 近似口径并标注；P4 建财务事实库后升级 |
| 事件重复/修订 | 重复计数 | `news_id` 幂等；修订链接；`same_event` 去重 |
| 范围膨胀 | 长期不能交付 | 只做 7 族；每阶段独立验收；例行组不建分析器 |
| 季节性峰值 | 单日处理超时 | 分区队列；并发下载；LLM 限流；先出确定性族报告 |

---

## 16. P0/P1 验收清单

- [ ] 81 项现有测试全绿。
- [ ] NDR 迁移后 10-30 报告与迁移前一致。
- [ ] `data/events.db` 可重建；同一快照重跑事件数不增加。
- [ ] `2026-10-30-ndr-brief.md` 生成，含 P0/P1 告警、Top 10、质量统计。
- [ ] 告警 Top 20 人工复核一致。
- [ ] `hkex-radar` 技能可被调用，能回答“某日回购最多的三家公司”并给页码。
- [ ] 报告中所有数字均有原文引文；无证据事实为 0。

---

## 17. 附录：2026-10-30 NDR 基线

- 128 份，128/128 文本抽取成功，无 OCR 需求。
- 交易所标签：股份購回 109、其他 21（2 份双标签）。
- 内容分类：新增購回 99、註銷購回股份 8、混合 7、購回並註銷 5、配售/認購 2、供股 2、股份計劃發行 1、內資股轉H股 1、以股代息 1、單位發行 1、股份合併/資本重組 1。
- 回购：85 份有第二章節，65,874,331 股；HKD 816,117,834 / USD 1,244,678 / GBP 10,004,670 / RMB 154,447,670。
- 目的：拟注销 35,781,381 股、拟持作库存 30,092,950 股。
- 待注销存量：25 份、323,762,341 股；纯注销 8 份、341,047,000 股；注销总量 352,072,936 股。
- 发行：15 份、+2,208,209,592 股；最大为煜榮 +1.368B（+300%）。
- 集中度：中国宏桥占 HKD 回购额 74.9%，前三名 83.0%。

这些数字是 P1 告警与回归的基线；后续重跑若变化，必须能解释来源。
