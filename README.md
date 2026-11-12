# 02-batchgate（闸序）

Batchgate — 离线作业依赖编排：作业定义 → 依赖就绪检查 → 执行/失败重试 → 产出水位与对账。

与 Feedstitch（多源 Feed 归并）主链路不同，禁止做成 Feed 解析/冲突/回看换皮。

## 启动

```bash
docker compose up --build
```

| 入口 | 地址 |
| --- | --- |
| 前端 | http://localhost:5200 |
| API | http://localhost:10200 |

## 主链

配置作业与依赖 → 触发一次编排 Run → 按依赖顺序执行夹具作业 → 写入尝试记录与产出水位 → 报告对账

## 并发槽

层内作业由 `SlotPool`（FIFO 取号、限号并发）约束，超限作业按 `slot_overflow_policy` 处置：

| 策略 | 超限作业 | 尝试状态 | 尝试 detail |
| --- | --- | --- | --- |
| `wait` | 阻塞等待前一批释放槽位后再跑 | `success` | `disposition=waited_then_acquired`、`waited_seconds` |
| `skip` | 不跑，记为跳过 | `skipped_slot` | `disposition=skipped_slot`、`reason`、`slot_state=not_acquired` |

- 每个实际执行过的作业都记录了占槽/释放：`slot_index`、`ticket`、`acquired_at`、`released_at`、
  `held_seconds`、`slot_state`（`released` / `released_after_failure`）。
- 设置页 `/settings` 可改 `concurrency_limit`（1–20，默认 2）与 `slot_overflow_policy`（默认 `wait`），落 SQLite；
  编排台可对单次 Run 临时覆盖（`POST /api/orchestrations` body），不改已存设置。
- 报告里的 `succeeded / failed / skipped_dep / skipped_slot / waited_then_acquired / attempt_count`
  全部由已落库的尝试记录汇总，报告与尝试列表逐项一致；`job_total == attempt_count`，不会静默丢作业。
  每层还给出 `dispositions`、`waves`、`peak_concurrency`（实测峰值并发 ≤ limit）。
- 演示：默认 limit=2 时层内两作业都够用、全部 `acquired`；改为 limit=1 + `wait` 出现 `waited_then_acquired`；
  改为 limit=1 + `skip` 出现 `skipped_slot`（下游相应 `skipped_dep`）。

## 种子说明

- **ingest_orders**：无依赖，写出订单水位。
- **dim_customer**：无依赖，写出客户维表水位。
- **fact_order_daily**：依赖上两者成功且水位推进后才可执行（底座仅做“上游成功”检查，严格水位闸与重试预算留给 0-1 题）。

## 技术栈

Python 3.12 + FastAPI + SQLite；Vue 3 + Vite + Nginx。

## 0-1 切口（未实现）

`dep_gate` / `retry_budget` / `watermark_reconcile` / `sla_breach`
