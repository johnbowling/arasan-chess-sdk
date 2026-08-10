#!/usr/bin/env node

import { appendFile } from "node:fs/promises";
import {
  command,
  compareTags,
  parseRemoteTags,
  parseStableTag,
  readManifest,
} from "./common.mjs";

const args = process.argv.slice(2);
const option = (name) => {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : undefined;
};

const manifest = await readManifest();
const requestedTag = option("--tag");
const outputPath = option("--github-output");
const remoteOutput = command("git", [
  "ls-remote",
  "--tags",
  manifest.repository,
  "refs/tags/v*",
]);
const tags = parseRemoteTags(remoteOutput);
const stableTags = [...tags.keys()].sort(compareTags);
const latestTag = requestedTag || stableTags.at(-1);

if (!latestTag || !parseStableTag(latestTag) || !tags.has(latestTag)) {
  throw new Error(`stable upstream tag not found: ${latestTag ?? "(none)"}`);
}

const latest = tags.get(latestTag);
if (latestTag === manifest.tag && latest.sourceCommit !== manifest.sourceCommit) {
  throw new Error(
    `upstream tag ${latestTag} moved from ${manifest.sourceCommit} to ${latest.sourceCommit}`,
  );
}

const result = {
  currentTag: manifest.tag,
  latestTag,
  updateAvailable: compareTags(latestTag, manifest.tag) > 0,
  tagObject: latest.tagObject,
  sourceCommit: latest.sourceCommit,
};

if (outputPath) {
  await appendFile(
    outputPath,
    [
      `current_tag=${result.currentTag}`,
      `latest_tag=${result.latestTag}`,
      `update_available=${result.updateAvailable}`,
      `tag_object=${result.tagObject}`,
      `source_commit=${result.sourceCommit}`,
      "",
    ].join("\n"),
  );
}

console.log(JSON.stringify(result, null, 2));
