#!/usr/bin/env node

import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { cp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const repoDir = resolve(scriptDir, "../..");
const [inputArgument, outputArgument, versionArgument = ""] = process.argv.slice(2);

if (!inputArgument || !outputArgument) {
  console.error(
    "usage: assemble.mjs <downloaded-artifacts-dir> <candidate-dist-dir> [candidate-version]",
  );
  process.exit(2);
}

const inputDir = resolve(inputArgument);
const outputDir = resolve(outputArgument);
const expectedOutput = process.env.ARASAN_RELEASE_DIST_DIR
  ? resolve(process.env.ARASAN_RELEASE_DIST_DIR)
  : join(repoDir, "dist", "release-candidate");

if (
  outputDir !== expectedOutput ||
  outputDir === dirname(outputDir) ||
  outputDir === process.env.HOME ||
  outputDir === repoDir ||
  outputDir === dirname(repoDir)
) {
  throw new Error(`refusing to replace unexpected candidate path: ${outputDir}`);
}

const upstream = JSON.parse(await readFile(join(repoDir, "sdk", "upstream.json"), "utf8"));
const sourceRepository = "https://github.com/johnbowling/arasan-chess-sdk.git";

function command(program, args) {
  return execFileSync(program, args, { cwd: repoDir, encoding: "utf8" }).trim();
}

function requireValue(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function normalizedMemberPath(member) {
  requireValue(typeof member === "string" && member.length > 0, "empty package member path");
  const segments = member.split("/");
  requireValue(
    !member.startsWith("/") && segments.every((segment) => segment && segment !== "." && segment !== ".."),
    `unsafe package member path: ${member}`,
  );
  return segments;
}

function packageMember(root, member) {
  const path = resolve(root, ...normalizedMemberPath(member));
  requireValue(path.startsWith(`${resolve(root)}${sep}`), `package member escapes root: ${member}`);
  return path;
}

async function metadata(path) {
  const contents = await readFile(path);
  return {
    bytes: contents.length,
    sha256: createHash("sha256").update(contents).digest("hex"),
  };
}

async function verifyDeclaredFiles(packageName, packageRoot, declaredFiles) {
  requireValue(
    declaredFiles && typeof declaredFiles === "object" && !Array.isArray(declaredFiles),
    `${packageName} manifest has no file inventory`,
  );
  for (const [member, expected] of Object.entries(declaredFiles)) {
    requireValue(
      Number.isSafeInteger(expected?.bytes) && expected.bytes >= 0,
      `${packageName} has invalid byte count for ${member}`,
    );
    requireValue(
      typeof expected.sha256 === "string" && /^[0-9a-f]{64}$/.test(expected.sha256),
      `${packageName} has invalid checksum for ${member}`,
    );
    const actual = await metadata(packageMember(packageRoot, member));
    requireValue(
      actual.bytes === expected.bytes && actual.sha256 === expected.sha256,
      `${packageName} payload does not match its manifest: ${member}`,
    );
  }
}

function verifyUpstream(packageName, manifestUpstream) {
  for (const field of ["repository", "tag", "sourceCommit"]) {
    requireValue(
      manifestUpstream?.[field] === upstream[field],
      `${packageName} upstream ${field} does not match sdk/upstream.json`,
    );
  }
}

function verifyNetwork(packageName, network) {
  requireValue(network?.bytes === upstream.network.bytes, `${packageName} network size differs`);
  requireValue(network?.sha256 === upstream.network.sha256, `${packageName} network checksum differs`);
}

async function collectFiles(root, directory = root) {
  const files = [];
  for (const entry of (await readdir(directory, { withFileTypes: true })).sort((a, b) =>
    a.name.localeCompare(b.name),
  )) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await collectFiles(root, path)));
    } else if (entry.isFile()) {
      files.push(relative(root, path).split(sep).join("/"));
    } else {
      throw new Error(`unsupported candidate entry: ${path}`);
    }
  }
  return files;
}

const sourceCommit = command("git", ["rev-parse", "HEAD"]);
requireValue(
  command("git", ["status", "--porcelain"]).length === 0,
  "release candidates must be assembled from a clean checkout",
);

const candidateVersion =
  versionArgument.trim() || `v${upstream.engineVersion}-embed.1-rc.1`;
const escapedEngineVersion = upstream.engineVersion.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
requireValue(
  new RegExp(`^v${escapedEngineVersion}-embed\\.[1-9][0-9]*-rc\\.[1-9][0-9]*$`).test(
    candidateVersion,
  ),
  `candidate version must look like v${upstream.engineVersion}-embed.1-rc.1`,
);

const inputRoots = {
  apple: join(inputDir, "arasan-chess-sdk-apple"),
  android: join(inputDir, "arasan-chess-sdk-android"),
  wasm: join(inputDir, "arasan-chess-sdk-wasm"),
};
const manifests = {};
for (const [platform, root] of Object.entries(inputRoots)) {
  manifests[platform] = JSON.parse(await readFile(join(root, "manifest.json"), "utf8"));
}

