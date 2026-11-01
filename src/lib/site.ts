// Shared site data: one place for URLs, navigation and the contact address,
// so naming stays consistent across nav, footer and pages.

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

/** Internal link that respects the configured base path (GitHub Pages). */
export function href(path: string): string {
  if (/^(?:[a-z]+:|#|\/\/)/i.test(path)) return path;
  return BASE + (path.startsWith("/") ? path : `/${path}`);
}

/** Path of the current page without the base, always with a trailing slash. */
export function pagePath(url: URL): string {
  const p = url.pathname.slice(BASE.length) || "/";
  return p.endsWith("/") ? p : `${p}/`;
}

export const MAIL = "info@entrosana.com";

// entrosana.app links go to the page itself: the bare origin answers with a
// redirect to /start. Two repositories, two sources: the engine behind the
// back office (entrosana/hub) and the Hub at entrosana.app (Giansn/entrosana-app).
export const ext = {
  hub: "https://entrosana.app/start",
  contribute: "https://entrosana.app/contribute",
  submit: "https://entrosana.app/contribute/submit",
  account: "https://entrosana.app/me",
  firstModule: "https://entrosana.app/modules/your-value-system",
  lp21Tool: "https://entrosana.app/tools/lehrplan21-citation",
  engineSource: "https://github.com/entrosana/hub",
  hubSource: "https://github.com/Giansn/entrosana-app",
  lp21: "https://github.com/entrosana/hub/tree/main/lp21-mcp",
  arboro: "https://arboro.entrosana.com/demo",
} as const;

/** Primary navigation. One name per area, used everywhere on the site. */
export const nav = [
  { href: "/service/", label: "Back office" },
  { href: "/modules/", label: "Modules" },
  { href: "/hub/", label: "Hub" },
  { href: "/roadmap/", label: "Roadmap" },
] as const;

/** Values of the "Interested in" field; `?interest=<id>` preselects one. */
export const interests = [
  { id: "accounting", label: "Back office · accounting" },
  { id: "hr", label: "Back office · HR & payroll" },
  { id: "consulting", label: "Back office · consulting" },
  { id: "hub", label: "Hub · co-created learning" },
  { id: "modules", label: "Modules · for our school or family" },
  { id: "contributing", label: "Contributing · connector or module" },
  { id: "partnership", label: "Partnership · foundation or research" },
  { id: "track", label: "Proposing · a new domain or track" },
] as const;
