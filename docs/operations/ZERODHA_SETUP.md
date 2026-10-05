# Zerodha (Kite Connect) setup — read-only Portfolio

Qfinera uses Kite Connect only to **read** a member's own holdings and
positions. It never places orders or changes the broker account.

## Redirect URL

Register exactly one redirect URL for the Kite Connect app, built from the
deployment's `FRONTEND_BASE_URL`:

| Environment | Redirect URL |
|---|---|
| Local | `http://localhost:3000/portfolio/zerodha/callback` |
| Production | `https://<production-domain>/portfolio/zerodha/callback` |

The production domain is not hardcoded anywhere; it is whatever
`FRONTEND_BASE_URL` points to.

## API configuration (`apps/api/.env`, never committed)

| Variable | Purpose |
|---|---|
| `ZERODHA_API_KEY`, `ZERODHA_API_SECRET` | Kite Connect app credentials |
| `BROKER_TOKEN_ENCRYPTION_SECRET` | Encrypts stored Kite access tokens (required to connect). Separate from `AI_KEY_ENCRYPTION_SECRET`. Use a long random value and keep it stable — changing it disconnects every member. |

Tokens stored before `BROKER_TOKEN_ENCRYPTION_SECRET` existed were encrypted
with `AI_KEY_ENCRYPTION_SECRET`; they are read once and re-encrypted under
the broker key automatically.

## Login flow and security

1. `GET /api/v1/portfolio/zerodha/connect` issues a single-use OAuth `state`
   (random, 10-minute TTL, bound to the member's user and session in Redis)
   and returns Kite's login URL with it in `redirect_params`.
2. Kite redirects to `/portfolio/zerodha/callback?request_token=…&state=…`.
   That page strips both from the address bar and POSTs them as JSON to
   `POST /api/v1/portfolio/zerodha/callback` (CSRF-protected).
3. The API consumes the state (rejecting missing, unknown, expired, reused,
   or other-session states) **before** sending the token to Kite.

Because the token travels in a POST body, the API server's access log never
records it. A reverse proxy in front of the **web** app would still see the
callback page's query string — configure it not to log query strings for
`/portfolio/zerodha/callback`.

## Known limitations

- Holding quantity = `quantity` (settled, T+2) + `t1_quantity`. Kite does not
  document how `collateral_quantity` relates to `quantity`, so it is never
  added. Verify against Zerodha Console with a real account.
- Disconnect deletes Qfinera's stored token; it does not call Kite's
  `DELETE /session/token`. Kite sessions also expire daily.
