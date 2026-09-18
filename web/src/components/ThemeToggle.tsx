import { useEffect, useState } from "react";
import { Moon, Sun } from "./icons";

type Theme = "light" | "dark";

const STORAGE_KEY = "upv-auto-theme";

/** Page background per theme: what the phone's status bar should match. */
const STATUS_BAR = { light: "#eef1f6", dark: "#1c202b" } as const;

function initialTheme(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(STORAGE_KEY, theme);
    // The app switches theme itself, so prefers-color-scheme metas would lie.
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute("content", STATUS_BAR[theme]);
  }, [theme]);

  const toggle = () => {
    // Colours cross-fade only during the switch, so hover stays instant.
    const root = document.documentElement;
    root.classList.add("theming");
    window.setTimeout(() => root.classList.remove("theming"), 360);
    setTheme((current) => (current === "dark" ? "light" : "dark"));
  };

  const label = theme === "dark" ? "Cambiar a modo claro" : "Cambiar a modo oscuro";

  return (
    <button className="toggle" type="button" onClick={toggle} aria-label={label} title={label}>
      <span className="track-icon" style={{ left: 12 }}>
        <Sun />
      </span>
      <span className="track-icon" style={{ right: 12 }}>
        <Moon />
      </span>
      <span className="knob">
        <span className="ico sun">
          <Sun />
        </span>
        <span className="ico moon">
          <Moon />
        </span>
      </span>
    </button>
  );
}
