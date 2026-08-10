// Raw UCI Web Worker host for Arasan WebAssembly.
// Copyright 2026 by the Arasan embedding fork contributors.

let engine = null;
let failed = false;
const pendingCommands = [];

function postInfo(message) {
    self.postMessage(`info string ${message}`);
}

function send(command) {
    const accepted = engine.ccall(
        "arasan_wasm_command",
        "number",
        ["string"],
        [command]
    );
    if (!accepted) {
        postInfo(`Arasan rejected command: ${command}`);
    }
    if (command.trim() === "quit") {
        engine.ccall("arasan_wasm_shutdown", null, [], []);
        self.close();
        return false;
    }
    return true;
}

self.onmessage = ({data}) => {
    if (typeof data !== "string") {
        postInfo("Arasan Worker accepts UCI command strings only");
        return;
    }
    const command = data.trim();
    if (!command || failed) {
        return;
    }
    if (engine === null) {
        pendingCommands.push(command);
        return;
    }
    send(command);
};

async function boot() {
    const loaderUrl = new URL("arasan.js", self.location.href);
    const wasmUrl = new URL("arasan.wasm", self.location.href);
    const networkUrl = new URL("arasan.nnue", self.location.href);
    const bookUrl = new URL("book.bin", self.location.href);

    self.importScripts(loaderUrl.href);
    const module = await createArasanModule({
        locateFile(path) {
            return path.endsWith(".wasm") ? wasmUrl.href : new URL(path, loaderUrl).href;
        },
        print(line) {
            self.postMessage(String(line));
        },
        printErr(line) {
            postInfo(`Arasan WebAssembly: ${line}`);
        },
    });

    const [networkResponse, bookResponse] = await Promise.all([
        fetch(networkUrl),
        fetch(bookUrl),
    ]);
    if (!networkResponse.ok) {
        throw new Error(`network fetch returned HTTP ${networkResponse.status}`);
    }
    if (!bookResponse.ok) {
        throw new Error(`book fetch returned HTTP ${bookResponse.status}`);
    }
    const [network, book] = await Promise.all([
        networkResponse.arrayBuffer().then((bytes) => new Uint8Array(bytes)),
        bookResponse.arrayBuffer().then((bytes) => new Uint8Array(bytes)),
    ]);
    module.FS.mkdirTree("/arasan");
    module.FS.writeFile("/arasan/arasan.nnue", network);
    module.FS.writeFile("/arasan/book.bin", book);

    const initialized = module.ccall(
        "arasan_wasm_initialize",
        "number",
        ["string"],
        ["/arasan"]
    );
    if (!initialized) {
        throw new Error("engine initialization failed");
    }

    engine = module;
    send("setoption name BookPath value /arasan/book.bin");
    for (const command of pendingCommands.splice(0)) {
        if (!send(command)) break;
    }
}

boot().catch((error) => {
    failed = true;
    pendingCommands.length = 0;
    postInfo(`Arasan initialization failed: ${error.message}`);
});
