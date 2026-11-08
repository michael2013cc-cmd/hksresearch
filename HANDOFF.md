# HKEX 公告雷达 · 交接说明

> 状态时间：2026-11-08　｜　分支：`master`　｜　最新功能提交：`282b50c`　｜　测试：155 passed

本文档面向第一次接手这个仓库的人。读完应能在 15 分钟内跑起来，并知道下一步该做什么。日常用法见 [README.md](README.md)，设计细节见 [架构设计](docs/superpowers/specs/2026-11-01-hkex-radar-architecture-design.md)。

## 1. 项目是什么

抓取港交所披露易（HKEXnews）每日公告 → 归一化 → 分诊 → 按事件族抽取事实 → 写入 SQLite → 生成日报、族简报与 P0/P1 告警。

明确不做：实时行情、买卖建议、非港交所公告、纯新闻摘要。

当前已跑通的闭环：

1. **全市场日报**：采集、归一、分诊、LLM/规则精读、评分、Markdown/JSON 日报。
2. **事件族专项**：NDR（回购/注销/发行）、资本动作（配售/供股/可转债）、停复牌（含交易所 HTML 通告）。每个族都能抽事实、写事件库、出决策简报。

## 2. 15 分钟接手

### 2.1 环境

- Python **3.11+**（Windows 上用 `python`，不要假设有 `python3`）。
- Git Bash / PowerShell 均可；命令示例按 Git Bash 写。

```bash
git clone https://github.com/michael2013cc-cmd/hksresearch.git
cd hksresearch
pip install httpx pydantic PyYAML pymupdf pytest

# 可选：配置 LLM。不配也能跑，自动降级为规则摘要
cp config/settings.example.yaml config/settings.yaml
export DEEPSEEK_API_KEY=...
# 或 MiniMax 国际版：编辑 settings.yaml 后 export MINIMAX_API_KEY=...
```

`config/settings.yaml` 已被 gitignore，只提交 `settings.example.yaml`。密钥只放环境变量，任何情况下不要写进仓库文件。

### 2.2 先验证，不联网

```bash
# 全量测试（约 3 秒，不触网；HTTP 用 MockTransport，LLM 用假客户端）
python -m pytest tests

# 用仓库自带的 590 条真实快照离线回放，不下载 PDF、不调 LLM
python -m hkexradar.run --date 2026-09-08 \
  --offline data/fixtures/2026-09-08.json --no-pdf --no-llm --limit 5
```

第二条命令应在 `reports/` 生成 `2026-09-08-hkex-daily.md` 与同名 `.json`。

Windows 终端若中文乱码，先设置：

```bash
export PYTHONIOENCODING=utf-8          # Git Bash
$env:PYTHONIOENCODING = "utf-8"        # PowerShell
```

### 2.3 跑一天真实数据

族分析脚本不负责抓公告列表，必须先有快照。首次运行：

```bash
# 1) 抓取当天公告快照（不下载 PDF 可加 --no-pdf；不调 LLM 加 --no-llm）
python -m hkexradar.run --date 2026-10-30 --no-pdf --no-llm

# 2) 再跑各族专项（脚本会自行下载/缓存 PDF 与 HTML）
PYTHONPATH=. python scripts/ndr_analysis.py --date 2026-10-30
PYTHONPATH=. python scripts/capital_analysis.py --date 2026-10-30
PYTHONPATH=. python scripts/trading_status_analysis.py --date 2026-10-30
```

`scripts/` 未安装为包，**所有脚本都要加 `PYTHONPATH=.`**。行情接口临时不可用时，NDR/资本脚本可加 `--no-market`。

## 3. 当前完成度

| 阶段 | 内容 | 状态 |
|---|---|---|
| P0 | 采集、归一、分诊、LLM 精读、评分、日报 | 已完成 |
| P0.1 | Analyzer 统一契约（事件/事实/证据） | 已完成 |
| P1 | SQLite 事件库、NDR 告警简报、hkex-radar 技能 | 已完成 |
| P2a | 资本动作分析器（配售/供股/可转债/合并） | 已完成 |
| P2b | 官方日行情、市值/成交额归一 | 已完成 |
| P3a | 停复牌（PDF 公司公告 + HTML 交易所通告） | 已完成 |
| P3b | 治理（董事/CFO/公司秘书/核数师/委员会） | **下一步** |
| P2c | 20 日 ADV 批量接入 | 待做 |
| P3c | 交易（须予披露/关连） | 待做 |
| P3d | 股息/分派 | 待做 |
| P4 | 业绩/盈警 + 财务事实库 | 待做 |
| P5 | 剩余内幕消息、跨族日报、定时任务 | 待做 |

已验收基线：

