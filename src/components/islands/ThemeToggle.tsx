import { useEffect, useState } from "preact/hooks";

// Light/dark switch. The default follows the operating system; a click sets
// an explicit choice that is remembered (same storage key as the live site).
// Icons are switched by CSS from the root theme, so they are right on first
// paint; the island only adds the click and the pressed state.
const KEY = "entrosana-theme";

function effectiveDark(): boolean {
  const t = document.documentElement.getAttribute("data-theme");
  return t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
}

export default function ThemeToggle() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    setDark(effectiveDark());
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setDark(effectiveDark());
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const toggle = () => {
    const next = effectiveDark() ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem(KEY, next); } catch { /* private mode: choice lasts this page */ }
    setDark(next === "dark");
  };

  return (
    <button
      class="theme"
      type="button"
      aria-pressed={dark}
      title={dark ? "Switch to light theme" : "Switch to dark theme"}
      onClick={toggle}
    >
      <span class="vh">Dark theme</span>
      <svg class="theme__sun" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
        <circle cx="12" cy="12" r="4.2" fill="none" stroke="currentColor" stroke-width="1.8" />
        <path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
      </svg>
      <svg class="theme__moon" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
        <path d="M20 14.6A8 8 0 0 1 9.4 4 8 8 0 1 0 20 14.6Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" />
      </svg>
    </button>
  );
}
