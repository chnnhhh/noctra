from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class FileRecord(BaseModel):
    id: int
    original_path: str
    identified_code: Optional[str]
    target_path: Optional[str]
    status: str  # pending, processed, skipped, target_exists, failed, ignored
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


class DeleteFileRequest(BaseModel):
    action: str  # delete_source, ignore_scan


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
