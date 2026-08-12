#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError as exc:
    raise SystemExit("Missing dependency: pyyaml. Install with: pip install pyyaml") from exc

WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+", re.UNICODE)
SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")


@dataclass
class FileMetrics:
    path: str
    chapter: str
    words: int
    symbols: int
    unique_words: int
    stopwords_words: int
    max_word_repeats: int
    sentences: int
    paragraphs: int
    avg_word_len: float
    avg_sentence_len_words: float
    avg_paragraph_len_words: float
    dialogue_lines: int
    lines: int
    dialogue_share_percent: float
    top_words: list[tuple[str, int]]


def load_config(config_path: Path) -> dict:
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def chapter_number_from_name(name: str) -> str:
    m = re.match(r"^(\d{2})_", name)
    return m.group(1) if m else "00"


def tokenize(text: str) -> list[str]:
    return [w.lower().replace("ё", "е") for w in WORD_RE.findall(text)]


def count_sentences(text: str) -> int:
    return len([s for s in SENTENCE_SPLIT_RE.split(text) if s.strip()])


def safe_div(a: float, b: float) -> float:
    return round(a / b, 1) if b else 0.0


def analyze_file(file_path: Path, chapter: str, cfg: dict) -> FileMetrics:
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    words_all = tokenize(text)
    words = [w for w in words_all if len(w) >= cfg["text"]["min_word_length_for_top"]]
    stopwords = set(cfg.get("stopwords", []))
    filtered = [w for w in words if w not in stopwords]
    stopwords_words = len([w for w in words_all if w in stopwords])
    freq_source = filtered if filtered else words_all
    max_word_repeats = Counter(freq_source).most_common(1)[0][1] if freq_source else 0
    top_words = Counter(filtered).most_common(cfg["text"]["top_words_limit"])

    dialogue_prefix = cfg["text"]["dialogue_prefix"]
    dialogue_lines = sum(1 for line in lines if line.lstrip().startswith(dialogue_prefix))

    sentence_count = count_sentences(text)
    words_count = len(words_all)

    rel_path = str(file_path.relative_to(Path.cwd())).replace("\\", "/")

    return FileMetrics(
        path=rel_path,
        chapter=chapter,
        words=words_count,
        symbols=len(text),
        unique_words=len(set(words_all)),
        stopwords_words=stopwords_words,
        max_word_repeats=max_word_repeats,
        sentences=sentence_count,
        paragraphs=len(paragraphs),
        avg_word_len=safe_div(sum(len(w) for w in words_all), words_count),
        avg_sentence_len_words=safe_div(words_count, sentence_count),
        avg_paragraph_len_words=safe_div(words_count, len(paragraphs)),
        dialogue_lines=dialogue_lines,
        lines=len(lines),
        dialogue_share_percent=safe_div(dialogue_lines * 100, len(lines)),
        top_words=top_words,
    )


def md_report_file_metrics(m: FileMetrics) -> str:
    top_lines = "\n".join(f"- `{w}`: {c}" for w, c in m.top_words[:15]) or "- n/a"
    return (
        f"# {Path(m.path).name}\n\n"
        f"- File: `{m.path}`\n"
        f"- Chapter: `{m.chapter}`\n"
        f"- Words: **{m.words}**\n"
        f"- Sentences: **{m.sentences}**\n"
        f"- Paragraphs: **{m.paragraphs}**\n"
        f"- Unique words: **{m.unique_words}**\n"
        f"- Avg word length: **{m.avg_word_len}**\n"
        f"- Avg sentence length (words): **{m.avg_sentence_len_words}**\n"
        f"- Dialogue lines: **{m.dialogue_lines}/{m.lines}** ({m.dialogue_share_percent}%)\n\n"
        f"## Top words\n{top_lines}\n"
    )


def collect_target_files(project_root: Path, cfg: dict, mode: str, chapter: str | None) -> list[Path]:
    chapter_dirs = []
    for d in project_root.iterdir():
        if d.is_dir() and re.match(r"^\d{2}_", d.name):
            chapter_dirs.append(d)

    if chapter:
        chapter_dirs = [d for d in chapter_dirs if d.name.startswith(f"{chapter}_")]

    files = []
    for d in sorted(chapter_dirs):
        for ext in cfg["include_extensions"]:
            files.extend(sorted(d.glob(f"*{ext}")))

    if mode == "changed":
        changed = changed_files_via_git(project_root)
        files = [f for f in files if str(f.relative_to(project_root)).replace("\\", "/") in changed]

    return files


def list_chapter_numbers(project_root: Path) -> list[str]:
    chapters: list[str] = []
    for d in project_root.iterdir():
        if d.is_dir() and re.match(r"^\d{2}_", d.name):
            chapters.append(chapter_number_from_name(d.name))
    return sorted(set(chapters))


