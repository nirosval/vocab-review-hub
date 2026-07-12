#!/usr/bin/env python3
r"""
extract_nsm_intros.py

For each memory course you name, find the Number Shape Method
Contextualised List docx and pull out the two intro paragraphs
(List 1 intro and List 2 intro). Output is a plain-text file you
can email, plus the same text printed to the console for quick copy.

The intros are everything between `List 1` (or `List 2`) and the
matching `Phase 1` header. `[SCENE START]`-style marker lines are
skipped automatically.

Usage:
  Double-click the .bat, or run from the command line:

      python extract_nsm_intros.py
      python extract_nsm_intros.py --roots "P:\January 2026" \
                                   --courses Biology Chemistry

The output file is `nsm_intros_extract.txt` next to the script.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ─── Bootstrap python-docx ──────────────────────────────────────


def _install(pkg: str) -> None:
    cmd = [sys.executable, "-m", "pip", "install", "--quiet",
           "--disable-pip-version-check", pkg]
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError:
        subprocess.check_call(cmd + ["--break-system-packages"])


try:
    from docx import Document  # python-docx
except ImportError:
    print("First-run setup: installing python-docx...")
    _install("python-docx")
    from docx import Document


# ─── Constants ──────────────────────────────────────────────────

METHOD_FOLDER = "Number Shape Method"
MEMORY_COURSE_SUFFIXES = (" Memory Course", " Memory Mastery")
# A course folder ends in some combination of Memory / Mastery / Course,
# e.g. "Memory Course", "Memory Mastery", or "Memory Mastery Course".
COURSE_SUFFIX_RE = re.compile(
    r"memory\s+(?:mastery|course)(?:\s+course)?\s*$", re.IGNORECASE)
PART_RE = re.compile(r"^part\s*\d+$", re.IGNORECASE)

# Regexes for the docx structure
LIST_RE = re.compile(r"^\s*l(?:ist)?\s*([12])\b", re.IGNORECASE)
PHASE_RE = re.compile(r"^\s*phase\s+\d", re.IGNORECASE)
SCENE_MARKER_RE = re.compile(r"^\s*\[?\s*scene\b", re.IGNORECASE)
# 'Step 1: The Foundation' / 'Step 2: ...' / 'Step 3: ...' section headings
# sit between the list/scene markers and the real narrative intro.
STEP_RE = re.compile(r"^\s*step\s*\d", re.IGNORECASE)
# Metadata label lines that sit after the intro (e.g. "Role: ...",
# "Course Title: ...") and must never be captured as intro text.
LABEL_PREFIX_RE = re.compile(r"^\s*(role|course\s+title)\s*:", re.IGNORECASE)
# Bare heading labels that can appear on their own line (no 'Step N:' prefix).
HEADING_LABELS = {
    "the foundation", "the code", "the numbers", "the translation",
    "the numerical scene", "the numerical scenes", "the link",
    "the number recall",
}


def _is_noise(txt: str) -> bool:
    """True if a paragraph is a heading/marker, not narrative intro text."""
    if SCENE_MARKER_RE.match(txt) or STEP_RE.match(txt) or LABEL_PREFIX_RE.match(txt):
        return True
    # normalise: drop trailing parenthetical + punctuation, lowercase
    low = re.sub(r"\s*\(.*?\)\s*$", "", txt.strip().lower())
    low = low.rstrip(" :.\u2019'\"").strip()
    if low in HEADING_LABELS:
        return True
    # generic guard: a short label-like line with no sentence punctuation
    if len(txt.strip()) <= 40 and not re.search(r"[.!?]", txt):
        return True
    return False


@dataclass
class CourseExtract:
    course_name: str           # display name (folder name)
    root: Path                 # which root it came from
    docx_path: Optional[Path] = None
    intros: Dict[int, str] = field(default_factory=dict)
    error: str = ""


# ─── Docx extraction ────────────────────────────────────────────


def extract_intros_from_docx(docx_path: Path) -> Tuple[Dict[int, str], str]:
    """Return ({1: list1_intro_text, 2: list2_intro_text}, error_message).
    The text is whitespace-cleaned and joined with spaces if it spans
    multiple paragraphs."""
    try:
        doc = Document(str(docx_path))
    except Exception as e:
        return {}, f"Could not read docx: {e}"

    captured: Dict[int, List[str]] = {1: [], 2: []}
    current_list: Optional[int] = None

    for p in doc.paragraphs:
        raw = p.text
        if not raw.strip():
            continue
        # A single paragraph may pack several logical lines together
        # (e.g. "[SCENE START]\nToday we master..."), so walk line by line.
        for line in re.split(r"[\n\r\x0b\x0c]+", raw):
            txt = line.strip()
            if not txt:
                continue
            m = LIST_RE.match(txt)
            if m:
                current_list = int(m.group(1))
                continue
            if PHASE_RE.match(txt):
                current_list = None
                continue
            # Skip scene markers, Step headings, and bare heading labels
            if _is_noise(txt):
                continue
            if current_list in (1, 2):
                captured[current_list].append(txt)

    out: Dict[int, str] = {}
    for n in (1, 2):
        if captured[n]:
            out[n] = " ".join(captured[n])
    return out, ""


# ─── Folder discovery ───────────────────────────────────────────


def _normalize_name(s: str) -> str:
    return " ".join(s.strip().lower().split())


def _loose_name(s: str) -> str:
    """Lowercase, turn any run of non-alphanumeric characters into a single
    space, collapse. Makes 'EAMCET / EAPCET (India ...)' match a folder named
    'EAMCET  EAPCET (India ...)' since '/' is illegal in Windows folder names.
    Also drops the local '(cl]' colon stand-in so a pCloud name with a real
    colon ('Microsoft Certified: Azure ...') matches the on-disk folder
    ('Microsoft Certified(cl] Azure ...')."""
    s = re.sub(r"[\(\[]cl[\]\)]", " ", s, flags=re.IGNORECASE)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s.lower()).split())


def discover_memory_courses(root: Path) -> List[Path]:
    found: List[Path] = []
    try:
        for dirpath, dirnames, _ in os.walk(root):
            keep = []
            for d in dirnames:
                if COURSE_SUFFIX_RE.search(d):
                    found.append(Path(dirpath) / d)
                    # Do NOT descend into a course folder. A real course never
                    # contains another course; anything course-named nested
                    # inside (e.g. under Course Trailer or Link Method) is a
                    # stray copy and must be ignored.
                else:
                    keep.append(d)
            dirnames[:] = keep
    except (OSError, PermissionError) as e:
        print(f"ERROR: Could not list {root}: {e}", file=sys.stderr)
        return []
    return sorted(set(found), key=lambda x: str(x).lower())


def match_course(all_courses: List[Path], req: str) -> Optional[Path]:
    """Match a typed course name against a real folder name. Accepts
    the short form ('Biology'), or any 'X Students' / 'X Memory Course' /
    'X Memory Mastery' expansion. Case-insensitive."""
    suffixes = ("", " students memory course", " students memory mastery",
                 " memory course", " memory mastery", " students")
    req_n = _normalize_name(req)
    if not req_n:
        return None
    # 1. exact match
    for c in all_courses:
        if _normalize_name(c.name) == req_n:
            return c
    # 2. expansions
    for suf in suffixes:
        target = req_n + suf
        for c in all_courses:
            if _normalize_name(c.name) == target:
                return c
    # 3. punctuation-insensitive exact match (handles / & ( ) etc.)
    req_l = _loose_name(req)
    for c in all_courses:
        if _loose_name(c.name) == req_l:
            return c
    for suf in suffixes:
        target = req_l + _loose_name(suf)
        target = " ".join(target.split())
        for c in all_courses:
            if _loose_name(c.name) == target:
                return c
    # 4. unambiguous substring match
    subs = [c for c in all_courses if req_n in _normalize_name(c.name)
            or req_l in _loose_name(c.name)]
    if len(subs) == 1:
        return subs[0]
    return None


def find_method_folder(course: Path) -> Optional[Path]:
    # 1) Try the exact path directly. On pCloud/OneDrive virtual drives this
    #    forces the client to resolve just this one folder, which often
    #    succeeds even when a full directory listing comes back empty.
    cand = course / METHOD_FOLDER
    try:
        if cand.is_dir():
            return cand
    except OSError:
        pass
    # 2) Fall back to scanning children, comparing on a normalized name so a
    #    trailing space / double space / odd casing still matches.
    target = _normalize_name(METHOD_FOLDER)
    try:
        for c in course.iterdir():
            try:
                if c.is_dir() and _normalize_name(c.name) == target:
                    return c
            except OSError:
                continue
    except (OSError, PermissionError):
        pass
    return None


def find_contextualised_docx(method_dir: Path) -> Optional[Path]:
    """Find the 'Number Shape Method Contextualised List.docx' file,
    handling British/American spelling and slight name variations."""
    if not method_dir.is_dir():
        return None
    # Pattern catches: Contextualised, Contextualized, List, Lists
    target = re.compile(r"contextuali[sz]ed\s+lists?", re.IGNORECASE)
    candidates: List[Path] = []
    try:
        for c in method_dir.iterdir():
            if c.is_file() and c.suffix.lower() == ".docx":
                if target.search(c.stem) or c.name.startswith("~$"):
                    if not c.name.startswith("~$"):
                        candidates.append(c)
    except (OSError, PermissionError):
        return None
    if not candidates:
        # fallback: any .docx that has 'List' in the name
        try:
            for c in method_dir.iterdir():
                if (c.is_file() and c.suffix.lower() == ".docx"
                        and "list" in c.stem.lower()
                        and not c.name.startswith("~$")):
                    candidates.append(c)
        except (OSError, PermissionError):
            pass
    if not candidates:
        return None
    # prefer the shortest filename (closest to canonical)
    return sorted(candidates, key=lambda p: (len(p.name), p.name.lower()))[0]


# ─── Interactive prompts ────────────────────────────────────────


def _prompt_roots() -> List[Path]:
    print("Paste one or more parent folders to search (one per line).")
    print("Examples:")
    print("  P:\\January 2026")
    print("  P:\\February 2026")
    print("Press Enter on a blank line to finish.")
    roots: List[Path] = []
    while True:
        try:
            line = input("> " if not roots else "+ ")
        except EOFError:
            break
        raw = line.strip().strip('"').strip("'")
        if not raw:
            break
        p = Path(raw).expanduser()
        if not p.is_dir():
            print(f"  (skipped: not a folder: {p})")
            continue
        roots.append(p)
    if not roots:
        print("No folders entered.", file=sys.stderr)
        sys.exit(2)
    return roots


def _prompt_courses() -> List[str]:
    print()
    print("Paste memory course names (one per line).")
    print("Press Enter on a blank line to finish.")
    names: List[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line.strip():
            break
        names.append(line.strip())
    if not names:
        print("No course names entered.", file=sys.stderr)
        sys.exit(2)
    return names


# ─── Main ───────────────────────────────────────────────────────


LECTURE_NUM_RE = re.compile(r"lecture\s*0*(\d+)", re.IGNORECASE)


def _lecture_number(title: str) -> Optional[int]:
    """'Lecture 42' -> 42, 'Lecture 60 Part 1' -> 60, etc."""
    m = LECTURE_NUM_RE.search(title)
    if m:
        return int(m.group(1))
    # fallback: bare number anywhere in the title
    m = re.search(r"\b(\d{1,3})\b", title)
    return int(m.group(1)) if m else None


def _build_list_maps(items: List[dict]) -> Dict[str, Dict[int, int]]:
    """For each course, collect the distinct lecture numbers that appear
    among its items, sort them ascending, and map the smallest -> List 1,
    next -> List 2, etc. This replaces the old hardcoded 'Lecture 60 ->
    List 1 / Lecture 61 -> List 2' rule so it works for any method
    (Number Shape Method's 60/61, Vocab Method's 42/43, and so on) as long
    as each course's docx covers its lectures in ascending order."""
    nums_by_course: Dict[str, set] = {}
    for it in items:
        n = _lecture_number(it.get("title", "") or it.get("lecture", ""))
        if n is None:
            continue
        course = it.get("course", "")
        nums_by_course.setdefault(course, set()).add(n)
    maps: Dict[str, Dict[int, int]] = {}
    for course, nums in nums_by_course.items():
        maps[course] = {n: i + 1 for i, n in enumerate(sorted(nums))}
    return maps


