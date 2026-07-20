#!/usr/bin/env python3
"""
make_video_manifest_vocab.py — build manifest.json for the Recall video-review app,
VOCAB METHOD version.
"""

import os, json, requests

API_HOST  = "api.pcloud.com"          # US (u.pcloud.link).  EU -> "eapi.pcloud.com"
SUBFOLDER = "Vocab Method"
OUT_FILE  = "manifest_vocab.json"

MONTHS = {
    "January 2026":  "kZmvQA5Z47mnuk84yzuoPpXXq4D4EHcVN2dV",
    "February 2026": "kZL5mA5ZRK8XSTKKiKXSbF1sgC8fYQAIYNey",
    "March 2026":    "kZY5mA5ZHj5J1bflKAyhCrr7lpgpBmFxPn87",
}

SPLIT_MONTH = "April 2026"
SPLIT_PARTS = {
    "Part 1": "kZAOaA5ZM5HVYvimKKF52c5CAQudoQQARYQV",
    "Part 2": "kZ3OaA5ZfetSvtAH9zjR6J7YC3FuNST8WbV7",
    "Part 3": "kZGOaA5ZdmLsl98vl5XErzYbPnlvJ8iixSU7",
    "Part 4": "kZvOaA5Z1caa0jC9O35dEfSJ2XEAO5beRwH7",
    "Part 5": "kZiOaA5Zw0qWhrR4nHLcEN0z5IfT78k1OoKk",
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
stats = {"folders": 0, "vocab_folders": 0, "videos": 0}


def walk(node, code, month, part):
    for c in node.get("contents", []):
        if not c.get("isfolder"):
            continue
        stats["folders"] += 1
        if c["name"].strip().lower() == SUBFOLDER.strip().lower():
            stats["vocab_folders"] += 1
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
                "month": month, 
                "part": part, 
                "course": course,
                "lecture": node.get("name", ""),
                "title": node.get("name", "") or os.path.splitext(video["name"])[0],
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

    log(f"\nTotals — folders scanned: {stats['folders']}  |  Vocab Method folders: {stats['vocab_folders']}  |  videos: {stats['videos']}")
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"items": items}, f, indent=2, ensure_ascii=False)
    log(f"Wrote {os.path.abspath(OUT_FILE)}  ({len(items)} videos)")
    if not items:
        log("No videos found — paste the output above to your assistant so we can adjust.")


if __name__ == "__main__":
    main()