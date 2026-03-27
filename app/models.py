from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class FileRecord(BaseModel):
    id: int
    original_path: str
    identified_code: Optional[str]
    target_path: Optional[str]
    status: str  # pending, duplicate, processed, skipped, target_exists, failed, ignored
    file_size: int
    file_mtime: float
    created_at: str
    updated_at: str


class StatsSummary(BaseModel):
    total_files: int
    identified: int
    unidentified: int
    pending: int
    processed: int


class ScanResult(StatsSummary):
    files: list[FileRecord]


class OrganizeRequest(BaseModel):
    file_ids: list[int]


class BatchCreateRequest(BaseModel):
    file_ids: list[int]


class DeleteFileRequest(BaseModel):
    action: str  # delete_source, ignore_scan


class BatchItemResult(BaseModel):
    id: int
    code: Optional[str] = None
    source_path: str
    target_path: Optional[str] = None
    status: str  # pending, processing, success, skipped, failed
    message: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class BatchJob(BaseModel):
    id: str
    status: str  # queued, running, completed, failed, cancelled
    total: int
    processed: int
    succeeded: int
    skipped: int
    failed: int
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    items: list[BatchItemResult]


class BatchCancelResult(BaseModel):
    id: str
    status: str
    message: str


class OrganizeResultItem(BaseModel):
    file_id: int
    original_path: str
    target_path: Optional[str]
    status: str  # moved, failed, skipped
    reason: Optional[str] = None


class OrganizeResult(BaseModel):
    success_count: int
    failed_count: int
    results: list[OrganizeResultItem]


class DeleteFileResult(BaseModel):
    file_id: int
    action: str
    message: str


class HistoryResult(StatsSummary):
    skipped: int
    files: list[FileRecord]


# ===== Scraping Models (MVP) =====


class ScrapeLogEntry(BaseModel):
    at: str
    level: str
    stage: str
    source: Optional[str] = None
    message: str


class ScrapeListItem(BaseModel):
    """刮削列表项"""
    file_id: int
    code: str
    target_path: str
    original_path: str
    status: str
    scrape_status: str  # pending, success, failed
    last_scrape_at: Optional[str] = None
    scrape_started_at: Optional[str] = None
    scrape_finished_at: Optional[str] = None
    scrape_stage: Optional[str] = None
    scrape_source: Optional[str] = None
    scrape_error: Optional[str] = None
    scrape_error_user_message: Optional[str] = None
    scrape_logs: list[ScrapeLogEntry] = Field(default_factory=list)


class ScrapeJobCreateRequest(BaseModel):
    file_ids: list[int]


class ScrapeJobItem(BaseModel):
    id: int
    code: Optional[str] = None
    target_path: Optional[str] = None
    status: str
    stage: Optional[str] = None
    source: Optional[str] = None
    user_message: Optional[str] = None
    technical_error: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class ScrapeJobSnapshot(BaseModel):
    id: str
    status: str
    total: int
    processed: int
    succeeded: int
    failed: int
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    current_file_id: Optional[int] = None
    current_file_code: Optional[str] = None
    current_stage: Optional[str] = None
    current_source: Optional[str] = None
    recent_logs: list[ScrapeLogEntry] = Field(default_factory=list)
    items: list[ScrapeJobItem] = Field(default_factory=list)


class ScrapeJobCancelResult(BaseModel):
    id: str
    status: str
    message: str


class ScrapeResponse(BaseModel):
    """单条刮削响应"""
    success: bool
    code: Optional[str] = None
    error: Optional[str] = None


class ScrapeBatchResultItem(BaseModel):
    """批量刮削结果项"""
    file_id: int
    success: bool
    error: Optional[str] = None


class ScrapeBatchResult(BaseModel):
    """批量刮削响应"""
    success_count: int
    failed_count: int
    results: list[ScrapeBatchResultItem]