- **155** 项测试全部通过。
- **2026-10-30 停复牌**：15 份命中 → 12 个唯一事件，全部 P0；3 份交易所通告被同日同状态的公司公告去重；复牌日与原停牌日不再混淆。
- **2026-10-30 NDR**：128/128 份解析，分类与明细、回購金额、注销管道均落库。
- **2026-10-30 资本动作**：配售/供股/终止等事件出简报并写事件库。
- **2026-10-29 / 10-28 行情**：主板约 16.8k 条、GEM 约 311 条，均可解析。

## 4. 目录地图

```
hkexradar/                     # 包本体
  collector.py                 # 披露易 titleSearchServlet 采集、快照读写、1000 行上限处理
  normalizer.py                # 多柜台代码、HTML 反转义、修订标记、去重
  triage.py                    # 按 config/routine_rules.yaml 剔除例常文件
  reader.py / llm.py           # LLM 精读与规则摘要降级
  scorer.py / reporter.py      # 评分与日报
  pipeline.py / run.py         # 全市场日报编排与 CLI
  pdf.py                       # PDF 下载、前 5 页抽取、免责声明清理、乱码判定
  htmltext.py                  # HTML 通告正文抽取（P3a）
  marketdata.py                # 主板/GEM 官方日行情、市值 proxy、20 日 ADV 工具
  store.py                     # SQLite：documents / events / facts / links / runs
  analyzers/
    base.py                    # Analyzer 协议 + AnalyzerEvent/Fact/Evidence
    ndr.py                     # NDR 事件族
    capital.py                 # 资本动作事件族
    trading_status.py          # 停复牌事件族
  ndr_brief.py                 # NDR 告警与简报
  capital_brief.py             # 资本动作告警与简报
  trading_status_brief.py      # 停复牌去重、P0 告警与简报

scripts/                       # 薄封装，必须 PYTHONPATH=.
  ndr_analysis.py
  capital_analysis.py
  trading_status_analysis.py
  fetch_fixture.py             # 把某天快照写入 data/fixtures/

config/
  settings.example.yaml        # LLM + 采集 + 日报参数
  routine_rules.yaml           # 分诊规则
  category_prior.yaml          # 类别先验
  analyzers/ndr.yaml           # NDR 告警阈值
  analyzers/capital.yaml       # 资本动作告警阈值

tests/                         # 155 项，全部离线
data/fixtures/2026-09-08.json  # 唯一入库的全天快照，用于离线回放
skills/hkex-radar/             # 可安装的 Qoder 技能（SKILL.md + 4 份参考手册）

data/raw/                      # gitignored：快照、PDF、HTML 缓存
data/cache/                    # gitignored：行情与 LLM 缓存
data/events.db                 # gitignored：事件库
reports/                       # gitignored：日报与族简报
```

## 5. 两条运行链路

### 5.1 全市场日报

`run.py` → `pipeline.run_day()`：

1. 实时抓取或读取 `--offline` 快照；实时抓取会写 `data/raw/<day>/announcements*.json`。
2. 归一化 → 分诊（剔例行件）→ 按类别先验与文件大小排序。
3. 下载前 N 份 PDF，抽取正文；有 LLM 时逐条精读，否则用规则摘要。
4. 评分：`final = 0.6 × magnitude + 0.4 × interest`；S≥80、A≥65、B≥50。
5. 写 `reports/YYYY-MM-DD-hkex-daily.md/.json`。

### 5.2 事件族专项

`scripts/<family>_analysis.py`：

1. 读取 `data/raw/<day>/announcements.json`。
2. `normalize_all()` 后用 `analyzer.matches()` 筛公告。
3. PDF 用 `pdf.download_pdf/extract_pages`；HTML 通告用 `htmltext`（P3a）。
4. `analyzer.analyze()` 产出 `AnalyzerResult`，事实带页码与原文引文。
5. `EventStore.add_result()` 按 `family` 幂等写库（同一 `news_id` 重跑会覆盖旧事件）。
6. 族简报做去重、告警排序，写 `reports/`。

## 6. 事件族契约（新增族照这个做）

```python
# hkexradar/analyzers/base.py
class Analyzer(Protocol):
    family: str
    def matches(self, ann) -> bool: ...
    def analyze(self, ann, text: str, ctx=None,
                pages: list[tuple[int, str]] | None = None) -> AnalyzerResult: ...
```

- `Announcement` 在 `models.py`：`news_id / primary_code / stock_name / published_at / title / doc_group / headline_tags / file_url / text_status ...`
- `AnalyzerEvent`：`family, type, code, news_id, effective_date, direction, materiality, confidence, summary, facts`
- `AnalyzerFact`：`key, value, unit, currency, evidence{page, quote}, confidence`
- 事实必须有原文引文；引文应能在抽取文本中找到，否则降置信度或丢弃。