def run_manifest_mode(manifest_path: Path, out_path: Path,
                      roots: List[Path]) -> int:
    import json
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: could not read manifest {manifest_path}: {e}",
              file=sys.stderr)
        return 2
    items = data.get("items", [])
    if not items:
        print("ERROR: manifest has no 'items'.", file=sys.stderr)
        return 2

    print(f"Manifest: {len(items)} videos")
    print("Discovering course folders...")
    courses_per_root = {r: discover_memory_courses(r) for r in roots}
    for r in roots:
        print(f"  {r}: {len(courses_per_root[r])} course folder(s)")

    cache: Dict[str, Dict[int, str]] = {}

    def intros_for(course_name: str) -> Dict[int, str]:
        key = _normalize_name(course_name)
        if key in cache:
            return cache[key]
        found: Dict[int, str] = {}
        for r in roots:
            c = match_course(courses_per_root[r], course_name)
            if c is None:
                continue
            method = find_method_folder(c)
            if method is None:
                continue
            docx = find_contextualised_docx(method)
            if docx is None:
                continue
            got, _ = extract_intros_from_docx(docx)
            if got:
                found = got
                break
        cache[key] = found
        return found

    list_maps = _build_list_maps(items)

    n_set = 0
    n_missing = 0
    missing_courses: set = set()
    for it in items:
        lec_num = _lecture_number(it.get("title", "") or it.get("lecture", ""))
        course_name = it.get("course", "")
        n = list_maps.get(course_name, {}).get(lec_num) if lec_num is not None else None
        if n is None:
            continue
        intros = intros_for(course_name)
        if n in intros and intros[n].strip():
            it["script"] = intros[n]
            n_set += 1
        else:
            n_missing += 1
            missing_courses.add(it.get("course", ""))

    try:
        out_path.write_text(json.dumps(data, ensure_ascii=False),
                            encoding="utf-8")
    except Exception as e:
        print(f"ERROR: could not write {out_path}: {e}", file=sys.stderr)
        return 2

    print()
    print(f"Intros attached to {n_set} videos.")
    if n_missing:
        print(f"No intro found for {n_missing} videos "
              f"across {len(missing_courses)} course(s):")
        for c in sorted(missing_courses)[:30]:
            print(f"  - {c}")
        if len(missing_courses) > 30:
            print(f"  ...and {len(missing_courses) - 30} more")
    print(f"Saved: {out_path}")
    return 0


