#!/usr/bin/env node

import { readFile, writeFile } from "node:fs/promises";
import { basename, resolve } from "node:path";
import {
  command,
  commandBytes,
  defaultManifestPath,
  parseStableTag,
  readManifest,
  repoDir,
  sha256,
  sha256Bytes,
} from "./common.mjs";

const tagIndex = process.argv.indexOf("--tag");
const tag = tagIndex >= 0 ? process.argv[tagIndex + 1] : undefined;
if (!tag || !parseStableTag(tag)) throw new Error("usage: prepare.mjs --tag vX.Y[.Z]");

const previous = await readManifest();
if (command("git", ["cat-file", "-t", tag]) !== "tag") {
  throw new Error(`${tag} is not an annotated upstream tag`);
}
const tagObject = command("git", ["rev-parse", tag]);
const sourceCommit = command("git", ["rev-list", "-n", "1", tag]);
command("git", ["merge-base", "--is-ancestor", sourceCommit, "HEAD"]);

const upstreamCmake = command("git", ["show", `${tag}:src/CMakeLists.txt`]);
const version = /add_compile_definitions\(ARASAN_VERSION=([^\s\)]+)\)/.exec(upstreamCmake)?.[1];
const networkName = /set\(NETWORK\s+([^\s\)]+)\s+CACHE/.exec(upstreamCmake)?.[1];
if (!version || !networkName) {
  throw new Error("could not derive engine version and network from src/CMakeLists.txt");
}
if (`v${version}` !== tag) {
  throw new Error(`tag ${tag} does not match upstream ARASAN_VERSION=${version}`);
}

const networkSourcePath = `network/${networkName}`;
const networkPath = resolve(repoDir, networkSourcePath);
const taggedNetwork = commandBytes("git", ["show", `${tag}:${networkSourcePath}`]);
const taggedNetworkChecksum = sha256Bytes(taggedNetwork);
if ((await sha256(networkPath)) !== taggedNetworkChecksum) {
  throw new Error("merged network payload differs from the upstream tag");
}
const openingBookPath = resolve(repoDir, previous.openingBook.sourcePath);
const taggedOpeningBook = commandBytes("git", [
  "show",
  `${tag}:${previous.openingBook.sourcePath}`,
]);
const taggedOpeningBookChecksum = sha256Bytes(taggedOpeningBook);
if ((await sha256(openingBookPath)) !== taggedOpeningBookChecksum) {
  throw new Error("merged opening-book payload differs from the upstream tag");
}
const licensePath = resolve(repoDir, previous.license.sourcePath);
const taggedLicense = commandBytes("git", ["show", `${tag}:${previous.license.sourcePath}`]);
const licenseChecksum = sha256Bytes(taggedLicense);
if (licenseChecksum !== previous.license.sha256) {
  throw new Error("upstream LICENSE changed; review it manually before updating the SDK pin");
}
if ((await sha256(licensePath)) !== licenseChecksum) {
  throw new Error("merged LICENSE differs from the upstream tag");
}
const next = {
  ...previous,
  tag,
  tagObject,
  sourceCommit,
  engineVersion: version,
  network: {
    ...previous.network,
    sourcePath: networkSourcePath,
    bytes: taggedNetwork.length,
    sha256: taggedNetworkChecksum,
  },
  openingBook: {
    ...previous.openingBook,
    bytes: taggedOpeningBook.length,
    sha256: taggedOpeningBookChecksum,
  },
  license: {
    ...previous.license,
    sha256: licenseChecksum,
  },
};
await writeFile(defaultManifestPath, `${JSON.stringify(next, null, 2)}\n`);

const commaBytes = (value) => new Intl.NumberFormat("en-US").format(value);
const replacements = new Map([
  [previous.tag, next.tag],
  [`Arasan ${previous.engineVersion}`, `Arasan ${next.engineVersion}`],
  [previous.tagObject, next.tagObject],
  [previous.sourceCommit, next.sourceCommit],
  [previous.network.sourcePath, next.network.sourcePath],
  [commaBytes(previous.network.bytes), commaBytes(next.network.bytes)],
  [previous.network.sha256, next.network.sha256],
  [commaBytes(previous.openingBook.bytes), commaBytes(next.openingBook.bytes)],
  [previous.openingBook.sha256, next.openingBook.sha256],
]);
for (const relativePath of ["FORK.md", "doc/PROVENANCE.md", "doc/UPSTREAM-DELTA.md"]) {
  const path = resolve(repoDir, relativePath);
  let contents = await readFile(path, "utf8");
  for (const [before, after] of replacements) contents = contents.replaceAll(before, after);
  await writeFile(path, contents);
}

console.log(
  `Prepared ${tag}: ${basename(networkSourcePath)} (${taggedNetwork.length} bytes), ${sourceCommit}`,
);