def changed_files_via_git(project_root: Path) -> set[str]:
    cmd = ["git", "-C", str(project_root), "status", "--porcelain"]
    out = subprocess.check_output(cmd, text=True, encoding="utf-8", errors="ignore")
    changed = set()
    for line in out.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        changed.add(path.replace("\\", "/"))
    return changed


def ensure_dirs(cfg: dict, project_root: Path) -> dict:
    out_cfg = cfg["output"]
    paths = {
        "meta_root": project_root / out_cfg["meta_root"],
        "json_dir": project_root / out_cfg["json_dir"],
        "file_metrics_dir": project_root / out_cfg["file_metrics_dir"],
        "reports_root": project_root / out_cfg["reports_root"],
        "chapters_reports_dir": project_root / out_cfg["chapters_reports_dir"],
        "dataview_root": project_root / out_cfg["reports_root"] / "dataview",
        "dataview_files_dir": project_root / out_cfg["reports_root"] / "dataview" / "files",
        "dataview_chapters_dir": project_root / out_cfg["reports_root"] / "dataview" / "chapters",
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    return paths


def write_outputs(project_root: Path, files_metrics: list[FileMetrics], paths: dict, run_mode: str) -> None:
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    by_chapter: dict[str, list[FileMetrics]] = {}
    chapter_note_name: dict[str, str] = {}
    for m in files_metrics:
        by_chapter.setdefault(m.chapter, []).append(m)
        chapter_dir = m.path.split("/", 1)[0]
        chapter_note_name.setdefault(m.chapter, chapter_dir)

    # Per-file JSON
    for m in files_metrics:
        file_key = m.path.replace("/", "__")
        out_json = paths["file_metrics_dir"] / f"{file_key}.json"
        out_json.write_text(json.dumps(m.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")

    # Chapter JSON
    chapter_json_summary = {}
    for chapter, items in by_chapter.items():
        c_words = sum(i.words for i in items)
        c_sent = sum(i.sentences for i in items)
        c_par = sum(i.paragraphs for i in items)
        chapter_tokens: set[str] = set()
        for i in items:
            text = (project_root / i.path).read_text(encoding="utf-8", errors="ignore")
            chapter_tokens.update(tokenize(text))
        lexicon_size = len(chapter_tokens)
        top = Counter()
        for i in items:
            top.update(dict(i.top_words))
        payload = {
            "chapter": chapter,
            "files": [i.path for i in items],
            "words": c_words,
            "symbols": sum(i.symbols for i in items),
            "lexicon_size": lexicon_size,
            "wateriness": safe_div(sum(i.stopwords_words for i in items) * 100, c_words),
            "nausea": safe_div(sum(i.max_word_repeats for i in items) * 100, c_words),
            "sentences": c_sent,
            "paragraphs": c_par,
            "avg_word_len": safe_div(
                sum(i.avg_word_len * i.words for i in items),
                c_words,
            ),
            "lexical_richness": safe_div(c_words, lexicon_size),
            "avg_sentence_len_words": safe_div(c_words, c_sent),
            "avg_paragraph_len_words": safe_div(c_words, c_par),
            "top_words": top.most_common(30),
        }
        (paths["json_dir"] / f"chapter_{chapter}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        chapter_json_summary[chapter] = payload

    # Book summary JSON
    total_words = sum(i.words for i in files_metrics)
    total_sent = sum(i.sentences for i in files_metrics)
    total_par = sum(i.paragraphs for i in files_metrics)

    book_json = {
        "generated_at": now,
        "mode": run_mode,
        "files_count": len(files_metrics),
        "chapters_count": len(by_chapter),
        "words": total_words,
        "sentences": total_sent,
        "paragraphs": total_par,
        "avg_sentence_len_words": safe_div(total_words, total_sent),
        "avg_paragraph_len_words": safe_div(total_words, total_par),
        "chapters": chapter_json_summary,
    }
    (paths["json_dir"] / "book_summary.json").write_text(
        json.dumps(book_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Markdown reports
    dashboard = [
        "# Text Analytics Dashboard",
        "",
        f"- Generated: `{now}`",
        f"- Mode: `{run_mode}`",
        f"- Files analyzed: **{len(files_metrics)}**",
        f"- Chapters analyzed: **{len(by_chapter)}**",
        f"- Words: **{total_words}**",
        f"- Sentences: **{total_sent}**",
        f"- Paragraphs: **{total_par}**",
        f"- Avg sentence length (words): **{safe_div(total_words, total_sent)}**",
        f"- Avg paragraph length (words): **{safe_div(total_words, total_par)}**",
        "",
        "## Dataview Tables",
        "![[dataview/00_Dataview_Таблицы]]",
        "",
        "## Chapters",
    ]
    for chapter in sorted(by_chapter):
        c = chapter_json_summary[chapter]
        dashboard.append(
            f"- `{chapter}`: {c['words']} words, {len(c['files'])} files -> `chapters/{chapter}.md`"
        )

    (paths["reports_root"] / "00_Dashboard.md").write_text("\n".join(dashboard) + "\n", encoding="utf-8")

    chapters_md = ["# Chapter Metrics", ""]
    for chapter in sorted(by_chapter):
        c = chapter_json_summary[chapter]
        chapters_md.extend(
            [
                f"## Chapter {chapter}",
                f"- Files: {len(c['files'])}",
                f"- Words: {c['words']}",
                f"- Sentences: {c['sentences']}",
                f"- Paragraphs: {c['paragraphs']}",
                f"- Avg sentence length: {c['avg_sentence_len_words']}",
                "",
            ]
        )
    (paths["reports_root"] / "01_По_главам.md").write_text("\n".join(chapters_md), encoding="utf-8")

    risky = sorted(files_metrics, key=lambda x: (x.avg_sentence_len_words, x.dialogue_share_percent), reverse=True)[:40]
    risky_md = ["# Files With Risks", "", "Heuristic: long sentences and high dialogue ratio.", ""]
    for item in risky:
        risky_md.append(
            f"- `{item.path}` | words={item.words}, avg_sentence={item.avg_sentence_len_words}, dialogue={item.dialogue_share_percent}%"
        )
    (paths["reports_root"] / "02_Файлы_с_рисками.md").write_text("\n".join(risky_md) + "\n", encoding="utf-8")

    for chapter, items in by_chapter.items():
        lines = [f"# Chapter {chapter}", ""]
        for m in sorted(items, key=lambda i: i.path):
            lines.append(f"## {Path(m.path).name}")
            lines.append(f"- Path: `{m.path}`")
            lines.append(f"- Words: {m.words}; Sentences: {m.sentences}; Paragraphs: {m.paragraphs}")
            lines.append(f"- Avg sentence: {m.avg_sentence_len_words}; Dialogue: {m.dialogue_share_percent}%")
            top = ", ".join(f"{w}({c})" for w, c in m.top_words[:8])
            lines.append(f"- Top words: {top if top else 'n/a'}")
            lines.append("")
        (paths["chapters_reports_dir"] / f"{chapter}.md").write_text("\n".join(lines), encoding="utf-8")

    # Dataview-friendly records (one note per file metric)
    for old_note in paths["dataview_files_dir"].glob("*.md"):
        old_note.unlink()
    for old_note in paths["dataview_chapters_dir"].glob("*.md"):
        old_note.unlink()

    for m in files_metrics:
        scene = Path(m.path).stem
        slug_base = str(Path(m.path).with_suffix("")).replace("/", "__")
        slug = re.sub(r"[^0-9A-Za-zА-Яа-яЁё._-]+", "_", slug_base)
        top_words_inline = ", ".join(f"{w}({c})" for w, c in m.top_words[:10])
        dv_note = (
            "---\n"
            "metric_type: text-metric\n"
            "dv_ready: true\n"
            "tags:\n"
            "  - text-metric\n"
            f"chapter: {int(m.chapter)}\n"
            f"scene: \"{scene}\"\n"
            f"source_path: \"{m.path}\"\n"
            f"words: {m.words}\n"
            f"sentences: {m.sentences}\n"
            f"paragraphs: {m.paragraphs}\n"
            f"unique_words: {m.unique_words}\n"
            f"avg_word_len: {m.avg_word_len}\n"
            f"avg_sentence_len: {m.avg_sentence_len_words}\n"
            f"avg_paragraph_len: {m.avg_paragraph_len_words}\n"
            f"dialogue_lines: {m.dialogue_lines}\n"
            f"lines: {m.lines}\n"
            f"dialogue_share: {m.dialogue_share_percent}\n"
            f"updated: \"{now}\"\n"
            "---\n\n"
            f"# {scene}\n\n"
            f"top_words:: {top_words_inline}\n"
        )
        (paths["dataview_files_dir"] / f"{slug}.md").write_text(dv_note, encoding="utf-8")

    # Dataview-friendly chapter metrics (one note per chapter)
    for chapter in sorted(chapter_json_summary):
        c = chapter_json_summary[chapter]
        slug = chapter_note_name.get(chapter, f"{chapter}_chapter_metrics")
        top_words_inline = ", ".join(f"{w}({n})" for w, n in c["top_words"][:10])
        top_words_5 = ", ".join(f"{w}({n})" for w, n in c["top_words"][:5])
        chapter_note = (
            "---\n"
            "metric_type: chapter-metric\n"
            "dv_ready: true\n"
            "tags:\n"
            "  - chapter-metric\n"
            f"chapter: {int(chapter)}\n"
            f"files_count: {len(c['files'])}\n"
            f"words: {c['words']}\n"
            f"symbols: {c['symbols']}\n"
            f"wateriness: {c['wateriness']}\n"
            f"nausea: {c['nausea']}\n"
            f"lexicon_size: {c['lexicon_size']}\n"
            f"lexical_richness: {c['lexical_richness']}\n"
            f"words_leng: {c['avg_word_len']}\n"
            f"top_words_5: \"{top_words_5}\"\n"
            f"sentences: {c['sentences']}\n"
            f"paragraphs: {c['paragraphs']}\n"
            f"avg_sentence_len: {c['avg_sentence_len_words']}\n"
            f"avg_paragraph_len: {c['avg_paragraph_len_words']}\n"
            f"updated: \"{now}\"\n"
            "---\n\n"
            f"# Chapter {chapter}\n\n"
            f"top_words:: {top_words_inline}\n"
        )
        (paths["dataview_chapters_dir"] / f"{slug}.md").write_text(chapter_note, encoding="utf-8")

    dataview_dashboard = (
        "# Dataview Tables\n\n"
        "## Summary by chapter\n\n"
        "```dataview\n"
        "TABLE files_count as Files, words as Words, symbols as Symbols, words_leng as WordsLeng, sentences as Sentences, wateriness as Wateriness, nausea as Nausea, lexicon_size as LexiconSize, lexical_richness as LexRich, top_words_5 as Top5Words\n"
        "FROM #chapter-metric\n"
        "WHERE contains(file.path, \"_sys/__reports/text-analytics/dataview/chapters\") AND dv_ready\n"
        "SORT chapter ASC\n"
        "```\n\n"
        "## Top scenes by sentence length\n\n"
        "```dataview\n"
        "TABLE file.link as File, chapter, scene, words, sentences, avg_sentence_len, dialogue_share\n"
        "FROM #text-metric\n"
        "WHERE contains(file.path, \"_sys/__reports/text-analytics/dataview/files\") AND dv_ready\n"
        "SORT avg_sentence_len DESC\n"
        "LIMIT 30\n"
        "```\n\n"
        "## Dialogue-heavy scenes\n\n"
        "```dataview\n"
        "TABLE file.link as File, chapter, scene, dialogue_share, words\n"
        "FROM #text-metric\n"
        "WHERE contains(file.path, \"_sys/__reports/text-analytics/dataview/files\") AND dv_ready AND dialogue_share >= 35\n"
        "SORT dialogue_share DESC\n"
        "LIMIT 30\n"
        "```\n\n"
        "## Chapter 7 details\n\n"
        "```dataview\n"
        "TABLE file.link as File, scene, words, avg_sentence_len, dialogue_share\n"
        "FROM #text-metric\n"
        "WHERE contains(file.path, \"_sys/__reports/text-analytics/dataview/files\") AND dv_ready AND chapter = 7\n"
        "SORT words DESC\n"
        "```\n"
    )
    (paths["dataview_root"] / "00_Dataview_Таблицы.md").write_text(dataview_dashboard, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Text analytics for manuscript markdown files")
    parser.add_argument("--config", default=".tools/text_analytics/config.yaml", help="Path to config YAML")
    parser.add_argument("--all", action="store_true", help="Analyze all chapters one by one")
    parser.add_argument("--full", action="store_true", help="Analyze all chapter files")
    parser.add_argument("--changed", action="store_true", help="Analyze only changed files by git status")
    parser.add_argument("--chapter", help="Analyze only one chapter number, e.g. 07")
    args = parser.parse_args()

    if args.all and args.chapter:
        raise SystemExit("--all cannot be used with --chapter")

    run_mode = "full"
    if args.changed:
        run_mode = "changed"
    elif args.all:
        run_mode = "all"

    project_root = Path.cwd()
    config_path = project_root / args.config
    cfg = load_config(config_path)

    chapter = args.chapter.zfill(2) if args.chapter else None

    files: list[Path] = []
    if args.all:
        for chapter_num in list_chapter_numbers(project_root):
            chapter_files = collect_target_files(project_root, cfg, "full", chapter_num)
            files.extend(chapter_files)
            print(f"Chapter {chapter_num}: {len(chapter_files)} files")
    else:
        files = collect_target_files(project_root, cfg, run_mode, chapter)

    metrics = [analyze_file(p, chapter_number_from_name(p.parent.name), cfg) for p in files]
    paths = ensure_dirs(cfg, project_root)
    write_outputs(project_root, metrics, paths, run_mode)

    print(f"Mode: {run_mode}")
    print(f"Chapter filter: {chapter or 'all'}")
    print(f"Analyzed files: {len(metrics)}")
    print(f"Reports dir: {paths['reports_root']}")
    print(f"JSON dir: {paths['json_dir']}")


if __name__ == "__main__":
    main()
