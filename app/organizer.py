import os
import shutil
from pathlib import Path
from typing import Optional
from datetime import datetime


class JAVOrganizer:
    def __init__(self, dist_dir: str):
        self.dist_dir = Path(dist_dir).resolve()

    def get_suffix(self, filename: str, code: str) -> Optional[str]:
        """
        提取文件名中的后缀（-C、-UC 等）

        例：
        - FPRE-123C.mp4 -> -C（补上连字符）
        - ABP-456-C.mp4 -> -C
        - MVSD-662-UC.mkv -> -UC
        - SSIS-123.mp4 -> None（没有后缀）
        """
        # 去掉扩展名
        name_without_ext = os.path.splitext(filename)[0]

        # 检查是否有番号（从番号开始）
        if name_without_ext.startswith(code):
            # 提取番号后的部分
            suffix = name_without_ext[len(code):]
            # 如果有内容，返回（可能是 C、-C、-UC 等）
            # 如果后缀没有连字符，补充连字符
            if suffix:
                if not suffix.startswith('-'):
                    suffix = '-' + suffix
                return suffix

        return None

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
        # 提取扩展名
        ext = os.path.splitext(original_filename)[1]

        # 提取后缀
        suffix = self.get_suffix(original_filename, code)

        if suffix:
            # 有后缀，生成新文件名
            new_filename = f"{code}{suffix}{ext}"
            return new_filename
        else:
            # 没有后缀，使用原文件名
            return original_filename

    def get_target_path(self, code: str, original_filename: str) -> str:
        """
        生成目标路径

        格式：/dist/{番号}/{文件名}
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
