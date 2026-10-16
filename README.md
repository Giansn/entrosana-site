# entrosana-site

Marketing site for [entrosana](https://entrosana.com) — adaptive learning modules and open back-office tooling for educational organisations, with a sealed record underneath both. Swiss/EU data residency by design.

> **Status (2026-10-16): prototype.** entrosana.com is currently served by WordPress. This repo carries the same content with a reworked UX (see [`docs/UX-AUDIT.md`](docs/UX-AUDIT.md)). Nothing here goes live until the owner approves.

## Stack
- **Astro 5** (static MPA) — real routes, static HTML by default
- **Preact islands** for the interactive parts only: header/menu/theme (`client:load`), record illustration (`client:visible`), forms (`client:idle` / `client:visible`). Everything else ships no JS.
- Hand-authored CSS design system (`src/styles/global.css`), no Tailwind
- Self-hosted fonts via `@fontsource`: **Carlito** (metric twin of Calibri) for text, **Inconsolata** for labels and the wordmark — no third-party font calls

## Design
Brand as on entrosana.com: graphite `#1b1e24` and cyan `#2bd4e8` (dark), cyan-tinted paper `#eef7f8` and teal `#077183` (light), the spiral mark. The theme follows the OS; the header toggle overrides it (`localStorage["entrosana-theme"]`). All text pairs ≥ 4.5:1 in both themes.
Signature element: the **record illustration** on the home page (`src/components/RecordChain.astro` + `islands/RecordChain.tsx`) — three log entries sealed with real SHA-256; rewriting one makes the re-computed chain fail from that entry on.

## Routes
- `/` — home: two services, the record, how we work, the Hub, where we stand
- `/service/` — back office: tools, consulting, data boundary, connectors, where it runs (`#deploy`), pilot
- `/modules/` — learning modules: first module, three areas, request/propose form
- `/hub/` — the Learning Hub (entrosana.app)
- `/roadmap/` — what is built, what is not, in what order
- `/request-access/` — contact form (`?interest=<id>` preselects, ids in `src/lib/site.ts`)
- `/imprint/`, `/privacy/`, `/privacy/de/` — legal texts, verbatim from the live site (`src/legal/`)
- `/tools`, `/learn`, `/hosted`, `/hybrid`, `/on-premises` — redirects from the June 2026 version

## Build-time settings
| Variable | Effect |
|---|---|
| `ASTRO_BASE` | Serve from a sub-path (the Pages workflow sets it from `actions/configure-pages`) |
| `PUBLIC_CONTACT_ENDPOINT` | Forms POST JSON (`name, org, email, interest, msg`) here. Unset: forms open the visitor's mail app with the message filled in |
| `ASTRO_NOINDEX=1` | Adds `noindex` (sub-path builds get it automatically) |

## Develop
```sh
pnpm install
pnpm dev        # http://localhost:4321
pnpm build      # → dist/
pnpm preview    # serve dist/
```

## Hosting (two front doors — do not conflate)

| Surface | How | When laptop is off |
|---------|-----|--------------------|
| **`https://entrosana.com`** | WordPress behind Cloudflare — **not served from this repo** (as of 2026-10-16) | stays up |
| **`https://giansn.github.io/entrosana-site/`** | GitHub Pages (this repo → Actions → Pages, on push to `master`) | stays up |
| **`https://e14-1.tailff64b5.ts.net/`** | Tailscale Funnel → e14 `:4321` | down with e14 |
| **e14 LAN / preview** | `entrosana-site.service` → `node server.mjs` on `:4321` | local only |

### e14 (preview / Funnel)
- **`entrosana-site.service`** runs `node server.mjs` (sirv) on `:4321`.
  Tracked copy: [`deploy/entrosana-site.service`](deploy/entrosana-site.service).
- **Linger** so it survives reboot without login.
- Funnel root path `/` → `127.0.0.1:4321` (Arboro paths on the same host are untouched).

### GitHub Pages (optional backup only — no custom domain)
- Workflow: [`.github/workflows/pages.yml`](.github/workflows/pages.yml) — runs on push to `master` only
- Live at https://giansn.github.io/entrosana-site/ (HTTPS works here); built with the `/entrosana-site` base path, so assets and links resolve
- **Do not** set Pages custom domain to `entrosana.com` unless DNS A records point at GitHub Pages IPs — otherwise GH shows “domain not properly configured for HTTPS”
- **Canonical production on e14:** see `deploy/edge/` (Caddy on LAN :443 → :4321)

### Deploy
```sh
pnpm deploy        # rebuild on e14 + restart systemd (Funnel/preview)
git push origin master   # publishes the GitHub Pages copy via Actions (not entrosana.com)
# logs (e14):  ~/.sygnif/logs/entrosana-site.log
```

### DNS (GoDaddy — NS is domaincontrol.com)
**Do not change MX/TXT** (ProtonMail). Only replace the dead EC2 **A** for the web apex.

Apex (required for GitHub Pages + HTTPS):
```
A   @     185.199.108.153
A   @     185.199.109.153
A   @     185.199.110.153
A   @     185.199.111.153
```
www (optional):
```
CNAME  www  giansn.github.io
```
Remove the old apex **A** `3.64.28.14` (EC2 EIP — ports 80/443 are dead; EC2 itself is unrelated SYGNIF infra, leave the EIP alone, only DNS).

After DNS propagates: GitHub repo → Settings → Pages → Custom domain `entrosana.com` → Enforce HTTPS.

e14 unbound still split-horizons `entrosana.com` → tailnet (local preview of the systemd build). To see the public Pages origin from e14: `curl --resolve entrosana.com:443:185.199.108.153 https://entrosana.com/`.