def run_alljson_mode(roots: List[Path], out_path: Path) -> int:
    import json
    months = {}
    total_courses = 0
    total_with_both = 0
    partials = []
    for root in roots:
        month = root.name or str(root)
        courses = discover_memory_courses(root)
        # bucket by (part, normalized course name); keep the most complete one
        bucket = {}
        for course in courses:
            try:
                mids = course.relative_to(root).parts[:-1]
            except Exception:
                mids = ()
            part = ""
            for comp in mids:
                if PART_RE.match(comp.strip()):
                    part = comp.strip()
                    break
            method = find_method_folder(course)
            intros = {}
            note = ""
            if method is None:
                note = "no 'Number Shape Method' folder at: " + str(course)
            else:
                docx = find_contextualised_docx(method)
                if docx is None:
                    note = "no Contextualised List .docx in: " + str(method)
                else:
                    got, err = extract_intros_from_docx(docx)
                    intros = got
                    if err:
                        note = err
                    elif not (got.get(1) and got.get(2)):
                        note = "document found but intros not parsed: " + docx.name
            score = (1 if intros.get(1) else 0) + (1 if intros.get(2) else 0)
            key = (part, _normalize_name(course.name))
            prev = bucket.get(key)
            if prev is None or score > prev["score"]:
                bucket[key] = {"part": part, "course": course.name,
                               "list1": intros.get(1, ""), "list2": intros.get(2, ""),
                               "note": note, "score": score}
        rows = []
        for v in bucket.values():
            row = {"part": v["part"], "course": v["course"],
                   "list1": v["list1"], "list2": v["list2"]}
            if not (v["list1"] and v["list2"]):
                row["note"] = v.get("note", "")
            rows.append(row)
            total_courses += 1
            if v["list1"] and v["list2"]:
                total_with_both += 1
            else:
                miss = []
                if not v["list1"]:
                    miss.append("List 1")
                if not v["list2"]:
                    miss.append("List 2")
                partials.append((month, v["part"], v["course"],
                                 ", ".join(miss), v.get("note", "")))
        rows.sort(key=lambda r: (r["part"].lower(), r["course"].lower()))
        months[month] = rows
        parts_here = sorted({r["part"] for r in rows if r["part"]})
        print(f"{month}: {len(rows)} course(s)"
              + (f", parts: {', '.join(parts_here)}" if parts_here else ""))
    out = {"months": months}
    try:
        out_path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"ERROR: could not write {out_path}: {e}", file=sys.stderr)
        return 2
    print()
    print(f"Courses: {total_courses}  (both intros: {total_with_both}, "
          f"partial/empty: {total_courses - total_with_both})")
    if partials:
        print("Partial/empty (missing one or both intros):")
        for month, part, course, miss, note in partials:
            loc = month + (f" / {part}" if part else "")
            extra = f"  [{note}]" if note else ""
            print(f"  [{loc}] {course}  -> missing {miss}{extra}")
    print(f"Saved: {out_path}")
    return 0