现有事实键前缀：

| 事件族 | 典型键 |
|---|---|
| NDR | `buyback.shares`、`buyback.amount.HKD`、`pending.shares`、`shares.start/end`、`issued.new`、`cancelled.shares` |
| 资本动作 | `issue.shares`、`issue.price`、`proceeds.gross/net`、`ratio.existing/post`、`shares.outstanding`、`rights.acceptance_pct`、`rights.undersubscribed.shares` |
| 停复牌 | `status`、`status.source`、`status.timing`、`status.reason`、`status.note` |

事件库表：`documents`（公告）、`events`（事件）、`facts`（事实）、`links`（事件关联，**已建表但尚未写入**）、`runs`（运行记录，尚简化）。核心查询：

```bash
PYTHONIOENCODING=utf-8 python -c "
import sqlite3
con = sqlite3.connect('data/events.db')
for row in con.execute('''
  select e.code, e.type, e.summary, d.published_at
  from events e join documents d on d.news_id = e.news_id
  order by d.published_at desc limit 10'''):
    print(row)
"
```

## 7. 产物与命令速查

| 命令 | 产物 |
|---|---|
| `python -m hkexradar.run --date D` | `reports/D-hkex-daily.md/.json` |
| `PYTHONPATH=. python scripts/ndr_analysis.py --date D` | `reports/D-ndr-analysis.md`、`D-ndr-brief.md`、`D-ndr.json` |
| `PYTHONPATH=. python scripts/capital_analysis.py --date D` | `reports/D-capital-actions.md/.json` |
| `PYTHONPATH=. python scripts/trading_status_analysis.py --date D` | `reports/D-trading-status.md/.json` |
| `python -m pytest tests` | 155 项离线测试 |
| `python scripts/fetch_fixture.py D` | `data/fixtures/D.json`（把某天固化为可回放快照） |

## 8. 已知限制与坑

1. **披露易 API 单日最多返回 1,000 行**。繁忙日需要按时间窗拆两次再合并；采集层已有处理，改动时别退化成单次拉取。
2. **交易所通告是 HTML，不是 PDF**。日报链路只给 PDF 精读，会跳过 HTML（`text_status=skipped`）；停复牌族专门支持 HTML。
3. **PDF 只读前 5 页**（`extract_pages(max_pages=5)`）。长文件的关键条款可能在后面；需要全文时改参数并评估耗时。
4. **市值是 proxy**：`股本 × 收市价`，不是交易所官方市值；停牌/无成交用前收市价。H 股发行人的 NDR 股本可能只含 H 股，市值会低估。
5. **20 日 ADV 还没接报告**：`marketdata.average_turnover()` 已有，但未批量抓历史行情。
6. **天数窗口 ≠ 交易日窗口**：行情缓存按自然日文件，缺失日跳过；ADV 按最近 20 个有数据的交易日取。
7. **事件去重只做同日同代码同状态**；跨天「停牌 → 复牌」关联、`links` 表写入尚未实现。
8. **分类以标题为主、正文兜底**。标题含「進展/更新/指引」时不判复牌；这类规则改动必须补测试，否则容易把「繼續停牌」误判为利好。
9. **报告与原始数据不入库**：`data/raw`、`data/cache`、`reports`、`data/events.db` 全部 gitignore。新机器需要重新采集或自备快照。
10. **没有 CI**。提交前本地跑全量测试与密钥扫描。

## 9. 安全与数据纪律

- 密钥只放环境变量：`DEEPSEEK_API_KEY` / `MINIMAX_API_KEY`；`config/settings.yaml` 已 gitignore。
- 提交前扫描：
  ```bash
  git diff | grep -nE "sk-[A-Za-z0-9_-]{10,}" || echo "no key"
  git status --short
  ```
- 如果密钥曾经提交：先轮换密钥，再清理历史；只删文件不算解决。
- 不提交 PDF、行情缓存、事件库、报告；它们体积大且可重建。
- Git 身份：本仓库历史作者是 `qoder <qoder@local>`。新维护者请配置自己的身份；不要为提交去改全局 git config，可临时用：
  ```bash
  git -c user.name="Your Name" -c user.email="you@example.com" commit -m "..."
  ```

## 10. 下一步怎么做

### P3b 治理事件族（建议下一项）

原因：10-30 标签粗算治理约 71 条，是未覆盖族里最大的一块；核数师辞任、CEO/CFO 离任属于高时效事件。

建议范围：

