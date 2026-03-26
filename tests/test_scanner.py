import asyncio
import pytest
import tempfile
from pathlib import Path

import app.main as main_mod
from app.organizer import JAVOrganizer
from app.scanner import JAVScanner
from app.statuses import (
    assign_batch_duplicate_statuses,
    classify_suffix_category,
    compare_candidate_priority,
    resolve_scan_status,
)


def build_scan_candidate(
    source_dir: Path,
    organizer: JAVOrganizer,
    scanner: JAVScanner,
    relative_path: str,
    size: int
) -> dict:
    source_path = source_dir / relative_path
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b'0' * size)

    filename = source_path.name
    identified_code = scanner.identify_code(filename)
    target_path = organizer.get_target_path(identified_code, filename) if identified_code else None

    return {
        'path': str(source_path),
        'original_path': str(source_path),
        'filename': filename,
        'identified_code': identified_code,
        'target_path': target_path,
        'status': resolve_scan_status(identified_code, target_path),
        'size': size,
        'file_size': size,
        'mtime': source_path.stat().st_mtime,
    }


class TestJAVScanner:
    def test_identify_code(self):
        """测试番号识别"""
        scanner = JAVScanner('/tmp/source', '/tmp/dist')

        test_cases = [
            ('SSIS-123.mp4', 'SSIS-123'),
            ('ABP-456-C.mp4', 'ABP-456'),
            ('MVSD-662-C.mp4', 'MVSD-662'),
            ('MVSD-662-UC.mkv', 'MVSD-662'),
            ('FPRE-123C.mp4', 'FPRE-123'),
            ('FC2-PPV-1234567.mp4', 'FC2-PPV-1234567'),
            ('ABC-123_字幕版.mp4', 'ABC-123'),
            ('ABC-123 [Uncensored].mp4', 'ABC-123'),
            ('SSIS-123字幕版.mp4', 'SSIS-123'),
            ('MEYD-695 出轨xxx@北野未奈.mp4', 'MEYD-695'),
            ('HMN-439-C.H265.mp4', 'HMN-439'),
            ('CEMD-721ch.mp4', 'CEMD-721'),
            ('HMN-112-C マジxxx痴 北野未奈.mp4', 'HMN-112'),
            ('unknown_file.mp4', None),
            ('123-456.mp4', None),  # 纯数字开头不支持
        ]

        for filename, expected in test_cases:
            result = scanner.identify_code(filename)
            assert result == expected, f'{filename} -> {result} (期望: {expected})'

    def test_video_file_detection(self):
        """测试视频文件识别"""
        scanner = JAVScanner('/tmp/source', '/tmp/dist')

        # 视频文件
        assert scanner.is_video_file(Path('/source/video.mp4'))
        assert scanner.is_video_file(Path('/source/video.mkv'))
        assert scanner.is_video_file(Path('/source/video.avi'))

        # 非视频文件
        assert not scanner.is_video_file(Path('/source/video.txt'))
        assert not scanner.is_video_file(Path('/source/photo.jpg'))

    def test_dist_skip(self):
        """测试 dist 目录跳过"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / 'source'
            dist_dir = source_dir / 'dist'
            source_dir.mkdir(parents=True)
            dist_dir.mkdir()

            scanner = JAVScanner(str(source_dir), str(dist_dir))

            # dist 目录应该被跳过
            assert scanner.should_skip(dist_dir)

            # dist 子目录也应该被跳过
            subdir = dist_dir / 'videos'
            subdir.mkdir()
            assert scanner.should_skip(subdir)

            # source 下的其他目录不应该被跳过
            other_dir = source_dir / 'other'
            other_dir.mkdir()
            assert not scanner.should_skip(other_dir)

    def test_scan(self):
        """测试完整扫描"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / 'source'
            dist_dir = source_dir / 'dist'
            actress_dir = source_dir / '北野未奈'
            source_dir.mkdir(parents=True)
            dist_dir.mkdir()
            actress_dir.mkdir()

            # 创建测试文件
            (source_dir / 'SSIS-123.mp4').write_text('fake')
            (actress_dir / 'FPRE-123C.mp4').write_text('fake')
            (actress_dir / 'MVSD-662-C.mp4').write_text('fake')
            (source_dir / 'unknown.txt').write_text('fake')
            (dist_dir / 'FC2-123.mp4').write_text('fake')  # 在 dist 中，应该被跳过

            scanner = JAVScanner(str(source_dir), str(dist_dir))
            results = scanner.scan()

            # 应该识别 3 个视频文件
            assert len(results) == 3

            # 检查识别结果
            code_map = {r['filename']: r['identified_code'] for r in results}
            assert code_map['SSIS-123.mp4'] == 'SSIS-123'
            assert code_map['FPRE-123C.mp4'] == 'FPRE-123'
            assert code_map['MVSD-662-C.mp4'] == 'MVSD-662'

            # dist 中的文件不应该被扫描到
            paths = [r['path'] for r in results]
            assert not any('dist' in p for p in paths)

    def test_resolve_scan_status_marks_existing_target(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / 'dist' / 'FPRE-123' / 'FPRE-123-C.mp4'
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('existing target')

            assert resolve_scan_status('FPRE-123', str(target)) == 'target_exists'
            assert resolve_scan_status('SSIS-123', str(target.parent / 'SSIS-123.mp4')) == 'pending'
            assert resolve_scan_status(None, None) == 'skipped'

    def test_resolve_scan_status_checks_full_target_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dist_dir = Path(tmpdir) / 'dist'
            organizer = JAVOrganizer(str(dist_dir))
            existing_target = Path(organizer.get_target_path('ABW-1008', 'ABW-1008-C.mp4'))
            existing_target.parent.mkdir(parents=True, exist_ok=True)
            existing_target.write_text('existing target')

            normal_target = organizer.get_target_path('ABW-1008', 'ABW-1008.mp4')

            assert resolve_scan_status('ABW-1008', str(existing_target)) == 'target_exists'
            assert resolve_scan_status('ABW-1008', normal_target) == 'pending'

    def test_classify_suffix_category(self):
        assert classify_suffix_category('ABW-1007-UC.mkv') == 'UC'
        assert classify_suffix_category('ABW-1007-C.mp4') == 'C'
        assert classify_suffix_category('ABW-1007_字幕版.mp4') == 'SUB'
        assert classify_suffix_category('ABW-1007xxx.mp4') == 'PLAIN'
        assert classify_suffix_category('CEMD-721ch.mp4') == 'C'

    def test_assign_batch_duplicate_statuses_prefers_suffix_priority(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / 'source'
            dist_dir = Path(tmpdir) / 'dist'
            source_dir.mkdir(parents=True)
            dist_dir.mkdir()

            scanner = JAVScanner(str(source_dir), str(dist_dir))
            organizer = JAVOrganizer(str(dist_dir))
            candidates = [
                build_scan_candidate(source_dir, organizer, scanner, 'ABW-1007.mp4', 100),
                build_scan_candidate(source_dir, organizer, scanner, 'ABW-1007-C.mp4', 200),
                build_scan_candidate(source_dir, organizer, scanner, 'ABW-1007_字幕版.mp4', 300),
                build_scan_candidate(source_dir, organizer, scanner, 'ABW-1007-UC.mkv', 50),
                build_scan_candidate(source_dir, organizer, scanner, 'ABW-1007xxx.mp4', 400),
            ]

            assign_batch_duplicate_statuses(candidates)
            status_map = {candidate['filename']: candidate['status'] for candidate in candidates}

            assert status_map['ABW-1007-UC.mkv'] == 'pending'
            assert status_map['ABW-1007-C.mp4'] == 'duplicate'
            assert status_map['ABW-1007_字幕版.mp4'] == 'duplicate'
            assert status_map['ABW-1007.mp4'] == 'duplicate'
            assert status_map['ABW-1007xxx.mp4'] == 'duplicate'

    def test_assign_batch_duplicate_statuses_prefers_larger_file_within_same_suffix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / 'source'
            dist_dir = Path(tmpdir) / 'dist'
            source_dir.mkdir(parents=True)
            dist_dir.mkdir()

            scanner = JAVScanner(str(source_dir), str(dist_dir))
            organizer = JAVOrganizer(str(dist_dir))
            larger = build_scan_candidate(source_dir, organizer, scanner, 'a/ABW-2001-UC.mp4', 200)
            smaller = build_scan_candidate(source_dir, organizer, scanner, 'b/ABW-2001 [Uncensored].mkv', 100)

            assign_batch_duplicate_statuses([larger, smaller])

            assert larger['status'] == 'pending'
            assert smaller['status'] == 'duplicate'

    def test_assign_batch_duplicate_statuses_groups_plain_candidates_across_extensions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / 'source'
            dist_dir = Path(tmpdir) / 'dist'
            source_dir.mkdir(parents=True)
            dist_dir.mkdir()

            scanner = JAVScanner(str(source_dir), str(dist_dir))
            organizer = JAVOrganizer(str(dist_dir))
            candidates = [
                build_scan_candidate(source_dir, organizer, scanner, 'plain/ABW-3001.mp4', 120),
                build_scan_candidate(source_dir, organizer, scanner, 'plain/ABW-3001.mkv', 160),
                build_scan_candidate(source_dir, organizer, scanner, 'plain/ABW-3001xxx.mp4', 140),
            ]

            assign_batch_duplicate_statuses(candidates)
            status_map = {candidate['filename']: candidate['status'] for candidate in candidates}

            assert status_map['ABW-3001.mkv'] == 'pending'
            assert status_map['ABW-3001.mp4'] == 'duplicate'
            assert status_map['ABW-3001xxx.mp4'] == 'duplicate'

    def test_compare_candidate_priority_falls_back_to_natural_name_then_path(self):
        left = {
            'filename': 'ABW-4001x2.mp4',
            'original_path': '/source/a/ABW-4001x2.mp4',
            'file_size': 100,
        }
        right = {
            'filename': 'ABW-4001x10.mp4',
            'original_path': '/source/a/ABW-4001x10.mp4',
            'file_size': 100,
        }
        same_name_other_path = {
            'filename': 'ABW-4001x2.mp4',
            'original_path': '/source/b/ABW-4001x2.mp4',
            'file_size': 100,
        }

        assert compare_candidate_priority(left, right) < 0
        assert compare_candidate_priority(left, same_name_other_path) < 0

    def test_related_candidates_become_target_exists_after_organize(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / 'source'
            dist_dir = Path(tmpdir) / 'dist'
            db_path = Path(tmpdir) / 'data' / 'noctra.db'
            source_dir.mkdir(parents=True)
            dist_dir.mkdir()

            for relative_path, size in [
                ('ABW-6007-C.mp4', 80),
                ('ABW-6007-UC.mkv', 120),
                ('ABW-6007.mp4', 60),
                ('ABW-6007_字幕版.mp4', 70),
                ('ABW-6007xxx.mp4', 50),
            ]:
                file_path = source_dir / relative_path
                file_path.write_bytes(b'0' * size)

            original_db_path = main_mod.DB_PATH
            original_source_dir = main_mod.SOURCE_DIR
            original_dist_dir = main_mod.DIST_DIR
            original_scanner = main_mod.scanner
            original_organizer = main_mod.organizer

            try:
                main_mod.DB_PATH = str(db_path)
                main_mod.SOURCE_DIR = str(source_dir)
                main_mod.DIST_DIR = str(dist_dir)
                main_mod.scanner = JAVScanner(str(source_dir), str(dist_dir))
                main_mod.organizer = JAVOrganizer(str(dist_dir))

                async def scenario():
                    await main_mod.init_db()

                    first_scan = await main_mod.scan_files()
                    first_statuses = {
                        Path(file.original_path).name: file.status
                        for file in first_scan.files
                    }

                    assert first_statuses['ABW-6007-UC.mkv'] == 'pending'
                    assert first_statuses['ABW-6007-C.mp4'] == 'duplicate'
                    assert first_statuses['ABW-6007.mp4'] == 'duplicate'
                    assert first_statuses['ABW-6007_字幕版.mp4'] == 'duplicate'
                    assert first_statuses['ABW-6007xxx.mp4'] == 'duplicate'

                    chosen = next(
                        file for file in first_scan.files
                        if Path(file.original_path).name == 'ABW-6007-C.mp4'
                    )
                    success, reason = await asyncio.to_thread(
                        main_mod.organizer.move_file,
                        chosen.original_path,
                        chosen.target_path
                    )
                    assert success, reason

                    await main_mod.update_file_status(chosen.id, 'processed', chosen.target_path)
                    await main_mod.mark_related_files_target_exists(chosen.id, chosen.identified_code)

                    second_scan = await main_mod.scan_files()
                    second_statuses = {
                        Path(file.original_path).name: file.status
                        for file in second_scan.files
                    }

                    assert 'ABW-6007-C.mp4' not in second_statuses
                    assert second_statuses['ABW-6007-UC.mkv'] == 'target_exists'
                    assert second_statuses['ABW-6007.mp4'] == 'target_exists'
                    assert second_statuses['ABW-6007_字幕版.mp4'] == 'target_exists'
                    assert second_statuses['ABW-6007xxx.mp4'] == 'target_exists'

                    history = await main_mod.get_history()
                    history_names = [Path(file.original_path).name for file in history.files]

                    assert history_names == ['ABW-6007-C.mp4']
                    assert history.processed == 1

                asyncio.run(scenario())
            finally:
                main_mod.DB_PATH = original_db_path
                main_mod.SOURCE_DIR = original_source_dir
                main_mod.DIST_DIR = original_dist_dir
                main_mod.scanner = original_scanner
                main_mod.organizer = original_organizer

    def test_same_suffix_different_extension_falls_back_to_target_exists_after_manual_organize(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / 'source'
            dist_dir = Path(tmpdir) / 'dist'
            db_path = Path(tmpdir) / 'data' / 'noctra.db'
            source_dir.mkdir(parents=True)
            dist_dir.mkdir()

            for relative_path, size in [
                ('ABP-456-C.mp4', 80),
                ('ABP-456-C.mkv', 120),
            ]:
                file_path = source_dir / relative_path
                file_path.write_bytes(b'0' * size)

            original_db_path = main_mod.DB_PATH
            original_source_dir = main_mod.SOURCE_DIR
            original_dist_dir = main_mod.DIST_DIR
            original_scanner = main_mod.scanner
            original_organizer = main_mod.organizer

            try:
                main_mod.DB_PATH = str(db_path)
                main_mod.SOURCE_DIR = str(source_dir)
                main_mod.DIST_DIR = str(dist_dir)
                main_mod.scanner = JAVScanner(str(source_dir), str(dist_dir))
                main_mod.organizer = JAVOrganizer(str(dist_dir))

                async def scenario():
                    await main_mod.init_db()

                    first_scan = await main_mod.scan_files()
                    first_statuses = {
                        Path(file.original_path).name: file.status
                        for file in first_scan.files
                    }

                    assert first_statuses['ABP-456-C.mkv'] == 'pending'
                    assert first_statuses['ABP-456-C.mp4'] == 'duplicate'

                    chosen = next(
                        file for file in first_scan.files
                        if Path(file.original_path).name == 'ABP-456-C.mp4'
                    )
                    success, reason = await asyncio.to_thread(
                        main_mod.organizer.move_file,
                        chosen.original_path,
                        chosen.target_path
                    )
                    assert success, reason

                    await main_mod.update_file_status(chosen.id, 'processed', chosen.target_path)
                    await main_mod.mark_related_files_target_exists(chosen.id, chosen.identified_code)

                    second_scan = await main_mod.scan_files()
                    second_statuses = {
                        Path(file.original_path).name: file.status
                        for file in second_scan.files
                    }

                    assert 'ABP-456-C.mp4' not in second_statuses
                    assert second_statuses['ABP-456-C.mkv'] == 'target_exists'
                    assert all(status != 'processed' for status in second_statuses.values())

                asyncio.run(scenario())
            finally:
                main_mod.DB_PATH = original_db_path
                main_mod.SOURCE_DIR = original_source_dir
                main_mod.DIST_DIR = original_dist_dir
                main_mod.scanner = original_scanner
                main_mod.organizer = original_organizer


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
