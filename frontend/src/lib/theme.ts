/**
 * Light and dark mode. The preference ("light", "dark" or "system") is a per browser
 * convenience kept in localStorage; the resolved theme lives on <html data-theme>.
 */

export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "helploom.theme";

export function readThemePreference(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    return "system";
  }
}

export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  if (preference !== "system") return preference;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyThemePreference(preference: ThemePreference): void {
  try {
    if (preference === "system") window.localStorage.removeItem(THEME_STORAGE_KEY);
    else window.localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // Storage can be blocked (private mode); the theme still applies for this page.
  }
  document.documentElement.dataset.theme = resolveTheme(preference);
}

/**
 * Runs inline in <head> before first paint so the page never flashes the wrong theme.
 * Kept as a string because it executes before React loads.
 */
export const themeInitScript = `(() => {
  try {
    var stored = localStorage.getItem("${THEME_STORAGE_KEY}");
    var dark = stored ? stored === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme = dark ? "dark" : "light";
  } catch (error) {}
})();`;
