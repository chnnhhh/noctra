from pathlib import Path
from typing import Optional


def resolve_scan_status(identified_code: Optional[str], target_path: Optional[str]) -> str:
    """根据当前扫描结果判断文件状态。"""
    if not identified_code:
        return 'skipped'

    if target_path and Path(target_path).exists():
        return 'target_exists'

    return 'pending'
