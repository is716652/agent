#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP-compatible Python wrapper for build_word.exe
- Accepts either file paths or inline contents
- Spawns the bundled EXE and returns structured JSON to stdout
- No third-party dependencies (stdlib only)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple


def _detect_exe_path(explicit: Optional[str] = None) -> Path:
     if explicit:
         p = Path(explicit)
         if p.is_file():
             return p
         raise FileNotFoundError(f"Specified exe not found: {explicit}")

     candidates: List[Path] = []
     # When running as a frozen wrapper
     if getattr(sys, 'frozen', False):
         exec_dir = Path(sys.executable).parent
         meipass = Path(getattr(sys, '_MEIPASS', exec_dir))
         # Prefer neighbor build_word.exe next to wrapper
         candidates += [
             exec_dir / 'build_word.exe',
             exec_dir / 'dist' / 'build_word.exe',
             # Fallback to extracted temp dir
             meipass / 'build_word.exe',
             meipass / 'dist' / 'build_word.exe',
         ]
     # When running as a script
     script_dir = Path(__file__).resolve().parent
     candidates += [
         script_dir / 'dist' / 'build_word.exe',
         script_dir / 'build_word.exe',
         script_dir.parent / 'IndependentRunningPackage' / 'dist' / 'build_word.exe',
     ]

     for c in candidates:
         if c.is_file():
             return c
     raise FileNotFoundError("build_word.exe not found. Tried: " + ", ".join(str(c) for c in candidates))


def _create_temp_file(dir_path: Path, filename: str, content: str) -> Path:
    p = dir_path / filename
    # Ensure parent exists
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('w', encoding='utf-8') as f:
        f.write(content)
    return p


def _build_exe_args(
    exe_path: Path,
    md_path: Optional[Path],
    json_data_path: Optional[Path],
    syllabus_path: Optional[Path],
    head_tpl_path: Optional[Path],
    week_tpl_path: Optional[Path],
    output_dir: Optional[Path],
    font_name: Optional[str],
    font_size: Optional[str],
    subject: Optional[str],
) -> List[str]:
    args = [str(exe_path)]
    if md_path:
        args += ['--md', str(md_path)]
    if json_data_path:
        args += ['--json-data', str(json_data_path)]
    if syllabus_path:
        args += ['--syllabus', str(syllabus_path)]
    if head_tpl_path:
        args += ['--head-tpl', str(head_tpl_path)]
    if week_tpl_path:
        args += ['--week-tpl', str(week_tpl_path)]
    if output_dir:
        args += ['--output-dir', str(output_dir)]
    if font_name:
        args += ['--font-name', font_name]
    if font_size:
        args += ['--font-size', font_size]
    if subject:
        args += ['--subject', subject]
    # Ensure JSON output for machine consumption
    args += ['--stdout-json']
    return args


def _parse_last_json_line(stdout_text: str) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    parsed: Optional[Dict[str, Any]] = None
    errors: List[str] = []
    for line in stdout_text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith('{') and s.endswith('}'):  # quick filter
            try:
                parsed = json.loads(s)
            except json.JSONDecodeError as e:
                errors.append(f"json decode failed: {e}: line={s[:200]}...")
    return parsed, errors

# Add a robust decoder for bytes -> str
_def_fallback_encs = ('utf-8', 'utf-8-sig', 'gbk', 'cp936', 'mbcs')

def _decode_bytes(data: bytes) -> str:
    if data is None:
        return ''
    # Try preferred encodings
    for enc in _def_fallback_encs + (sys.getfilesystemencoding() or 'utf-8',):
        try:
            return data.decode(enc)  # strict
        except Exception:
            continue
    # Final fallback: ignore errors in utf-8
    return data.decode('utf-8', errors='ignore')


