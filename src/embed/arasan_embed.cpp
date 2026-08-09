// In-process host for Arasan's existing UCI protocol implementation.
// Copyright 2026 by the Arasan embedding fork contributors.

#include "arasan_embed.h"

#include "../attacks.h"
#include "../bitutil.h"
#include "../globals.h"
#include "../protocol.h"
#include "../search.h"

#include <atomic>
#include <condition_variable>
#include <filesystem>
#include <map>
#include <memory>
#include <mutex>
#include <ostream>
#include <streambuf>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace {

class CallbackStreamBuffer final : public std::streambuf {
  public:
    CallbackStreamBuffer(arasan_output_callback callback, void *context)
        : callback(callback), context(context) {
    }

  protected:
    int_type overflow(int_type character) override {
        if (traits_type::eq_int_type(character, traits_type::eof())) {
            return traits_type::not_eof(character);
        }
        const char value = traits_type::to_char_type(character);
        write(&value, 1);
        return character;
    }

    std::streamsize xsputn(const char *data, std::streamsize length) override {
        write(data, static_cast<size_t>(length));
        return length;
    }

  private:
    void write(const char *data, size_t length) {
        std::vector<std::string> completed;
        {
            std::lock_guard<std::mutex> lock(mutex);
            std::string &partial = partialLines[std::this_thread::get_id()];
            for (size_t i = 0; i < length; ++i) {
                const char value = data[i];
                if (value == '\n') {
                    if (!partial.empty() && partial.back() == '\r') {
                        partial.pop_back();
                    }
                    completed.push_back(std::move(partial));
                    partial.clear();
                } else {
                    partial.push_back(value);
                }
            }
        }
        for (const std::string &line : completed) {
            callback(line.c_str(), context);
        }
    }

    arasan_output_callback callback;
    void *context;
    std::mutex mutex;
    std::map<std::thread::id, std::string> partialLines;
};

class CallbackStream final : public std::ostream {
  public:
    CallbackStream(arasan_output_callback callback, void *context)
        : std::ostream(nullptr), buffer(callback, context) {
        rdbuf(&buffer);
    }

  private:
    CallbackStreamBuffer buffer;
};

class EmbeddedRuntime final {
  public:
    int initialize(const char *resourceRoot, arasan_output_callback callback, void *context) {
        std::lock_guard<std::mutex> lock(lifecycleMutex);
        if (ready.load(std::memory_order_acquire) || resourceRoot == nullptr ||
            *resourceRoot == '\0' || callback == nullptr) {
            return 0;
        }

        output = std::make_unique<CallbackStream>(callback, context);
        globals::setOutput(output.get());

        try {
            globals::options = Options();
            BitUtils::init();
            Board::init();
            if (!globals::initOptions(false, nullptr, false, false)) {
                resetFailedInitialization();
                return 0;
            }

            globals::options.search.ncpus = 1;
            globals::options.book.book_enabled = false;
            globals::options.book.eco_enabled = false;
            globals::options.learning.position_learning = false;
            globals::options.games.store_games = false;
#ifdef SYZYGY_TBS
            globals::options.search.use_tablebases = false;
#endif

            const std::filesystem::path networkPath =
                std::filesystem::path(resourceRoot) / globals::DEFAULT_NETWORK_NAME;
            globals::options.search.nnueFile = networkPath.string();

            Attacks::init();
            Search::init();
            if (!globals::initGlobals(false)) {
                resetFailedInitialization();
                return 0;
            }
            globalsInitialized = true;

            if (!globals::loadNetwork(networkPath.string(), false)) {
                resetFailedInitialization();
                return 0;
            }
            globals::nnueInitDone = true;

            Board board;
            owner = std::make_unique<Protocol>(board, false, false, true, false, false);
            active.store(owner.get(), std::memory_order_release);
            shuttingDown.store(false, std::memory_order_release);
            ready.store(true, std::memory_order_release);
            return 1;
        } catch (...) {
            resetFailedInitialization();
            return 0;
        }
    }

    int send(const char *command) {
        if (command == nullptr || *command == '\0' || !enterCall()) {
            return 0;
        }
        Protocol *protocol = active.load(std::memory_order_acquire);
        int result = 0;
        if (protocol != nullptr) {
            const std::string commandString(command);
            const bool keepRunning = protocol->dispatchCommand(commandString);
            result = keepRunning || commandString == "quit" ? 1 : 0;
        }
        leaveCall();
        return result;
    }

    int isReady() const {
        return ready.load(std::memory_order_acquire) &&
               !shuttingDown.load(std::memory_order_acquire);
    }

    int isSearching() {
        if (!enterCall()) {
            return 0;
        }
        Protocol *protocol = active.load(std::memory_order_acquire);
        const int result = protocol != nullptr && protocol->isSearching();
        leaveCall();
        return result;
    }

    void shutdown() {
        std::unique_lock<std::mutex> lifecycleLock(lifecycleMutex);
        if (!ready.load(std::memory_order_acquire)) {
            return;
        }

        shuttingDown.store(true, std::memory_order_release);
        Protocol *protocol = active.load(std::memory_order_acquire);
        if (protocol != nullptr && protocol->isSearching()) {
            protocol->dispatchCommand("stop");
        }

        {
            std::unique_lock<std::mutex> callLock(callMutex);
            callCondition.wait(callLock, [this] {
                return activeCalls.load(std::memory_order_acquire) == 0;
            });
        }

        protocol = active.exchange(nullptr, std::memory_order_acq_rel);
        if (protocol != nullptr) {
            protocol->dispatchCommand("quit");
        }
        owner.reset();
        if (globalsInitialized) {
            globals::cleanupGlobals();
            globalsInitialized = false;
        }
        globals::setOutput(nullptr);
        output.reset();
        ready.store(false, std::memory_order_release);
    }

  private:
    bool enterCall() {
        if (shuttingDown.load(std::memory_order_acquire) ||
            !ready.load(std::memory_order_acquire)) {
            return false;
        }
        activeCalls.fetch_add(1, std::memory_order_acq_rel);
        if (shuttingDown.load(std::memory_order_acquire)) {
            leaveCall();
            return false;
        }
        return true;
    }

    void leaveCall() {
        if (activeCalls.fetch_sub(1, std::memory_order_acq_rel) == 1) {
            callCondition.notify_all();
        }
    }

    void resetFailedInitialization() {
        active.store(nullptr, std::memory_order_release);
        owner.reset();
        if (globalsInitialized) {
            globals::cleanupGlobals();
            globalsInitialized = false;
        }
        globals::setOutput(nullptr);
        output.reset();
        ready.store(false, std::memory_order_release);
    }

    std::mutex lifecycleMutex;
    std::mutex callMutex;
    std::condition_variable callCondition;
    std::atomic<unsigned> activeCalls{0};
    std::atomic<bool> ready{false};
    std::atomic<bool> shuttingDown{false};
    std::atomic<Protocol *> active{nullptr};
    std::unique_ptr<Protocol> owner;
    std::unique_ptr<CallbackStream> output;
    bool globalsInitialized = false;
};

EmbeddedRuntime runtime;

} // namespace

extern "C" {

int arasan_embed_initialize(
    const char *resource_root,
    arasan_output_callback output,
    void *context
) {
    return runtime.initialize(resource_root, output, context);
}

int arasan_embed_send(const char *uci_command) {
    return runtime.send(uci_command);
}

int arasan_embed_is_ready(void) {
    return runtime.isReady();
}

int arasan_embed_is_searching(void) {
    return runtime.isSearching();
}

void arasan_embed_shutdown(void) {
    runtime.shutdown();
}

}
