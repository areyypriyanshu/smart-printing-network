// Check that the main bundle stays inside the budget.
//
// The budget is 250 KB gzipped, from FRONTEND_GUIDELINES section 11. The
// main bundle is the entry chunk and the chunks it imports, which is what
// a visitor downloads before the first route renders. The routes that are
// loaded lazily, such as the vendor board, are not counted, because they
// are not part of that first load.
//
// Run it after `npm run build`.

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const BUDGET_BYTES = 250 * 1024;

const here = dirname(fileURLToPath(import.meta.url));
const dist = join(here, "..", "dist");
const manifestPath = join(dist, ".vite", "manifest.json");

let manifest;
try {
  manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
} catch {
  console.error(
    `bundle-size: no build manifest at ${manifestPath}. Run npm run build first.`,
  );
  process.exit(1);
}

const entry = Object.values(manifest).find((chunk) => chunk.isEntry);
if (entry === undefined) {
  console.error("bundle-size: the build manifest has no entry chunk");
  process.exit(1);
}

const files = new Set();
const collect = (chunk) => {
  if (chunk === undefined || files.has(chunk.file)) return;
  files.add(chunk.file);
  for (const imported of chunk.imports ?? []) {
    collect(manifest[imported]);
  }
};
collect(entry);

let total = 0;
for (const file of files) {
  const code = readFileSync(join(dist, file));
  total += gzipSync(code, { level: 9 }).length;
}

const kilobytes = (total / 1024).toFixed(1);
console.log(
  `bundle-size: main bundle is ${kilobytes} KB gzipped across ${files.size} chunk(s)`,
);

if (total > BUDGET_BYTES) {
  console.error(
    `bundle-size: over the ${BUDGET_BYTES / 1024} KB budget by ${((total - BUDGET_BYTES) / 1024).toFixed(1)} KB`,
  );
  process.exit(1);
}

console.log(`bundle-size: inside the ${BUDGET_BYTES / 1024} KB budget`);
