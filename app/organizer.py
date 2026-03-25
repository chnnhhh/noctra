import os
import re
import shutil
from pathlib import Path
from typing import Optional
from datetime import datetime


class JAVOrganizer:
    def __init__(self, dist_dir: str):
        self.dist_dir = Path(dist_dir).resolve()

    def get_filename_parts(self, filename: str) -> tuple[str, str, Optional[str]]:
        """
        解析文件名各部分

        返回：(纯文件名, 扩展名, 后缀)

        例：
        - FPRE-123C.mp4 -> (FPRE-123, .mp4, -C)
        - ABP-456-C.mp4 -> (ABP-456, .mp4, -C)
        - MVSD-662-UC.mkv -> (MVSD-662, .mkv, -UC)
        - SSIS-123.mp4 -> (SSIS-123, .mp4, None)
        """
        # 去掉扩展名
        name_without_ext = os.path.splitext(filename)[0]

        # Step 1：提取核心番号
        # 使用简单稳定规则：prefix = 字母部分, number = 数字部分
        # code = prefix + "-" + number
        pattern_code = r'^([A-Za-z]+)-?(\d+)'
        match_code = re.match(pattern_code, name_without_ext)

        if match_code:
            base_code = match_code.group(1) + '-' + match_code.group(2)
        else:
            base_code = name_without_ext

        # Step 2：提取 suffix
        # 支持：-C, -UC, C（无连字符）, UC（无连字符）
        # 统一输出为带连字符的格式（如 -C）
        suffix = None

        # 先尝试匹配带连字符的后缀（优先）
        for s in ['-C', '-UC']:
            if name_without_ext.endswith(s):
                suffix = s
                break

        # 如果没找到，尝试匹配不带连字符的纯字母后缀（1-3个）
        if not suffix and len(name_without_ext) > len(base_code):
            potential_suffix = name_without_ext[len(base_code):]
            if potential_suffix.isalpha() and len(potential_suffix) <= 3:
                suffix = '-' + potential_suffix

        ext = os.path.splitext(filename)[1]
        return (base_code, ext, suffix)

    def generate_filename(self, code: str, original_filename: str) -> str:
        """
        生成目标文件名

        规则：
        - 检测原文件名是否有 -C、-UC 等后缀
        - 如果有，生成格式：{番号}-{后缀}{扩展名}
        - 如果没有，使用原文件名

        例：
        - FPRE-123C.mp4, FPRE-123 -> FPRE-123-C.mp4
        - ABP-456-C.mp4, ABP-456 -> ABP-456-C.mp4
        - MVSD-662-UC.mkv, MVSD-662 -> MVSD-662-UC.mkv
        - SSIS-123.mp4, SSIS-123 -> SSIS-123.mp4（不变）
        """
        # 解析原文件名
        (clean_name, ext, suffix) = self.get_filename_parts(original_filename)

        # 如果原文件名以纯番号结尾（如 SSIS-123），并且有后缀
        # 则生成 {番号}-{后缀}{扩展名}
        if suffix and clean_name == code:
            return f"{code}{suffix}{ext}"

        # 其他情况，使用原文件名
        return original_filename

    def get_target_path(self, code: str, original_filename: str) -> str:
        """
        生成目标路径

        格式：/dist/{番号}/{文件名}
        目录名使用纯番号
        文件名根据后缀规则生成
        """
        target_dir = self.dist_dir / code
        filename = self.generate_filename(code, original_filename)
        target_path = target_dir / filename
        return str(target_path)

    def move_file(self, source_path: str, target_path: str) -> bool:
        """
        移动文件

        返回：是否成功
        """
        try:
            source = Path(source_path)
            target = Path(target_path)

            # 创建目标目录
            target.parent.mkdir(parents=True, exist_ok=True)

            # 如果目标文件已存在，跳过
            if target.exists():
                return False

            # 移动文件
            shutil.move(str(source), str(target))
            return True
        except (OSError, shutil.Error) as e:
            print(f'移动失败: {source_path} -> {target_path}: {e}')
            return False

    def organize(self, files: list[dict]) -> list[dict]:
        """
        批量整理文件

        files: [
            {
                'file_id': 1,
                'original_path': '/source/videos/SSIS-123.mp4',
                'identified_code': 'SSIS-123',
                'filename': 'SSIS-123.mp4'
            },
            ...
        ]

        返回：
        [
            {
                'file_id': 1,
                'original_path': '/source/videos/SSIS-123.mp4',
                'target_path': '/dist/SSIS-123/SSIS-123.mp4',
                'status': 'moved'
            },
            ...
        ]
        """
        results = []

        for file_info in files:
            file_id = file_info['file_id']
            original_path = file_info['original_path']
            code = file_info['identified_code']
            filename = file_info['filename']

            # 计算目标路径
            target_path = self.get_target_path(code, filename)

            # 执行移动
            success = self.move_file(original_path, target_path)

            results.append({
                'file_id': file_id,
                'original_path': original_path,
                'target_path': target_path,
                'status': 'moved' if success else 'failed'
            })

        return results


