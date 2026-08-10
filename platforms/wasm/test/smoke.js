const summary = document.querySelector("#summary");
const results = document.querySelector("#results");
let worker = null;
let generation = 0;
let lines = [];
let waiters = [];

function record(name, passed, detail = "") {
    const item = document.createElement("li");
    item.className = passed ? "pass" : "fail";
    item.textContent = `${passed ? "PASS" : "FAIL"} — ${name}${detail ? `: ${detail}` : ""}`;
    results.append(item);
}

function startWorker() {
    const current = ++generation;
    worker?.terminate();
    lines = [];
    waiters = [];
    worker = new Worker("../arasan-worker.js");
    worker.onmessage = ({data}) => {
        if (current !== generation) return;
        lines.push(data);
        const pending = waiters;
        waiters = [];
        for (const waiter of pending) {
            if (waiter.predicate(data, lines)) waiter.resolve(data);
            else waiters.push(waiter);
        }
    };
    return worker;
}

function waitFor(predicate, timeout = 60000) {
    return new Promise((resolve, reject) => {
        const waiter = {predicate, resolve};
        waiters.push(waiter);
        setTimeout(() => {
            const index = waiters.indexOf(waiter);
            if (index >= 0) waiters.splice(index, 1);
            reject(new Error(`timed out after ${timeout} ms`));
        }, timeout);
    });
}

async function commandAndWait(command, predicate, timeout) {
    const awaited = waitFor(predicate, timeout);
    worker.postMessage(command);
    return awaited;
}

async function initialize() {
    startWorker();
    await commandAndWait("uci", (line) => line === "uciok");
    await commandAndWait("isready", (line) => line === "readyok");
}

async function cancelInfiniteAndRestart() {
    worker.postMessage("position startpos");
    const searching = waitFor((line) => line.startsWith("info depth "));
    worker.postMessage("go infinite");
    await searching;
    startWorker();
    await commandAndWait("uci", (line) => line === "uciok");
    await commandAndWait("isready", (line) => line === "readyok");
}

async function run() {
    await initialize();
    record("UCI initialization and readiness", true);

    worker.postMessage("setoption name MultiPV value 3");
    worker.postMessage("position fen r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3");
    const firstSearchStart = lines.length;
    await commandAndWait("go depth 6", (line) => line.startsWith("bestmove "));
    const firstSearch = lines.slice(firstSearchStart);
    for (const pv of [1, 2, 3]) {
        if (!firstSearch.some((line) => line.includes(` multipv ${pv} `))) {
            throw new Error(`MultiPV ${pv} was not reported`);
        }
    }
    record("FEN analysis and MultiPV 1–3", true);

    worker.postMessage("position startpos moves e2e4 e7e5 g1f3 b8c6");
    await commandAndWait("go movetime 150", (line) => line.startsWith("bestmove "));
    record("bounded movetime search returns bestmove", true);

    await cancelInfiniteAndRestart();
    await cancelInfiniteAndRestart();
    worker.postMessage("position startpos");
    await commandAndWait("go movetime 100", (line) => line.startsWith("bestmove "));
    record("repeated Worker replacement cancels search without stale output", true);

    summary.className = "pass";
    summary.textContent = "All WebAssembly smoke checks passed.";
    document.documentElement.dataset.testStatus = "passed";
}

run().catch((error) => {
    record("smoke suite", false, error.message);
    summary.className = "fail";
    summary.textContent = `Smoke test failed: ${error.message}`;
    document.documentElement.dataset.testStatus = "failed";
});
