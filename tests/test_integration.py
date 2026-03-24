#!/usr/bin/env python3
"""
测试 noctra 的番号识别和整理逻辑
"""

import os
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent

# 直接运行 scanner 和 organizer 文件
exec(open(project_root / 'app' / 'scanner.py').read())
exec(open(project_root / 'app' / 'organizer.py').read())


def test_scanner():
    """测试番号识别"""
    print("\n=== 测试番号识别 ===\n")

    scanner_instance = JAVScanner('/tmp/source', '/tmp/dist')

    test_cases = [
        ('SSIS-123.mp4', 'SSIS-123'),
        ('ABP-456-C.mp4', 'ABP-456'),
        ('MVSD-662-C.mp4', 'MVSD-662'),
        ('FPRE-123C.mp4', 'FPRE-123'),
        ('FC2-PPV-1234567.mp4', 'FC2-PPV-1234567'),
        ('ABC-123_字幕版.mp4', 'ABC-123'),
        ('ABC-123 [Uncensored].mp4', 'ABC-123'),
        ('SSIS-123字幕版.mp4', 'SSIS-123'),
        ('unknown_file.mp4', None),
        ('123-456.mp4', None),  # 纯数字开头不支持
    ]

    passed = 0
    failed = 0

    for filename, expected in test_cases:
        result = scanner_instance.identify_code(filename)
        if result == expected:
            print(f"✓ {filename:40} -> {result or 'None':20}")
            passed += 1
        else:
            print(f"✗ {filename:40} -> {result or 'None':20} (期望: {expected})")
            failed += 1

    print(f"\n结果: {passed}/{passed+failed} 通过\n")
    return failed == 0


def test_organizer():
    """测试文件名生成"""
    print("\n=== 测试文件名生成 ===\n")

    organizer_instance = JAVOrganizer('/tmp/dist')

    test_cases = [
        # (番号, 原文件名, 期望文件名)
        ('FPRE-123', 'FPRE-123C.mp4', 'FPRE-123-C.mp4'),
        ('ABP-456', 'ABP-456-C.mp4', 'ABP-456-C.mp4'),
        ('MVSD-662', 'MVSD-662-UC.mkv', 'MVSD-662-UC.mkv'),
        ('SSIS-123', 'SSIS-123.mp4', 'SSIS-123.mp4'),  # 无后缀，不变
    ]

    passed = 0
    failed = 0

    for code, original_filename, expected_filename in test_cases:
        result_filename = organizer_instance.generate_filename(code, original_filename)
        if result_filename == expected_filename:
            print(f"✓ {code:15} + {original_filename:25} -> {result_filename}")
            passed += 1
        else:
            print(f"✗ {code:15} + {original_filename:25} -> {result_filename} (期望: {expected_filename})")
            failed += 1

    print(f"\n结果: {passed}/{passed+failed} 通过\n")
    return failed == 0


if __name__ == '__main__':
    scanner_ok = test_scanner()
    organizer_ok = test_organizer()

    print("\n=== 总体结果 ===")
    if scanner_ok and organizer_ok:
        print("✓ 所有测试通过")
        sys.exit(0)
    else:
        print("✗ 部分测试失败")
        sys.exit(1)
