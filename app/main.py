import asyncio
import json
import os
import uuid
from functools import cmp_to_key
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from app.models import (
    BatchCancelResult,
    BatchCreateRequest,
    BatchJob,
    BatchItemResult,
    DeleteFileRequest,
    DeleteFileResult,
    FileRecord,
    HistoryResult,
    OrganizeRequest,
    OrganizeResult,
    ScanResult,
    ScrapeLogEntry,
    ScrapeListItem,
    ScrapeResponse,
    ScrapeBatchResult,
)
from app.scanner import JAVScanner
from app.organizer import JAVOrganizer
from app.scraper import ScraperScheduler
from app.statuses import (
    SELECTABLE_SCAN_STATUSES,
    assign_batch_duplicate_statuses,
    compare_candidate_priority,
    resolve_scan_status,
)

app = FastAPI(title="Noctra JAV Organizer", version="1.0.0")

# 环境变量
SOURCE_DIR = os.getenv('SOURCE_DIR', '/source')
DIST_DIR = os.getenv('DIST_DIR', '/dist')
DB_PATH = os.getenv('DB_PATH', '/app/data/noctra.db')
PROCESSED_LIKE_STATUSES = ('processed', 'organized')

# 初始化组件
scanner = JAVScanner(SOURCE_DIR, DIST_DIR)
organizer = JAVOrganizer(DIST_DIR)
batch_jobs: dict[str, dict] = {}
batch_jobs_lock = asyncio.Lock()

# 挂载静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")


async def init_db():
    """初始化数据库"""
    db_dir = Path(DB_PATH).parent
    db_dir.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_path TEXT UNIQUE NOT NULL,
                identified_code TEXT,
                target_path TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                file_size INTEGER NOT NULL,
                file_mtime REAL NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        await ensure_scrape_schema(db)
        await db.commit()


async def ensure_scrape_schema(db: aiosqlite.Connection):
    """为已有数据库补齐刮削字段，避免新版本启动时依赖手工迁移。"""
    cursor = await db.execute('PRAGMA table_info(files)')
    rows = await cursor.fetchall()
    existing_columns = {row[1] for row in rows}

    columns_to_add = [
        ('scrape_status', "ALTER TABLE files ADD COLUMN scrape_status TEXT DEFAULT 'pending'"),
        ('last_scrape_at', "ALTER TABLE files ADD COLUMN last_scrape_at TEXT"),
        ('scrape_started_at', "ALTER TABLE files ADD COLUMN scrape_started_at TEXT"),
        ('scrape_finished_at', "ALTER TABLE files ADD COLUMN scrape_finished_at TEXT"),
        ('scrape_stage', "ALTER TABLE files ADD COLUMN scrape_stage TEXT"),
        ('scrape_source', "ALTER TABLE files ADD COLUMN scrape_source TEXT"),
        ('scrape_error', "ALTER TABLE files ADD COLUMN scrape_error TEXT"),
        ('scrape_error_user_message', "ALTER TABLE files ADD COLUMN scrape_error_user_message TEXT"),
        ('scrape_logs', "ALTER TABLE files ADD COLUMN scrape_logs TEXT"),
    ]

    for column_name, alter_sql in columns_to_add:
        if column_name not in existing_columns:
            await db.execute(alter_sql)

    await db.execute("UPDATE files SET scrape_status = 'pending' WHERE scrape_status IS NULL")
    await db.execute('CREATE INDEX IF NOT EXISTS idx_files_scrape_status ON files(scrape_status)')


@app.on_event("startup")
async def startup_event():
    await init_db()


