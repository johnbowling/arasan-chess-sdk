import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const repoDir = resolve(
  process.env.ARASAN_REPO_DIR ?? resolve(dirname(fileURLToPath(import.meta.url)), "../.."),
);
export const defaultManifestPath = resolve(repoDir, "sdk/upstream.json");

export function command(program, args, options = {}) {
  return execFileSync(program, args, {
    cwd: repoDir,
    encoding: "utf8",
    ...options,
  }).trim();
}

export function commandBytes(program, args, options = {}) {
  return execFileSync(program, args, {
    cwd: repoDir,
    maxBuffer: 128 * 1024 * 1024,
    ...options,
  });
}

export async function readManifest(path = defaultManifestPath) {
  return JSON.parse(await readFile(path, "utf8"));
}

export function parseStableTag(tag) {
  const match = /^v(\d+)\.(\d+)(?:\.(\d+))?$/.exec(tag);
  if (!match) return null;
  return match.slice(1).map((part) => Number(part ?? 0));
}

export function compareTags(left, right) {
  const a = parseStableTag(left);
  const b = parseStableTag(right);
  if (!a || !b) throw new Error(`cannot compare non-stable tags: ${left}, ${right}`);
  for (let index = 0; index < 3; index += 1) {
    if (a[index] !== b[index]) return a[index] - b[index];
  }
  return 0;
}

export function parseRemoteTags(output) {
  const tags = new Map();
  for (const line of output.trim().split("\n")) {
    if (!line) continue;
    const [sha, ref] = line.split(/\s+/);
    const match = /^refs\/tags\/(v[^\^]+)(\^\{\})?$/.exec(ref);
    if (!match || !parseStableTag(match[1])) continue;
    const entry = tags.get(match[1]) ?? {};
    if (match[2]) entry.sourceCommit = sha;
    else entry.tagObject = sha;
    tags.set(match[1], entry);
  }
  for (const entry of tags.values()) {
    entry.sourceCommit ??= entry.tagObject;
  }
  return tags;
}

export async function sha256(path) {
  return createHash("sha256").update(await readFile(path)).digest("hex");
}

export function sha256Bytes(contents) {
  return createHash("sha256").update(contents).digest("hex");
}
