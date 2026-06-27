import { defineConfig } from 'astro/config';

// Production site lives behind a Tailscale Funnel on e14 for now; the canonical
// domain is entrosana.com. `site` is used for canonical URLs / sitemap.
export default defineConfig({
  site: 'https://entrosana.com',
  build: { inlineStylesheets: 'auto' },
});
