# Scrape Feedback And Observability Design

Date: 2026-03-27

## Summary

Fix the scrape page so scraping behaves like a real observable task rather than a fire-and-forget action. Single-file scrape and batch scrape will use one unified job model and one shared progress panel. Failed scrapes will become inspectable after the fact through persisted file-level details: user-readable reason, technical error, last stage, last source, and recent logs.

This design covers only scrape-page feedback and observability. Rebuilding `test_data` from real codes is explicitly out of scope for this spec and will be handled as a separate follow-up.

## Goals

- Make scrape failures visible and understandable from the page itself.
- Show real progress for both single-file and batch scraping.
- Reuse the scan-page batch interaction pattern so scrape feels consistent with organize.
- Persist the latest scrape attempt details so a page refresh does not hide the last failure reason or logs.
- Support source-aware progress text now for `JavDB`, while keeping the model ready for future multi-source fallback such as `JavTrailers`.

## Non-Goals

- Do not build a full scrape attempt history system.
- Do not add multiple concurrent scrape panels or a multi-job dashboard.
- Do not redesign the entire scrape page layout from scratch.
- Do not implement the real-code `test_data` rebuild in this spec.
- Do not add WebSocket or SSE transport for progress updates in this phase.

## Current Problems

- `POST /api/scrape/batch` runs synchronously and returns only after work finishes, so the current panel cannot reflect real progress.
- Frontend scrape logic is split and partially duplicated in `static/js/features.js`, which causes the visible UI skeleton and the actual behavior to drift apart.
- `GET /api/scrape` only returns minimal list fields, so the failure modal has no persisted `scrape_error`, stage, source, or logs to display.
- The existing scraper core returns only `success/code/error`, which is not rich enough for progress stages, source-aware messages, or readable failure summaries.
- The current UI still feels like a separate one-off system instead of a scrape-flavored version of the organize workflow.

## Product Decisions

- Persist only the most recent scrape attempt details per file.
- Use one unified scrape task model for both single-file and batch scrape.
- Allow batch selection only for `pending` items.
- Keep `failed` items retryable only through the row-level action.
- Show the current source name in progress text and logs. In this phase that source is `JavDB`, but the design must support future source-to-source fallback without redesign.

## High-Level Approach

The system will have two layers:

1. File-level persisted scrape result details on the `files` table.
2. In-memory scrape job state for the currently running or recently finished job.

The file-level layer is responsible for refresh-safe visibility. The job layer is responsible for live progress, current file, current source, current stage, and the shared task panel.

This intentionally does not copy MrBanana's full job-history-plus-log-files system. Noctra only needs live observability plus last-attempt persistence, so the lighter design is sufficient and easier to fit into the current codebase.

## Data Model

### 1. Persisted file-level fields

Keep the existing fields:

- `scrape_status`
- `last_scrape_at`

Add the following columns to `files`:

- `scrape_started_at TEXT`
- `scrape_finished_at TEXT`
- `scrape_stage TEXT`
- `scrape_source TEXT`
- `scrape_error TEXT`
- `scrape_error_user_message TEXT`
- `scrape_logs TEXT`

Field meanings:

- `scrape_started_at`: start time of the latest scrape attempt.
- `scrape_finished_at`: finish time of the latest scrape attempt.
- `scrape_stage`: last known stage key of the latest attempt.
- `scrape_source`: last source key used by the latest attempt, such as `javdb`.
- `scrape_error`: raw technical error text for the latest failed attempt.
- `scrape_error_user_message`: readable explanation shown first in the UI.
- `scrape_logs`: JSON array string containing the latest attempt's recent structured log entries.

Behavior rules:

- `last_scrape_at` becomes the completion timestamp of the latest scrape attempt, whether the attempt succeeded or failed.
- `scrape_status = success` clears both error fields.
- `scrape_status = failed` requires both a stage key and a readable failure message.
- `scrape_logs` is trimmed to the newest 30 entries or roughly 8 KB serialized size, whichever limit is hit first.

### 2. In-memory scrape job model

Add a scrape-job registry in `app.main`, parallel to the existing organize batch registry:

- `scrape_jobs: dict[str, dict]`
- `scrape_jobs_lock`

Each job contains:

- `id`
- `status`: `queued`, `running`, `completed`, `failed`, `cancelled`
- `total`
- `processed`
- `succeeded`
- `failed`
- `created_at`
- `started_at`
- `finished_at`
- `cancel_requested`
- `current_file_id`
- `current_file_code`
- `current_stage`
- `current_source`
- `recent_logs`
- `items`

Each item contains:

- `id`
- `code`
- `target_path`
- `status`: `pending`, `processing`, `success`, `failed`, `cancelled`
- `stage`
- `source`
- `user_message`
- `technical_error`
- `started_at`
- `finished_at`

### 3. Concurrency policy

Allow only one active scrape job at a time.

