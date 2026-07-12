// Minimal Google service-account OAuth (JWT bearer flow) using only Node's
// built-in crypto module — no googleapis / google-auth-library dependency.
//
// Requires two env vars (set these in the Vercel project settings):
//   GOOGLE_SERVICE_ACCOUNT_EMAIL  — the service account's client_email
//   GOOGLE_PRIVATE_KEY            — the service account's private_key
//                                    (paste with literal \n between lines,
//                                    this code un-escapes them)
//
// The target Google Sheet must be shared with GOOGLE_SERVICE_ACCOUNT_EMAIL
// as an Editor, or the API calls below will get a 403.

const crypto = require('crypto');

function base64url(input) {
  return Buffer.from(input)
    .toString('base64')
    .replace(/=/g, '')
    .replace(/\+/g, '-')
    .replace(/\//g, '_');
}

let cachedToken = null;
let cachedExpiry = 0;

async function getAccessToken() {
  const now = Math.floor(Date.now() / 1000);
  if (cachedToken && now < cachedExpiry - 60) {
    return cachedToken; // reuse until ~1 min before expiry
  }

  const email = process.env.GOOGLE_SERVICE_ACCOUNT_EMAIL;
  const rawKey = process.env.GOOGLE_PRIVATE_KEY;
  if (!email || !rawKey) {
    throw new Error(
      'Missing GOOGLE_SERVICE_ACCOUNT_EMAIL or GOOGLE_PRIVATE_KEY env vars'
    );
  }
  const privateKey = rawKey.replace(/\\n/g, '\n');

  const header = { alg: 'RS256', typ: 'JWT' };
  const claims = {
    iss: email,
    scope: 'https://www.googleapis.com/auth/spreadsheets',
    aud: 'https://oauth2.googleapis.com/token',
    iat: now,
    exp: now + 3600,
  };
  const unsigned = `${base64url(JSON.stringify(header))}.${base64url(
    JSON.stringify(claims)
  )}`;

  const signer = crypto.createSign('RSA-SHA256');
  signer.update(unsigned);
  signer.end();
  const signature = signer
    .sign(privateKey)
    .toString('base64')
    .replace(/=/g, '')
    .replace(/\+/g, '-')
    .replace(/\//g, '_');
  const jwt = `${unsigned}.${signature}`;

  const res = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
      assertion: jwt,
    }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(`Google auth failed: ${JSON.stringify(data)}`);
  }
  cachedToken = data.access_token;
  cachedExpiry = now + (data.expires_in || 3600);
  return cachedToken;
}

module.exports = { getAccessToken };
