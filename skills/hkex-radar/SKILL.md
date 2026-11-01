---
name: hkex-radar
description: 分析港交所披露易公告并按事件族抽取事实、评估重大性、生成日报与告警。用于查询某日公告、翌日披露报表、股份回购、配售/供股、业绩/盈警、须予披露/关连交易、停牌复牌等任务。
---

# HKEX 公告雷达

## 何时使用

- 用户问“今天/某天港交所有什么值得看的公告”“昨天回购最多的是谁”。
- 需要分析翌日披露报表（NDR）、回购、注销、库存股、配售、供股、可转债、业绩、盈警、须予披露交易、关连交易、董事/核数师变更、停牌复牌。
- 需要把公告里的数字（股数、金额、摊薄比例）抽出来并给出处。
- 需要把同一公司的多份公告串成事件（配售 → 次日 NDR → 月报表）。

不适用于：实时行情、买卖建议、非港交所公告、纯新闻摘要。

## 仓库位置

默认根目录：

```bash
cd "C:/Users/user/OneDrive/文件/qoo/hkexradar"
```

若设置了 `HKEXRADAR_ROOT`，以该变量为准。

## 标准流程

1. **确认日期与时间窗**：默认 HKT；用户说“16:00 之后”就用 `--from-time 16:00`。
2. **采集或回放**：优先用已有快照 `data/raw/YYYY-MM-DD/announcements.json`；没有则实时抓取。
3. **跑族分析**：NDR 用 `scripts/ndr_analysis.py`；其他族按对应命令（未实现的族不要假装有结果）。
4. **先读简报**：`reports/YYYY-MM-DD-ndr-brief.md` 的 P0/P1，再看完整分析；每个数字回到 PDF 页码。
5. **查事件库**：跨天、跨文件的问题查 `data/events.db`，不要只读单日报告。
6. **回答**：结论 + 关键数字 + 出处（时间、代码、页码/引文）+ 不确定性。

## 命令

```bash
# 采集并生成全市场日报（可加时间窗）
python -m hkexradar.run --date 2026-10-30 --from-time 16:00

# 离线回放，不联网
python -m hkexradar.run --date 2026-09-08 --offline data/fixtures/2026-09-08.json --no-pdf

# 只分析翌日披露报表
PYTHONPATH=. python scripts/ndr_analysis.py --date 2026-10-30

# 只分析资本动作（配售/供股/认购/可换股/合并）
PYTHONPATH=. python scripts/capital_analysis.py --date 2026-10-30
```

产物：

- `reports/YYYY-MM-DD-hkex-daily.md`：全市场日报。
- `reports/YYYY-MM-DD-ndr-analysis.md`：NDR 分类明细。
- `reports/YYYY-MM-DD-ndr-brief.md`：NDR 决策简报（P0/P1 + Top 5）。
- `reports/YYYY-MM-DD-capital-actions.md`：资本动作简报（摊薄/供股认购率/完成/终止）。
- `data/events.db`：事件库（documents / events / facts / links）。

快速查询（Windows 不一定有 `sqlite3` CLI）：

```bash
PYTHONIOENCODING=utf-8 python -c "
import sqlite3
con = sqlite3.connect('data/events.db')
for row in con.execute('''
  select d.code, d.name, sum(cast(f.value as integer)) shares
  from facts f join events e on e.event_id = f.event_id
  join documents d on d.news_id = e.news_id
  where f.key = 'buyback.shares' and substr(d.published_at, 1, 10) = '2026-10-30'
  group by d.code order by shares desc limit 3'''):
    print(row)
"
```

## 硬性护栏

- 所有时间默认 HKT；报告必须写明统计窗口。
- 港交所 API 单日最多返回 1,000 行；繁忙日必须双向拉取合并，并在报告中说明。
- **交易所标签不等于内容**：NDR 的“股份購回”标签下可能当日零回购；“其他”标签下可能藏着配售、供股、股份合并。
- 没有原文引文的数字不得进入结论；引文必须能在 PDF 文本中找到。
- 比例必须写清分母（期初股本 / 期末股本 / 市值 / 成交额），不能把绝对金额当影响力。
- 配售「最多 X 股」是上限，必须标明「上限」，不能当成已发行。
- 通函、上市文件不独立抽数字；延迟寄发通函/澄清归入「其他命中」，不假装有结果。
- 不输出买卖建议；“方向”是语义描述，不是股价预测。
- 未接入行情数据时，明确写“未按市值/成交额归一”。

## 事件族与参考文件

| 族 | 参考文件 | 状态 |
|---|---|---|
| NDR（回购/注销/发行） | `references/ndr-playbook.md` | 已实现 |
| 分类路由与例行清单 | `references/taxonomy.md` | 已实现 |
| 告警与决策口径 | `references/decision-rules.md` | 已实现 |
| 资本动作（配售/供股/可转债） | `references/capital-playbook.md` | 已实现（完成/结果/终止） |
| 交易（须予披露/关连） | P3，未实现 | 计划中 |
| 业绩/盈警 | P4，未实现 | 计划中 |
| 治理/股息/停复牌 | P3–P5，未实现 | 计划中 |

未实现的族只能做“标题级”提示，不得输出未经核验的数字。

## 参考

- 架构设计：`docs/superpowers/specs/2026-11-01-hkex-radar-architecture-design.md`
- 现有日报设计：`../docs/superpowers/specs/2026-10-29-hkex-daily-radar-design.md`
