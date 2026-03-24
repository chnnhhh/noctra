from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class FileRecord(BaseModel):
    id: int
    original_path: str
    identified_code: Optional[str]
    target_path: Optional[str]
    status: str  # pending, processed, skipped
    file_size: int
    file_mtime: float
    created_at: str
    updated_at: str


class ScanResult(BaseModel):
    total_files: int
    identified: int
    unidentified: int
    pending: int
    processed: int
    files: list[FileRecord]


class OrganizeRequest(BaseModel):
    file_ids: list[int]


class OrganizeResultItem(BaseModel):
    file_id: int
    original_path: str
    target_path: Optional[str]
    status: str  # moved, failed, skipped


class OrganizeResult(BaseModel):
    success_count: int
    failed_count: int
    results: list[OrganizeResultItem]


class HistoryResult(BaseModel):
    total: int
    processed: int
    skipped: int
    files: list[FileRecord]
