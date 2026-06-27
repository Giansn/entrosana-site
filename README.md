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

## Hosting
Served from e14 via `tailscale funnel` (preview) for now; canonical domain `entrosana.com`. The live EC2 site is untouched until an explicit DNS cutover.
