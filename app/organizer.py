import os
import shutil
from pathlib import Path
from typing import Optional
from datetime import datetime


class JAVOrganizer:
    def __init__(self, dist_dir: str):
        self.dist_dir = Path(dist_dir).resolve()

    def get_target_path(self, code: str, original_filename: str) -> str:
        """
        生成目标路径

        格式：/dist/{番号}/{原文件名}
        例：/dist/SSIS-123/SSIS-123.mp4
        """
        target_dir = self.dist_dir / code
        target_path = target_dir / original_filename
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
