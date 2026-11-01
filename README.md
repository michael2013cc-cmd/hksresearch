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

## 資本動作專項分析

掃描「公告及通告」中的配售、供股、認購、可換股、股份合併類公告，逐份抽取發行股數、價格、募資總額/淨額、發行前/後佔比、供股認購率與未獲認購股數：

```bash
PYTHONPATH=. python scripts/capital_analysis.py --date 2026-10-30
```

產物：`reports/YYYY-MM-DD-capital-actions.md` 與同名 `.json`；事件以 `family=capital` 寫入 `data/events.db`，事實帶頁碼與原文。

- 告警：攤薄（按發行前股本）≥10% 為 P0，5–10% 為 P1；供股認購率 <90% 為 P1。
- 「配售最多 X 股」標記為 `配售/認購（上限）`，比例按上限計算，避免把上限當成確定發行。
- 延遲寄發通函、澄清、條款調整歸入「其他命中」，不強行抽數字。
- 閾值在 `config/analyzers/capital.yaml`。

## 停復牌事件族（P3a）

掃描「公告及通告」中標籤為停牌/復牌/短暫停牌的公告，以及交易所發出的停復牌通告；同時處理 PDF 公司公告與 HTML 交易所通告：

```bash
PYTHONPATH=. python scripts/trading_status_analysis.py --date 2026-10-30
```

產物：`reports/YYYY-MM-DD-trading-status.md` 與同名 `.json`；事件以 `family=trading_status` 寫入 `data/events.db`，事實帶頁碼與原文。

- 分類：`停牌`、`短暫停牌`、`復牌`、`繼續停牌`。標題優先，正文兜底；「復牌進展/季度更新」不會誤判為復牌。
- 全部事件直接 P0；「繼續停牌」是延續既有停牌，不代表當日新停牌。
- 同日同代碼同狀態去重：公司公告優先於交易所通告；「繼續停牌」歸一到「停牌」分組；保留公司公告的同時，從交易所通告補齊缺失的生效時間。
- 生效時間優先取與當前狀態匹配的日期，例如復牌公告同時提到原停牌日與復牌日時，只取復牌日。
- HTML 交易所通告正文抽取後緩存於 `data/raw/YYYY-MM-DD/html/`；PDF 公司公告緩存於 `pdf/`。

## 行情數據與市值/成交額歸一（P2b）

資本動作與 NDR 簡報默認會抓取港交所官方每日行情，把「募資額」「回購金額」換算成佔市值比例和當日成交額倍數：

```bash
PYTHONPATH=. python scripts/capital_analysis.py --date 2026-10-30
PYTHONPATH=. python scripts/ndr_analysis.py --date 2026-10-30

# 離線、或不想聯網時
PYTHONPATH=. python scripts/capital_analysis.py --date 2026-10-30 --no-market
```

- 行情來源：主機板 `https://www.hkex.com.hk/eng/stat/smstat/dayquot/dYYMMDDe.htm`，GEM `https://www.hkex.com.hk/eng/stat/smstat/dayquot/GEM/e_GYYMMDD.htm`。固定寬度兩行報價，代碼補齊 5 位，停牌行單獨標記。
- 快取：`data/cache/market/quotes-YYYY-MM-DD.json`（已 gitignore）。同一天重跑不重複下載；刪掉檔案可強制刷新。
- 市值(推算) = 股本 × 收市價（停牌或無成交時用前收市價）。這是代理指標，不是交易所官方市值。
- 股本優先序：公告明確披露的 `shares.outstanding` > 事件庫同/近日 NDR `shares.end`（僅當它不小於比例推算值）> 由 `ratio.existing` / `ratio.post` 反推 > 單獨 NDR 期末股本。
- 「募資/成交額」用當日成交額；低成交個股倍數會很大，只適合當日橫向對照，不能直接當成影響力結論。
- `hkexradar.marketdata.average_turnover()` 已支持 20 日 ADV（平均成交額），但尚未批量抓取歷史行情接入報告。
- H 股發行人的 NDR 期末股本可能只涵蓋 H 股，市值可能低估；簡報的數據質量段會提示該口徑。

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
