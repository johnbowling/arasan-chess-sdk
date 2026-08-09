// Native smoke test for the Arasan embedding C API.

#include "embed/arasan_embed.h"

#include <atomic>
#include <chrono>
#include <iostream>
#include <mutex>
#include <regex>
#include <string>
#include <thread>
#include <vector>

namespace {

struct OutputLines {
    std::mutex mutex;
    std::vector<std::string> values;
};

void receiveLine(const char *line, void *context) {
    auto *output = static_cast<OutputLines *>(context);
    std::lock_guard<std::mutex> lock(output->mutex);
    output->values.emplace_back(line);
}

bool contains(const OutputLines &output, const std::string &expected) {
    for (const std::string &line : output.values) {
        if (line == expected) {
            return true;
        }
    }
    return false;
}

bool hasLegalBestMove(const OutputLines &output) {
    const std::regex bestMove("^bestmove [a-h][1-8][a-h][1-8][qrbn]?( ponder .+)?$");
    for (const std::string &line : output.values) {
        if (std::regex_match(line, bestMove)) {
            return true;
        }
    }
    return false;
}

} // namespace

int main(int argc, char **argv) {
    if (argc != 2) {
        std::cerr << "usage: arasan-embed-smoke <resource-root>" << std::endl;
        return 2;
    }

    OutputLines output;
    if (!arasan_embed_initialize(argv[1], receiveLine, &output)) {
        std::cerr << "embedding initialization failed" << std::endl;
        return 1;
    }
    if (!arasan_embed_is_ready()) {
        std::cerr << "embedding host did not report ready" << std::endl;
        return 1;
    }

    const char *commands[] = {
        "uci",
        "isready",
        "ucinewgame",
        "position fen rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "go movetime 100",
    };
    for (const char *command : commands) {
        if (!arasan_embed_send(command)) {
            std::cerr << "command failed: " << command << std::endl;
            arasan_embed_shutdown();
            return 1;
        }
    }

    std::atomic<int> infiniteSearchResult{0};
    std::thread infiniteSearch([&infiniteSearchResult] {
        infiniteSearchResult.store(arasan_embed_send("go infinite"));
    });
    bool observedSearching = false;
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
    while (std::chrono::steady_clock::now() < deadline) {
        if (arasan_embed_is_searching()) {
            observedSearching = true;
            break;
        }
        std::this_thread::yield();
    }
    const bool stopped = arasan_embed_send("stop") != 0;
    infiniteSearch.join();

    const bool passed = contains(output, "uciok") && contains(output, "readyok") &&
                        hasLegalBestMove(output) && observedSearching && stopped &&
                        infiniteSearchResult.load() != 0;
    if (!arasan_embed_send("quit")) {
        std::cerr << "command failed: quit" << std::endl;
        arasan_embed_shutdown();
        return 1;
    }
    arasan_embed_shutdown();
    if (!passed || arasan_embed_is_ready()) {
        std::cerr << "UCI smoke assertions failed" << std::endl;
        return 1;
    }

    std::cout << "Arasan embedded UCI smoke test passed" << std::endl;
    return 0;
}
