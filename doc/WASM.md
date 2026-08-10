# Arasan WebAssembly SDK

This target packages Arasan 26.0 as a single-threaded WebAssembly SIMD engine
hosted in a dedicated Web Worker. The application boundary remains raw UCI:
send one command string to the Worker and receive one engine output line string
per message.

## Runtime profile

| Capability | Web target |
| --- | --- |
| Protocol | Raw UCI strings through a Web Worker |
| Search threads | 1 |
| WebAssembly SIMD | Required |
| `SharedArrayBuffer` / cross-origin isolation | Not required |
| NNUE | External `arasan.nnue` asset loaded into the virtual filesystem at startup |
| Opening book / ECO | Disabled and not packaged |
| Syzygy tablebases | Not compiled or packaged |
| Learning / game storage | Disabled |
| Initial / maximum memory | 128 MiB / 512 MiB, with growth enabled |

This is deliberately the lowest-complexity browser profile. It avoids pthreads,
cross-origin isolation requirements, persistence, and browser-specific engine
changes. It does not alter evaluation or search behavior.

## Reproducible build

Install and activate the official Emscripten SDK 6.0.6, then run:

```sh
./platforms/wasm/build.sh
```

The script requires `emcmake`, CMake, Ninja, and Node on `PATH`; the pinned
Emscripten SDK supplies all four. It configures the dedicated CMake target,
builds it, and creates `dist/wasm`. Generated build and distribution directories
are ignored by Git.

The package contains:

- `arasan.js` and `arasan.wasm`: the modular Emscripten loader and engine;
- `arasan.nnue`: the unchanged, MIT-licensed upstream v26.0 network;
- `arasan-worker.js`: the raw UCI Worker adapter;
- `manifest.json`: source, toolchain, capabilities, sizes, and SHA-256 values;
- `LICENSE` and `PROVENANCE.md`; and
- `demo/` and `test/`: static integration and acceptance harnesses.

The network is renamed for a stable package contract. Its bytes must continue to
match the size and SHA-256 in [PROVENANCE.md](PROVENANCE.md).

## Browser use

Serve the package over HTTP. Static hosting must send `.wasm` as
`application/wasm`; `.nnue` may use `application/octet-stream`. For example:

```sh
python3 -m http.server 4173 --bind 127.0.0.1 --directory dist/wasm
```

The smallest host is:

```js
const engine = new Worker("/arasan/arasan-worker.js");

engine.onmessage = ({data: uciLine}) => {
    console.log(uciLine);
};

engine.postMessage("uci");
engine.postMessage("isready");
engine.postMessage("position startpos");
engine.postMessage("go movetime 250");
```

Commands sent during network loading are queued in order. The normal `uciok`
and `readyok` responses are the readiness handshake; the Worker does not add a
parallel control protocol. Invalid message types and initialization errors are
reported as UCI `info string` lines.

## Cancellation contract

Search is synchronous inside the Worker. While a `go` command is running, that
Worker cannot receive a later `stop` message from JavaScript. Use bounded UCI
searches for normal work. To cancel immediately—including `go infinite`—call
`terminate()` and create a fresh Worker.

The application wrapper should assign each Worker a generation number and
ignore output from older generations. Recreate the engine, complete `uci` and
`isready`, reapply desired options and position, then start the replacement
search. This gives deterministic cancellation without pthreads or Asyncify.

## Verification

Open `http://127.0.0.1:4173/test/` after building. The browser suite verifies:

1. `uci` / `uciok` and `isready` / `readyok`;
2. FEN loading and MultiPV lines 1–3;
3. a bounded `go movetime` returning `bestmove`; and
4. termination of `go infinite`, Worker replacement, and a clean second search.

The GitHub Actions workflow rebuilds with Emscripten 6.0.6, runs the same suite
in a headless browser, and uploads the checksummed package. Release publication
and signing are intentionally outside this increment.
