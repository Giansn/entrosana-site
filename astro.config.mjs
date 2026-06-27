import { defineConfig } from 'astro/config';

// Production site lives behind a Tailscale Funnel on e14 for now; the canonical
// domain is entrosana.com. `site` is used for canonical URLs / sitemap.
export default defineConfig({
  site: 'https://entrosana.com',
  // format:'file' → dist/hub.html etc., so the sirv server resolves clean,
  // extensionless URLs (/hub) without trailing-slash redirects.
  build: { inlineStylesheets: 'auto', format: 'file' },
  // The preview server sits behind a Tailscale Funnel; allow its public host
  // (Vite blocks unknown Host headers by default as anti-DNS-rebinding).
  vite: {
    preview: { allowedHosts: ['e14-1.tailff64b5.ts.net'] },
    server: { allowedHosts: ['e14-1.tailff64b5.ts.net'] },
  },
});