If a second scrape job is created while another scrape job is `queued` or `running`, return HTTP `409` with a clear message such as `已有刮削任务正在运行，请等待当前任务完成`.

This keeps the panel model simple, avoids overlapping writes to the same library structure, and matches the current product need better than a multi-job queue.

## Backend Architecture

### 1. Refactor scrape execution into an event-driven runner

Refactor `ScraperScheduler` into a richer runner that can emit progress events while preserving the current crawl pipeline:

1. Validate file record and scrape eligibility.
2. Mark attempt start in the database.
3. Emit source-aware query stage events.
4. Crawl metadata from the active source.
5. Parse metadata.
6. Write NFO.
7. Download poster if available.
8. Mark attempt success or failure in the database.

The core runner should accept callbacks or a small recorder object so that each stage transition can update:

- active scrape job state
- latest file-level persisted scrape details

### 2. Stage model

Use stable stage keys:

- `queued`
- `validating`
- `querying_source`
- `fetching_detail`
- `parsing_metadata`
- `writing_nfo`
- `downloading_poster`
- `finalizing`
- `success`
- `failed`

These keys are persisted so UI copy can evolve without changing stored records.

### 3. Source model

Use stable source keys such as:

- `javdb`
- `javtrailers`

In this phase only `javdb` is executed, but both the job model and file-level persisted fields must carry the source explicitly so future multi-source fallback can surface messages like:

- `正在查询 JavDB`
- `JavDB 查询失败`
- `正在查询 JavTrailers`

### 4. Cancellation

Cancellation is cooperative:

- it is honored before starting the next file
- it may also be honored between major stages when safe
- it does not interrupt an in-flight HTTP request or partially written file operation

If cancellation happens after some files succeed, completed work remains valid and unfinished items remain untouched.

## API Design

### 1. `POST /api/scrape/jobs`

Purpose:

- create a scrape job for one or more files

Request:

```json
{
  "file_ids": [1, 2, 3]
}
```

Validation rules:

- all file IDs must exist
- all selected rows must have status in processed-like statuses
- batch creation accepts only rows whose `scrape_status` is `pending`
- single-file row action may target both `pending` and `failed`

Response:

- full scrape job snapshot, shaped like organize batch jobs plus scrape-specific fields

### 2. `GET /api/scrape/jobs/{job_id}`

Purpose:

- fetch live job progress for polling

Response includes:

- counts
- current file
- current stage
- current source
- recent logs
- per-item statuses

### 3. `POST /api/scrape/jobs/{job_id}/cancel`

Purpose:

- request cooperative cancellation

Response includes:

- job ID
- status
- user message

### 4. `GET /api/scrape`

Expand the list payload so each item can support the failure modal without relying on in-memory state.

Add fields:

- `original_path`
- `status`
- `scrape_stage`
- `scrape_source`
- `scrape_error`
- `scrape_error_user_message`
- `scrape_logs`
- `scrape_started_at`
- `scrape_finished_at`

Also include:

- `active_job` when a scrape job is currently `queued` or `running`

This lets the page restore the progress panel after a refresh by loading the active job snapshot and continuing polling.

### 5. Legacy endpoints

Keep the existing endpoints temporarily for compatibility:

- `POST /api/scrape/{file_id}`
- `POST /api/scrape/batch`

They should delegate to the same refactored scrape runner so persisted details stay correct, but the new frontend will no longer call them.

## Frontend Design

### 1. Shared task-panel behavior

The scrape page must reuse the same visual language and interaction model as the organize batch panel:

- same panel placement
- same expand and collapse animation
- same progress bar behavior
- same status tokens and structural layout
- same polling rhythm

The scrape-specific panel content replaces organize-specific copy only where needed.

### 2. Unified entry flow

- Row-level scrape action creates a scrape job with one file.
- Batch scrape action creates a scrape job with the selected pending files.
- Both flows open the same panel immediately.
- Both flows use the same polling code path.

### 3. Selection rules

- `pending`: selectable for batch
- `failed`: not batch-selectable, row-level retry only
- `success`: not selectable

### 4. Row action and status rail

Keep the repaired hover-expand behavior aligned with the scan page:

- same width transition behavior
- same hover and leave timing
- same status rail token colors

Change the scrape action icon so it is not visually confused with organize. Use the scrape icon family, not the organize one. The intended icon is `sparkles`, not the current repeated organize-like icon choice.

### 5. Progress panel content

The scrape panel must show:

- total
- processed
- success count
- failure count
- current file code
- current stage
- current source
- recent log lines

For a one-file job this still appears, but shows `1 / 1` scale.

### 6. Failure modal

Clicking a failed status opens a modal with this order:

1. file code
2. user-readable failure reason
3. failed stage
4. failed source
5. recent logs
6. technical details

The main text must never default to raw exception text when a mapped readable reason exists.

### 7. Refresh recovery

