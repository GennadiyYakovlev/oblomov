#!/usr/bin/env python3
"""checkStyle runner for Russian manuscript notes.

Runs both clean_view_ru and wateriness_words_ru on a single file or a folder
of .md files with one command.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent
CLEAN_VIEW = TOOLS_DIR / "clean_view_ru" / "clean_view_ru.py"
WATERINESS = TOOLS_DIR / "wateriness_words_ru" / "wateriness_words_ru.py"


def run_script(script: Path, target: Path, folder_mode: bool) -> int:
    cmd = [sys.executable, str(script)]
    if folder_mode:
        cmd.extend(["--folder", str(target)])
    else:
        cmd.append(str(target))
    print(f"\n>>> Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    return result.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Запускает clean_view_ru и wateriness_words_ru одной командой"
    )
    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        help="Путь к исходному .md файлу или папке",
    )
    parser.add_argument(
        "--folder",
        action="store_true",
        help="Обрабатывать input как папку со всеми .md файлами",
    )
    parser.add_argument(
        "--clean-view-only",
        action="store_true",
        help="Запустить только clean_view_ru",
    )
    parser.add_argument(
        "--wateriness-only",
        action="store_true",
        help="Запустить только wateriness_words_ru",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.input:
        parser.print_help()
        raise SystemExit("\nУкажите input-файл или папку")

    if args.clean_view_only and args.wateriness_only:
        raise SystemExit("Нельзя одновременно указывать --clean-view-only и --wateriness-only")

    target = args.input
    folder_mode = args.folder

    if folder_mode and not target.is_dir():
        raise SystemExit(f"Folder not found: {target}")
    if not folder_mode and not target.is_file():
        raise SystemExit(f"File not found: {target}")

    exit_codes: list[int] = []

    if not args.wateriness_only:
        exit_codes.append(run_script(CLEAN_VIEW, target, folder_mode))

    if not args.clean_view_only:
        exit_codes.append(run_script(WATERINESS, target, folder_mode))

    if any(code != 0 for code in exit_codes):
        raise SystemExit(max(exit_codes))


if __name__ == "__main__":
    main()
