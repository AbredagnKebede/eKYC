# Fayda Bank Portal (Next.js)

Per-bank staff console for Fast Forward gates, outbound/inbound queues, and RBAC.

## Local

```bash
cp .env.example .env.local
npm install
npm run dev
```

Set `API_PROXY_TARGET` to your local API (default in example: `http://127.0.0.1:8005`) so `/v1/*` rewrites work without CORS friction.

## Vercel

1. Import this GitHub repo in Vercel.
2. **Root Directory:** `bank-portal`
3. **Production Branch:** `bank-portal` (recommended) or `master`
4. Env var: `NEXT_PUBLIC_API_BASE_URL` = your Render API origin (e.g. `https://ekyc-api-jj0j.onrender.com`)

No rewrite target is required on Vercel; the browser calls the API origin directly.

## Auth (sandbox)

- Bank: `bank_cbe`
- Email: `super@cbe.portal.local`
- Password: `ChangeMeBankPortal1!` (or `BANK_PORTAL_BOOTSTRAP_PASSWORD`)
