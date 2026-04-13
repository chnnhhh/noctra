import asyncio
import errno

from app.storage_diagnostics import diagnose_storage_move_mode


def test_diagnose_storage_move_mode_reports_rename(tmp_path):
    source_dir = tmp_path / "source"
    dist_dir = tmp_path / "dist"
    source_dir.mkdir()
    dist_dir.mkdir()

    result = diagnose_storage_move_mode(str(source_dir), str(dist_dir))

    assert result["mode"] == "rename"
    assert result["rename_capable"] is True


def test_diagnose_storage_move_mode_reports_copy_delete_on_exdev(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    dist_dir = tmp_path / "dist"
    source_dir.mkdir()
    dist_dir.mkdir()

    def fake_replace(src, dst):
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr("app.organizer.os.replace", fake_replace)

    result = diagnose_storage_move_mode(str(source_dir), str(dist_dir))

    assert result["mode"] == "copy_delete"
    assert result["rename_capable"] is False


def test_diagnose_storage_move_mode_handles_missing_source(tmp_path):
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()

    result = diagnose_storage_move_mode(str(tmp_path / "missing"), str(dist_dir))

    assert result["mode"] == "unknown"
    assert result["rename_capable"] is None


def test_health_check_includes_storage_diagnostic(monkeypatch):
    import app.main as main_mod

    monkeypatch.setattr(
        main_mod,
        "get_storage_diagnostic",
        lambda refresh=False: {
            "mode": "copy_delete",
            "rename_capable": False,
            "reason": "probe",
        },
    )

    result = asyncio.run(main_mod.health_check())

    assert result["storage_diagnostic"] == {
        "mode": "copy_delete",
        "rename_capable": False,
        "reason": "probe",
    }
