// Copy static extension assets after TypeScript compilation.
import { cp, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

await mkdir("dist", { recursive: true });
for (const file of ["manifest.json", "sidepanel.html", "sidepanel.css"]) {
  await cp(`src/${file}`, `dist/${file}`);
}
await cp("src/icons", "dist/icons", { recursive: true });

const extensionDir = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(extensionDir, "..");
let apiToken = "";
try {
  const auth = JSON.parse(await readFile(resolve(projectRoot, ".runtime", "auth.json"), "utf8"));
  if (typeof auth.apiToken === "string") apiToken = auth.apiToken;
} catch {
  // The extension builds without credentials for source validation, but cannot call the API.
}
await writeFile(
  "dist/project-config.json",
  JSON.stringify(
    {
      projectRoot,
      apiToken,
      appId: "jp.clarith.local-api",
      protocolVersion: 1,
    },
    null,
    2,
  ),
  "utf8",
);
