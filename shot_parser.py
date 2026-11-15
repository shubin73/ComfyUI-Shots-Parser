"""Shot-script parser (pure Python, no ComfyUI imports, so it can be unit tested).

Script format (compatible with the existing scripts):

    ### SHOT 1: Title (0:00 - 0:08)
    CONTINUOUS: NO
    PROMPT: text of the shot ...

    ### SHOT 2: Title (0:08 - 0:16)
    CONTINUOUS: YES
    PROMPT: ...

* A shot starts at a line beginning with ``###`` ``SHOT`` and a number (``SHOT 1``, ``SHOT 01``,
  ``###SHOT 1`` are all accepted).  Text that merely *mentions* "### SHOT n" in the middle of a
  line is not a marker.
* ``CONTINUOUS:`` is optional.  ``PROMPT:`` is required; the prompt runs to the next marker.
* A time range in the header, ``(m:ss - m:ss)``, is only used for a consistency warning.

The film length is derived from the shots that were actually parsed, so the shot count and the
shot text can never disagree.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MARKER_RE = re.compile(r"^[ \t]*#{2,4}[ \t]*SHOT[ \t]*0*(\d+)\b([^\n]*)$", re.I | re.M)
CONT_RE = re.compile(r"^[ \t]*CONTINUOUS[ \t]*:[ \t]*([^\n]*)$", re.I | re.M)
PROMPT_RE = re.compile(r"^[ \t]*PROMPT[ \t]*:[ \t]*(.*)\Z", re.I | re.M | re.S)
TIME_RE = re.compile(r"(\d+):(\d{2})(?:\.\d+)?\s*(?:-|–|—|~|to)\s*(\d+):(\d{2})(?:\.\d+)?", re.I)
PIC_RE = re.compile(r"<\s*Picture\s*(\d+)\s*>", re.I)

YES = {"yes", "y", "true", "1"}
NO = {"no", "n", "false", "0"}


@dataclass
class Shot:
    shot_id: int
    title: str
    prompt: str
    continuous: bool | None = None
    header_seconds: float | None = None
    start: float = 0.0
    end: float = 0.0


@dataclass
class ParseResult:
    shots: list[Shot] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    markers_found: int = 0
    skipped_ids: list[int] = field(default_factory=list)
    shots_text: str = ""
    shot_count: int = 0
    total_seconds: float = 0.0
    chunk_seconds: float = 0.0
    report: str = ""


def fmt_seconds(x: float) -> str:
    """15.0 -> '15', 7.5 -> '7.5'."""
    return f"{x:g}"


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")


def _title_and_range(header: str) -> tuple[str, float | None]:
    header = header.strip()
    seconds = None
    m = TIME_RE.search(header)
    if m:
        a = int(m.group(1)) * 60 + int(m.group(2))
        b = int(m.group(3)) * 60 + int(m.group(4))
        if b > a:
            seconds = float(b - a)
        header = (header[: m.start()] + header[m.end():]).strip()
    title = re.sub(r"^[:\-–—\s]+", "", header)          # leading ':' or dash
    title = re.sub(r"[\(\[\s]+$", "", title).strip()              # dangling '(' left by the range
    title = re.sub(r"\(\s*\)", "", title).strip()
    return title, seconds


def parse_script(
    text: str,
    first_shot_id: int = 1,
    shot_seconds: float = 15,
    max_shot_seconds: float = 15,
    max_shots: int = 0,
    picture_alias: bool = True,
) -> ParseResult:
    res = ParseResult()
    text = normalize_newlines(text or "")
    markers = list(MARKER_RE.finditer(text))
    res.markers_found = len(markers)

    if shot_seconds <= 0:
        res.errors.append(f"shot_seconds must be > 0 (got {shot_seconds}).")
    if max_shot_seconds > 0 and shot_seconds > max_shot_seconds:
        res.errors.append(f"shot_seconds {shot_seconds:g} s is longer than max_shot_seconds {max_shot_seconds:g} s.")
    if not markers:
        res.errors.append("No shot markers found. Each shot must start on its own line with '### SHOT <number>'.")

    parsed: list[Shot] = []
    seen: dict[int, int] = {}
    for i, m in enumerate(markers):
        sid = int(m.group(1))
        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        block = text[m.end(): end]
        title, header_seconds = _title_and_range(m.group(2))

        if sid in seen:
            res.errors.append(f"Shot {sid} appears more than once (marker #{seen[sid]} and #{i + 1}).")
            continue
        seen[sid] = i + 1

        cont = None
        cm = CONT_RE.search(block)
        if cm:
            v = cm.group(1).strip().lower()
            if v in YES:
                cont = True
            elif v in NO:
                cont = False
            else:
                res.warnings.append(f"Shot {sid}: CONTINUOUS value '{cm.group(1).strip()}' is not YES/NO; ignored.")

        pm = PROMPT_RE.search(block)
        prompt = re.sub(r"\s*\n\s*", " ", pm.group(1)).strip() if pm else ""
        if not prompt:
            res.errors.append(f"Shot {sid}: no text after 'PROMPT:'.")
            continue
        if picture_alias:
            prompt = PIC_RE.sub(lambda mm: f"@pic{mm.group(1)}", prompt)
        parsed.append(Shot(sid, title, prompt, cont, header_seconds))

    ids_in_file = [s.shot_id for s in parsed]
    if ids_in_file != sorted(ids_in_file):
        res.warnings.append("Shot numbers are not in ascending order in the file; shots are used in numeric order.")
    parsed.sort(key=lambda s: s.shot_id)

    res.skipped_ids = [s.shot_id for s in parsed if s.shot_id < first_shot_id]
    shots = [s for s in parsed if s.shot_id >= first_shot_id]

    ids = [s.shot_id for s in shots]
    if ids and ids != list(range(ids[0], ids[0] + len(ids))):
        res.warnings.append(f"Shot numbers {ids} have gaps; they are rendered back to back in this order (no empty time).")
    if max_shots and len(shots) > max_shots:
        res.errors.append(f"{len(shots)} shots found but max_shots is {max_shots}.")
    if markers and not shots and not res.errors:
        res.errors.append(f"No shots left at or after first_shot_id={first_shot_id}.")

    t = 0.0
    lines = []
    for s in shots:
        s.start, s.end = t, t + shot_seconds
        t = s.end
        lines.append(f"{fmt_seconds(s.start)}-{fmt_seconds(s.end)}: {s.prompt}")
        if s.header_seconds is not None and abs(s.header_seconds - shot_seconds) > 0.5:
            res.warnings.append(
                f"Shot {s.shot_id}: header says {s.header_seconds:g} s but every shot is rendered at {shot_seconds:g} s."
            )

    res.shots = shots
    res.shot_count = len(shots)
    res.shots_text = "\n".join(lines)
    res.chunk_seconds = float(shot_seconds)
    res.total_seconds = float(shot_seconds) * len(shots)
    res.report = build_report(res, first_shot_id)
    return res


def build_report(res: ParseResult, first_shot_id: int) -> str:
    out = [
        f"shots: {res.shot_count} | markers in file: {res.markers_found} | "
        f"{res.chunk_seconds:g} s each | film length: {res.total_seconds:g} s",
    ]
    if res.skipped_ids:
        out.append(f"skipped (before first_shot_id={first_shot_id}): {res.skipped_ids}")
    for s in res.shots:
        cont = {True: "YES", False: "NO", None: "-"}[s.continuous]
        hdr = f" | header {s.header_seconds:g} s" if s.header_seconds else ""
        out.append(f"  #{s.shot_id} {fmt_seconds(s.start)}-{fmt_seconds(s.end)} | continuous {cont}{hdr} | {len(s.prompt)} chars | {s.title}")
    for w in res.warnings:
        out.append(f"WARNING: {w}")
    for e in res.errors:
        out.append(f"ERROR: {e}")
    return "\n".join(out)
