import asyncio
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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
)
from app.scanner import JAVScanner
from app.organizer import JAVOrganizer
from app.statuses import resolve_scan_status

app = FastAPI(title="Noctra JAV Organizer", version="1.0.0")

# 环境变量
SOURCE_DIR = os.getenv('SOURCE_DIR', '/source')
DIST_DIR = os.getenv('DIST_DIR', '/dist')
DB_PATH = os.getenv('DB_PATH', '/app/data/noctra.db')

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
        await db.commit()


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


async def get_all_files() -> list[dict]:
    """获取所有文件记录"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM files ORDER BY id DESC')
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


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
        for row in rows
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
        elif status == 'processed':
            processed += 1

    return {
        'total_files': total_files,
        'identified': identified,
        'unidentified': unidentified,
        'pending': pending,
        'processed': processed,
    }


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

    file_records = []

    for file_info in scanned_files:
        original_path = file_info['path']
        code = file_info['identified_code']
        existing = await get_file_by_path(original_path)

        # 判断是否已识别
        if code:
            # 计算目标路径
            filename = file_info['filename']
            target_path = organizer.get_target_path(code, filename)
            status = resolve_scan_status(code, target_path)
        else:
            target_path = None
            status = resolve_scan_status(code, target_path)

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

        # 检查历史记录
        if not force_rescan:
            if existing:
                # 文件未变化（大小和 mtime 相同）
                if existing['file_size'] == file_info['size'] and existing['file_mtime'] == file_info['mtime']:
                    if existing['status'] == 'processed' and status == 'pending':
                        status = existing['status']
                        target_path = existing['target_path']
                    else:
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
                    # 文件已变化，更新记录
                    await upsert_file(
                        original_path=original_path,
                        identified_code=code,
                        target_path=target_path,
                        status=status,
                        file_size=file_info['size'],
                        file_mtime=file_info['mtime']
                    )
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
        cursor = await db.execute(
            f'SELECT * FROM files WHERE id IN ({placeholders}) AND status = ?',
            (*request.file_ids, 'pending')
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
    for row in rows:
        row_dict = dict(row)
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

        if status == 'moved':
            await update_file_status(file_id, 'processed', target_path)
            success_count += 1
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
        raise HTTPException(status_code=400, detail='请选择至少一个待处理文件')

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        placeholders = ','.join('?' * len(request.file_ids))
        cursor = await db.execute(
            f'SELECT * FROM files WHERE id IN ({placeholders}) AND status = ?',
            (*request.file_ids, 'pending')
        )
        rows = await cursor.fetchall()

    if not rows:
        raise HTTPException(status_code=400, detail='没有可整理的待处理文件')

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
    processed_files = [f for f in all_files if f['status'] == 'processed']

    file_records = [
        FileRecord(
            id=f['id'],
            original_path=f['original_path'],
            identified_code=f['identified_code'],
            target_path=f['target_path'],
            status=f['status'],
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
        processed=stats['processed'],
        skipped=skipped,
        files=file_records
    )


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
