# Updating the Arasan baseline

This fork treats upstream updates as a hobby-friendly, automated maintenance
task. It follows stable Arasan tags only; upstream `master` is never merged
automatically into the SDK release line.

## Normal workflow

Once a week, the `Upstream update` GitHub workflow checks the tags published by
`jdart1/arasan-chess`.

If there is no newer stable tag, the workflow exits successfully and does
nothing. If a newer tag exists, it attempts to:

1. create `update/arasan-vX.Y` from this fork's `main`;
2. merge the annotated upstream tag without rebasing or squashing history;
3. update version, network, checksum, and license metadata;
4. push the candidate and open a draft PR inside this fork; and
5. dispatch every validation workflow currently available in the fork.

The automation never opens a PR against upstream Arasan and never merges or
releases a candidate automatically.

The owner has one decision:

- If the draft PR and its dispatched workflows are green, merge it when the
  update is wanted.
- If the update Action or any validation is red, leave it alone until the
  failure is investigated.

Old SDK tags and consumer checksums remain valid, so SixtyFour does not need to
adopt an engine update immediately and can roll back by restoring its previous
pin.

## One-time GitHub setting

In the fork's **Settings → Actions → General → Workflow permissions**, enable
read/write workflow permissions and allow GitHub Actions to create pull
requests. No personal access token or additional service is required.

## Manual check

The scheduled workflow can also be run from GitHub's Actions page. Leave the
tag input blank to use the newest stable tag, or supply a specific newer stable
tag such as `v26.1`.

For a local read-only check:

```sh
node scripts/upstream/check.mjs
```

To verify that the checked-out SDK still matches its pinned baseline:

```sh
node scripts/upstream/validate.mjs
```

## What is automated

[`sdk/upstream.json`](../sdk/upstream.json) is the single machine-readable
baseline. It pins the tag object, source commit, engine version, NNUE file,
checksums, and license checksum. Embedded builds and package manifests read
these values rather than duplicating release-specific constants.

Candidate preparation stops instead of guessing when:

- the upstream merge conflicts;
- the upstream tag is not annotated or has moved;
- the version or network cannot be derived from upstream CMake metadata;
- the network or license checksum is inconsistent; or
- a dispatched build/test workflow fails.

Those are the only cases expected to need manual help.
