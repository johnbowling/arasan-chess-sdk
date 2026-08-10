// Emscripten exports for the common Arasan embedding API.
// Copyright 2026 by the Arasan embedding fork contributors.

#include "../../src/embed/arasan_embed.h"

#include <emscripten/emscripten.h>

#include <iostream>

namespace {

void forwardOutput(const char *line, void *) {
    // Emscripten delivers complete stdout lines to Module.print, which the
    // Worker forwards unchanged to its UCI consumer.
    std::cout << line << std::endl;
}

} // namespace

extern "C" {

EMSCRIPTEN_KEEPALIVE int arasan_wasm_initialize(const char *resource_root) {
    return arasan_embed_initialize(resource_root, forwardOutput, nullptr);
}

EMSCRIPTEN_KEEPALIVE int arasan_wasm_command(const char *uci_command) {
    return arasan_embed_send(uci_command);
}

EMSCRIPTEN_KEEPALIVE int arasan_wasm_is_ready() {
    return arasan_embed_is_ready();
}

EMSCRIPTEN_KEEPALIVE int arasan_wasm_is_searching() {
    return arasan_embed_is_searching();
}

EMSCRIPTEN_KEEPALIVE void arasan_wasm_shutdown() {
    arasan_embed_shutdown();
}

}
