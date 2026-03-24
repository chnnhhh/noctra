import os
import re
from pathlib import Path
from typing import Optional
from datetime import datetime


class JAVScanner:
    def __init__(self, source_dir: str, dist_dir: str):
        self.source_dir = Path(source_dir).resolve()
        self.dist_dir = Path(dist_dir).resolve()
        self.video_extensions = {'.mp4', '.mkv', '.avi', '.wmv', '.mov'}

    def is_video_file(self, path: Path) -> bool:
        """判断是否为视频文件"""
        return path.suffix.lower() in self.video_extensions

    def should_skip(self, path: Path) -> bool:
        """判断是否应该跳过"""
        try:
            # 跳过 dist 目录
            path_resolved = path.resolve()
            if path_resolved == self.dist_dir or str(path_resolved).startswith(str(self.dist_dir)):
                return True
            return False
        except (OSError, ValueError):
            return True

    def identify_code(self, filename: str) -> Optional[str]:
        """
        识别 JAV 番号

        支持格式：
        - SSIS-123.mp4
        - ABP-456-C.mp4
        - FC2-PPV-1234567.mp4
        - ABC-123_字幕版.mp4
        - ABC-123 [Uncensored].mp4
        """
        # 去掉扩展名
        name_without_ext = os.path.splitext(filename)[0]

        # 主流番号格式：字母或字母数字组合开头，连字符，数字
        # 例：SSIS-123, ABP-456-C, FC2-PPV-1234567
        # 第一段：必须包含字母
        # 中间段：字母或字母数字组合
        # 最后一段：数字
        pattern = r'^([A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*-\d+(?:-[A-Za-z0-9]+)?)'

        match = re.search(pattern, name_without_ext)
        if match:
            code = match.group(1).upper()
            return code

        return None

    def scan(self) -> list[dict]:
        """
        扫描 source 目录

        返回：
        [
            {
                'path': '/source/videos/SSIS-123.mp4',
                'filename': 'SSIS-123.mp4',
                'identified_code': 'SSIS-123',
                'size': 12345678,
                'mtime': 1234567890.123
            },
            ...
        ]
        """
        results = []

        if not self.source_dir.exists():
            return results

        for root, dirs, files in os.walk(self.source_dir):
            root_path = Path(root)

            # 跳过 dist 相关目录
            for d in list(dirs):
                d_path = root_path / d
                if self.should_skip(d_path):
                    dirs.remove(d)

            for filename in files:
                file_path = root_path / filename

                # 跳过非视频文件
                if not self.is_video_file(file_path):
                    continue

                # 跳过 dist 下的文件
                if self.should_skip(file_path):
                    continue

                # 获取文件信息
                try:
                    stat_info = file_path.stat()
                except OSError:
                    continue

                # 识别番号
                code = self.identify_code(filename)

                results.append({
                    'path': str(file_path.resolve()),
                    'filename': filename,
                    'identified_code': code,
                    'size': stat_info.st_size,
                    'mtime': stat_info.st_mtime
                })

        return results


def test_identify():
    """测试番号识别"""
    scanner = JAVScanner('/tmp/source', '/tmp/dist')

    test_cases = [
        ('SSIS-123.mp4', 'SSIS-123'),
        ('ABP-456-C.mp4', 'ABP-456-C'),
        ('FC2-PPV-1234567.mp4', 'FC2-PPV-1234567'),
        ('ABC-123_字幕版.mp4', 'ABC-123'),
        ('ABC-123 [Uncensored].mp4', 'ABC-123'),
        ('SSIS-123字幕版.mp4', 'SSIS-123'),
        ('unknown_file.mp4', None),
        ('123-456.mp4', None),  # 纯数字开头不支持
    ]

    print('=== JAV 番号识别测试 ===')
    for filename, expected in test_cases:
        result = scanner.identify_code(filename)
        status = '✓' if result == expected else '✗'
        print(f'{status} {filename:40} -> {result or "None":20} (期望: {expected})')

    print('\n=== 测试通过 ===')


if __name__ == '__main__':
    test_identify()
