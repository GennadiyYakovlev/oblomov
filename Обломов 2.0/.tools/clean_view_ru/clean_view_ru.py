#!/usr/bin/env python3
"""Text quality analyzer for Obsidian notes.

Features:
1) Finds repeated lemmas (same root/normal form) and different word forms.
2) Finds repeated letter n-grams that appear close to each other.

Designed for Russian literary text checks similar to "Чистый взгляд" workflows.
"""

from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+", re.UNICODE)
RUS_LETTER_RE = re.compile(r"[А-Яа-яЁё]", re.UNICODE)
DEFAULT_REPORTS_DIR = Path(r"D:\Mee\obsidian\Обломов\_sys\__reports\clean")

# Minimal stoplist; can be extended via --stopwords-file
DEFAULT_STOPWORDS = {
    "и",
    "в",
    "во",
    "на",
    "с",
    "со",
    "к",
    "ко",
    "о",
    "об",
    "от",
    "до",
    "по",
    "за",
    "из",
    "у",
    "а",
    "но",
    "ли",
    "же",
    "бы",
    "что",
    "как",
    "это",
    "то",
    "не",
    "ни",
    "я",
    "ты",
    "он",
    "она",
    "мы",
    "вы",
    "они",
    "их",
    "его",
    "ее",
    "её",
    "мой",
    "твой",
    "наш",
    "ваш",
    "был",
    "была",
    "были",
    "быть",
}


@dataclass
class Token:
    raw: str
    lowered: str
    lemma: str
    idx: int
    char_start: int


@dataclass
class LemmaRepeat:
    lemma: str
    count: int
    forms: list[str]
    positions: list[int]
    token_idxs: list[int]


@dataclass
class NearNgram:
    ngram: str
    count: int
    hits: list[tuple[int, int]]
    mark_positions: list[int]


@dataclass
class SpanMark:
    start: int
    end: int
    tag: str
    title: str


def load_stopwords(path: Path | None) -> set[str]:
    stopwords = set(DEFAULT_STOPWORDS)
    if not path:
        return stopwords

    lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        word = line.strip().lower()
        if word and not word.startswith("#"):
            stopwords.add(word)
    return stopwords


def to_tokens(text: str, morph: object, stopwords: set[str]) -> list[Token]:
    tokens: list[Token] = []
    for idx, match in enumerate(WORD_RE.finditer(text)):
        raw = match.group(0)
        lowered = raw.lower()
        if lowered in stopwords:
            continue

        # For non-Russian words keep lower form as lemma.
        if RUS_LETTER_RE.search(lowered):
            lemma = morph.parse(lowered)[0].normal_form
        else:
            lemma = lowered

        tokens.append(
            Token(
                raw=raw,
                lowered=lowered,
                lemma=lemma,
                idx=len(tokens),
                char_start=match.start(),
            )
        )
    return tokens


def find_lemma_repeats(
    tokens: Iterable[Token],
    min_count: int,
    min_forms: int,
    window_chars: int,
) -> list[LemmaRepeat]:
    by_lemma: dict[str, list[Token]] = defaultdict(list)
    for token in tokens:
        by_lemma[token.lemma].append(token)

    repeats: list[LemmaRepeat] = []
    for lemma, lemma_tokens in by_lemma.items():
        if len(lemma_tokens) < 2:
            continue

        close_idxs: set[int] = set()
        left = 0
        for right in range(1, len(lemma_tokens)):
            while (
                lemma_tokens[right].char_start - lemma_tokens[left].char_start > window_chars
                and left < right
            ):
                left += 1
            for i in range(left, right):
                if lemma_tokens[right].char_start - lemma_tokens[i].char_start <= window_chars:
                    close_idxs.add(lemma_tokens[i].idx)
                    close_idxs.add(lemma_tokens[right].idx)

        if len(close_idxs) < min_count:
            continue

        close_tokens = [t for t in lemma_tokens if t.idx in close_idxs]
        if len(close_tokens) < min_count:
            continue

        forms_counter = Counter(token.lowered for token in close_tokens)
        forms = [f"{form} ({count})" for form, count in forms_counter.most_common()]
        if len(forms_counter) < min_forms:
            continue

        positions = [t.idx + 1 for t in close_tokens]
        repeats.append(
            LemmaRepeat(
                lemma=lemma,
                count=len(close_tokens),
                forms=forms,
                positions=positions,
                token_idxs=[t.idx for t in close_tokens],
            )
        )

    repeats.sort(key=lambda x: (-x.count, x.lemma))
    return repeats


