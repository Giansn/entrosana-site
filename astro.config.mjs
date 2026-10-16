import { defineConfig } from 'astro/config';
import preact from '@astrojs/preact';

// Redirect targets are written as-is, so they carry the base path themselves.
const B = (process.env.ASTRO_BASE || '').replace(/\/$/, '');

// Canonical domain is entrosana.com. `site` feeds canonical URLs and OG tags and
// stays fixed, so every copy of the build (e14 preview, GitHub Pages backup)
// points search engines at the one canonical origin.
//
// ASTRO_BASE serves the build from a sub-path. The Pages workflow passes the
// base path from actions/configure-pages (e.g. "/entrosana-site" for the
// project page without a custom domain); everywhere else it is "/".
// Internal links go through `href()` in src/lib/site.ts so they follow it.
export default defineConfig({
  site: 'https://entrosana.com',
  base: process.env.ASTRO_BASE || '/',
  // Interactive parts are Preact islands (src/components/islands); every
  // other component renders to static HTML and ships no JavaScript.
  integrations: [preact()],
  // format:'directory' → dist/service/index.html, served at /service/ by both
  // GitHub Pages and sirv — the same trailing-slash URLs the live site uses,
  // so existing inbound links keep working.
  build: { inlineStylesheets: 'auto', format: 'directory' },
  // Hover/focus prefetch: subpages load near-instantly on click.
  prefetch: { prefetchAll: true, defaultStrategy: 'hover' },
  // Routes from the June 2026 version of this site, kept as redirects so old
  // links land on the page that now carries their content.
  redirects: {
    '/tools': `${B}/service/`,
    '/learn': `${B}/modules/`,
    '/hosted': `${B}/service/#deploy`,
    '/hybrid': `${B}/service/#deploy`,
    '/on-premises': `${B}/service/#deploy`,
  },
  // The preview server sits behind a Tailscale Funnel; allow its public host
  // (Vite blocks unknown Host headers by default as anti-DNS-rebinding).
  vite: {
    preview: { allowedHosts: ['e14-1.tailff64b5.ts.net'] },
    server: { allowedHosts: ['e14-1.tailff64b5.ts.net'] },
  },
});
