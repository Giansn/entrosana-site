import type { APIRoute } from "astro";

// One <url> per page in src/pages, so a new page cannot be left out. Kept out:
// the 404 page; the redirects from the June 2026 version are config, not pages.
// Paths end in a slash, like the canonical URLs in Layout.astro.
const pages = Object.keys(import.meta.glob("./**/*.astro"))
  .map((f) => f.replace(/^\.\//, "/").replace(/\.astro$/, "").replace(/(^|\/)index$/, "$1"))
  .filter((p) => p !== "/404")
  .map((p) => (p.endsWith("/") ? p : `${p}/`))
  .sort();

export const GET: APIRoute = ({ site }) => {
  const urls = pages.map((p) => `  <url><loc>${new URL(p, site)}</loc></url>`).join("\n");
  return new Response(
    `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`,
    { headers: { "Content-Type": "application/xml; charset=utf-8" } },
  );
};