def normalize_for_ngrams(text: str) -> str:
    lowered = text.lower().replace("ё", "е")
    # Keep string length identical to source so n-gram offsets match original text.
    return "".join(ch if ("а" <= ch <= "я" or "a" <= ch <= "z") else " " for ch in lowered)


def find_near_ngrams(
    text: str,
    ngram_len: int,
    window_chars: int,
    min_hits: int,
) -> list[NearNgram]:
    normalized = normalize_for_ngrams(text)
    positions_by_ngram: dict[str, list[int]] = defaultdict(list)

    for i in range(0, max(0, len(normalized) - ngram_len + 1)):
        ngram = normalized[i : i + ngram_len]
        if " " in ngram:
            continue
        if len(set(ngram)) == 1:
            continue
        positions_by_ngram[ngram].append(i)

    result: list[NearNgram] = []
    for ngram, positions in positions_by_ngram.items():
        if len(positions) < 2:
            continue

        near_pairs: list[tuple[int, int]] = []
        left = 0
        for right in range(1, len(positions)):
            while positions[right] - positions[left] > window_chars and left < right:
                left += 1
            for i in range(left, right):
                if positions[right] - positions[i] <= window_chars:
                    near_pairs.append((positions[i], positions[right]))

        if len(near_pairs) >= min_hits:
            mark_positions = sorted({p for pair in near_pairs for p in pair})
            result.append(
                NearNgram(
                    ngram=ngram,
                    count=len(near_pairs),
                    hits=near_pairs[:8],
                    mark_positions=mark_positions,
                )
            )

    result.sort(key=lambda x: (-x.count, x.ngram))
    return result


def find_close_lemma_clusters(
    lemma_repeats: list[LemmaRepeat],
    window_words: int,
    min_cluster_size: int,
) -> list[tuple[str, int, list[int]]]:
    clusters: list[tuple[str, int, list[int]]] = []
    for item in lemma_repeats:
        lemma = item.lemma
        positions = item.positions
        if len(positions) < min_cluster_size:
            continue

        best_chain: list[int] = []
        current: list[int] = [positions[0]]
        for p in positions[1:]:
            if p - current[-1] <= window_words:
                current.append(p)
            else:
                if len(current) > len(best_chain):
                    best_chain = current
                current = [p]

        if len(current) > len(best_chain):
            best_chain = current

        if len(best_chain) >= min_cluster_size:
            clusters.append((lemma, len(best_chain), best_chain))

    clusters.sort(key=lambda x: (-x[1], x[0]))
    return clusters


def render_report(
    source_path: Path,
    token_count: int,
    lemma_repeats: list[LemmaRepeat],
    clusters: list[tuple[str, int, list[int]]],
    ngrams: list[NearNgram],
    args: argparse.Namespace,
) -> str:
    lines: list[str] = []
    lines.append("# Отчёт: литературная чистка текста")
    lines.append("")
    lines.append(f"Источник: `{source_path.name}`")
    lines.append(f"Слов (без стоп-слов): **{token_count}**")
    lines.append(
        "Параметры: "
        f"min-lemma-count={args.min_lemma_count}, "
        f"min-lemma-forms={args.min_lemma_forms}, "
        f"window-words={args.window_words}, "
        f"ngram-len={args.ngram_len}, "
        f"ngram-window-chars={args.ngram_window_chars}"
    )
    lines.append("")

    lines.append("## 1) Однокоренные / словоформы")
    if not lemma_repeats:
        lines.append("- Повторов по леммам не найдено по текущим порогам.")
    else:
        for item in lemma_repeats[: args.limit]:
            pos_preview = ", ".join(map(str, item.positions[:10]))
            forms_preview = ", ".join(item.forms[:8])
            lines.append(
                f"- **{item.lemma}** — {item.count} | формы: {forms_preview} | позиции слов: {pos_preview}"
            )
    lines.append("")

    lines.append("## 2) Близкие повторы одной леммы")
    if not clusters:
        lines.append("- Кластеров близких повторов лемм не найдено.")
    else:
        for lemma, size, positions in clusters[: args.limit]:
            pos_preview = ", ".join(map(str, positions[:12]))
            lines.append(f"- **{lemma}** — цепочка {size} вхождений | позиции: {pos_preview}")
    lines.append("")

    lines.append("## 3) Повторяющиеся буквенные комбинации рядом")
    if not ngrams:
        lines.append("- Повторов n-грамм рядом не найдено.")
    else:
        for ngram in ngrams[: args.limit]:
            hit_preview = ", ".join(f"{a}->{b}" for a, b in ngram.hits)
            lines.append(
                f"- **{ngram.ngram}** — {ngram.count} близких пар (в окне) | примеры: {hit_preview}"
            )

    lines.append("")
    lines.append("---")
    lines.append("Скрипт: `obsidian_tools/clean_view_ru.py`")
    return "\n".join(lines)


