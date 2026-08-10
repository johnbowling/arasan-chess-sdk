import ArasanEngine
import Foundation
import UIKit

private final class OutputCollector {
    private let lock = NSLock()
    private var storage: [String] = []

    func append(_ line: String) {
        lock.lock()
        storage.append(line)
        lock.unlock()
    }

    func reset() {
        lock.lock()
        storage.removeAll(keepingCapacity: true)
        lock.unlock()
    }

    func lines() -> [String] {
        lock.lock()
        defer { lock.unlock() }
        return storage
    }
}

private func collectEngineOutput(
    _ line: UnsafePointer<CChar>?,
    _ context: UnsafeMutableRawPointer?
) {
    guard let line, let context else { return }
    let collector = Unmanaged<OutputCollector>.fromOpaque(context).takeUnretainedValue()
    collector.append(String(cString: line))
}

private enum SmokeFailure: Error, CustomStringConvertible {
    case failed(String)

    var description: String {
        switch self {
        case let .failed(message): message
        }
    }
}

private func require(_ condition: @autoclosure () -> Bool, _ message: String) throws {
    if !condition() {
        throw SmokeFailure.failed(message)
    }
}

private func hasBestMove(_ lines: [String]) -> Bool {
    lines.contains { line in
        guard line.hasPrefix("bestmove ") else { return false }
        let fields = line.split(separator: " ")
        guard fields.count >= 2 else { return false }
        let move = fields[1]
        return move != "(none)" && (move.count == 4 || move.count == 5)
    }
}

private func runEngineSmoke() throws {
    guard let resourceRoot = Bundle.main.resourcePath else {
        throw SmokeFailure.failed("application resource path is unavailable")
    }

    let collector = OutputCollector()
    let context = Unmanaged.passUnretained(collector).toOpaque()

    for cycle in 1...2 {
        collector.reset()
        try require(
            arasan_embed_initialize(resourceRoot, collectEngineOutput, context) == 1,
            "cycle \(cycle): initialize failed"
        )
        defer { arasan_embed_shutdown() }

        try require(arasan_embed_is_ready() == 1, "cycle \(cycle): engine is not ready")
        try require(arasan_embed_send("uci") == 1, "cycle \(cycle): uci failed")
        try require(arasan_embed_send("isready") == 1, "cycle \(cycle): isready failed")

        if cycle == 1 {
            try require(
                arasan_embed_send("setoption name MultiPV value 3") == 1,
                "MultiPV option failed"
            )
            try require(
                arasan_embed_send("position fen r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3") == 1,
                "FEN position failed"
            )
            try require(arasan_embed_send("go depth 5") == 1, "bounded search failed")

            let boundedLines = collector.lines()
            try require(boundedLines.contains("uciok"), "uciok was not emitted")
            try require(boundedLines.contains("readyok"), "readyok was not emitted")
            try require(hasBestMove(boundedLines), "bounded search emitted no legal bestmove")
            for index in 1...3 {
                try require(
                    boundedLines.contains { $0.contains(" multipv \(index) ") },
                    "bounded search emitted no multipv \(index) line"
                )
            }

            let searchGroup = DispatchGroup()
            searchGroup.enter()
            DispatchQueue.global(qos: .userInitiated).async {
                _ = arasan_embed_send("go infinite")
                searchGroup.leave()
            }

            let searchDeadline = Date().addingTimeInterval(5)
            while arasan_embed_is_searching() == 0 && Date() < searchDeadline {
                Thread.sleep(forTimeInterval: 0.01)
            }
            try require(arasan_embed_is_searching() == 1, "infinite search did not start")
            try require(arasan_embed_send("stop") == 1, "stop failed")
            try require(
                searchGroup.wait(timeout: .now() + 20) == .success,
                "infinite search did not stop"
            )
            try require(hasBestMove(collector.lines()), "stopped search emitted no bestmove")
        } else {
            try require(arasan_embed_send("position startpos") == 1, "startpos failed")
            try require(arasan_embed_send("go depth 4") == 1, "restart search failed")
            try require(hasBestMove(collector.lines()), "restart search emitted no bestmove")
        }

        arasan_embed_shutdown()
        try require(arasan_embed_is_ready() == 0, "cycle \(cycle): shutdown failed")
    }
}

@main
final class AppDelegate: UIResponder, UIApplicationDelegate {
    var window: UIWindow?
    private let statusLabel = UILabel()

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        let window = UIWindow(frame: UIScreen.main.bounds)
        let controller = UIViewController()
        controller.view.backgroundColor = .systemBackground
        statusLabel.text = "Running Arasan Apple SDK smoke test…"
        statusLabel.numberOfLines = 0
        statusLabel.textAlignment = .center
        statusLabel.translatesAutoresizingMaskIntoConstraints = false
        controller.view.addSubview(statusLabel)
        NSLayoutConstraint.activate([
            statusLabel.leadingAnchor.constraint(equalTo: controller.view.leadingAnchor, constant: 24),
            statusLabel.trailingAnchor.constraint(equalTo: controller.view.trailingAnchor, constant: -24),
            statusLabel.centerYAnchor.constraint(equalTo: controller.view.centerYAnchor),
        ])
        window.rootViewController = controller
        window.makeKeyAndVisible()
        self.window = window

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result: String
            do {
                try runEngineSmoke()
                result = "PASS: UCI, MultiPV, cancellation, restart, and shutdown"
            } catch {
                arasan_embed_shutdown()
                result = "FAIL: \(error)"
            }

            let resultURL = FileManager.default.urls(
                for: .documentDirectory,
                in: .userDomainMask
            )[0].appendingPathComponent("arasan-smoke-result.txt")
            try? result.write(to: resultURL, atomically: true, encoding: .utf8)
            DispatchQueue.main.async {
                self?.statusLabel.text = result
            }
        }
        return true
    }
}
