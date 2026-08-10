import {createHash} from "node:crypto";
import {execFileSync} from "node:child_process";
import {cp, mkdir, readFile, rm, stat, writeFile} from "node:fs/promises";
import {dirname, join, resolve} from "node:path";
import {fileURLToPath} from "node:url";

const platformDir = dirname(fileURLToPath(import.meta.url));
const repoDir = resolve(platformDir, "../..");
const buildDir = resolve(process.argv[2] ?? join(repoDir, "build/wasm"));
const distDir = resolve(process.argv[3] ?? join(repoDir, "dist/wasm"));
const upstream = JSON.parse(await readFile(join(repoDir, "sdk/upstream.json"), "utf8"));

if (!distDir.startsWith(`${repoDir}/dist/`)) {
    throw new Error(`refusing to replace a package outside ${join(repoDir, "dist")}`);
}

await rm(distDir, {recursive: true, force: true});
await mkdir(join(distDir, "demo"), {recursive: true});
await mkdir(join(distDir, "test"), {recursive: true});

const copies = [
    [join(buildDir, "arasan.js"), join(distDir, "arasan.js")],
    [join(buildDir, "arasan.wasm"), join(distDir, "arasan.wasm")],
    [join(repoDir, upstream.network.sourcePath), join(distDir, upstream.network.packagedName)],
    [join(platformDir, "arasan-worker.js"), join(distDir, "arasan-worker.js")],
    [join(platformDir, "demo/index.html"), join(distDir, "demo/index.html")],
    [join(platformDir, "demo/demo.js"), join(distDir, "demo/demo.js")],
    [join(platformDir, "demo/styles.css"), join(distDir, "demo/styles.css")],
    [join(platformDir, "test/index.html"), join(distDir, "test/index.html")],
    [join(platformDir, "test/smoke.js"), join(distDir, "test/smoke.js")],
    [join(repoDir, "LICENSE"), join(distDir, "LICENSE")],
    [join(repoDir, "doc/PROVENANCE.md"), join(distDir, "PROVENANCE.md")],
];

for (const [source, destination] of copies) {
    await cp(source, destination);
}

const releaseFiles = [
    "arasan.js",
    "arasan.wasm",
    upstream.network.packagedName,
    "arasan-worker.js",
    "LICENSE",
];
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
    return execFileSync(program, args, {cwd: repoDir, encoding: "utf8"}).trim();
}

const sourceStatus = command("git", ["status", "--porcelain"]);
const manifest = {
    schemaVersion: 1,
    package: "arasan-chess-sdk-wasm",
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
    toolchain: command("emcc", ["--version"]).split("\n")[0],
    capabilities: {
        protocol: "UCI",
        webWorker: true,
        wasmSimd: true,
        threads: 1,
        tablebases: false,
        openingBook: false,
    },
    files,
};

await writeFile(join(distDir, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
