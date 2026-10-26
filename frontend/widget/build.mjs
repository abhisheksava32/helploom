// Bundles widget/src into public/widget.js: one small, dependency free IIFE that
// customers load with a script tag. Run with --watch during development.
import { build, context } from "esbuild";
import { statSync } from "node:fs";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const outfile = "public/widget.js";

const options = {
  absWorkingDir: root,
  entryPoints: ["widget/src/index.ts"],
  outfile,
  bundle: true,
  format: "iife",
  platform: "browser",
  target: ["es2020"],
  minify: true,
  legalComments: "none",
  banner: { js: "/* Helploom website widget. Source: frontend/widget/src. */" },
  logLevel: "warning",
};

if (process.argv.includes("--watch")) {
  const ctx = await context({ ...options, logLevel: "info" });
  await ctx.watch();
  console.log("Watching widget/src for changes...");
} else {
  await build(options);
  const kb = (statSync(new URL(`../${outfile}`, import.meta.url)).size / 1024).toFixed(1);
  console.log(`widget: ${outfile} ${kb} KB`);
}
