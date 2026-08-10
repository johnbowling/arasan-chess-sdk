#!/usr/bin/env node

import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { cp, mkdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const platformDir = dirname(fileURLToPath(import.meta.url));
const repoDir = resolve(platformDir, "../..");
const [aarInput, distInput] = process.argv.slice(2);

if (!aarInput || !distInput) {
  console.error("usage: package.mjs <release-aar> <dist-dir>");
  process.exit(2);
}

const aarSource = resolve(aarInput);
const distDir = resolve(distInput);
const expectedDefault = join(repoDir, "dist", "android");
const expectedOverride = process.env.ARASAN_ANDROID_DIST_DIR
  ? resolve(process.env.ARASAN_ANDROID_DIST_DIR)
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

const upstream = JSON.parse(await readFile(join(repoDir, "sdk", "upstream.json"), "utf8"));
const propertiesText = await readFile(join(platformDir, "gradle.properties"), "utf8");
const properties = Object.fromEntries(
  propertiesText
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#") && line.includes("="))
    .map((line) => {
      const separator = line.indexOf("=");
      return [line.slice(0, separator), line.slice(separator + 1)];
    }),
);

const zipListing = spawnSync("unzip", ["-Z1", aarSource], { encoding: "utf8" });
if (zipListing.status !== 0) {
  process.stderr.write(zipListing.stderr ?? "");
  process.exit(zipListing.status ?? 1);
}
const entries = new Set(zipListing.stdout.trim().split(/\r?\n/));
const networkEntry = `assets/arasan/${upstream.network.packagedName}`;
const requiredEntries = [
  "AndroidManifest.xml",
  "classes.jar",
  networkEntry,
  "assets/arasan/LICENSE",
  "assets/arasan/PROVENANCE.md",
  "jni/arm64-v8a/libarasan_android.so",
  "jni/x86_64/libarasan_android.so",
];
for (const entry of requiredEntries) {
  if (!entries.has(entry)) {
    throw new Error(`Android AAR is missing ${entry}`);
  }
}

const packagedNetwork = spawnSync("unzip", ["-p", aarSource, networkEntry], {
  encoding: null,
  maxBuffer: 64 * 1024 * 1024,
});
if (packagedNetwork.status !== 0) {
  process.stderr.write(packagedNetwork.stderr?.toString() ?? "");
  process.exit(packagedNetwork.status ?? 1);
}
const networkSha256 = createHash("sha256").update(packagedNetwork.stdout).digest("hex");
if (
  packagedNetwork.stdout.length !== upstream.network.bytes ||
  networkSha256 !== upstream.network.sha256
) {
  throw new Error("Android AAR network payload does not match sdk/upstream.json");
}

await rm(distDir, { recursive: true, force: true });
await mkdir(distDir, { recursive: true });
const aarName = "arasan-chess-sdk-android.aar";
await cp(aarSource, join(distDir, aarName));
await cp(join(repoDir, "LICENSE"), join(distDir, "LICENSE"));
await cp(join(repoDir, "doc", "ANDROID.md"), join(distDir, "README.md"));
await cp(join(repoDir, "doc", "PROVENANCE.md"), join(distDir, "PROVENANCE.md"));

const releaseFiles = [aarName, "LICENSE", "README.md", "PROVENANCE.md"];
const files = {};
for (const name of releaseFiles) {
  const path = join(distDir, name);
  const contents = await readFile(path);
  files[name] = {
    bytes: (await stat(path)).size,
    sha256: createHash("sha256").update(contents).digest("hex"),
  };
}

function command(program, args) {
  const result = spawnSync(program, args, { cwd: repoDir, encoding: "utf8" });
  if (result.status !== 0) {
    throw new Error(`${program} failed: ${result.stderr}`);
  }
  return result.stdout.trim();
}

const sourceStatus = command("git", ["status", "--porcelain"]);
const manifest = {
  schemaVersion: 1,
  package: "arasan-chess-sdk-android",
  engineVersion: upstream.engineVersion,
  upstream: {
    repository: upstream.repository,
    tag: upstream.tag,
    sourceCommit: upstream.sourceCommit,
  },
  fork: {
    repository: "https://github.com/johnbowling/arasan-chess-sdk.git",
    sourceCommit: command("git", ["rev-parse", "HEAD"]),
    dirty: sourceStatus.length > 0,
  },
  android: {
    minSdk: Number(properties.arasanMinSdk),
    compileSdk: Number(properties.arasanCompileSdk),
    targetSdk: Number(properties.arasanTargetSdk),
    abis: properties.arasanAbis.split(","),
    networkAsset: networkEntry,
  },
  network: {
    file: upstream.network.packagedName,
    bytes: upstream.network.bytes,
    sha256: upstream.network.sha256,
  },
  toolchain: {
    androidGradlePlugin: properties.arasanAgpVersion,
    gradle: properties.arasanGradleVersion,
    ndk: properties.arasanNdkVersion,
    cmake: properties.arasanCmakeVersion,
  },
  capabilities: {
    protocol: "UCI",
    javaApi: "org.arasanchess.sdk.ArasanEngine",
    processWideInstances: 1,
    tablebases: false,
    openingBook: false,
  },
  files,
};
await writeFile(join(distDir, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);

console.log(`${basename(aarSource)} packaged for ${manifest.android.abis.join(", ")}`);
