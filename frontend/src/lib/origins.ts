/**
 * Client side twin of the server's origin rules (docs/API.md, PATCH /widget/config/):
 * scheme and host (and port) only, lower case, default ports dropped. The server
 * re-validates; this only gives instant feedback while typing.
 */
export function normalizeOrigin(raw: string): { origin: string } | { error: string } {
  const value = raw.trim();
  if (!value) return { error: "Enter an origin such as https://shop.example.com." };
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return { error: "Include the scheme, for example https://shop.example.com." };
  }
  if (url.protocol !== "https:" && url.protocol !== "http:") return { error: "Use an http or https origin." };
  if (url.username || url.password) return { error: "Origins cannot contain credentials." };
  if ((url.pathname && url.pathname !== "/") || url.search || url.hash) {
    return { error: "Use the origin only: no path, query or fragment." };
  }
  return { origin: `${url.protocol}//${url.host}`.toLowerCase() };
}

/**
 * Readable text colour on a #rrggbb brand colour: whichever of white or near black
 * has the higher WCAG contrast ratio against it. Shared with the widget bundle.
 */
export function contrastText(hex: string): "#ffffff" | "#0b0f19" {
  const match = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!match) return "#ffffff";
  const value = Number.parseInt(match[1], 16);
  const channel = (shift: number) => {
    const c = ((value >> shift) & 255) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  const luminance = 0.2126 * channel(16) + 0.7152 * channel(8) + 0.0722 * channel(0);
  const onWhite = 1.05 / (luminance + 0.05);
  const onDark = (luminance + 0.05) / 0.0555; // #0b0f19 has a relative luminance of about 0.0055
  return onWhite >= onDark ? "#ffffff" : "#0b0f19";
}
