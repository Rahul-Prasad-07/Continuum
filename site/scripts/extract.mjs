// Faithful extractor: splits the original index.html into CSS, markup, and JS
// so the Next.js migration is byte-identical to the source. Run: node scripts/extract.mjs
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const html = readFileSync(join(root, "index.html"), "utf8");

// --- collect all <style> blocks (head reset + big body sheet), in order ---
const styleRe = /<style>([\s\S]*?)<\/style>/g;
const styles = [];
let m;
while ((m = styleRe.exec(html))) styles.push(m[1]);
const css = styles.join("\n\n");

// --- collect plain <script> blocks (skip the JSON-LD in <head>) ---
const scriptRe = /<script(?:\s+type="([^"]*)")?>([\s\S]*?)<\/script>/g;
const scripts = [];
let jsonld = null;
while ((m = scriptRe.exec(html))) {
  const type = m[1];
  const code = m[2];
  if (type === "application/ld+json") jsonld = code.trim();
  else if (!type) scripts.push(code.trim());
}

// --- extract body markup, stripped of <style>/<script>, for SSR injection ---
const bodyInner = html.match(/<body>([\s\S]*)<\/body>/)[1];
const markup = bodyInner
  .replace(/<style>[\s\S]*?<\/style>/g, "")
  .replace(/<script[\s\S]*?<\/script>/g, "")
  .trim();

const outDir = join(root, "generated");
mkdirSync(outDir, { recursive: true });

writeFileSync(join(root, "app", "globals.css"), css + "\n");
writeFileSync(
  join(outDir, "markup.ts"),
  "// AUTO-GENERATED from index.html by scripts/extract.mjs — do not edit by hand.\n" +
    "export const MARKUP = " +
    JSON.stringify(markup) +
    ";\n"
);
writeFileSync(
  join(outDir, "scripts.ts"),
  "// AUTO-GENERATED from index.html by scripts/extract.mjs — do not edit by hand.\n" +
    "// Each entry is the verbatim body of an original <script> IIFE.\n" +
    "export const SCRIPTS: string[] = " +
    JSON.stringify(scripts, null, 2) +
    ";\n"
);
writeFileSync(join(outDir, "jsonld.ts"), "export const JSONLD = " + JSON.stringify(jsonld) + ";\n");

console.log(
  `styles=${styles.length} scripts=${scripts.length} jsonld=${jsonld ? "yes" : "no"} markupBytes=${markup.length}`
);
