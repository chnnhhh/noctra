import os
import re
from collections import defaultdict
from functools import cmp_to_key
from pathlib import Path
from typing import Any, MutableMapping, Optional

SELECTABLE_SCAN_STATUSES = ('pending', 'duplicate')

CODE_PATTERN = re.compile(r'([A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*-\d+)', re.IGNORECASE)
SUBTITLE_MARKER_PATTERN = re.compile(r'字幕版|字幕')
UNCENSORED_MARKER_PATTERN = re.compile(r'uncensored', re.IGNORECASE)
SUFFIX_PREFIX_PATTERN = re.compile(r'^[\s._@-]*(?P<marker>UC|CH|C)(?=$|[^A-Za-z0-9])', re.IGNORECASE)
NATURAL_TOKEN_PATTERN = re.compile(r'(\d+)')

SUFFIX_PRIORITY = {
    'UC': 0,
    'C': 1,
    'SUB': 2,
    'PLAIN': 3,
}


def resolve_scan_status(identified_code: Optional[str], target_path: Optional[str]) -> str:
    """根据当前扫描结果判断单文件基础状态。"""
    if not identified_code:
        return 'skipped'

    if target_path and Path(target_path).exists():
        return 'target_exists'

    return 'pending'


def classify_suffix_category(filename: str) -> str:
    """将候选文件归一化到 UC / C / SUB / PLAIN 四类。"""
    name_without_ext = os.path.splitext(filename)[0]
    code_match = CODE_PATTERN.search(name_without_ext)
    if not code_match:
        return 'PLAIN'

    tail = name_without_ext[code_match.end():]
    suffix_match = SUFFIX_PREFIX_PATTERN.match(tail)
    if suffix_match:
        marker = suffix_match.group('marker').upper()
        return 'UC' if marker == 'UC' else 'C'

    stripped_tail = tail.lstrip(' ._@-')
    if stripped_tail.startswith('字幕版') or stripped_tail.startswith('字幕'):
        return 'SUB'
    if UNCENSORED_MARKER_PATTERN.search(stripped_tail):
        return 'UC'

    if SUBTITLE_MARKER_PATTERN.search(name_without_ext):
        return 'SUB'
    if UNCENSORED_MARKER_PATTERN.search(name_without_ext):
        return 'UC'

    return 'PLAIN'


def compare_candidate_priority(left: MutableMapping[str, Any], right: MutableMapping[str, Any]) -> int:
    """比较同一标准番号下两个候选文件的优先级。"""
    left_suffix = classify_suffix_category(_candidate_filename(left))
    right_suffix = classify_suffix_category(_candidate_filename(right))

    suffix_diff = SUFFIX_PRIORITY[left_suffix] - SUFFIX_PRIORITY[right_suffix]
    if suffix_diff != 0:
        return suffix_diff

    left_size = _candidate_size(left)
    right_size = _candidate_size(right)
    if left_size != right_size:
        return -1 if left_size > right_size else 1

    filename_diff = _compare_natural(_candidate_filename(left), _candidate_filename(right))
    if filename_diff != 0:
        return filename_diff

    return _compare_natural(_candidate_original_path(left), _candidate_original_path(right))


def assign_batch_duplicate_statuses(
    scan_results: list[MutableMapping[str, Any]]
) -> list[MutableMapping[str, Any]]:
    """对本批扫描结果补全 pending / duplicate 状态。"""
    grouped_candidates: dict[str, list[MutableMapping[str, Any]]] = defaultdict(list)

    for result in scan_results:
        identified_code = result.get('identified_code')
        if identified_code and result.get('status') == 'pending':
            grouped_candidates[str(identified_code).upper()].append(result)

    for candidates in grouped_candidates.values():
        if len(candidates) <= 1:
            continue

        sorted_candidates = sorted(candidates, key=cmp_to_key(compare_candidate_priority))
        sorted_candidates[0]['status'] = 'pending'

        for candidate in sorted_candidates[1:]:
            candidate['status'] = 'duplicate'

    return scan_results


def _candidate_filename(candidate: MutableMapping[str, Any]) -> str:
    filename = candidate.get('filename')
    if filename:
        return str(filename)

    original_path = candidate.get('original_path') or candidate.get('path')
    if original_path:
        return Path(str(original_path)).name

    return ''


def _candidate_original_path(candidate: MutableMapping[str, Any]) -> str:
    return str(candidate.get('original_path') or candidate.get('path') or '')


def _candidate_size(candidate: MutableMapping[str, Any]) -> int:
    size = candidate.get('file_size')
    if size is None:
        size = candidate.get('size')
    return int(size or 0)


def _natural_sort_key(value: str) -> tuple[tuple[int, Any], ...]:
    parts = NATURAL_TOKEN_PATTERN.split(value or '')
    key: list[tuple[int, Any]] = []

    for part in parts:
        if not part:
            continue
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part.lower()))

    return tuple(key)


def _compare_natural(left: str, right: str) -> int:
    left_key = _natural_sort_key(left)
    right_key = _natural_sort_key(right)

    if left_key < right_key:
        return -1
    if left_key > right_key:
        return 1
    return 0
