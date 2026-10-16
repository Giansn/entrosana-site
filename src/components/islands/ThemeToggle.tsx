import { useEffect, useState } from "preact/hooks";

// Dark/light switch, as on the live site: dark is the state without an
// attribute, light is [data-theme="light"], the choice is remembered under
// the live storage key. The OS preference is not consulted (owner's decision).
// The glyph is the live one (◐) and the same in both themes; the island
// adds the click and the pressed state.
const KEY = "entrosana-theme";
const isLight = () => document.documentElement.getAttribute("data-theme") === "light";

export default function ThemeToggle() {
  const [light, setLight] = useState(false);
  useEffect(() => setLight(isLight()), []);

  const toggle = () => {
    const root = document.documentElement;
    const next = !isLight();
    if (next) root.setAttribute("data-theme", "light");
    else root.removeAttribute("data-theme");
    try { localStorage.setItem(KEY, next ? "light" : "dark"); } catch { /* private mode: choice lasts this page */ }
    setLight(next);
  };

  return (
    <button
      class="theme"
      type="button"
      aria-pressed={light}
      title={light ? "Switch to dark theme" : "Switch to light theme"}
      onClick={toggle}
    >
      <span class="vh">Light theme</span>
      <span class="theme__glyph" aria-hidden="true">◐</span>
    </button>
  );
}
