const output = document.querySelector("#output");
const status = document.querySelector("#status");
const commandInput = document.querySelector("#command");
let worker;
let generation = 0;

function append(prefix, line) {
    output.textContent += `${prefix} ${line}\n`;
    output.scrollTop = output.scrollHeight;
}

function startWorker() {
    generation += 1;
    const current = generation;
    worker?.terminate();
    worker = new Worker("../arasan-worker.js");
    status.textContent = "Loading engine and NNUE network…";
    worker.onmessage = ({data}) => {
        if (current !== generation) return;
        append("←", data);
        if (data === "uciok") {
            status.textContent = "Engine loaded; waiting for readiness…";
            send("isready");
        } else if (data === "readyok") {
            status.textContent = "Ready";
        } else if (data.startsWith("info string Arasan initialization failed")) {
            status.textContent = "Initialization failed";
        }
    };
    worker.onerror = (event) => {
        status.textContent = "Worker failed";
        append("!", event.message);
    };
    send("uci");
}

function send(command) {
    append("→", command);
    worker.postMessage(command);
}

document.querySelector("#command-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const command = commandInput.value.trim();
    if (command) send(command);
});

document.querySelector("#sample").addEventListener("click", () => {
    send("setoption name MultiPV value 3");
    send("position fen r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3");
    send("go movetime 500");
});

document.querySelector("#restart").addEventListener("click", () => {
    append("!", "Worker terminated and replaced");
    startWorker();
});

document.querySelector("#clear").addEventListener("click", () => {
    output.textContent = "";
});

startWorker();