When the scrape page loads:

- fetch `GET /api/scrape`
- if `active_job` exists, restore the panel from that snapshot
- resume polling automatically

This keeps a refresh from hiding an in-flight scrape task.

## Stage Copy

Default user-facing copy by stage:

- `queued`: `已加入刮削队列`
- `validating`: `正在检查文件信息`
- `querying_source`: `正在查询 {source}`
- `fetching_detail`: `{source} 已返回结果，正在读取详情页`
- `parsing_metadata`: `详情页读取成功，正在解析元数据`
- `writing_nfo`: `元数据解析成功，正在生成 NFO 文件`
- `downloading_poster`: `NFO 已生成，正在下载封面图片`
- `finalizing`: `正在保存刮削结果`
- `success`: `刮削完成`

Source display names:

- `javdb` -> `JavDB`
- future mapping examples:
  - `javtrailers` -> `JavTrailers`

## Failure Mapping

Map technical failures into readable messages before persisting them:

- metadata not found:
  - `在 {source} 没有找到这个番号的元数据`
- source request timeout or network failure:
  - `连接 {source} 失败，请稍后重试`
- detail page or parsing failure:
  - `{source} 返回了页面，但元数据解析失败`
- NFO write failure:
  - `元数据已获取，但写入 NFO 文件失败`
- poster download failure:
  - `NFO 已生成，但封面图片下载失败`
- missing local file metadata:
  - `文件信息不完整，无法开始刮削`
- unknown failure:
  - `刮削过程中发生未知错误`

Persist both:

- the readable mapped message
- the original technical error text

## Logging Model

Use structured log entries for both active job display and last-attempt persistence.

Each entry contains:

- `at`
- `level`
- `stage`
- `source`
- `message`

Example sequence for a successful `JavDB` attempt:

- `开始刮削 ALDN-480`
- `正在查询 JavDB`
- `JavDB 返回搜索结果，已定位详情页`
- `详情页读取成功，正在解析元数据`
- `正在写入 /dist/ALDN-480/ALDN-480.nfo`
- `封面下载完成`
- `刮削完成`

## File And Module Changes

### Backend

- `app/main.py`
  - add schema backfill for new scrape fields
  - add scrape job registry and routes
  - expand `GET /api/scrape`
- `app/models.py`
  - add scrape job request and response models
  - expand scrape list item fields
- `app/scraper.py`
  - refactor single-file scrape flow into stage-aware execution
  - emit structured progress and log events
  - persist latest attempt details

### Frontend

- `static/js/state.js`
  - remove pseudo scrape-batch assumptions and store real scrape job state
- `static/js/features.js`
  - remove duplicated scrape methods
  - create and poll real scrape jobs
  - restore active job from scrape-list payload
- `static/js/render.js`
  - render stage, source, and readable failure messages
  - use scrape-specific action icon
- `static/index.html`
  - keep one shared panel skeleton, but populate it with real scrape progress fields
  - expand failure modal sections

### Tests

- `tests/test_api/test_scrape_endpoints.py`
  - expand list endpoint expectations
  - add scrape-job endpoint coverage
- `tests/test_scraper.py`
  - add stage progression and failure-mapping tests
- `tests/test_e2e/test_scraping_flow.py`
  - verify persisted last-attempt fields and panel-compatible state

## Testing Plan

### Automated

- list endpoint returns new persisted detail fields
- scrape job creation rejects invalid selection combinations
- active job polling returns current file, source, stage, and recent logs
- cancellation returns the correct terminal state
- success clears stale error fields
- source failure persists readable and technical error details
- NFO write failure persists correct stage and failure copy
- poster download failure persists correct stage and failure copy
- failed items remain retryable individually
- failed items remain excluded from batch selection rules

### Manual

- trigger a single-file scrape and confirm the panel appears with `1 / 1`
- trigger batch scrape and confirm the panel updates live per file
- force a failure and confirm clicking the failed badge shows readable reason, stage, source, logs, and technical details
- refresh during an active scrape and confirm the panel restores and keeps polling
- verify row hover behavior and icon styling match the organize interaction pattern

## Risks And Mitigations

- Risk: adding too much data to `files` could bloat rows.
  - Mitigation: persist only the latest attempt and trim logs aggressively.
- Risk: scrape job state and file-level state diverge.
  - Mitigation: stage transitions must update both through the same recorder path.
- Risk: cancellation appears stronger than it really is.
  - Mitigation: document and message it as cooperative cancellation, not hard abort.
- Risk: frontend keeps legacy duplicated logic.
  - Mitigation: delete the duplicate scrape handlers instead of layering new code on top.

## Rollout Notes

- Migrate schema automatically on startup, just like the existing scrape columns.
- Keep legacy scrape endpoints available during the transition so tests and scripts do not break immediately.
- Do not begin the `test_data` rebuild until the new scrape observability flow is verified end to end.