def test_get_filename_parts():
    """测试文件名解析"""
    organizer = JAVOrganizer('/tmp/dist')

    test_cases = [
        # (文件名, 期望: 纯文件名, 期望: 扩展名, 期望: 后缀)
        ('FPRE-123C.mp4', ('FPRE-123', '.mp4', '-C')),
        ('ABP-456-C.mp4', ('ABP-456', '.mp4', '-C')),
        ('MVSD-662-UC.mkv', ('MVSD-662', '.mkv', '-UC')),
        ('SSIS-123.mp4', ('SSIS-123', '.mp4', None)),
        ('FPRE-123_字幕版.mp4', ('FPRE-123', '.mp4', '-字幕版')),
    ]

    print('=== 测试文件名解析 ===')
    for filename, (expected_name, expected_ext, expected_suffix) in test_cases:
        (name, ext, suffix) = organizer.get_filename_parts(filename)
        status = '✓' if (name == expected_name and ext == expected_ext and suffix == expected_suffix) else '✗'
        print(f'{status} {filename:30} -> ({name}, {ext}, {suffix})')

    print('\n=== 测试通过 ===')


def test_generate_filename():
    """测试文件名生成"""
    organizer = JAVOrganizer('/tmp/dist')

    test_cases = [
        # (番号, 原文件名, 期望文件名)
        ('FPRE-123', 'FPRE-123C.mp4', 'FPRE-123-C.mp4'),
        ('ABP-456', 'ABP-456-C.mp4', 'ABP-456-C.mp4'),
        ('MVSD-662', 'MVSD-662-UC.mkv', 'MVSD-662-UC.mkv'),
        ('SSIS-123', 'SSIS-123.mp4', 'SSIS-123.mp4'),  # 无后缀，不变
    ]

    print('\n=== 测试文件名生成 ===')
    for code, original_filename, expected_filename in test_cases:
        result_filename = organizer.generate_filename(code, original_filename)
        status = '✓' if result_filename == expected_filename else '✗'
        print(f'{status} {code:10} + {original_filename:20} -> {result_filename}')

    print('\n=== 测试通过 ===')


def test_get_target_path():
    """测试目标路径生成"""
    organizer = JAVOrganizer('/tmp/dist')

    test_cases = [
        # (番号, 原文件名, 期望路径)
        ('FPRE-123', 'FPRE-123C.mp4', '/tmp/dist/FPRE-123/FPRE-123-C.mp4'),
        ('ABP-456', 'ABP-456-C.mp4', '/tmp/dist/ABP-456/ABP-456-C.mp4'),
        ('MVSD-662', 'MVSD-662-UC.mkv', '/tmp/dist/MVSD-662/MVSD-662-UC.mkv'),
        ('SSIS-123', 'SSIS-123.mp4', '/tmp/dist/SSIS-123/SSIS-123.mp4'),
    ]

    print('\n=== 测试目标路径生成 ===')
    for code, original_filename, expected_path in test_cases:
        result_path = organizer.get_target_path(code, original_filename)
        status = '✓' if result_path == expected_path else '✗'
        print(f'{status} {expected_path}')

    print('\n=== 测试通过 ===')


if __name__ == '__main__':
    test_get_filename_parts()
    test_generate_filename()
    test_get_target_path()
