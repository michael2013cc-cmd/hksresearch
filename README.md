# HKEX 公告雷达

抓取港交所每日全部公告，剔除例常文件，精读候选公告，按影响力排序生成 Markdown 日报。

## 安装

无需安装包，直接使用系统 Python 3.11：

```bash
pip install httpx pydantic PyYAML pymupdf pytest
```

PDF 文本用 PyMuPDF 抽取（比 Xpdf 自带的 `pdftotext` 更能处理港交所常用的 CID 字体）；抽取后若中文字符占比过低会判定为乱码并降级为规则摘要。

## 配置

```bash
cp config/settings.example.yaml config/settings.yaml
export DEEPSEEK_API_KEY=sk-...
```

不配 key 时自动降级为规则摘要（等同 `--no-llm`）。

MiniMax 国际版示例（`config/settings.yaml`）：

```yaml
llm:
  base_url: https://api.minimax.io/v1
  model: MiniMax-M3.1-Flash
  api_key_env: MINIMAX_API_KEY
  reasoning_effort: low   # low / max；low 约 5 秒/条，max 约 30 秒/条
```

```bash
export MINIMAX_API_KEY=sk-...
```

## 运行

```bash
# 实时抓取指定日期
python -m hkexradar.run --date 2026-09-08

# 离线回放冻结快照（不联网）
python -m hkexradar.run --date 2026-09-08 --offline data/fixtures/2026-09-08.json --no-pdf

# 只精读前 10 条
python -m hkexradar.run --date 2026-09-08 --limit 10
```

产物：`reports/YYYY-MM-DD-hkex-daily.md` 与同名 `.json`。Top 20 每条都标注具体发布时间，另附全部候选的发布时间时间线。每次实时抓取的原始响应快照保存在 `data/raw/YYYY-MM-DD/announcements*.json`，PDF 保存在同目录 `pdf/`。

## 翌日披露报表专项分析

只处理 `doc_group == "翌日披露报表"` 的公告，逐份解析 FF305 表格的股份变动、購回報告、庫存股份出售，按内容而非交易所标签分类：

```bash
PYTHONPATH=. python scripts/ndr_analysis.py --date 2026-10-30
```

产物：`reports/YYYY-MM-DD-ndr-analysis.md`（分类分布、回購金额、註銷、发行事件、全部明细）与同名 `.json`。PDF 并发下载（8 线程），解析逻辑在 `hkexradar/analyzers/ndr.py`，统一的事件/事实契约在 `hkexradar/analyzers/base.py`。

同一命令还会：

- 把每份公告写成 `documents` / `events` / `facts` 记录，落入 `data/events.db`（SQLite，已 gitignore）。每条事实带页码与原文引文，重复运行按 `news_id` 幂等覆盖，类型变化会清掉旧事件。
- 按 `config/analyzers/ndr.yaml` 的阈值生成 `reports/YYYY-MM-DD-ndr-brief.md`：稀释（发行股数/期初股本）、待註銷股本、回購强度、註銷强度；P0/P1 排序并附证据引文。
- `內資股轉H股` 与 `股份合併/資本重組` 视为非稀释类别，不触发稀释告警（总股本未变）。

```bash
# 调整告警阈值后重跑即可
cat config/analyzers/ndr.yaml

# 直接查事件库
sqlite3 data/events.db "select code,type,summary from events where substr(created_at,1,10)='2026-10-30'"
```

## 技能

`skills/hkex-radar/` 是可安装的 Qoder 技能（公告分类体系、NDR 操作手册、决策规则）。安装到用户级：

```bash
cp -r skills/hkex-radar ~/.qoder/skills/
```

安装后可用 `/hkex-radar` 触发，回答“昨天回购最多的三家公司”这类问题时按事件库 + 证据引文作答。

## 测试

```bash
python -m pytest -v
```

测试不触网：HTTP 用 `httpx.MockTransport`，LLM 用假客户端，全链路用 `data/fixtures/2026-09-08.json`（真实 590 条快照）回放。

## 处理链条

1. Collector：`titleSearchServlet` 单次拉取全天数据（`rowRange=1000`），失败指数退避重试。
2. Normalizer：多柜台代码拆分、HTML 反转义、修订版标记、按文件链接去重。
3. Triage：按 `config/routine_rules.yaml` 剔除月报表、ETF 交易资料等例常件，590 条压到约 121 条。
4. Reader：下载 PDF，PyMuPDF 抽前 5 页并去掉标准免责声明，LLM 输出摘要与事实；事实引文必须能在正文中原样找到，否则丢弃。
5. Scorer：`magnitude = 40×类别先验 + 20×规模 + 40×意外度`；`interest = 50×稀缺度 + 30×覆盖度 + 20×传播潜力`；`final = 0.6×magnitude + 0.4×interest`，S≥80、A≥65、B≥50、C<50。
6. Reporter：Markdown 日报 + JSON（含完整评分拆解与数据质量统计）。

详见 `../docs/superpowers/specs/2026-10-29-hkex-daily-radar-design.md`。