def run_report_mode(json_path: Path) -> int:
    import json
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: could not read {json_path}: {e}", file=sys.stderr)
        return 2
    partials = []
    total = 0
    for month, rows in data.get("months", {}).items():
        for r in rows:
            total += 1
            l1 = bool((r.get("list1") or "").strip())
            l2 = bool((r.get("list2") or "").strip())
            if not (l1 and l2):
                miss = []
                if not l1:
                    miss.append("List 1")
                if not l2:
                    miss.append("List 2")
                partials.append((month, r.get("part", ""),
                                 r.get("course", ""), ", ".join(miss),
                                 r.get("note", "")))
    print(f"Read {json_path}")
    print(f"Courses: {total}  (partial/empty: {len(partials)})")
    print()
    if not partials:
        print("Every course has both intros. Nothing missing.")
    else:
        print("These courses are missing one or both intros:")
        for month, part, course, miss, note in partials:
            loc = month + (f" / {part}" if part else "")
            print(f"  [{loc}] {course}")
            print(f"        missing {miss}" + (f"  ({note})" if note else ""))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Extract List 1 and List 2 intros from Number Shape "
                    "Method docx files for named courses.")
    ap.add_argument("--roots", nargs="*", default=None)
    ap.add_argument("--courses", nargs="*", default=None)
    ap.add_argument("--output", default=None,
                    help="Output text file (default: nsm_intros_extract.txt "
                          "next to this script).")
    ap.add_argument("--manifest", default=None,
                    help="Path to manifest.json. In this mode the script "
                         "finds the distinct lecture numbers per course, "
                         "sorts them ascending, and attaches List 1's intro "
                         "to the lowest-numbered lecture, List 2's intro to "
                         "the next one, and so on, then writes the manifest "
                         "back out.")
    ap.add_argument("--out", default=None,
                    help="Output manifest path for --manifest mode "
                         "(default: overwrite the input manifest).")
    ap.add_argument("--alljson", default=None,
                    help="Extract intros for EVERY course found under the "
                         "roots and write them to a JSON file (for the intros "
                         "site). Output keyed by month -> course -> intros.")
    ap.add_argument("--report", default=None,
                    help="Read an existing intros JSON and list which courses "
                         "are missing one or both intros. No scanning.")
    args = ap.parse_args()

    script_dir = Path(__file__).resolve().parent

    # ── Report mode: just read an existing JSON, no scanning ─────
    if args.report:
        return run_report_mode(Path(args.report))

    # Roots
    if args.roots:
        roots: List[Path] = []
        for r in args.roots:
            p = Path(r).expanduser()
            if not p.is_dir():
                print(f"ERROR: Not a folder: {p}", file=sys.stderr)
                return 2
            roots.append(p)
    else:
        roots = _prompt_roots()

    # ── All-courses JSON mode: build the intros-site data file ───
    if args.alljson:
        return run_alljson_mode(roots, Path(args.alljson))

    # ── Manifest mode: enrich manifest.json with intros ──────────
    if args.manifest:
        return run_manifest_mode(Path(args.manifest),
                                 Path(args.out) if args.out else Path(args.manifest),
                                 roots)

    # Course names
    if args.courses is not None:
        course_names = [c for c in args.courses if c.strip()]
        if not course_names:
            print("No course names given.", file=sys.stderr)
            return 2
    else:
        course_names = _prompt_courses()

    output = (Path(args.output) if args.output
                else script_dir / "nsm_intros_extract.txt")

    # Build a course-name -> Path map per root
    print()
    print(f"Roots: {len(roots)}")
    courses_per_root: Dict[Path, List[Path]] = {}
    for root in roots:
        courses_per_root[root] = discover_memory_courses(root)
        print(f"  {root}: {len(courses_per_root[root])} memory course(s) "
              f"found")

    # For each requested course, search each root in order
    extracts: List[CourseExtract] = []
    for name in course_names:
        matched_any = False
        for root in roots:
            course = match_course(courses_per_root[root], name)
            if course is None:
                continue
            matched_any = True
            ce = CourseExtract(course_name=course.name, root=root)
            method = find_method_folder(course)
            if method is None:
                ce.error = f"No '{METHOD_FOLDER}' folder under this course."
                extracts.append(ce)
                continue
            docx = find_contextualised_docx(method)
            if docx is None:
                ce.error = (f"No Contextualised List docx found in "
                            f"{METHOD_FOLDER}.")
                extracts.append(ce)
                continue
            ce.docx_path = docx
            intros, err = extract_intros_from_docx(docx)
            if err:
                ce.error = err
                extracts.append(ce)
                continue
            ce.intros = intros
            extracts.append(ce)
        if not matched_any:
            ce = CourseExtract(course_name=name, root=Path(""))
            ce.error = "Course name not found under any of the given roots."
            extracts.append(ce)

    # Build the formatted output
    lines: List[str] = []
    show_root_label = len(roots) > 1
    last_root: Optional[Path] = None
    for ce in extracts:
        if show_root_label and ce.root != last_root and ce.root.name:
            lines.append(f"========== {ce.root.name} ==========")
            lines.append("")
            last_root = ce.root
        lines.append(ce.course_name)
        if ce.error:
            lines.append(f"  [ERROR: {ce.error}]")
        else:
            if 1 in ce.intros:
                lines.append(ce.intros[1])
            else:
                lines.append("  [List 1 intro not found]")
            if 2 in ce.intros:
                lines.append(ce.intros[2])
            else:
                lines.append("  [List 2 intro not found]")
        lines.append("")  # blank line between courses

    text = "\n".join(lines)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")

    # Print to console
    print()
    print("=" * 60)
    print("EXTRACTED INTROS")
    print("=" * 60)
    print(text)
    print("=" * 60)
    print(f"Saved to: {output}")

    # Summary
    n_total = len(extracts)
    n_clean = sum(1 for e in extracts if not e.error and len(e.intros) == 2)
    n_partial = sum(1 for e in extracts if not e.error and 0 < len(e.intros) < 2)
    n_failed = sum(1 for e in extracts if e.error)
    print(f"\nCourses requested: {len(course_names)}")
    print(f"Course extracts:   {n_total}  "
          f"(clean: {n_clean}, partial: {n_partial}, failed: {n_failed})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
