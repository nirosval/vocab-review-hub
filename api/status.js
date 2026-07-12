// GET  /api/status   -> { history: [...], latest: { "<course>::<lecture>::<component>": row } }
// POST /api/status   -> body { month, course, lecture, checker, component, status, notes }
//                       appends one row (append-only, so revision history is
//                       automatic — nothing is ever overwritten).
//
// Requires env vars:
//   GOOGLE_SHEET_ID   — the spreadsheet ID (the long string in the sheet's URL)
//   GOOGLE_SHEET_TAB  — the tab name to log into (default: "Review Status")
//
// Expected header row in that tab (create it once, manually):
//   Timestamp | Month | Course | Lecture | Checker | Component | Status | Notes

const { getAccessToken } = require('./_sheetsAuth');

const SHEET_ID = process.env.GOOGLE_SHEET_ID;
const TAB = process.env.GOOGLE_SHEET_TAB || 'Review Status';
const RANGE = `${TAB}!A:H`;

module.exports = async (req, res) => {
  if (!SHEET_ID) {
    res.status(500).json({ error: 'Missing GOOGLE_SHEET_ID env var' });
    return;
  }

  try {
    const token = await getAccessToken();

    if (req.method === 'GET') {
      const url = `https://sheets.googleapis.com/v4/spreadsheets/${SHEET_ID}/values/${encodeURIComponent(
        RANGE
      )}`;
      const r = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await r.json();
      if (!r.ok) {
        res.status(502).json({ error: data });
        return;
      }

      const rows = (data.values || []).slice(1); // skip header row
      const history = rows.map((row) => ({
        timestamp: row[0] || '',
        month: row[1] || '',
        course: row[2] || '',
        lecture: row[3] || '',
        checker: row[4] || '',
        component: row[5] || '',
        status: row[6] || '',
        notes: row[7] || '',
      }));

      // Sheet is append-only in chronological order, so the last row for a
      // given key is always the latest status for that component.
      const latest = {};
      for (const entry of history) {
        const key = `${entry.course}::${entry.lecture}::${entry.component}`;
        latest[key] = entry;
      }

      res.setHeader('Cache-Control', 'no-store');
      res.status(200).json({ history, latest });
      return;
    }

    if (req.method === 'POST') {
      let body = req.body;
      if (typeof body === 'string') {
        try {
          body = JSON.parse(body);
        } catch {
          body = {};
        }
      }
      const { month, course, lecture, checker, component, status, notes } =
        body || {};
      if (!course || !lecture || !checker || !component || !status) {
        res.status(400).json({
          error:
            'course, lecture, checker, component, and status are required',
        });
        return;
      }

      const row = [
        new Date().toISOString(),
        month || '',
        course,
        lecture,
        checker,
        component,
        status,
        notes || '',
      ];

      const url = `https://sheets.googleapis.com/v4/spreadsheets/${SHEET_ID}/values/${encodeURIComponent(
        RANGE
      )}:append?valueInputOption=USER_ENTERED`;
      const r = await fetch(url, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ values: [row] }),
      });
      const data = await r.json();
      if (!r.ok) {
        res.status(502).json({ error: data });
        return;
      }
      res.status(200).json({ ok: true });
      return;
    }

    res.status(405).json({ error: 'Use GET or POST' });
  } catch (e) {
    res.status(500).json({ error: String(e) });
  }
};
