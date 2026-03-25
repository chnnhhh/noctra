import pytest
import tempfile
from pathlib import Path

from app.scanner import JAVScanner
from app.statuses import resolve_scan_status


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


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
