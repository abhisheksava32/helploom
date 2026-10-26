/** Joins class names, skipping falsy values, so conditional classes stay readable. */
export function cn(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}
