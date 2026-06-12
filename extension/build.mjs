// Copy static extension assets after TypeScript compilation.
import { cp, mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

await mkdir("dist", { recursive: true });
for (const file of ["manifest.json", "sidepanel.html", "sidepanel.css"]) {
  await cp(`src/${file}`, `dist/${file}`);
}
await cp("src/icons", "dist/icons", { recursive: true });

const extensionDir = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(extensionDir, "..");
await writeFile(
  "dist/project-config.json",
  JSON.stringify({ projectRoot }, null, 2),
  "utf8",
);
