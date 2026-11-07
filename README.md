# entrosana-site

The website of [entrosana](https://entrosana.com): adaptive learning modules and open back-office tooling for educational organisations, with a sealed record underneath both. Swiss/EU data residency by design. The Hub itself is a separate application at [entrosana.app](https://entrosana.app) ([source](https://github.com/Giansn/entrosana-app)).

> **Status (2026-10-31):** ready to replace the WordPress site that serves entrosana.com today. Content and design were carried over from it, with a reworked structure (see [`docs/UX-AUDIT.md`](docs/UX-AUDIT.md)). How it goes live, and how to roll back: [`deploy/DEPLOY.md`](deploy/DEPLOY.md).

## Stack
- **Astro 5** (static MPA): real routes, static HTML by default
- **Preact islands** only for the interactive parts: header, menu and theme (`client:load`), the record illustration (`client:visible`), the forms (`client:idle` / `client:visible`). Everything else ships no JS.
- Hand-written CSS design system (`src/styles/global.css`), no Tailwind
- Self-hosted fonts: **Carlito** (metric twin of Calibri) for text, **Inconsolata** for labels and the wordmark. No third-party font calls.
- `server.mjs`: production server (sirv) with the canonical host, redirects, security headers and the 404 page

## Design
The brand of entrosana.com: graphite `#1b1e24` and cyan `#2bd4e8` in dark; in light, paper `#f5fffe` on a bright cyan ground `#CDEEF4`, with teal `#077183`; the spiral mark. Dark is the state without an attribute. Light comes only from the header toggle (`localStorage["entrosana-theme"]`); the OS preference does not switch the theme (owner's decision). All text pairs are at least 4.5:1 in both themes.

Signature element: the **record illustration** on the home page (`src/components/RecordChain.astro` + `islands/RecordChain.tsx`). Three log entries are sealed with real SHA-256; rewriting one makes the re-computed chain fail from that entry on.

## Routes
- `/`: home (modules and the back office, how we work, the Hub, where we stand, the record last)
- `/service/`: back office (tools, consulting, data boundary, connectors, where it runs `#deploy`, pilot)
- `/modules/`: learning modules (first module, three areas, request form; proposals go to the Hub)
- `/hub/`: the Learning Hub (entrosana.app)
- `/roadmap/`: what is built, what is not, in what order
- `/request-access/`: contact form (`?interest=<id>` preselects; ids in `src/lib/site.ts`)
- `/imprint/`, `/privacy/`, `/privacy/de/`: legal texts (`src/legal/`)
- `/sitemap.xml` (built from `src/pages/`), `/robots.txt`
- `/wp-content/uploads/…`: WordPress files that entrosana.app and others link to, kept at their old URLs
- `/tools`, `/learn`, `/hosted`, `/hybrid`, `/on-premises`: redirects from the June 2026 version

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
node server.mjs # serve dist/ as in production, http://127.0.0.1:4321
```

## Where it runs

| Address | How |
|---|---|
| `https://entrosana.com` | WordPress on e14 until the cutover in [`deploy/DEPLOY.md`](deploy/DEPLOY.md); afterwards this site, `server.mjs` on `127.0.0.1:4321`, behind the Cloudflare tunnel |
| `https://giansn.github.io/entrosana-site/` | GitHub Pages preview copy, built on every push to `master` (sub-path, `noindex`) |
| `https://e14-1.tailff64b5.ts.net/` | Tailscale Funnel to the same `127.0.0.1:4321` |

On e14 the site runs as `entrosana-site.service` (copy in [`deploy/`](deploy/entrosana-site.service)). `pnpm deploy` builds and restarts it; logs go to `~/.sygnif/logs/entrosana-site.log`.
