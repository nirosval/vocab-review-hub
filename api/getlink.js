// POST /api/getlink
// Body: { code: "<pCloud public link code>", fileid: 123456 }
// Returns: { url: "https://<host>/<path>" } — a fresh, direct-streamable
// URL for that file. Minted on demand so members never need a pCloud
// account or the shared edit credentials.

module.exports = async (req, res) => {
  if (req.method !== 'POST') {
    res.status(405).json({ error: 'Use POST' });
    return;
  }

  let body = req.body;
  if (typeof body === 'string') {
    try {
      body = JSON.parse(body);
    } catch {
      body = {};
    }
  }
  const { code, fileid } = body || {};
  if (!code || !fileid) {
    res.status(400).json({ error: 'code and fileid are required' });
    return;
  }

  try {
    const apiUrl = `https://api.pcloud.com/getpublinkdownload?code=${encodeURIComponent(
      code
    )}&fileid=${encodeURIComponent(fileid)}`;
    const r = await fetch(apiUrl);
    const data = await r.json();

    if (data.result !== 0) {
      res
        .status(502)
        .json({ error: `pCloud error ${data.result}: ${data.error || ''}` });
      return;
    }

    const host = Array.isArray(data.hosts) ? data.hosts[0] : null;
    if (!host || !data.path) {
      res.status(502).json({ error: 'pCloud returned no host/path' });
      return;
    }

    const url = `https://${host}${data.path}`;
    // Cache briefly on the client only — pCloud's minted links themselves
    // expire, so don't let browsers/CDNs cache this response long-term.
    res.setHeader('Cache-Control', 'private, max-age=60');
    res.status(200).json({ url });
  } catch (e) {
    res.status(500).json({ error: String(e) });
  }
};
