// Production static server for the built site (dist/).
// sirv: gzip/brotli negotiation, immutable caching for hashed assets, clean
// URLs (extensionless via build.format='file'). No Host allowlist — safe to
// sit behind the Tailscale Funnel. Bound to 0.0.0.0 for tailnet + funnel.
import { createServer } from "node:http";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import sirv from "sirv";

const root = join(dirname(fileURLToPath(import.meta.url)), "dist");
const PORT = Number(process.env.PORT || 4321);
const HOST = process.env.HOST || "0.0.0.0";

const serve = sirv(root, {
  etag: true,
  gzip: true,
  brotli: true,
  extensions: ["html"],
  setHeaders(res, pathname) {
    // Astro emits content-hashed files under /_astro — cache them hard.
    if (pathname.startsWith("/_astro/")) {
      res.setHeader("Cache-Control", "public, max-age=31536000, immutable");
    }
  },
});

createServer((req, res) => {
  serve(req, res, () => {
    res.statusCode = 404;
    res.setHeader("Content-Type", "text/plain; charset=utf-8");
    res.end("404 — not found\n");
  });
}).listen(PORT, HOST, () => {
  console.log(`entrosana-site serving dist/ on http://${HOST}:${PORT}`);
});