def _palette(idx: int) -> str:
    colors = [
        "#ffe4b5",
        "#ffd1dc",
        "#d0f0c0",
        "#cfe8ff",
        "#f4d8ff",
        "#fff3b0",
        "#c9f2ff",
        "#fdd9b5",
    ]
    return colors[idx % len(colors)]


def _add_span(spans: list[SpanMark], start: int, end: int, tag: str, title: str) -> None:
    if start < end:
        spans.append(SpanMark(start=start, end=end, tag=tag, title=title))


def _choose_non_overlapping(spans: list[SpanMark]) -> list[SpanMark]:
    spans_sorted = sorted(spans, key=lambda s: (s.start, -(s.end - s.start)))
    selected: list[SpanMark] = []
    last_end = -1
    for span in spans_sorted:
        if span.start >= last_end:
            selected.append(span)
            last_end = span.end
    return selected


def build_annotated_copy(
    text: str,
    tokens: list[Token],
    lemma_repeats: list[LemmaRepeat],
    ngrams: list[NearNgram],
    args: argparse.Namespace,
) -> str:
    spans: list[SpanMark] = []

    tracked_lemma_items = lemma_repeats[: args.limit]
    tracked_lemmas = {item.lemma: i + 1 for i, item in enumerate(tracked_lemma_items)}
    token_map: dict[int, Token] = {token.idx: token for token in tokens}

    for item in tracked_lemma_items:
        lemma_group = tracked_lemmas[item.lemma]
        for token_idx in item.token_idxs:
            token = token_map.get(token_idx)
            if token is None:
                continue
            start = token.char_start
            end = start + len(token.raw)
            _add_span(spans, start, end, f"L{lemma_group}", f"Лемма-группа L{lemma_group}: {item.lemma}")

    folded_text = normalize_for_ngrams(text)
    for idx, ngram in enumerate(ngrams[: args.limit], start=1):
        for at in ngram.mark_positions:
            if folded_text[at : at + len(ngram.ngram)] != ngram.ngram:
                continue
            _add_span(
                spans,
                at,
                at + len(ngram.ngram),
                f"N{idx}",
                f"N-грамма N{idx}: {ngram.ngram}",
            )

    spans = _choose_non_overlapping(spans)

    lines: list[str] = []
    lines.append("# Аннотированная копия")
    lines.append("")
    lines.append("Легенда:")
    lines.append("- Группы лемм: `L1`, `L2`, ...")
    lines.append("- Группы n-грамм: `N1`, `N2`, ...")
    lines.append("")

    for lemma, group in tracked_lemmas.items():
        lines.append(
            f"- <span style=\"background:{_palette(group)};padding:0 2px;border-radius:3px;\"><b>L{group}</b></span> лемма: `{lemma}`"
        )
    for idx, ngram in enumerate(ngrams[: args.limit], start=1):
        lines.append(
            f"- <span style=\"background:{_palette(idx + 20)};padding:0 2px;border-radius:3px;\"><b>N{idx}</b></span> n-грамма: `{ngram.ngram}`"
        )
    lines.append("")
    lines.append("---")
    lines.append("")

    cursor = 0
    rendered: list[str] = []
    for span in spans:
        if cursor < span.start:
            rendered.append(text[cursor:span.start])

        group_number = int(span.tag[1:])
        if span.tag.startswith("L"):
            color = _palette(group_number)
        else:
            color = _palette(group_number + 20)

        marked = (
            f"<span style=\"background:{color};padding:0 2px;border-radius:3px;\" "
            f"title=\"{span.title}\"><b>{span.tag}</b>:{text[span.start:span.end]}</span>"
        )
        rendered.append(marked)
        cursor = span.end

    if cursor < len(text):
        rendered.append(text[cursor:])

    lines.append("".join(rendered))
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Анализатор повторов для литературной чистки текста в Obsidian"
    )
    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        help="Путь к исходному .md/.txt файлу (не нужен, если указан --folder)",
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
        help=(
            "Путь отчёта .md "
            f"(по умолчанию в {DEFAULT_REPORTS_DIR}; нельзя с --folder)"
        ),
    )
    parser.add_argument("--stopwords-file", type=Path, default=None)
    parser.add_argument("--min-lemma-count", type=int, default=2)
    parser.add_argument("--min-lemma-forms", type=int, default=2)
    parser.add_argument("--window-words", type=int, default=35)
    parser.add_argument("--min-cluster-size", type=int, default=3)
    parser.add_argument("--ngram-len", type=int, default=4)
    parser.add_argument("--ngram-window-chars", type=int, default=110)
    parser.add_argument("--min-ngram-hits", type=int, default=2)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument(
        "--mode",
        choices=["report", "annotated", "both"],
        default="annotated",
        help="Режим вывода: отчёт, аннотированная копия, или оба файла",
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

    try:
        import pymorphy3
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Missing dependency: pymorphy3. Install with: pip install pymorphy3"
        ) from exc

    morph = pymorphy3.MorphAnalyzer()
    stopwords = load_stopwords(args.stopwords_file)

    for source_path in files:
        if not source_path.exists():
            print(f"Skip: file not found {source_path}")
            continue

        text = source_path.read_text(encoding="utf-8")

        tokens = to_tokens(text=text, morph=morph, stopwords=stopwords)
        lemma_repeats = find_lemma_repeats(
            tokens=tokens,
            min_count=args.min_lemma_count,
            min_forms=args.min_lemma_forms,
            window_chars=args.ngram_window_chars,
        )
        clusters = find_close_lemma_clusters(
            lemma_repeats=lemma_repeats,
            window_words=args.window_words,
            min_cluster_size=args.min_cluster_size,
        )
        ngrams = find_near_ngrams(
            text=text,
            ngram_len=args.ngram_len,
            window_chars=args.ngram_window_chars,
            min_hits=args.min_ngram_hits,
        )

        created_files: list[Path] = []

        if args.mode in {"report", "both"}:
            report_output = args.output
            if report_output is None:
                report_output = DEFAULT_REPORTS_DIR / f"{source_path.stem}.clean-view-report.md"

            report_output.parent.mkdir(parents=True, exist_ok=True)

            report = render_report(
                source_path=source_path,
                token_count=len(tokens),
                lemma_repeats=lemma_repeats,
                clusters=clusters,
                ngrams=ngrams,
                args=args,
            )
            report_output.write_text(report, encoding="utf-8")
            created_files.append(report_output)

        if args.mode in {"annotated", "both"}:
            annotated_output = (
                DEFAULT_REPORTS_DIR / f"{source_path.stem}.clean-view-annotated.md"
            )
            annotated_output.parent.mkdir(parents=True, exist_ok=True)
            annotated = build_annotated_copy(
                text=text,
                tokens=tokens,
                lemma_repeats=lemma_repeats,
                ngrams=ngrams,
                args=args,
            )
            annotated_output.write_text(annotated, encoding="utf-8")
            created_files.append(annotated_output)

        for path in created_files:
            print(f"Created: {path}")


if __name__ == "__main__":
    main()
