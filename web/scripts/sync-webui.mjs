// Copy the Next static export (web/out) into the Python package's webui folder,
// which FastAPI serves at "/". Run after `next build` (see `build:webui`).
import { cpSync, existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const out = resolve(here, "..", "out");
const dest = resolve(here, "..", "..", "src", "code_intel", "webui");

if (!existsSync(out)) {
  console.error(`No export found at ${out} — run \`next build\` first.`);
  process.exit(1);
}

rmSync(dest, { recursive: true, force: true });
mkdirSync(dest, { recursive: true });
cpSync(out, dest, { recursive: true });
// Keep the tracked directory placeholder; the built assets themselves are
// git-ignored (see .gitignore).
writeFileSync(resolve(dest, ".gitkeep"), "");
console.log(`Synced ${out} -> ${dest}`);
