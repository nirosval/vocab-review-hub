# Vocab Method — Checking Queue

A small internal tool for checking Vocab Method lecture videos: video, audio,
and the script intro all in one page, with every check logged (append-only)
to a Google Sheet tab so revision history is never lost.

No pCloud account needed by checkers — the site mints a fresh, temporary
streaming link for each video/audio on the fly.

---

## 1. How it fits together

```
pCloud (source files)
   │
   │  make_video_manifest_vocab.py   → scans pCloud public links,
   │                                    writes manifest_vocab.json
   │                                    (video + audio fileids)
   │
   │  extract_nsm_intros.py --manifest → reads the local docx script files,
   │                                       attaches script_intro per lecture
   │
   ▼
data/manifest_vocab.json   (commit this into the repo)
   │
   ▼
This site (Vercel)
   ├─ index.html, style.css, app.js   static frontend (queue + review UI)
   └─ api/        serverless functions
        ├─ getlink.js   → mints a fresh pCloud stream URL per file
        └─ status.js    → reads/appends check rows in Google Sheets
```

## 2. One-time setup

### A. Generate the manifest

On your machine, with the pCloud share-link codes filled in:

```bash
pip install requests
python make_video_manifest_vocab.py
python extract_nsm_intros.py --manifest manifest_vocab.json --roots "P:\January 2026" ...
```

Copy the resulting `manifest_vocab.json` into `data/manifest_vocab.json`
in this repo (replacing the empty placeholder), then commit it.

> Re-run and re-commit this whenever new lectures are added.

### B. Google Sheets — service account

1. In [Google Cloud Console](https://console.cloud.google.com/), create (or
   reuse) a project → **APIs & Services → Library** → enable **Google
   Sheets API**.
2. **IAM & Admin → Service Accounts → Create service account.** Any name is
   fine (e.g. `vocab-review-bot`).
3. Open the new service account → **Keys → Add key → Create new key → JSON**.
   Download it.
4. From the downloaded JSON, copy:
   - `client_email` → this is `GOOGLE_SERVICE_ACCOUNT_EMAIL`
   - `private_key` → this is `GOOGLE_PRIVATE_KEY` (keep the `\n` characters
     literally, as they appear in the JSON file — don't convert them to real
     line breaks)
5. Open your Google Sheet → **Share** → paste the service account's email →
   give it **Editor** access.
6. In that same spreadsheet, create a **new tab** named `Review Status`
   (or whatever you set `GOOGLE_SHEET_TAB` to) with this header row in `A1:H1`:

   ```
   Timestamp | Month | Course | Lecture | Checker | Component | Status | Notes
   ```

   This tab is separate from the existing TASK SHEET — the site only ever
   writes here, so the main tracking sheet is never touched.

### C. Deploy to Vercel

1. Push this folder to a new GitHub repo.
2. In [Vercel](https://vercel.com), **Add New → Project** → import that repo.
3. Before the first deploy (or right after, then redeploy), go to
   **Project Settings → Environment Variables** and add everything from
   `.env.example` with your real values.
4. Deploy. Vercel auto-detects the `api/` folder as serverless functions and
   serves everything else as the static site — no `vercel.json` needed.

## 3. Local development

```bash
npm i -g vercel
vercel dev
```

This runs both the static frontend and the `/api` functions locally, reading
env vars from a local `.env` file if you create one (not committed).

## 4. Notes

- **Revision history is automatic.** Every check (including rechecks) is a
  new row — nothing is overwritten, so you always have the full history per
  lecture per component.
- **Overall status logic** (shown as the badge in the queue): if any
  component's *latest* check is "Needs Revision", the lecture shows Needs
  Revision; it shows Passed only once video, audio, and script have all been
  checked and passed; otherwise it's Not Started.
- **Minted links expire** — that's expected, it's how pCloud's public-link
  API works. The site re-mints a fresh one every time a lecture is opened.
