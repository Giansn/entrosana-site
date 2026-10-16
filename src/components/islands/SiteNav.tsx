import { useEffect, useRef, useState } from "preact/hooks";
import Mark from "./Mark";
import ThemeToggle from "./ThemeToggle";
import "../../styles/nav.css";

// Site header as one island (client:load), laid out as on entrosana.com:
// the header itself is the floating pill; brand, links, theme switch, then
// the call to action as a ghost pill. Below 760px: burger, theme switch,
// and a floating menu panel under the pill.
// Server-rendered first, so every link works before and without JS; with JS
// off the narrow-screen menu simply stays expanded (see nav.css).

export interface NavLink { href: string; label: string; current: boolean }
interface Props {
  home: string;
  homeCurrent: boolean;
  links: NavLink[];
  cta: { href: string; label: string; current: boolean };
}

const WIDE = "(min-width: 760px)";   // live breakpoint

export default function SiteNav({ home, homeCurrent, links, cta }: Props) {
  const [open, setOpen] = useState(false);
  const header = useRef<HTMLElement>(null);
  const burger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setOpen(false); burger.current?.focus(); }
    };
    const onClick = (e: MouseEvent) => {
      if (header.current && !header.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("click", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("click", onClick);
    };
  }, [open]);

  // growing past the breakpoint must not leave a stale open panel behind
  useEffect(() => {
    const mq = matchMedia(WIDE);
    const onChange = () => setOpen(false);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const close = () => setOpen(false);

  return (
    <header class="nav" data-open={String(open)} ref={header}>
      <div class="nav__bar">
        <a href={home} class="brand" aria-label="entrosana — home" aria-current={homeCurrent ? "page" : undefined}>
          <Mark size={40} class="brand__mark" />
          <span class="brand__word">entrosana</span>
        </a>

        <nav class="nav__menu" id="site-menu" aria-label="Primary">
          <ul class="nav__links">
            {links.map((l) => (
              <li key={l.href}>
                <a href={l.href} class="nav__link" aria-current={l.current ? "page" : undefined} onClick={close}>{l.label}</a>
              </li>
            ))}
            {/* the call to action as the last row of the open phone menu */}
            <li class="nav__cta-item">
              <a href={cta.href} class="nav__link nav__link--cta" aria-current={cta.current ? "page" : undefined} onClick={close}>{cta.label}</a>
            </li>
          </ul>
        </nav>

        <button
          ref={burger}
          class="nav__burger"
          type="button"
          aria-expanded={open}
          aria-controls="site-menu"
          onClick={() => setOpen(!open)}
        >
          <span class="vh">Menu</span>
          <span class="nav__burger-lines" aria-hidden="true" />
        </button>
        <ThemeToggle />
        <a href={cta.href} class="btn btn--ghost nav__cta" aria-current={cta.current ? "page" : undefined}>{cta.label}</a>
      </div>
    </header>
  );
}
