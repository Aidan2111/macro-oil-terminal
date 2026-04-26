#!/usr/bin/env node
// Walk every {route}-{viewport}.json file in this directory, pull out
// the four core category scores (performance / accessibility /
// best-practices / SEO), and write a Markdown table to README.md.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const files = fs
  .readdirSync(__dirname)
  .filter((f) => f.endsWith(".json") && f !== "package.json");

const rows = files
  .map((file) => {
    try {
      const json = JSON.parse(
        fs.readFileSync(path.join(__dirname, file), "utf8"),
      );
      const cats = json.categories ?? {};
      const score = (k) =>
        Math.round(((cats[k]?.score ?? 0) * 100));
      const m = file.match(/^(.+)-(desktop|mobile)\.json$/);
      const route = m ? m[1] : file;
      const viewport = m ? m[2] : "—";
      return {
        route,
        viewport,
        perf: score("performance"),
        a11y: score("accessibility"),
        bp: score("best-practices"),
        seo: score("seo"),
      };
    } catch {
      return null;
    }
  })
  .filter(Boolean)
  .sort((a, b) =>
    a.route === b.route
      ? a.viewport.localeCompare(b.viewport)
      : a.route.localeCompare(b.route),
  );

const lines = [];
lines.push("# Wave 4 Lighthouse summary");
lines.push("");
lines.push("Run via `bash docs/perf/lighthouse-wave4/run.sh` from the");
lines.push("user's host (the agent's sandbox cannot reach the live SWA).");
lines.push("");
lines.push("| Route | Viewport | Perf | A11y | BP | SEO |");
lines.push("|-------|----------|-----:|-----:|---:|----:|");
for (const r of rows) {
  lines.push(
    `| ${r.route} | ${r.viewport} | ${r.perf} | ${r.a11y} | ${r.bp} | ${r.seo} |`,
  );
}
lines.push("");
lines.push("Targets: ≥90 perf / 100 a11y / 100 BP / 100 SEO.");

const outFile = path.join(__dirname, "README.md");
fs.writeFileSync(outFile, lines.join("\n") + "\n", "utf8");
console.log(`wrote ${outFile} (${rows.length} rows)`);
