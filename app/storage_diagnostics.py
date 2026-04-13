import uuid
from pathlib import Path
from typing import Optional

from app.organizer import JAVOrganizer


def diagnose_storage_move_mode(source_dir: str, dist_dir: str) -> dict[str, Optional[object]]:
    source_root = Path(source_dir)
    dist_root = Path(dist_dir)

    if not source_root.exists():
        return {
            "mode": "unknown",
            "rename_capable": None,
            "reason": "源目录不存在，无法探测当前部署的移动方式",
        }

    if not dist_root.exists():
        return {
            "mode": "unknown",
            "rename_capable": None,
            "reason": "目标目录不存在，无法探测当前部署的移动方式",
        }

    probe_id = uuid.uuid4().hex
    source_probe = source_root / f".noctra-move-probe-{probe_id}.tmp"
    target_dir = dist_root / ".noctra-move-probe"
    target_probe = target_dir / f"{probe_id}.tmp"

    organizer = JAVOrganizer(str(dist_root))
    source_probe.write_bytes(b"probe")

    try:
        success, reason, move_method = organizer.move_file(str(source_probe), str(target_probe))

        if success and move_method == "rename":
            return {
                "mode": "rename",
                "rename_capable": True,
                "reason": "当前部署探测结果为原子 rename，可直接在源目录和目标目录之间快速移动",
            }

        if success and move_method == "copy_delete":
            return {
                "mode": "copy_delete",
                "rename_capable": False,
                "reason": "当前部署探测结果为 copy_delete，说明 rename 在当前挂载/文件系统边界下不可用",
            }

        return {
            "mode": "unknown",
            "rename_capable": None,
            "reason": reason or "移动方式探测失败",
        }
    finally:
        if source_probe.exists():
            source_probe.unlink()
        if target_probe.exists():
            target_probe.unlink()
        if target_dir.exists() and not any(target_dir.iterdir()):
            target_dir.rmdir()
