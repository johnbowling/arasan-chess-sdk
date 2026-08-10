#!/usr/bin/env node

import { createHash } from "node:crypto";
import { cp, mkdir, mkdtemp, readdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const repoDir = resolve(scriptDir, "../..");
const [deviceInput, simulatorInput, distInput, deploymentTarget] = process.argv.slice(2);
const upstream = JSON.parse(await readFile(join(repoDir, "sdk", "upstream.json"), "utf8"));

if (!deviceInput || !simulatorInput || !distInput || !deploymentTarget) {
  console.error(
    "usage: package.mjs <device-library> <simulator-library> <dist-dir> <deployment-target>",
  );
  process.exit(2);
}

const deviceLibrary = resolve(deviceInput);
const simulatorLibrary = resolve(simulatorInput);
const distDir = resolve(distInput);
const expectedDefault = join(repoDir, "dist", "apple");
const expectedOverride = process.env.ARASAN_APPLE_DIST_DIR
  ? resolve(process.env.ARASAN_APPLE_DIST_DIR)
  : expectedDefault;

if (
  distDir !== expectedOverride ||
  distDir === dirname(distDir) ||
  distDir === process.env.HOME ||
  distDir === repoDir ||
  distDir === dirname(repoDir)
) {
  throw new Error(`refusing to replace unexpected distribution path: ${distDir}`);
}

const stagingDir = await mkdtemp(join(tmpdir(), "arasan-apple-package-"));
await mkdir(join(stagingDir, "include"), { recursive: true });
await mkdir(join(stagingDir, "resources"), { recursive: true });

await cp(join(repoDir, "src", "embed", "arasan_embed.h"), join(stagingDir, "include", "arasan_embed.h"));
await cp(join(scriptDir, "include", "module.modulemap"), join(stagingDir, "include", "module.modulemap"));
await cp(
  join(repoDir, upstream.network.sourcePath),
  join(stagingDir, "resources", upstream.network.packagedName),
);
await cp(
  join(repoDir, upstream.openingBook.sourcePath),
  join(stagingDir, "resources", upstream.openingBook.packagedName),
);
await cp(join(repoDir, "LICENSE"), join(stagingDir, "LICENSE"));
await cp(join(repoDir, "doc", "APPLE.md"), join(stagingDir, "README.md"));
await cp(join(repoDir, "doc", "PROVENANCE.md"), join(stagingDir, "PROVENANCE.md"));

const xcframework = join(stagingDir, "Arasan.xcframework");
const createResult = spawnSync(
  "xcodebuild",
  [
    "-create-xcframework",
    "-library",
    deviceLibrary,
    "-headers",
    join(stagingDir, "include"),
    "-library",
    simulatorLibrary,
    "-headers",
    join(stagingDir, "include"),
    "-output",
    xcframework,
  ],
  { encoding: "utf8" },
);
if (createResult.status !== 0) {
  process.stderr.write(createResult.stdout ?? "");
  process.stderr.write(createResult.stderr ?? "");
  await rm(stagingDir, { recursive: true, force: true });
  process.exit(createResult.status ?? 1);
}

await rm(join(stagingDir, "include"), { recursive: true, force: true });

async function collectFiles(directory) {
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await collectFiles(path)));
    } else if (entry.isFile() && entry.name !== "manifest.json") {
      files.push(path);
    }
  }
  return files.sort();
}

const files = await collectFiles(stagingDir);
const artifacts = {};
for (const path of files) {
  const data = await readFile(path);
  artifacts[relative(stagingDir, path).split(sep).join("/")] = {
    bytes: data.length,
    sha256: createHash("sha256").update(data).digest("hex"),
  };
}

const xcodeVersion = spawnSync("xcodebuild", ["-version"], { encoding: "utf8" });
const sourceCommit = spawnSync("git", ["-C", repoDir, "rev-parse", "HEAD"], {
  encoding: "utf8",
}).stdout.trim();
const sourceStatus = spawnSync("git", ["-C", repoDir, "status", "--porcelain"], {
  encoding: "utf8",
}).stdout.trim();
const manifest = {
  formatVersion: 1,
  package: "arasan-chess-sdk-apple",
  arasanVersion: upstream.engineVersion,
  minimumIOSVersion: deploymentTarget,
  networkFile: `resources/${upstream.network.packagedName}`,
  openingBookFile: `resources/${upstream.openingBook.packagedName}`,
  upstream: {
    repository: upstream.repository,
    tag: upstream.tag,
    sourceCommit: upstream.sourceCommit,
  },
  source: {
    repository: "https://github.com/johnbowling/arasan-chess-sdk.git",
    commit: sourceCommit,
    dirty: sourceStatus.length > 0,
  },
  toolchain: xcodeVersion.stdout.trim().split("\n"),
  artifacts,
};
await writeFile(join(stagingDir, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
await rm(distDir, { recursive: true, force: true });
await mkdir(dirname(distDir), { recursive: true });
await cp(stagingDir, distDir, { recursive: true });
await rm(stagingDir, { recursive: true, force: true });

console.log(`${basename(xcframework)} packaged with ${Object.keys(artifacts).length} checksummed files`);