async def upsert_file(
    original_path: str,
    identified_code: Optional[str],
    target_path: Optional[str],
    status: str,
    file_size: int,
    file_mtime: float
) -> int:
    """
    插入或更新文件记录

    返回：文件 ID
    """
    now = datetime.now().isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            '''
            INSERT OR REPLACE INTO files
            (original_path, identified_code, target_path, status, file_size, file_mtime, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (original_path, identified_code, target_path, status, file_size, file_mtime, now, now)
        )
        await db.commit()
        return cursor.lastrowid


async def update_file_status(file_id: int, status: str, target_path: Optional[str] = None):
    """更新文件状态"""
    now = datetime.now().isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        if target_path:
            await db.execute(
                'UPDATE files SET status = ?, target_path = ?, updated_at = ? WHERE id = ?',
                (status, target_path, now, file_id)
            )
        else:
            await db.execute(
                'UPDATE files SET status = ?, updated_at = ? WHERE id = ?',
                (status, now, file_id)
            )
        await db.commit()


async def refresh_file_record(
    file_id: int,
    identified_code: Optional[str],
    target_path: Optional[str],
    status: str,
    file_size: int,
    file_mtime: float
):
    """刷新扫描得到的文件元数据，避免沿用旧规则生成的目标路径。"""
    now = datetime.now().isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''
            UPDATE files
            SET identified_code = ?, target_path = ?, status = ?, file_size = ?, file_mtime = ?, updated_at = ?
            WHERE id = ?
            ''',
            (identified_code, target_path, status, file_size, file_mtime, now, file_id)
        )
        await db.commit()


async def mark_related_files_target_exists(file_id: int, identified_code: Optional[str]):
    """当同番号已有一条被整理后，将其余同番号候选标记为已存在。"""
    if not identified_code:
        return

    now = datetime.now().isoformat()
    related_statuses = (*SELECTABLE_SCAN_STATUSES, 'target_exists')
    placeholders = ','.join('?' * len(related_statuses))

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f'''
            UPDATE files
            SET status = 'target_exists', updated_at = ?
            WHERE id != ?
              AND identified_code = ?
              AND status IN ({placeholders})
            ''',
            (now, file_id, identified_code, *related_statuses)
        )
        await db.commit()


