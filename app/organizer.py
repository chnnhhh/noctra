import errno
import os
import re
import shutil
from pathlib import Path
from typing import Optional


class JAVOrganizer:
    CODE_PATTERN = re.compile(r'([A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*-\d+)', re.IGNORECASE)
    SUBTITLE_MARKER_PATTERN = re.compile(r'字幕版|字幕')
    UNCENSORED_MARKER_PATTERN = re.compile(r'uncensored', re.IGNORECASE)
    SUFFIX_PREFIX_PATTERN = re.compile(r'^[\s._@-]*(?P<marker>UC|CH|C)(?=$|[^A-Za-z0-9])', re.IGNORECASE)

    def __init__(self, dist_dir: str):
        self.dist_dir = Path(dist_dir).resolve()

    def detect_suffix(self, name_without_ext: str) -> Optional[str]:
        """从番号后的前缀标记中提取标准后缀。"""
        code_match = self.CODE_PATTERN.search(name_without_ext)
        if not code_match:
            return None

        tail = name_without_ext[code_match.end():]
        suffix_match = self.SUFFIX_PREFIX_PATTERN.match(tail)
        if suffix_match:
            marker = suffix_match.group('marker').upper()
            return '-UC' if marker == 'UC' else '-C'

        stripped_tail = tail.lstrip(' ._@-')
        if stripped_tail.startswith('字幕版') or stripped_tail.startswith('字幕'):
            return '-C'
        if self.UNCENSORED_MARKER_PATTERN.search(stripped_tail):
            return '-UC'

        if self.SUBTITLE_MARKER_PATTERN.search(name_without_ext):
            return '-C'
        if self.UNCENSORED_MARKER_PATTERN.search(name_without_ext):
            return '-UC'

        return None

    def get_filename_parts(self, filename: str) -> tuple[str, str, Optional[str]]:
        """
        解析文件名各部分

        返回：(纯文件名, 扩展名, 后缀)

        例：
        - FPRE-123C.mp4 -> (FPRE-123, .mp4, -C)
        - ABP-456-C.mp4 -> (ABP-456, .mp4, -C)
        - MVSD-662-UC.mkv -> (MVSD-662, .mkv, -UC)
        - SSIS-123.mp4 -> (SSIS-123, .mp4, None)
        - FPRE-123_字幕版.mp4 -> (FPRE-123, .mp4, -C)
        - HMN-439-C.H265.mp4 -> (HMN-439, .mp4, -C)
        """
        name_without_ext = os.path.splitext(filename)[0]

        code_match = self.CODE_PATTERN.search(name_without_ext)
        base_code = code_match.group(1).upper() if code_match else name_without_ext
        ext = os.path.splitext(filename)[1]
        suffix = self.detect_suffix(name_without_ext)
        return (base_code, ext, suffix)

    def generate_filename(self, code: str, original_filename: str) -> str:
        """
        生成目标文件名

        规则：
        - 统一清洗成 {番号}{后缀}{扩展名}
        - 保留 -C、-UC、字幕、Uncensored 等语义后缀
        - 去掉番号后的中文、日文、编码标记等冗余文本

        例：
        - FPRE-123C.mp4, FPRE-123 -> FPRE-123-C.mp4
        - ABP-456-C.mp4, ABP-456 -> ABP-456-C.mp4
        - MVSD-662-UC.mkv, MVSD-662 -> MVSD-662-UC.mkv
        - FPRE-123_字幕版.mp4, FPRE-123 -> FPRE-123-C.mp4
        - MEYD-695 出轨xxx@北野未奈.mp4, MEYD-695 -> MEYD-695.mp4
        """
        (_, ext, suffix) = self.get_filename_parts(original_filename)
        normalized_code = code.upper()
        return f"{normalized_code}{suffix or ''}{ext}"

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

    def _copy_then_unlink(self, source: Path, target: Path) -> tuple[bool, Optional[str], Optional[str]]:
        """
        跨文件系统回退逻辑。

        EXDEV 表示源和目标不在同一个文件系统上，rename 无法原子跨设备移动，
        这时只能显式复制到目标端，确保目标文件落盘后再删除源文件。
        """
        try:
            shutil.copy2(str(source), str(target))

            # copy2 已经关闭写句柄，这里重新打开并 fsync，尽量确保目标文件已落盘。
            with target.open('rb') as target_file:
                os.fsync(target_file.fileno())

            if not target.exists():
                return (False, '复制完成后未找到目标文件', None)

            source.unlink()
            return (True, None, 'copy_delete')
        except OSError as e:
            return (False, f'跨文件系统复制失败: {e}', None)
        except shutil.Error as e:
            return (False, f'跨文件系统复制失败: {e}', None)

    def _move_file_atomic_or_copy_fallback(self, source: Path, target: Path) -> tuple[bool, Optional[str], Optional[str]]:
        """
        先尝试同文件系统原子移动，只有在 EXDEV 时才显式降级为 copy + delete。

        不能直接依赖 shutil.move，因为它会在内部悄悄决定走 rename 还是 copy+delete，
        调用层既看不到本次使用了哪条路径，也不方便后续排查跨盘性能问题。
        """
        try:
            # 同一文件系统下优先使用原子 replace，速度快且不会出现“复制到一半”的中间态。
            os.replace(str(source), str(target))
            return (True, None, 'rename')
        except OSError as e:
            if e.errno == errno.EXDEV:
                # EXDEV 说明发生了跨设备/跨文件系统移动，rename 无法直接完成。
                return self._copy_then_unlink(source, target)
            return (False, f'原子移动失败: {e}', None)

    def move_file(self, source_path: str, target_path: str) -> tuple[bool, Optional[str], Optional[str]]:
        """
        移动文件

        返回：(是否成功, 失败原因, 移动方式)
        """
        try:
            source = Path(source_path)
            target = Path(target_path)

            if not source.exists():
                return (False, '源文件不存在', None)

            # 创建目标目录
            target.parent.mkdir(parents=True, exist_ok=True)

            # 如果目标文件已存在，跳过
            if target.exists():
                return (False, '目标文件已存在', None)

            return self._move_file_atomic_or_copy_fallback(source, target)
        except OSError as e:
            print(f'移动失败: {source_path} -> {target_path}: {e}')
            return (False, f'移动失败: {e}', None)

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
            (success, reason, move_method) = self.move_file(original_path, target_path)
            result_status = 'moved'
            if not success:
                result_status = 'skipped' if reason == '目标文件已存在' else 'failed'

            results.append({
                'file_id': file_id,
                'original_path': original_path,
                'target_path': target_path,
                'status': result_status,
                'reason': reason,
                'move_method': move_method,
            })

        return results


