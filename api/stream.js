// GET /api/stream?code=<pCloud public link code>&fileid=<fileid>
//
// pCloud ties a minted download link to the IP address that requested it
// (via getpublinkdownload). If we mint the link on the server and then hand
// the raw URL to the browser, the browser's IP won't match and pCloud
// returns "410 Gone". So instead this endpoint does BOTH steps itself —
// mint the link AND fetch the actual file bytes — from the same server IP,
// then streams the response straight through to the browser. The browser
// never sees a pCloud URL, just this endpoint.
//
// Supports Range requests so video/audio seeking still works.

module.exports = async (req, res) => {
  const { code, fileid } = req.query || {};
  if (!code || !fileid) {
    res.status(400).json({ error: 'code and fileid are required' });
    return;
  }

  try {
    const mintUrl = `https://api.pcloud.com/getpublinkdownload?code=${encodeURIComponent(
      code
    )}&fileid=${encodeURIComponent(fileid)}`;
    const mintRes = await fetch(mintUrl);
    const mintData = await mintRes.json();

    if (mintData.result !== 0) {
      res
        .status(502)
        .json({ error: `pCloud error ${mintData.result}: ${mintData.error || ''}` });
      return;
    }

    const host = Array.isArray(mintData.hosts) ? mintData.hosts[0] : null;
    if (!host || !mintData.path) {
      res.status(502).json({ error: 'pCloud returned no host/path' });
      return;
    }
    const fileUrl = `https://${host}${mintData.path}`;

    // Forward the Range header (if any) so the browser can seek.
    const forwardHeaders = {};
    if (req.headers.range) forwardHeaders.range = req.headers.range;

    const fileRes = await fetch(fileUrl, { headers: forwardHeaders });

    if (!fileRes.ok && fileRes.status !== 206) {
      res
        .status(fileRes.status)
        .json({ error: `pCloud file server returned ${fileRes.status}` });
      return;
    }

    res.status(fileRes.status);
    const passthroughHeaders = [
      'content-type',
      'content-length',
      'content-range',
      'accept-ranges',
    ];
    for (const h of passthroughHeaders) {
      const v = fileRes.headers.get(h);
      if (v) res.setHeader(h, v);
    }
    if (!fileRes.headers.get('accept-ranges')) {
      res.setHeader('Accept-Ranges', 'bytes');
    }
    // Fresh mint every request, and content itself never changes for a
    // given fileid, so a short private cache is fine and saves re-minting
    // on repeated seeks within the same viewing session.
    res.setHeader('Cache-Control', 'private, max-age=120');

    if (!fileRes.body) {
      res.end();
      return;
    }

    const reader = fileRes.body.getReader();
    res.on('close', () => {
      try {
        reader.cancel();
      } catch {
        // ignore
      }
    });

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      res.write(Buffer.from(value));
    }
    res.end();
  } catch (e) {
    if (!res.headersSent) {
      res.status(500).json({ error: String(e) });
    } else {
      res.end();
    }
  }
};
