// Production server for the built site (dist/): entrosana.com on e14, behind the
// Cloudflare tunnel, next to entrosana.app.
//
// sirv serves dist/ (gzip/brotli negotiation, ETags, ranges; Astro's /_astro/ files
// are content-hashed and cached for a year). Around it, what WordPress did for
// entrosana.com until the cutover:
//   · one origin: www and plain http answer 301 to https://entrosana.com
//   · one URL per page: /service answers 301 to /service/, as on WordPress
//   · real 301s for the redirects in astro.config.mjs (read from the built stubs)
//     and for WordPress-only addresses that may still be linked (?p=12, /feed/, …)
//   · security headers on every response
// Unknown paths get the built 404 page with status 404. sirv reads dist/ once at
// start: after a build, restart the service (deploy/DEPLOY.md).
import { createServer } from "node:http";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import sirv from "sirv";

const root = join(dirname(fileURLToPath(import.meta.url)), "dist");
const PORT = Number(process.env.PORT || 4321);
// Loopback only: cloudflared and the Tailscale Funnel both connect locally.
const HOST = process.env.HOST || "127.0.0.1";
const CANON = "entrosana.com";

// Only directives that cannot break the page: no framing, no plugins, no foreign
// <base>. A script-src policy would need the hashes of Astro's inline scripts.
const SECURITY = {
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
  "X-Frame-Options": "DENY",
  "Content-Security-Policy": "frame-ancestors 'none'; object-src 'none'; base-uri 'self'",
};

// WordPress page IDs (?p= and ?page_id=) and paths that only WordPress had.
const WP_IDS = { 7: "/", 12: "/service/", 13: "/hub/", 14: "/modules/", 15: "/request-access/", 16: "/imprint/", 17: "/privacy/", 112: "/roadmap/", 161: "/privacy/de/" };
const MOVED = new Map([["/wp-sitemap.xml", "/sitemap.xml"], ["/feed", "/"], ["/comments/feed", "/"]]);
// Astro writes each redirect as a stub page with a meta refresh: turn them into 301s.
for (const dir of existsSync(root) ? readdirSync(root, { withFileTypes: true }) : []) {
  if (!dir.isDirectory()) continue;
  try {
    const stub = readFileSync(join(root, dir.name, "index.html"), "utf8");
    const to = /^<!doctype html><title>Redirecting to: [^<]*<\/title><meta http-equiv="refresh" content="0;url=([^"]+)">/i.exec(stub);
    if (to) MOVED.set(`/${dir.name}`, to[1]);
  } catch { /* no index.html: not a page */ }
}

const serve = sirv(root, {
  etag: true,
  gzip: true,
  brotli: true,
  extensions: ["html"],
  setHeaders(res, pathname) {
    if (pathname.startsWith("/_astro/")) res.setHeader("Cache-Control", "public, max-age=31536000, immutable");
    else if (pathname.startsWith("/wp-content/uploads/")) res.setHeader("Cache-Control", "public, max-age=86400");
    // Pages and the rest: a new build shows at once, unchanged files come back as 304.
    else res.setHeader("Cache-Control", "no-cache");
  },
});

let notFound = "404 — not found\n";
try { notFound = readFileSync(join(root, "404.html"), "utf8"); } catch {}

const redirect = (res, to) => res.writeHead(301, { Location: to, "Content-Length": 0, "Cache-Control": "no-cache" }).end();

createServer((req, res) => {
  for (const [k, v] of Object.entries(SECURITY)) res.setHeader(k, v);
  if (req.method !== "GET" && req.method !== "HEAD") { res.writeHead(405, { Allow: "GET, HEAD", "Content-Length": 0 }).end(); return; }
  if (req.url === "/healthz") { res.writeHead(200, { "Content-Type": "text/plain" }).end("ok\n"); return; }

  // Host and scheme arrive unchanged through the tunnel: cloudflared passes the
  // Host header on, the Cloudflare edge sets X-Forwarded-Proto to the visitor's scheme.
  const host = String(req.headers.host || "").split(":")[0].toLowerCase();
  const proto = String(req.headers["x-forwarded-proto"] || "").toLowerCase();
  if (host === "www." + CANON || (host === CANON && proto === "http")) return redirect(res, `https://${CANON}${req.url}`);
  if (proto === "https") res.setHeader("Strict-Transport-Security", "max-age=31536000");

  const url = new URL(req.url, "http://x");
  const path = url.pathname.length > 1 ? url.pathname.replace(/\/+$/, "") : url.pathname;
  const id = url.pathname === "/" && (url.searchParams.get("p") || url.searchParams.get("page_id"));
  if (id && WP_IDS[id]) return redirect(res, WP_IDS[id]);
  if (MOVED.has(path)) return redirect(res, MOVED.get(path));
  if (!url.pathname.endsWith("/") && !/\.[a-z0-9]+$/i.test(path) && existsSync(join(root, path, "index.html")))
    return redirect(res, path + "/" + url.search);

  serve(req, res, () => {
    res.statusCode = 404;
    res.setHeader("Content-Type", `${notFound.startsWith("<") ? "text/html" : "text/plain"}; charset=utf-8`);
    res.setHeader("Cache-Control", "no-cache");
    res.end(notFound);
  });
}).listen(PORT, HOST, () => {
  console.log(`entrosana-site serving dist/ on http://${HOST}:${PORT} (${MOVED.size} redirects)`);
});