const apple = manifests.apple;
requireValue(apple.formatVersion === 1, "unsupported Apple manifest version");
requireValue(apple.package === "arasan-chess-sdk-apple", "unexpected Apple package name");
requireValue(apple.arasanVersion === upstream.engineVersion, "Apple engine version differs");
verifyUpstream("Apple", apple.upstream);
requireValue(apple.source?.repository === sourceRepository, "Apple source repository differs");
requireValue(apple.source?.commit === sourceCommit, "Apple source commit differs");
requireValue(apple.source?.dirty === false, "Apple package was built from a dirty checkout");
const appleNetworkPath = `resources/${upstream.network.packagedName}`;
verifyNetwork("Apple", apple.artifacts?.[appleNetworkPath]);
await verifyDeclaredFiles("Apple", inputRoots.apple, apple.artifacts);

const android = manifests.android;
requireValue(android.schemaVersion === 1, "unsupported Android manifest version");
requireValue(android.package === "arasan-chess-sdk-android", "unexpected Android package name");
requireValue(android.engineVersion === upstream.engineVersion, "Android engine version differs");
verifyUpstream("Android", android.upstream);
requireValue(android.fork?.repository === sourceRepository, "Android source repository differs");
requireValue(android.fork?.sourceCommit === sourceCommit, "Android source commit differs");
requireValue(android.fork?.dirty === false, "Android package was built from a dirty checkout");
requireValue(android.network?.file === upstream.network.packagedName, "Android network name differs");
verifyNetwork("Android", android.network);
await verifyDeclaredFiles("Android", inputRoots.android, android.files);

const wasm = manifests.wasm;
requireValue(wasm.schemaVersion === 1, "unsupported WebAssembly manifest version");
requireValue(wasm.package === "arasan-chess-sdk-wasm", "unexpected WebAssembly package name");
requireValue(wasm.engineVersion === upstream.engineVersion, "WebAssembly engine version differs");
verifyUpstream("WebAssembly", wasm.upstream);
requireValue(wasm.fork?.repository === sourceRepository, "WebAssembly source repository differs");
requireValue(wasm.fork?.sourceCommit === sourceCommit, "WebAssembly source commit differs");
requireValue(wasm.fork?.dirty === false, "WebAssembly package was built from a dirty checkout");
verifyNetwork("WebAssembly", wasm.files?.[upstream.network.packagedName]);
await verifyDeclaredFiles("WebAssembly", inputRoots.wasm, wasm.files);

await rm(outputDir, { recursive: true, force: true });
await mkdir(outputDir, { recursive: true });
for (const [platform, root] of Object.entries(inputRoots)) {
  await cp(root, join(outputDir, platform), { recursive: true });
}
await cp(join(repoDir, "LICENSE"), join(outputDir, "LICENSE"));
await cp(join(repoDir, "doc", "PROVENANCE.md"), join(outputDir, "PROVENANCE.md"));
await cp(join(repoDir, "doc", "RELEASES.md"), join(outputDir, "README.md"));

const candidateFiles = await collectFiles(outputDir);
const files = {};
for (const member of candidateFiles) {
  files[member] = await metadata(packageMember(outputDir, member));
}
const checksumContents = `${Object.entries(files)
  .map(([member, value]) => `${value.sha256}  ${member}`)
  .join("\n")}\n`;
await writeFile(join(outputDir, "SHA256SUMS"), checksumContents);
const checksumFile = await metadata(join(outputDir, "SHA256SUMS"));

const releaseManifest = {
  schemaVersion: 1,
  package: "arasan-chess-sdk-release-candidate",
  candidateVersion,
  engineVersion: upstream.engineVersion,
  upstream: {
    repository: upstream.repository,
    tag: upstream.tag,
    sourceCommit: upstream.sourceCommit,
  },
  fork: {
    repository: sourceRepository,
    sourceCommit,
    dirty: false,
  },
  network: {
    file: upstream.network.packagedName,
    bytes: upstream.network.bytes,
    sha256: upstream.network.sha256,
  },
  platforms: {
    apple: {
      package: apple.package,
      path: "apple",
      manifest: "apple/manifest.json",
      minimumIOSVersion: apple.minimumIOSVersion,
    },
    android: {
      package: android.package,
      path: "android",
      manifest: "android/manifest.json",
      minimumApi: android.android.minSdk,
      abis: android.android.abis,
    },
    wasm: {
      package: wasm.package,
      path: "wasm",
      manifest: "wasm/manifest.json",
      capabilities: wasm.capabilities,
    },
  },
  validation: {
    native: "passed",
    appleSimulator: "passed",
    androidEmulator: "passed",
    wasmBrowser: "passed",
    physicalAppleArm64: "required-before-stable-release",
    physicalAndroidArm64: "required-before-stable-release",
  },
  publication: {
    gitTagCreated: false,
    githubReleaseCreated: false,
    packageRegistryPublished: false,
  },
  files,
  checksumFile: {
    path: "SHA256SUMS",
    ...checksumFile,
  },
};

await writeFile(
  join(outputDir, "release-manifest.json"),
  `${JSON.stringify(releaseManifest, null, 2)}\n`,
);

console.log(
  `${candidateVersion} assembled from ${sourceCommit} with ${candidateFiles.length} checksummed files`,
);
