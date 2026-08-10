#!/usr/bin/env node

import { stat, readFile } from "node:fs/promises";
import { resolve } from "node:path";
import {
  command,
  commandBytes,
  parseStableTag,
  readManifest,
  repoDir,
  sha256,
  sha256Bytes,
} from "./common.mjs";

const manifest = await readManifest();
const failures = [];
const expect = (condition, message) => {
  if (!condition) failures.push(message);
};

expect(manifest.schemaVersion === 1, "unsupported manifest schema");
expect(parseStableTag(manifest.tag), `invalid stable tag: ${manifest.tag}`);
expect(manifest.tag === `v${manifest.engineVersion}`, "tag and engine version differ");

const tagType = command("git", ["cat-file", "-t", manifest.tag]);
const tagObject = command("git", ["rev-parse", manifest.tag]);
const sourceCommit = command("git", ["rev-list", "-n", "1", manifest.tag]);
expect(tagType === "tag", `${manifest.tag} is not annotated`);
expect(tagObject === manifest.tagObject, "tag object does not match manifest");
expect(sourceCommit === manifest.sourceCommit, "source commit does not match manifest");
try {
  command("git", ["merge-base", "--is-ancestor", manifest.sourceCommit, "HEAD"]);
} catch {
  failures.push("manifest source commit is not an ancestor of HEAD");
}

const upstreamCmake = command("git", ["show", `${manifest.tag}:src/CMakeLists.txt`]);
const cmakeVersion = /add_compile_definitions\(ARASAN_VERSION=([^\s\)]+)\)/.exec(upstreamCmake)?.[1];
const cmakeNetwork = /set\(NETWORK\s+([^\s\)]+)\s+CACHE/.exec(upstreamCmake)?.[1];
expect(cmakeVersion === manifest.engineVersion, "src/CMakeLists.txt version differs");
expect(`network/${cmakeNetwork}` === manifest.network.sourcePath, "network name differs");

const upstreamMakefile = command("git", ["show", `${manifest.tag}:src/Makefile`]);
const makeVersion = /^VERSION\s*=\s*(\S+)/m.exec(upstreamMakefile)?.[1];
const makeNetwork = /^NETWORK\s*\?=\s*(\S+)/m.exec(upstreamMakefile)?.[1];
expect(makeVersion === manifest.engineVersion, "src/Makefile version differs");
expect(`network/${makeNetwork}` === manifest.network.sourcePath, "src/Makefile network differs");

const networkPath = resolve(repoDir, manifest.network.sourcePath);
const networkStat = await stat(networkPath);
const taggedNetwork = commandBytes("git", [
  "show",
  `${manifest.tag}:${manifest.network.sourcePath}`,
]);
expect(networkStat.size === manifest.network.bytes, "network size differs");
expect((await sha256(networkPath)) === manifest.network.sha256, "network checksum differs");
expect(taggedNetwork.length === manifest.network.bytes, "tagged network size differs");
expect(sha256Bytes(taggedNetwork) === manifest.network.sha256, "tagged network checksum differs");
const taggedLicense = commandBytes("git", [
  "show",
  `${manifest.tag}:${manifest.license.sourcePath}`,
]);
expect(
  (await sha256(resolve(repoDir, manifest.license.sourcePath))) === manifest.license.sha256,
  "license checksum differs",
);
expect(sha256Bytes(taggedLicense) === manifest.license.sha256, "tagged license checksum differs");

for (const path of ["FORK.md", "doc/PROVENANCE.md"]) {
  const contents = await readFile(resolve(repoDir, path), "utf8");
  expect(contents.includes(manifest.tag), `${path} does not reference ${manifest.tag}`);
}
const delta = await readFile(resolve(repoDir, "doc/UPSTREAM-DELTA.md"), "utf8");
expect(
  delta.includes(`Arasan ${manifest.engineVersion}`),
  `doc/UPSTREAM-DELTA.md does not reference Arasan ${manifest.engineVersion}`,
);

if (failures.length) {
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}
console.log(`Upstream baseline ${manifest.tag} is internally consistent.`);
