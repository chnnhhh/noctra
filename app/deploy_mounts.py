import os
from pathlib import Path
from typing import Optional


def _shared_root_compose_file(compose_file: str) -> str:
    if compose_file.endswith(".yml"):
        return f"{compose_file[:-4]}-shared-root.yml"
    if compose_file.endswith(".yaml"):
        return f"{compose_file[:-5]}-shared-root.yaml"
    return f"{compose_file}-shared-root"


def _stat_device_id(path: Path) -> int:
    return path.stat().st_dev


def _is_relative_to(path: Path, candidate_root: Path) -> bool:
    try:
        path.relative_to(candidate_root)
        return True
    except ValueError:
        return False


def _auto_media_bind_root(source_dir: Path, dist_dir: Path) -> Optional[Path]:
    source_resolved = source_dir.resolve()
    dist_resolved = dist_dir.resolve()

    if _stat_device_id(source_resolved) != _stat_device_id(dist_resolved):
        return None

    common_root = Path(os.path.commonpath([source_resolved, dist_resolved]))
    if common_root == Path(source_resolved.anchor):
        return None

    return common_root


def _validate_media_bind_root(source_dir: Path, dist_dir: Path, media_bind_root: Optional[str]) -> Path:
    if not media_bind_root:
        raise ValueError("NOCTRA_MEDIA_BIND_ROOT is required when mount mode is shared-root")

    bind_root = Path(media_bind_root).resolve()
    source_resolved = source_dir.resolve()
    dist_resolved = dist_dir.resolve()

    if not _is_relative_to(source_resolved, bind_root) or not _is_relative_to(dist_resolved, bind_root):
        raise ValueError("NOCTRA_MEDIA_BIND_ROOT must contain both NOCTRA_SOURCE_DIR and NOCTRA_DIST_DIR")

    if _stat_device_id(source_resolved) != _stat_device_id(dist_resolved):
        raise ValueError("shared-root mount mode requires source and dist on the same filesystem")

    return bind_root


def resolve_nas_mount_config(
    *,
    source_dir: str,
    dist_dir: str,
    compose_file: str,
    requested_mode: str = "auto",
    media_bind_root: Optional[str] = None,
) -> dict[str, Optional[str]]:
    source_path = Path(source_dir)
    dist_path = Path(dist_dir)
    mount_mode = requested_mode
    bind_root: Optional[Path] = None

    if requested_mode == "auto":
        bind_root = _auto_media_bind_root(source_path, dist_path)
        mount_mode = "shared-root" if bind_root else "separate"
    elif requested_mode == "shared-root":
        bind_root = _validate_media_bind_root(source_path, dist_path, media_bind_root)
    elif requested_mode == "separate":
        bind_root = None
    else:
        raise ValueError("NOCTRA_REMOTE_MOUNT_MODE must be one of: auto, separate, shared-root")

    selected_compose_file = compose_file
    if mount_mode == "shared-root":
        selected_compose_file = _shared_root_compose_file(compose_file)

    return {
        "mount_mode": mount_mode,
        "media_bind_root": str(bind_root) if bind_root else None,
        "compose_file": selected_compose_file,
    }
