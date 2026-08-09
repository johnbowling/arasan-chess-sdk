// Stable C interface for embedding the Arasan UCI engine.
// Copyright 2026 by the Arasan embedding fork contributors.

#ifndef ARASAN_EMBED_H
#define ARASAN_EMBED_H

#if defined(_WIN32)
#if defined(ARASAN_EMBED_BUILD)
#define ARASAN_EMBED_API __declspec(dllexport)
#else
#define ARASAN_EMBED_API __declspec(dllimport)
#endif
#else
#define ARASAN_EMBED_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

// Called once for each complete UCI output line. The line does not include a
// trailing newline and is valid only for the duration of the callback.
typedef void (*arasan_output_callback)(const char *line, void *context);

// Initializes one process-wide engine instance. resource_root must contain the
// NNUE file named by this Arasan release. Returns 1 on success and 0 on error.
ARASAN_EMBED_API int arasan_embed_initialize(
    const char *resource_root,
    arasan_output_callback output,
    void *context
);

// Submits one UCI command without a trailing newline. A bounded `go` command
// runs synchronously; another host thread may submit `stop` while it runs.
ARASAN_EMBED_API int arasan_embed_send(const char *uci_command);

ARASAN_EMBED_API int arasan_embed_is_ready(void);
ARASAN_EMBED_API int arasan_embed_is_searching(void);

// Stops any active search and releases the engine. Do not invoke shutdown from
// inside the output callback.
ARASAN_EMBED_API void arasan_embed_shutdown(void);

#ifdef __cplusplus
}
#endif

#endif
