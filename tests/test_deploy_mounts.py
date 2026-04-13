from pathlib import Path

import pytest

from app.deploy_mounts import resolve_nas_mount_config


def test_auto_mode_uses_shared_root_for_same_filesystem(tmp_path):
    media_root = tmp_path / "vol2" / "1000" / "porn"
    source_dir = media_root / "ChaosJAV"
    dist_dir = media_root / "OrderedJAV"
    source_dir.mkdir(parents=True)
    dist_dir.mkdir(parents=True)

    result = resolve_nas_mount_config(
        source_dir=str(source_dir),
        dist_dir=str(dist_dir),
        compose_file="docker-compose.nas-image.yml",
        requested_mode="auto",
    )

    assert result["mount_mode"] == "shared-root"
    assert result["media_bind_root"] == str(media_root)
    assert result["compose_file"] == "docker-compose.nas-image-shared-root.yml"


def test_auto_mode_keeps_separate_for_different_filesystems(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    dist_dir = tmp_path / "dist"
    source_dir.mkdir()
    dist_dir.mkdir()

    original_stat = Path.stat

    def fake_stat(self: Path):
        result = original_stat(self)
        if self == dist_dir:
            return type(result)((
                result.st_mode,
                result.st_ino,
                result.st_dev + 1,
                result.st_nlink,
                result.st_uid,
                result.st_gid,
                result.st_size,
                result.st_atime,
                result.st_mtime,
                result.st_ctime,
            ))
        return result

    monkeypatch.setattr(Path, "stat", fake_stat)

    result = resolve_nas_mount_config(
        source_dir=str(source_dir),
        dist_dir=str(dist_dir),
        compose_file="docker-compose.nas.yml",
        requested_mode="auto",
    )

    assert result["mount_mode"] == "separate"
    assert result["media_bind_root"] is None
    assert result["compose_file"] == "docker-compose.nas.yml"


def test_explicit_separate_mode_wins_even_when_same_filesystem(tmp_path):
    media_root = tmp_path / "media"
    source_dir = media_root / "source"
    dist_dir = media_root / "dist"
    source_dir.mkdir(parents=True)
    dist_dir.mkdir(parents=True)

    result = resolve_nas_mount_config(
        source_dir=str(source_dir),
        dist_dir=str(dist_dir),
        compose_file="docker-compose.nas-image.yml",
        requested_mode="separate",
    )

    assert result["mount_mode"] == "separate"
    assert result["media_bind_root"] is None
    assert result["compose_file"] == "docker-compose.nas-image.yml"


def test_explicit_shared_root_requires_paths_under_bind_root(tmp_path):
    source_dir = tmp_path / "source"
    dist_dir = tmp_path / "dist"
    bad_root = tmp_path / "other"
    source_dir.mkdir()
    dist_dir.mkdir()
    bad_root.mkdir()

    with pytest.raises(ValueError, match="NOCTRA_MEDIA_BIND_ROOT"):
        resolve_nas_mount_config(
            source_dir=str(source_dir),
            dist_dir=str(dist_dir),
            compose_file="docker-compose.nas-image.yml",
            requested_mode="shared-root",
            media_bind_root=str(bad_root),
        )
