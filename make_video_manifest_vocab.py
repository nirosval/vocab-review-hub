#!/usr/bin/env python3
"""
make_video_manifest_vocab.py — build manifest.json for the Recall video-review app,
VOCAB METHOD version.

Same scan logic as make_video_manifest.py, but looks for "Vocab Method" folders
instead of "Number Shape Method". Does NOT download anything during the scan — for
each month it lists the public folder once, finds "Vocab Method" folders at any
depth, and records each .mp4's pCloud file id (plus the matching .txt script's file
id, if present). The app mints fresh per-viewer links for both at review time.

>>> CHECK THIS <<<
SUBFOLDER below assumes the folder is literally named "Vocab Method" in pCloud.
If it's actually named something else (e.g. "Vocabulary Method"), change it to match
EXACTLY what you see in pCloud — the match is case-insensitive but must be the whole
name.

If one month's Vocab Method videos turn out to be too big for a single public link
(same "2293 Contents of the link are too big to be displayed" error April hit), split
that month into per-Part links the same way APRIL_PARTS does below, and tag them with
their part.

Usage:
    pip install requests
    python make_video_manifest_vocab.py   # writes manifest_vocab.json in the current folder
"""

import os, json, requests

API_HOST  = "api.pcloud.com"          # US (u.pcloud.link).  EU -> "eapi.pcloud.com"
SUBFOLDER = "Vocab Method"
OUT_FILE  = "manifest_vocab.json"

# label -> public link CODE (the part after code= in each month's share URL)
# Fill these in with the Vocab Method share-link codes for each month.
# To get a code: in pCloud, share/get-link on the month's public folder, then copy
# everything after "code=" in the resulting URL.
MONTHS = {
    "January 2026":  "PASTE_CODE_HERE",
    "February 2026": "PASTE_CODE_HERE",
    "March 2026":    "PASTE_CODE_HERE",
    "April 2026":    "PASTE_CODE_HERE",
}

# Only fill this in if a month needs to be split into per-Part links (same reason
# April got split for Number Shape Method — link too big for pCloud to display).
# Leave SPLIT_MONTH = "" if no month needs this.
SPLIT_MONTH = ""          # e.g. "April 2026" — leave "" if not needed
SPLIT_PARTS = {
    # "Part 1": "PASTE_CODE_HERE",
    # "Part 2": "PASTE_CODE_HERE",
}


def log(*a):
    print(*a, flush=True)


def api(method, **p):
    j = requests.get(f"https://{API_HOST}/{method}",
                     params={k: v for k, v in p.items() if v is not None}, timeout=120).json()
    if j.get("result", 0) != 0:
        raise SystemExit(f"pCloud error on {method}: {j.get('result')} {j.get('error')}")
    return j


items = []
stats = {"folders": 0, "nsm": 0, "videos": 0}


def walk(node, code, month, part):
    for c in node.get("contents", []):
        if not c.get("isfolder"):
            continue
        stats["folders"] += 1
        if c["name"].strip().lower() == SUBFOLDER.strip().lower():
            stats["nsm"] += 1
            emit(c, node.get("name", ""), code, month, part)
        else:
            walk(c, code, month, part)


def emit(method_folder, course, code, month, part):
    """Find every lecture folder inside this Vocab Method folder — a folder
    counts as a 'lecture' if it directly contains a video file. Pair that
    video with the audio file sitting in the same folder (if any)."""
    def collect(node):
        contents = node.get("contents", [])
        videos = [c for c in contents if not c.get("isfolder")
                  and c["name"].lower().endswith((".mp4", ".mov", ".m4v", ".mkv", ".webm"))]
        audios = [c for c in contents if not c.get("isfolder")
                  and c["name"].lower().endswith((".mp3", ".wav", ".m4a", ".aac"))]
        if videos:
            video = videos[0]
            audio = audios[0] if audios else None
            items.append({
                "month": month, "part": part, "course": course,
                "lecture": node.get("name", ""),
                "title": os.path.splitext(video["name"])[0],
                "video_fileid": video["fileid"],
                "audio_fileid": audio["fileid"] if audio else None,
                "code": code,
            })
            stats["videos"] += 1
            if stats["videos"] % 50 == 0:
                log(f"   ...{stats['videos']} lectures so far")
        for c in contents:
            if c.get("isfolder"):
                collect(c)
    collect(method_folder)


def scan(label, month, part, code):
    if not code or code.startswith("PASTE"):
        log(f"(skipping {label} — no code set)")
        return
    log(f"\nScanning {label} ...")
    root = api("showpublink", code=code)["metadata"]
    top = [c for c in root.get("contents", []) if c.get("isfolder")]
    nested = any(f.get("contents") for f in top)
    log(f"   top-level folders: {len(top)}  |  full tree returned: {nested}")
    if top and not nested:
        log("   WARNING: pCloud returned only the top level — deeper folders are empty, so videos can't be found this way.")
    before = stats["videos"]
    walk(root, code, month, part)
    log(f"   {label}: {stats['videos'] - before} videos found")


def main():
    # Regular months: one link each, no part.
    for month, code in MONTHS.items():
        if not code or code.startswith("PASTE"):
            log(f"(skipping {month} — no code set yet)")
            continue
        scan(month, month, "", code)
    # Split month (if any): one link per part.
    if SPLIT_MONTH:
        for part, code in SPLIT_PARTS.items():
            scan(f"{SPLIT_MONTH} · {part}", SPLIT_MONTH, part, code)

    log(f"\nTotals — folders scanned: {stats['folders']}  |  Number Shape Method folders: {stats['nsm']}  |  videos: {stats['videos']}")
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"items": items}, f, indent=2, ensure_ascii=False)
    log(f"Wrote {os.path.abspath(OUT_FILE)}  ({len(items)} videos)")
    if not items:
        log("No videos found — paste the output above to your assistant so we can adjust.")


if __name__ == "__main__":
    main()