- 标签：`更換董事/重要職能`、`更換審核/薪酬/提名委員會成員`、`更換公司秘書`、`更換核數師`、`董事名單`。
- 抽取：角色、姓名、离任原因、继任者、生效日；核数师更换单独标记。
- 告警：核数师辞任/罢免 P0；CEO/CFO/公司秘书离任且无继任 P1；普通董事变动 P2。
- 验收：用 2026-10-30 的治理公告人工核对，分类与角色抽取准确率 ≥90%，全部有页码/引文。

### 其余顺序

1. **P2c**：批量抓近 20 个交易日行情，把 ADV 接入 NDR/资本简报，替代单日成交额倍数。
2. **P3c 交易**：须予披露/主要/非常重大/关连交易；代价/市值、关连属性；四项规模比率需财务基数，先做近似并明确标注。
3. **P3d 股息**：每股股息、总额、除净日、派付日；股息率需要股价，复用 P2b。
4. **P4 业绩**：收入/利润/EPS/毛利率/股息/指引，建立财务事实库，升级交易规模比率。
5. **P5 剩余内幕消息 + 跨族日报 + 定时任务**。

### 新增一个事件族的固定流程（TDD）

1. 读 [架构设计](docs/superpowers/specs/2026-11-01-hkex-radar-architecture-design.md) 的族设计与 [决策口径](skills/hkex-radar/references/decision-rules.md)。
2. **先写失败测试**：`tests/test_<family>.py` 覆盖 `matches()`、分类、关键事实、证据页码、无正文降级。
3. 实现 `hkexradar/analyzers/<family>.py`；需要去重/告警就加 `hkexradar/<family>_brief.py`。
4. 加 `scripts/<family>_analysis.py`：读快照 → matches → PDF/HTML → analyze → `store.add_result` → 简报。
5. 阈值放 `config/analyzers/<family>.yaml`，代码只读配置。
6. 更新 README、`skills/hkex-radar/SKILL.md`、`references/decision-rules.md`、架构文档。
7. 同步用户级技能（可选）：
   ```bash
   cp -r skills/hkex-radar/. ~/.qoder/skills/hkex-radar/
   ```
8. 全量测试 → 密钥扫描 → 提交（小步、一族一提交）。

## 11. 排障

| 现象 | 处理 |
|---|---|
| `ModuleNotFoundError: hkexradar` | 脚本前加 `PYTHONPATH=.`，或在仓库根目录运行 |
| 中文输出乱码 | `export PYTHONIOENCODING=utf-8` |
| `data/raw/<day>/announcements.json` 不存在 | 先跑 `python -m hkexradar.run --date <day> --no-pdf --no-llm` |
| 行情抓取失败/为空 | 加 `--no-market`；报告会标注未归一 |
| PDF 抽取 `unavailable` | 检查网络、文件是否为扫描件；单份失败只降级该条 |
| 同一天重跑很慢 | PDF/HTML 已缓存会跳过；删 `data/raw/<day>/pdf|html` 可强制刷新 |
| 事件库想重来 | 停进程后删 `data/events.db*`，下次运行自动建表 |
| `Author identity unknown` | 按第 9 节用 `git -c user.name=... -c user.email=... commit` |
| 测试通过但功能不对 | 测试只保证契约与解析；UI/报告类改动需用真实一天数据人工复核 |

## 12. 接手检查表

- [ ] `python -m pytest tests` → 155 passed。
- [ ] 离线回放命令能生成日报。
- [ ] 能说清「全市场日报」与「事件族专项」两条链路的区别。
- [ ] 知道族脚本依赖 `data/raw/<day>/announcements.json`，需要先采集。
- [ ] 知道密钥只放环境变量，提交前扫描。
- [ ] 读过 `skills/hkex-radar/references/decision-rules.md` 的 P0/P1 口径。
- [ ] 选定下一项（建议 P3b 治理），按 TDD 流程开新分支或直接小步提交。

## 13. 关键文档索引

| 文档 | 用途 |
|---|---|
| [README.md](README.md) | 安装、命令、各族用法、产物 |
| [HANDOFF.md](HANDOFF.md) | 本文档：接手、状态、限制、路线 |
| [架构设计](docs/superpowers/specs/2026-11-01-hkex-radar-architecture-design.md) | 事件族架构、表结构、阶段计划 |
| [SKILL.md](skills/hkex-radar/SKILL.md) | 给 AI 助手的使用流程与硬性护栏 |
| [decision-rules.md](skills/hkex-radar/references/decision-rules.md) | P0/P1 级别、公式、证据规则 |
| [taxonomy.md](skills/hkex-radar/references/taxonomy.md) | 14 大类、7 事件族、路由与标签陷阱 |
| [ndr-playbook.md](skills/hkex-radar/references/ndr-playbook.md) | NDR 表格结构与口径 |
| [capital-playbook.md](skills/hkex-radar/references/capital-playbook.md) | 配售/供股/可转债口径 |