def run_wrapper(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='MCP wrapper for build_word.exe')
    parser.add_argument('--exe-path', help='Path to build_word.exe (optional, auto-detect by default)')

    # Path mode (same as EXE)
    parser.add_argument('--md', dest='md_path', help='Path to MD file (教案模板标记值-*.md)')
    parser.add_argument('--json-data', dest='json_data_path', help='Path to JSON data file (*-data.json)')
    parser.add_argument('--syllabus', dest='syllabus_path', help='Path to syllabus markdown (optional)')
    parser.add_argument('--head-tpl', dest='head_tpl_path', help='Path to 教案-模板.docx')
    parser.add_argument('--week-tpl', dest='week_tpl_path', help='Path to 课程教学教案-模板.docx')
    parser.add_argument('--output-dir', dest='output_dir', help='Output directory')
    parser.add_argument('--font-name', dest='font_name', help='Override font name')
    parser.add_argument('--font-size', dest='font_size', help='Override font size')
    parser.add_argument('--subject', dest='subject', help='Override subject')

    # Content mode (inline payloads). If provided, will be written to temp files and passed via paths.
    parser.add_argument('--md-content', dest='md_content', help='Inline content for MD (alternative to --md)')
    parser.add_argument('--json-data-content', dest='json_data_content', help='Inline JSON content (alternative to --json-data)')
    parser.add_argument('--syllabus-content', dest='syllabus_content', help='Inline syllabus markdown (alternative to --syllabus)')

    parser.add_argument('--timeout', type=int, default=600, help='Timeout seconds (default: 600)')
    parser.add_argument('--verbose', action='store_true', help='Verbose logging to stderr')

    args = parser.parse_args(argv)

    t0 = time.time()
    tmp_dir: Optional[tempfile.TemporaryDirectory] = None
    created_files: List[Path] = []

    try:
        exe_path = _detect_exe_path(args.exe_path)
        if args.verbose:
            print(f"[wrapper] using exe: {exe_path}", file=sys.stderr)

        # Resolve content-mode inputs
        if args.md_content and not args.md_path:
            if tmp_dir is None:
                tmp_dir = tempfile.TemporaryDirectory(prefix='mcp_wrapper_')
            base = Path(tmp_dir.name)
            p = _create_temp_file(base, '教案模板标记值-临时.md', args.md_content)
            created_files.append(p)
            args.md_path = str(p)

        if args.json_data_content and not args.json_data_path:
            if tmp_dir is None:
                tmp_dir = tempfile.TemporaryDirectory(prefix='mcp_wrapper_')
            base = Path(tmp_dir.name)
            p = _create_temp_file(base, '临时-data.json', args.json_data_content)
            created_files.append(p)
            args.json_data_path = str(p)

        if args.syllabus_content and not args.syllabus_path:
            if tmp_dir is None:
                tmp_dir = tempfile.TemporaryDirectory(prefix='mcp_wrapper_')
            base = Path(tmp_dir.name)
            p = _create_temp_file(base, '教学大纲-临时.md', args.syllabus_content)
            created_files.append(p)
            args.syllabus_path = str(p)

        # Normalize paths
        md_path = Path(args.md_path).resolve() if args.md_path else None
        json_data_path = Path(args.json_data_path).resolve() if args.json_data_path else None
        syllabus_path = Path(args.syllabus_path).resolve() if args.syllabus_path else None
        head_tpl_path = Path(args.head_tpl_path).resolve() if args.head_tpl_path else None
        week_tpl_path = Path(args.week_tpl_path).resolve() if args.week_tpl_path else None
        output_dir = Path(args.output_dir).resolve() if args.output_dir else None

        exe_argv = _build_exe_args(
            exe_path=exe_path,
            md_path=md_path,
            json_data_path=json_data_path,
            syllabus_path=syllabus_path,
            head_tpl_path=head_tpl_path,
            week_tpl_path=week_tpl_path,
            output_dir=output_dir,
            font_name=args.font_name,
            font_size=args.font_size,
            subject=args.subject,
        )

        if args.verbose:
            print(f"[wrapper] running: {exe_argv}", file=sys.stderr)

        cp = subprocess.run(
            exe_argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=args.timeout,
            check=False,
        )

        stdout_text = _decode_bytes(cp.stdout)
        stderr_text = _decode_bytes(cp.stderr)

        if args.verbose:
            print(f"[wrapper] stdout(bytes={len(cp.stdout or b'')}) preview: {stdout_text[-200:]}" , file=sys.stderr)
            if stderr_text:
                print(f"[wrapper] stderr(bytes={len(cp.stderr or b'')}) preview: {stderr_text[-200:]}" , file=sys.stderr)

        parsed, json_errors = _parse_last_json_line(stdout_text)
        elapsed_ms = int((time.time() - t0) * 1000)

        if parsed is None:
            result: Dict[str, Any] = {
                'ok': False,
                'error': 'NO_JSON_FROM_EXE',
                'message': 'Failed to parse JSON from exe stdout',
                'stdout_tail': stdout_text[-1000:],
                'stderr_tail': stderr_text[-1000:],
                'returncode': cp.returncode,
                'json_errors': json_errors,
                'elapsed_ms': elapsed_ms,
                'wrapper_version': '1.0.0',
            }
            print(json.dumps(result, ensure_ascii=False), flush=True)
            return 1

        # Attach wrapper metadata
        parsed['wrapper_version'] = '1.0.0'
        parsed['elapsed_ms'] = elapsed_ms
        parsed['returncode'] = cp.returncode
        if cp.returncode != 0 and parsed.get('ok', True):
            parsed['ok'] = False
            parsed['message'] = parsed.get('message') or f"exe returned non-zero: {cp.returncode}"

        print(json.dumps(parsed, ensure_ascii=False), flush=True)
        return 0 if parsed.get('ok') else 2

    except subprocess.TimeoutExpired:
        result = {
            'ok': False,
            'error': 'TIMEOUT',
            'message': f'timeout after {args.timeout}s',
        }
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 3
    except FileNotFoundError as e:
        result = {
            'ok': False,
            'error': 'NOT_FOUND',
            'message': str(e),
        }
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 4
    except Exception as e:
        result = {
            'ok': False,
            'error': 'WRAPPER_EXCEPTION',
            'message': f'{type(e).__name__}: {e}',
        }
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 5
    finally:
        # Cleanup temp files
        try:
            if tmp_dir is not None:
                tmp_dir.cleanup()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(run_wrapper())