def test_get_filename_parts():
    """测试文件名解析"""
    organizer = JAVOrganizer('/tmp/dist')

    test_cases = [
        # (文件名, 期望: 纯文件名, 期望: 扩展名, 期望: 后缀)
        ('FPRE-123C.mp4', ('FPRE-123', '.mp4', '-C')),
        ('ABP-456-C.mp4', ('ABP-456', '.mp4', '-C')),
        ('MVSD-662-C.mp4', ('MVSD-662', '.mp4', '-C')),
        ('MVSD-662-UC.mkv', ('MVSD-662', '.mkv', '-UC')),
        ('SSIS-123.mp4', ('SSIS-123', '.mp4', None)),
        ('FPRE-123_字幕版.mp4', ('FPRE-123', '.mp4', '-C')),
        ('SSIS-123字幕版.mp4', ('SSIS-123', '.mp4', '-C')),
        ('MEYD-695 出轨xxx@北野未奈.mp4', ('MEYD-695', '.mp4', None)),
        ('HMN-439-C.H265.mp4', ('HMN-439', '.mp4', '-C')),
        ('CEMD-721ch.mp4', ('CEMD-721', '.mp4', '-C')),
        ('HMN-112-C マジxxx痴 北野未奈.mp4', ('HMN-112', '.mp4', '-C')),
        ('ABC-123 [Uncensored].mp4', ('ABC-123', '.mp4', '-UC')),
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
        ('MVSD-662', 'MVSD-662-C.mp4', 'MVSD-662-C.mp4'),
        ('MVSD-662', 'MVSD-662-UC.mkv', 'MVSD-662-UC.mkv'),
        ('FPRE-123', 'FPRE-123_字幕版.mp4', 'FPRE-123-C.mp4'),
        ('SSIS-123', 'SSIS-123.mp4', 'SSIS-123.mp4'),
        ('MEYD-695', 'MEYD-695 出轨xxx@北野未奈.mp4', 'MEYD-695.mp4'),
        ('HMN-439', 'HMN-439-C.H265.mp4', 'HMN-439-C.mp4'),
        ('CEMD-721', 'CEMD-721ch.mp4', 'CEMD-721-C.mp4'),
        ('HMN-112', 'HMN-112-C マジxxx痴 北野未奈.mp4', 'HMN-112-C.mp4'),
        ('ABC-123', 'ABC-123 [Uncensored].mp4', 'ABC-123-UC.mp4'),
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
    dist_root = organizer.dist_dir

    test_cases = [
        # (番号, 原文件名, 期望路径)
        ('FPRE-123', 'FPRE-123C.mp4', str(dist_root / 'FPRE-123' / 'FPRE-123-C.mp4')),
        ('ABP-456', 'ABP-456-C.mp4', str(dist_root / 'ABP-456' / 'ABP-456-C.mp4')),
        ('MVSD-662', 'MVSD-662-C.mp4', str(dist_root / 'MVSD-662' / 'MVSD-662-C.mp4')),
        ('MVSD-662', 'MVSD-662-UC.mkv', str(dist_root / 'MVSD-662' / 'MVSD-662-UC.mkv')),
        ('FPRE-123', 'FPRE-123_字幕版.mp4', str(dist_root / 'FPRE-123' / 'FPRE-123-C.mp4')),
        ('SSIS-123', 'SSIS-123.mp4', str(dist_root / 'SSIS-123' / 'SSIS-123.mp4')),
        ('MEYD-695', 'MEYD-695 出轨xxx@北野未奈.mp4', str(dist_root / 'MEYD-695' / 'MEYD-695.mp4')),
        ('HMN-439', 'HMN-439-C.H265.mp4', str(dist_root / 'HMN-439' / 'HMN-439-C.mp4')),
        ('CEMD-721', 'CEMD-721ch.mp4', str(dist_root / 'CEMD-721' / 'CEMD-721-C.mp4')),
        ('HMN-112', 'HMN-112-C マジxxx痴 北野未奈.mp4', str(dist_root / 'HMN-112' / 'HMN-112-C.mp4')),
    ]

    print('\n=== 测试目标路径生成 ===')
    for code, original_filename, expected_path in test_cases:
        result_path = organizer.get_target_path(code, original_filename)
        status = '✓' if result_path == expected_path else '✗'
        print(f'{status} {expected_path} -> {result_path}')

    print('\n=== 测试通过 ===')


if __name__ == '__main__':
    test_get_filename_parts()
    test_generate_filename()
    test_get_target_path()