async def get_all_files() -> list[dict]:
    """获取所有文件记录"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM files ORDER BY id DESC')
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


def _parse_scrape_logs(raw: Optional[str]) -> list[ScrapeLogEntry]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []

    if not isinstance(value, list):
        return []

    parsed_logs: list[ScrapeLogEntry] = []
    for item in value:
        try:
            parsed_logs.append(ScrapeLogEntry.model_validate(item))
        except (TypeError, ValueError, ValidationError):
            continue
    return parsed_logs


async def get_processed_history_codes() -> set[str]:
    """获取历史上已处理且源文件已不存在的番号集合。"""
    all_files = await get_all_files()
    return {
        str(file['identified_code']).upper()
        for file in all_files
        if file.get('identified_code') and is_history_processed_record(file)
    }


async def get_file_by_path(original_path: str) -> Optional[dict]:
    """根据原路径获取文件记录"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            'SELECT * FROM files WHERE original_path = ?',
            (original_path,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_file_by_id(file_id: int) -> Optional[dict]:
    """根据 ID 获取文件记录"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            'SELECT * FROM files WHERE id = ?',
            (file_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def delete_file_record(file_id: int):
    """删除文件记录"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM files WHERE id = ?', (file_id,))
        await db.commit()


def utcnow_iso() -> str:
    return datetime.now().isoformat()


def clone_batch_job(job: dict) -> dict:
    return {
        **job,
        'items': [dict(item) for item in job['items']],
    }


async def set_batch_job(job_id: str, updater):
    async with batch_jobs_lock:
        job = batch_jobs.get(job_id)
        if not job:
            return None
        updater(job)
        return clone_batch_job(job)


async def get_batch_job(job_id: str) -> Optional[dict]:
    async with batch_jobs_lock:
        job = batch_jobs.get(job_id)
        return clone_batch_job(job) if job else None


async def create_batch_job(rows: list[aiosqlite.Row]) -> dict:
    now = utcnow_iso()
    batch_id = uuid.uuid4().hex[:12]
    sorted_rows = sorted((dict(row) for row in rows), key=cmp_to_key(compare_candidate_priority))
    items = [
        {
            'id': row['id'],
            'code': row['identified_code'],
            'source_path': row['original_path'],
            'target_path': row['target_path'],
            'status': 'pending',
            'message': None,
            'started_at': None,
            'finished_at': None,
        }
        for row in sorted_rows
    ]
    job = {
        'id': batch_id,
        'status': 'queued',
        'total': len(items),
        'processed': 0,
        'succeeded': 0,
        'skipped': 0,
        'failed': 0,
        'created_at': now,
        'started_at': None,
        'finished_at': None,
        'cancel_requested': False,
        'items': items,
    }
    async with batch_jobs_lock:
        batch_jobs[batch_id] = job
    return clone_batch_job(job)


async def run_batch_job(batch_id: str):
    started_at = utcnow_iso()

    async with batch_jobs_lock:
        job = batch_jobs.get(batch_id)
        if not job:
            return
        job['status'] = 'running'
        job['started_at'] = started_at

    while True:
        async with batch_jobs_lock:
            job = batch_jobs.get(batch_id)
            if not job:
                return
            if job['cancel_requested']:
                job['status'] = 'cancelled'
                job['finished_at'] = utcnow_iso()
                return

            pending_item = next((item for item in job['items'] if item['status'] == 'pending'), None)
            if pending_item is None:
                if job['failed'] == job['total'] and job['total'] > 0:
                    job['status'] = 'failed'
                else:
                    job['status'] = 'completed'
                job['finished_at'] = utcnow_iso()
                return

            pending_item['status'] = 'processing'
            pending_item['started_at'] = utcnow_iso()
            file_id = pending_item['id']
            source_path = pending_item['source_path']
            code = pending_item['code']
            target_path = organizer.get_target_path(code, Path(source_path).name)
            pending_item['target_path'] = target_path

        success, reason = await asyncio.to_thread(organizer.move_file, source_path, target_path)
        finished_at = utcnow_iso()

        if success:
            final_status = 'success'
            final_message = '整理完成'
            db_status = 'processed'
        elif reason == '目标文件已存在':
            final_status = 'skipped'
            final_message = reason
            db_status = 'target_exists'
        else:
            final_status = 'failed'
            final_message = reason or '整理失败'
            db_status = 'failed'

        if final_status == 'success':
            await update_file_status(file_id, db_status, target_path)
            await mark_related_files_target_exists(file_id, code)
        elif final_status == 'skipped':
            await update_file_status(file_id, db_status, target_path)
        else:
            await update_file_status(file_id, db_status)

        async with batch_jobs_lock:
            job = batch_jobs.get(batch_id)
            if not job:
                return

            item = next((candidate for candidate in job['items'] if candidate['id'] == file_id), None)
            if not item:
                continue

            item['status'] = final_status
            item['message'] = final_message
            item['finished_at'] = finished_at
            job['processed'] += 1

            if final_status == 'success':
                job['succeeded'] += 1
            elif final_status == 'skipped':
                job['skipped'] += 1
            else:
                job['failed'] += 1


def build_global_stats(files: list[object]) -> dict[str, int]:
    """根据文件记录生成统一的全局统计。"""
    total_files = 0
    identified = 0
    unidentified = 0
    pending = 0
    processed = 0

    for file in files:
        if isinstance(file, dict):
            identified_code = file.get('identified_code')
            status = file.get('status')
        else:
            identified_code = getattr(file, 'identified_code', None)
            status = getattr(file, 'status', None)

        if status == 'ignored':
            continue

        total_files += 1

        if identified_code:
            identified += 1
        else:
            unidentified += 1

        if status == 'pending':
            pending += 1
        elif status in PROCESSED_LIKE_STATUSES and _is_processed_history_like(file):
            processed += 1

    return {
        'total_files': total_files,
        'identified': identified,
        'unidentified': unidentified,
        'pending': pending,
        'processed': processed,
    }


def is_history_processed_record(file: dict) -> bool:
    """历史记录只展示真正已移动走源文件的已处理项。"""
    if file.get('status') not in PROCESSED_LIKE_STATUSES:
        return False
    original_path = file.get('original_path')
    return bool(original_path) and not Path(original_path).exists()


def _is_processed_history_like(file: object) -> bool:
    if isinstance(file, dict):
        return is_history_processed_record(file)

    status = getattr(file, 'status', None)
    original_path = getattr(file, 'original_path', None)
    return status in PROCESSED_LIKE_STATUSES and bool(original_path) and not Path(original_path).exists()


@app.get("/")
async def index():
    """前端页面"""
    return FileResponse("static/index.html")


@app.get("/api/scan", response_model=ScanResult)
async def scan_files(force_rescan: bool = False):
    """
    扫描 /source 目录

    参数：
    - force_rescan: 是否强制重新扫描（默认 false）
    """
    # 扫描文件系统
    scanned_files = scanner.scan()
    scanned_candidates = []
    processed_history_codes = await get_processed_history_codes()

    for file_info in scanned_files:
        code = file_info['identified_code']
        target_path = None
        if code:
            target_path = organizer.get_target_path(code, file_info['filename'])

        status = resolve_scan_status(code, target_path)
        if code and str(code).upper() in processed_history_codes:
            status = 'target_exists'

        scanned_candidates.append({
            **file_info,
            'original_path': file_info['path'],
            'target_path': target_path,
            'status': status,
        })

    assign_batch_duplicate_statuses(scanned_candidates)

    file_records = []

    for file_info in scanned_candidates:
        original_path = file_info['original_path']
        code = file_info['identified_code']
        target_path = file_info['target_path']
        status = file_info['status']
        existing = await get_file_by_path(original_path)

        if existing and existing['status'] == 'ignored':
            metadata_changed = (
                existing['identified_code'] != code
                or existing['target_path'] != target_path
                or existing['file_size'] != file_info['size']
                or existing['file_mtime'] != file_info['mtime']
            )
            if metadata_changed:
                await refresh_file_record(
                    file_id=existing['id'],
                    identified_code=code,
                    target_path=target_path,
                    status='ignored',
                    file_size=file_info['size'],
                    file_mtime=file_info['mtime']
                )
            continue

        if existing:
            if existing['file_size'] == file_info['size'] and existing['file_mtime'] == file_info['mtime']:
                metadata_changed = (
                    existing['identified_code'] != code
                    or existing['target_path'] != target_path
                    or existing['status'] != status
                )
                if metadata_changed:
                    await refresh_file_record(
                        file_id=existing['id'],
                        identified_code=code,
                        target_path=target_path,
                        status=status,
                        file_size=file_info['size'],
                        file_mtime=file_info['mtime']
                    )
                    existing['identified_code'] = code
                    existing['target_path'] = target_path
                    existing['status'] = status
                    existing['file_size'] = file_info['size']
                    existing['file_mtime'] = file_info['mtime']
                    existing['updated_at'] = datetime.now().isoformat()
            else:
                # 文件已变化，刷新记录并重新走当前扫描规则。
                await refresh_file_record(
                    file_id=existing['id'],
                    identified_code=code,
                    target_path=target_path,
                    status=status,
                    file_size=file_info['size'],
                    file_mtime=file_info['mtime']
                )
                existing['identified_code'] = code
                existing['target_path'] = target_path
                existing['status'] = status
                existing['file_size'] = file_info['size']
                existing['file_mtime'] = file_info['mtime']
                existing['updated_at'] = datetime.now().isoformat()

            file_records.append(FileRecord(
                id=existing['id'],
                original_path=original_path,
                identified_code=code,
                target_path=target_path,
                status=status,
                file_size=file_info['size'],
                file_mtime=file_info['mtime'],
                created_at=existing['created_at'],
                updated_at=existing['updated_at']
            ))
            continue

        # 插入新记录
        file_id = await upsert_file(
            original_path=original_path,
            identified_code=code,
            target_path=target_path,
            status=status,
            file_size=file_info['size'],
            file_mtime=file_info['mtime']
        )

        now = datetime.now().isoformat()
        file_records.append(FileRecord(
            id=file_id,
            original_path=original_path,
            identified_code=code,
            target_path=target_path,
            status=status,
            file_size=file_info['size'],
            file_mtime=file_info['mtime'],
            created_at=now,
            updated_at=now
        ))

    all_files = await get_all_files()
    stats = build_global_stats(all_files)

    return ScanResult(
        total_files=stats['total_files'],
        identified=stats['identified'],
        unidentified=stats['unidentified'],
        pending=stats['pending'],
        processed=stats['processed'],
        files=file_records
    )


@app.post("/api/organize", response_model=OrganizeResult)
async def organize_files(request: OrganizeRequest):
    """
    执行整理操作

    请求：
    {
        "file_ids": [1, 2, 3]
    }
    """
    # 获取要处理的文件
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        placeholders = ','.join('?' * len(request.file_ids))
        status_placeholders = ','.join('?' * len(SELECTABLE_SCAN_STATUSES))
        cursor = await db.execute(
            f'SELECT * FROM files WHERE id IN ({placeholders}) AND status IN ({status_placeholders})',
            (*request.file_ids, *SELECTABLE_SCAN_STATUSES)
        )
        rows = await cursor.fetchall()

    if not rows:
        return OrganizeResult(
            success_count=0,
            failed_count=0,
            results=[]
        )

    # 准备整理任务
    organize_tasks = []
    sorted_rows = sorted((dict(row) for row in rows), key=cmp_to_key(compare_candidate_priority))
    for row_dict in sorted_rows:
        organize_tasks.append({
            'file_id': row_dict['id'],
            'original_path': row_dict['original_path'],
            'identified_code': row_dict['identified_code'],
            'filename': Path(row_dict['original_path']).name
        })

    # 执行整理
    results = organizer.organize(organize_tasks)

    # 更新数据库
    success_count = 0
    failed_count = 0

    for result in results:
        file_id = result['file_id']
        target_path = result['target_path']
        status = result['status']
        row_dict = next((item for item in sorted_rows if item['id'] == file_id), None)

        if status == 'moved':
            await update_file_status(file_id, 'processed', target_path)
            await mark_related_files_target_exists(file_id, row_dict['identified_code'] if row_dict else None)
            success_count += 1
        elif status == 'skipped':
            await update_file_status(file_id, 'target_exists', target_path)
        else:
            await update_file_status(file_id, 'failed')
            failed_count += 1

    return OrganizeResult(
        success_count=success_count,
        failed_count=failed_count,
        results=results
    )


@app.post("/api/batches", response_model=BatchJob)
async def create_batch(request: BatchCreateRequest):
    """创建整理批任务并在后台串行执行。"""
    if not request.file_ids:
        raise HTTPException(status_code=400, detail='请选择至少一个可整理文件')

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        placeholders = ','.join('?' * len(request.file_ids))
        status_placeholders = ','.join('?' * len(SELECTABLE_SCAN_STATUSES))
        normalized_ids = [int(file_id) for file_id in request.file_ids]
        cursor = await db.execute(
            f'SELECT * FROM files WHERE id IN ({placeholders}) AND status IN ({status_placeholders})',
            (*normalized_ids, *SELECTABLE_SCAN_STATUSES)
        )
        rows = await cursor.fetchall()

        if not rows:
            cursor = await db.execute(
                f'SELECT id FROM files WHERE id IN ({placeholders})',
                tuple(normalized_ids)
            )
            existing_rows = await cursor.fetchall()

            if existing_rows:
                raise HTTPException(status_code=409, detail='所选文件状态已变化，请刷新列表后重试')

    if not rows:
        raise HTTPException(status_code=400, detail='没有可整理的文件')

    batch_job = await create_batch_job(rows)
    asyncio.create_task(run_batch_job(batch_job['id']))
    return batch_job


@app.get("/api/batches/{batch_id}", response_model=BatchJob)
async def get_batch(batch_id: str):
    """获取批任务当前状态。"""
    batch_job = await get_batch_job(batch_id)
    if not batch_job:
        raise HTTPException(status_code=404, detail='批任务不存在')
    return batch_job


@app.post("/api/batches/{batch_id}/cancel", response_model=BatchCancelResult)
async def cancel_batch(batch_id: str):
    """请求取消正在执行的批任务。"""
    batch_job = await set_batch_job(
        batch_id,
        lambda job: job.update({'cancel_requested': True})
    )
    if not batch_job:
        raise HTTPException(status_code=404, detail='批任务不存在')

    if batch_job['status'] not in {'queued', 'running'}:
        return BatchCancelResult(
            id=batch_id,
            status=batch_job['status'],
            message='批任务当前不可取消'
        )

    return BatchCancelResult(
        id=batch_id,
        status='cancelling',
        message='已请求取消批任务'
    )


@app.post("/api/files/{file_id}/delete", response_model=DeleteFileResult)
async def delete_file(file_id: int, request: DeleteFileRequest):
    """处理已存在文件：删除原始文件或忽略扫描记录。"""
    file_record = await get_file_by_id(file_id)
    if not file_record:
        raise HTTPException(status_code=404, detail='文件记录不存在')

    if request.action == 'ignore_scan':
        await update_file_status(file_id, 'ignored', file_record['target_path'])
        return DeleteFileResult(
            file_id=file_id,
            action=request.action,
            message='已忽略该记录，后续扫描将不再显示'
        )

    if request.action == 'delete_source':
        source_path = Path(file_record['original_path'])
        if source_path.exists():
            source_path.unlink()
            message = '已删除原始文件并清理扫描记录'
        else:
            message = '源文件不存在，已清理扫描记录'

        await delete_file_record(file_id)
        return DeleteFileResult(
            file_id=file_id,
            action=request.action,
            message=message
        )

    raise HTTPException(status_code=400, detail='不支持的删除动作')


@app.get("/api/history", response_model=HistoryResult)
async def get_history():
    """
    获取历史记录
    """
    all_files = await get_all_files()
    stats = build_global_stats(all_files)

    skipped = sum(1 for f in all_files if f['status'] == 'skipped')
    processed_files = [f for f in all_files if is_history_processed_record(f)]

    file_records = [
        FileRecord(
            id=f['id'],
            original_path=f['original_path'],
            identified_code=f['identified_code'],
            target_path=f['target_path'],
            status='processed',
            file_size=f['file_size'],
            file_mtime=f['file_mtime'],
            created_at=f['created_at'],
            updated_at=f['updated_at']
        )
        for f in processed_files
    ]

    return HistoryResult(
        total_files=stats['total_files'],
        identified=stats['identified'],
        unidentified=stats['unidentified'],
        pending=stats['pending'],
        processed=len(processed_files),
        skipped=skipped,
        files=file_records
    )


@app.get("/api/scrape")
async def get_scrape_list(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    filter: str = Query(default='all'),
    sort: str = Query(default='code'),
):
    """
    获取刮削列表 (兼容 processed / organized 两种已整理状态)

    参数:
    - page: 页码 (默认 1)
    - per_page: 每页条数 (默认 50)
    - filter: 过滤 scrape_status (all/pending/success/failed)
    - sort: 排序方式 (code/scrape_time)
    """
    # Validate filter
    valid_filters = {'all', 'pending', 'success', 'failed'}
    if filter not in valid_filters:
        raise HTTPException(status_code=400, detail=f'Invalid filter: {filter}')

    # Validate sort
    valid_sorts = {'code', 'scrape_time'}
    if sort not in valid_sorts:
        raise HTTPException(status_code=400, detail=f'Invalid sort: {sort}')

    # Build WHERE clauses
    processed_placeholders = ','.join('?' * len(PROCESSED_LIKE_STATUSES))
    where_clauses = [f"status IN ({processed_placeholders})"]
    params: list = list(PROCESSED_LIKE_STATUSES)

    if filter != 'all':
        where_clauses.append("COALESCE(scrape_status, 'pending') = ?")
        params.append(filter)

    where_sql = " AND ".join(where_clauses)

    # Build ORDER BY
    if sort == 'code':
        order_sql = "ORDER BY identified_code ASC"
    else:  # scrape_time
        order_sql = "ORDER BY last_scrape_at DESC, identified_code ASC"

    # Count total
    count_sql = f"SELECT COUNT(*) FROM files WHERE {where_sql}"
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(count_sql, tuple(params))
            row = await cursor.fetchone()
            total = row[0] if row else 0

            stats_cursor = await db.execute(
                f"""
                SELECT
                    COUNT(*) AS organized,
                    SUM(CASE WHEN COALESCE(scrape_status, 'pending') = 'pending' THEN 1 ELSE 0 END) AS pending,
                    SUM(CASE WHEN COALESCE(scrape_status, 'pending') = 'success' THEN 1 ELSE 0 END) AS scraped,
                    SUM(CASE WHEN COALESCE(scrape_status, 'pending') = 'failed' THEN 1 ELSE 0 END) AS failed
                FROM files
                WHERE status IN ({processed_placeholders})
                """,
                tuple(PROCESSED_LIKE_STATUSES)
            )
            stats_row = await stats_cursor.fetchone()

            # Query items
            offset = (page - 1) * per_page
            data_sql = f"""
                SELECT
                    id,
                    original_path,
                    identified_code,
                    target_path,
                    status,
                    COALESCE(scrape_status, 'pending') AS scrape_status,
                    last_scrape_at,
                    scrape_started_at,
                    scrape_finished_at,
                    scrape_stage,
                    scrape_source,
                    scrape_error,
                    scrape_error_user_message,
                    scrape_logs
                FROM files
                WHERE {where_sql}
                {order_sql}
                LIMIT ? OFFSET ?
            """
            cursor = await db.execute(data_sql, (*tuple(params), per_page, offset))
            rows = await cursor.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Database error: {str(e)}')

    items = []
    for row in rows:
        row_data = dict(row)
        items.append(
            ScrapeListItem(
                file_id=row_data['id'],
                code=row_data.get('identified_code') or '',
                target_path=row_data.get('target_path') or '',
                original_path=row_data.get('original_path') or '',
                status=row_data.get('status') or 'processed',
                scrape_status=row_data.get('scrape_status') or 'pending',
                last_scrape_at=row_data.get('last_scrape_at'),
                scrape_started_at=row_data.get('scrape_started_at'),
                scrape_finished_at=row_data.get('scrape_finished_at'),
                scrape_stage=row_data.get('scrape_stage'),
                scrape_source=row_data.get('scrape_source'),
                scrape_error=row_data.get('scrape_error'),
                scrape_error_user_message=row_data.get('scrape_error_user_message'),
                scrape_logs=_parse_scrape_logs(row_data.get('scrape_logs')),
            )
        )

    stats = {
        'organized': int(stats_row['organized'] or 0) if stats_row else 0,
        'pending': int(stats_row['pending'] or 0) if stats_row else 0,
        'scraped': int(stats_row['scraped'] or 0) if stats_row else 0,
        'failed': int(stats_row['failed'] or 0) if stats_row else 0,
    }

    return {"total": total, "items": items, "stats": stats}


@app.post("/api/scrape/batch", response_model=ScrapeBatchResult)
async def scrape_files_batch(request: OrganizeRequest):
    """
    批量刮削文件元数据

    请求：
    {
        "file_ids": [1, 2, 3]
    }
    """
    scheduler = ScraperScheduler()
    results = []
    success_count = 0
    failed_count = 0

    for file_id in request.file_ids:
        try:
            result = await scheduler.scrape_single(file_id)
            results.append({
                'file_id': file_id,
                'success': result.success,
                'error': result.error
            })
            if result.success:
                success_count += 1
            else:
                failed_count += 1
        except Exception as e:
            results.append({
                'file_id': file_id,
                'success': False,
                'error': str(e)
            })
            failed_count += 1

    return ScrapeBatchResult(
        success_count=success_count,
        failed_count=failed_count,
        results=results
    )


@app.post("/api/scrape/{file_id}", response_model=ScrapeResponse)
async def scrape_file(file_id: int):
    """
    刮削单个文件元数据

    参数:
    - file_id: 文件数据库 ID
    """
    scheduler = ScraperScheduler()
    try:
        result = await scheduler.scrape_single(file_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "profile": os.getenv('NOCTRA_PROFILE', 'unknown'),
        "source_dir": SOURCE_DIR,
        "dist_dir": DIST_DIR,
        "db_path": DB_PATH,
        "cwd": str(Path.cwd()),
    }
