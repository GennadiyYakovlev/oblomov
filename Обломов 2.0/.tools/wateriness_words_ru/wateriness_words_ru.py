#!/usr/bin/env python3
"""Wateriness words marker for Russian texts.

Marks stopwords that are counted in the Wateriness index (from text_analytics).
Produces an annotated copy of the source text and a short report.
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: pyyaml. Install with: pip install pyyaml"
    ) from exc

WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+", re.UNICODE)
DEFAULT_REPORTS_DIR = Path(r"D:\Mee\obsidian\Обломов\_sys\__reports\wateriness")
DEFAULT_CONFIG = (
    Path(__file__).resolve().parent.parent / "text_analytics" / "config.yaml"
)
DEFAULT_TOXIC_WORDS_FILE = Path(
    r"D:\Mee\obsidian\Обломов\_sys\Мусорные конструкции.md"
)
COLOR_WATERINESS = "#fff3b0"
COLOR_TOXIC = "#ff9aa2"


@dataclass
class Token:
    raw: str
    lowered: str
    char_start: int
    char_end: int


@dataclass
class WateryWord:
    word: str
    count: int


def load_stopwords(path: Path) -> set[str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    words = data.get("stopwords", []) if isinstance(data, dict) else []
    return {
        word.lower().replace("ё", "е")
        for word in words
        if isinstance(word, str)
    }


def load_word_list(path: Path | None, base: set[str]) -> set[str]:
    if not path:
        return base
    lines = path.read_text(encoding="utf-8").splitlines()
    words = {
        line.strip().lower().replace("ё", "е")
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    }
    return base | words


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    for match in WORD_RE.finditer(text):
        raw = match.group(0)
        lowered = raw.lower().replace("ё", "е")
        tokens.append(
            Token(
                raw=raw,
                lowered=lowered,
                char_start=match.start(),
                char_end=match.end(),
            )
        )
    return tokens


def find_watery_tokens(tokens: Iterable[Token], stopwords: set[str]) -> list[Token]:
    return [t for t in tokens if t.lowered in stopwords]


def classify_tokens(tokens: list[Token], stopwords: set[str], toxic: set[str]) -> list[tuple[Token, str]]:
    """Return (token, category) pairs for tokens that should be marked."""
    result: list[tuple[Token, str]] = []
    for token in tokens:
        if token.lowered in toxic:
            result.append((token, "toxic"))
        elif token.lowered in stopwords:
            result.append((token, "wateriness"))
    return result


def build_report(
    source_path: Path,
    tokens: list[Token],
    classified: list[tuple[Token, str]],
    stopwords: set[str],
    toxic: set[str],
    args: argparse.Namespace,
) -> str:
    total = len(tokens)
    watery_count = len(classified)
    toxic_count = sum(1 for _, category in classified if category == "toxic")
    wateriness = round(watery_count * 100 / total, 1) if total else 0.0
    toxic_ratio = round(toxic_count * 100 / total, 1) if total else 0.0

    freq_watery = Counter(t.lowered for t, category in classified if category == "wateriness")
    freq_toxic = Counter(t.lowered for t, category in classified if category == "toxic")
    top_watery = freq_watery.most_common(args.limit)
    top_toxic = freq_toxic.most_common(args.limit)

    lines = [
        "# Отчёт: водянистые слова (Wateriness)",
        "",
        f"Источник: `{source_path.name}`",
        f"Всего слов: **{total}**",
        f"Водянистых слов: **{watery_count}** ({wateriness}%)",
        f"Особо вредных слов: **{toxic_count}** ({toxic_ratio}%)",
        f"Источник wateriness: `{args.config}`",
        f"Источник вредных слов: `{args.toxic_words_file}`",
        "",
        "## Частоты водянистых слов",
    ]
    if not top_watery:
        lines.append("- Водянистых слов не найдено.")
    else:
        for word, count in top_watery:
            lines.append(f"- `{word}`: {count}")

    lines.extend(["", "## Частоты особо вредных слов"])
    if not top_toxic:
        lines.append("- Особо вредных слов не найдено.")
    else:
        for word, count in top_toxic:
            lines.append(f"- `{word}`: {count}")

    lines.extend(
        [
            "",
            "---",
            "Скрипт: `.tools/wateriness_words_ru/wateriness_words_ru.py`",
        ]
    )
    return "\n".join(lines)


def build_annotated_copy(text: str, classified: list[tuple[Token, str]]) -> str:
    spans = sorted(
        {
            (token.char_start, token.char_end, token.raw, category)
            for token, category in classified
        },
        key=lambda x: x[0],
    )

    lines = [
        "# Аннотированная копия: водянистые слова",
        "",
        "Легенда:",
        '- <span style="background:#fff3b0;padding:0 2px;border-radius:3px;">жёлтое</span> — '
        "слово, учитываемое в индексе Wateriness",
        '- <span style="background:#ff9aa2;padding:0 2px;border-radius:3px;">красное</span> — '
        "особо вредное слово из списка «Мусорные конструкции»",
        "",
        "---",
        "",
    ]

    cursor = 0
    rendered: list[str] = []
    colors = {"wateriness": COLOR_WATERINESS, "toxic": COLOR_TOXIC}
    titles = {
        "wateriness": "водянистое слово",
        "toxic": "особо вредное слово",
    }
    for start, end, raw, category in spans:
        if start < cursor:
            # overlapping spans should not happen for separate words, but skip stale ones
            continue
        if cursor < start:
            rendered.append(text[cursor:start])
        color = colors[category]
        title = titles[category]
        marked = (
            f'<span style="background:{color};padding:0 2px;border-radius:3px;" '
            f'title="{title}">{raw}</span>'
        )
        rendered.append(marked)
        cursor = end
    if cursor < len(text):
        rendered.append(text[cursor:])

    lines.append("".join(rendered))
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Маркировка водянистых слов в русском тексте (Wateriness)"
    )
    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        help="Путь к исходному .md/.txt файлу",
    )
    parser.add_argument(
        "--folder",
        type=Path,
        default=None,
        help="Путь к папке для пакетной обработки всех .md файлов",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Путь отчёта .md (нельзя с --folder)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Путь к config.yaml с полем stopwords",
    )
    parser.add_argument(
        "--stopwords-file",
        type=Path,
        default=None,
        help="Дополнительный список стоп-слов (одно слово на строку)",
    )
    parser.add_argument(
        "--toxic-words-file",
        type=Path,
        default=DEFAULT_TOXIC_WORDS_FILE,
        help="Список особо вредных слов (одно слово на строку)",
    )
    parser.add_argument(
        "--mode",
        choices=["report", "annotated", "both"],
        default="annotated",
        help="Режим вывода: отчёт, аннотированная копия, или оба файла",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Максимум частотных слов в отчёте",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.folder and args.output:
        raise SystemExit("--output нельзя использовать вместе с --folder")

    if args.folder:
        if not args.folder.is_dir():
            raise SystemExit(f"Folder not found: {args.folder}")
        files = sorted(args.folder.glob("*.md"))
        if not files:
            raise SystemExit(f"No .md files found in: {args.folder}")
    else:
        if not args.input:
            parser.print_help()
            raise SystemExit("\nУкажите input-файл или --folder")
        files = [args.input]

    stopwords = load_stopwords(args.config)
    stopwords = load_word_list(args.stopwords_file, stopwords)
    toxic = load_word_list(args.toxic_words_file, set())
    # Ensure toxic words are also counted as wateriness if they are in the stopword list.
    # They will be rendered with the more severe toxic color in the annotated copy.

    for source_path in files:
        if not source_path.exists():
            print(f"Skip: file not found {source_path}")
            continue

        text = source_path.read_text(encoding="utf-8")
        tokens = tokenize(text)
        classified = classify_tokens(tokens, stopwords, toxic)

        created_files: list[Path] = []

        if args.mode in {"report", "both"}:
            report_output = args.output
            if report_output is None:
                report_output = (
                    DEFAULT_REPORTS_DIR / f"{source_path.stem}.wateriness-report.md"
                )
            report_output.parent.mkdir(parents=True, exist_ok=True)
            report = build_report(source_path, tokens, classified, stopwords, toxic, args)
            report_output.write_text(report, encoding="utf-8")
            created_files.append(report_output)

        if args.mode in {"annotated", "both"}:
            annotated_output = (
                DEFAULT_REPORTS_DIR / f"{source_path.stem}.wateriness-annotated.md"
            )
            annotated_output.parent.mkdir(parents=True, exist_ok=True)
            annotated = build_annotated_copy(text, classified)
            annotated_output.write_text(annotated, encoding="utf-8")
            created_files.append(annotated_output)

        for path in created_files:
            print(f"Created: {path}")


if __name__ == "__main__":
    main()
