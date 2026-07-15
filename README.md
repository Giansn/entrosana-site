# entrosana-site

Marketing site for [entrosana](https://entrosana.com) — Deterministic Language Models for back-office work. Swiss-hosted, audit-grade, built on CashCtrl.

Rebuilt 2026-06-27 as a proper Astro project after the previous deploy turned out to be an orphaned single-file bundle with no source under version control.

## Stack
- **Astro** (static MPA) — real routes/subpages, minimal JS
- Hand-authored CSS design system (`src/styles/global.css`), no Tailwind
- Self-hosted fonts via `@fontsource` (no third-party font calls — fits Swiss data-residency posture)

## Design
"The signed record." Monospace (Geist Mono) as the display voice — determinism = exactness; Hanken Grotesk body; Newsreader serif italic reserved for the human-review moments. Cool paper `#F4F5F3`, ink `#16181D`, one ink-blue "seal" accent `#2742E0` tied to the signed audit trail. Signature element: the interactive **determinism receipt** in the hero (`src/components/Receipt.astro`) — same input → identical SHA-256 every run; the stochastic toggle drifts.

## Routes
- `/` — home (hero receipt, audit thesis, deployment summary, hub teaser)
- `/hub` — the foundation: review tiers, propose-a-track, shared runway
- `/hosted`, `/hybrid`, `/on-premises` — the three deployment models

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
| **`https://entrosana.com`** | **GitHub Pages** (this repo → Actions → Pages) | **stays up** |
| **`https://e14-1.tailff64b5.ts.net/`** | Tailscale Funnel → e14 `:4321` | down with e14 |
| **e14 LAN / preview** | `entrosana-site.service` → `node server.mjs` on `:4321` | local only |

### e14 (preview / Funnel)
- **`entrosana-site.service`** runs `node server.mjs` (sirv) on `:4321`.
  Tracked copy: [`deploy/entrosana-site.service`](deploy/entrosana-site.service).
- **Linger** so it survives reboot without login.
- Funnel root path `/` → `127.0.0.1:4321` (Arboro paths on the same host are untouched).

### GitHub Pages (canonical public domain)
- Workflow: [`.github/workflows/pages.yml`](.github/workflows/pages.yml)
- `public/CNAME` → `entrosana.com` (copied into `dist/` on build)
- GitHub provisions Let’s Encrypt for the custom domain once DNS points at Pages

### Deploy
```sh
pnpm deploy        # rebuild on e14 + restart systemd (Funnel/preview)
git push origin master   # publishes Pages (entrosana.com) via Actions
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
