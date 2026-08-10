package org.arasanchess.sdk.smoke;

import android.app.Activity;
import android.os.Bundle;
import android.util.Log;
import android.view.Gravity;
import android.widget.TextView;

import org.arasanchess.sdk.ArasanEngine;

import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

public final class SmokeActivity extends Activity {
    private static final String TAG = "ArasanAndroidSmoke";
    private static final String RESULT_FILE = "arasan-smoke-result.txt";
    private static final String TEST_FEN =
            "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3";

    private TextView status;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        status = new TextView(this);
        status.setGravity(Gravity.CENTER);
        status.setText("Running Arasan Android SDK smoke test…");
        status.setPadding(48, 48, 48, 48);
        setContentView(status);
        writeResult("RUNNING");

        Thread smoke = new Thread(this::runSmoke, "arasan-android-smoke");
        smoke.start();
    }

    private void runSmoke() {
        String result;
        try {
            runEngineCycle(true);
            runEngineCycle(false);
            result = "PASS: UCI, MultiPV, cancellation, restart, and shutdown";
        } catch (Throwable error) {
            result = "FAIL: " + error.getClass().getSimpleName() + ": " + error.getMessage();
        }
        Log.i(TAG, result);
        writeResult(result);
        String displayed = result;
        runOnUiThread(() -> status.setText(displayed));
    }

    private void runEngineCycle(boolean fullSuite) throws Exception {
        OutputCollector output = new OutputCollector();
        try (ArasanEngine engine = ArasanEngine.open(this, Runnable::run, output::append)) {
            require(engine.isReady(), "engine is not ready after initialization");
            require(engine.send("uci"), "uci command failed");
            require(engine.send("isready"), "isready command failed");
            require(output.containsExact("uciok"), "uciok was not emitted");
            require(output.containsExact("readyok"), "readyok was not emitted");

            if (fullSuite) {
                require(engine.send("setoption name MultiPV value 3"), "MultiPV option failed");
                require(engine.send("position fen " + TEST_FEN), "FEN command failed");
                require(engine.send("go depth 5"), "bounded search failed");
                require(output.hasBestMove(), "bounded search emitted no legal bestmove");
                for (int index = 1; index <= 3; ++index) {
                    require(
                            output.containsFragment(" multipv " + index + " "),
                            "bounded search emitted no multipv " + index + " line"
                    );
                }
                runCancellationTest(engine, output);
            } else {
                require(engine.send("position startpos"), "startpos command failed");
                require(engine.send("go depth 4"), "restart search failed");
                require(output.hasBestMove(), "restart search emitted no legal bestmove");
            }
        }
    }

    private static void runCancellationTest(ArasanEngine engine, OutputCollector output)
            throws Exception {
        int previousBestMoves = output.bestMoveCount();
        AtomicReference<Throwable> searchFailure = new AtomicReference<>();
        Thread search = new Thread(() -> {
            try {
                require(engine.send("go infinite"), "infinite search command failed");
            } catch (Throwable error) {
                searchFailure.set(error);
            }
        }, "arasan-infinite-search");
        search.start();

        long startDeadline = System.nanoTime() + 5_000_000_000L;
        while (!engine.isSearching() && System.nanoTime() < startDeadline) {
            Thread.sleep(10);
        }
        require(engine.isSearching(), "infinite search did not start");
        require(engine.send("stop"), "stop command failed");
        search.join(20_000);
        require(!search.isAlive(), "infinite search did not stop");
        if (searchFailure.get() != null) {
            throw new AssertionError("infinite search thread failed", searchFailure.get());
        }
        require(
                output.bestMoveCount() > previousBestMoves,
                "stopped search emitted no bestmove"
        );
    }

    private void writeResult(String result) {
        File destination = new File(getFilesDir(), RESULT_FILE);
        try (FileOutputStream output = new FileOutputStream(destination, false)) {
            output.write(result.getBytes(StandardCharsets.UTF_8));
            output.getFD().sync();
        } catch (Exception error) {
            Log.e(TAG, "could not write smoke result", error);
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static final class OutputCollector {
        private final List<String> lines = new ArrayList<>();

        synchronized void append(String line) {
            lines.add(line);
        }

        synchronized boolean containsExact(String expected) {
            return lines.contains(expected);
        }

        synchronized boolean containsFragment(String fragment) {
            for (String line : lines) {
                if (line.contains(fragment)) {
                    return true;
                }
            }
            return false;
        }

        synchronized boolean hasBestMove() {
            return bestMoveCount() > 0;
        }

        synchronized int bestMoveCount() {
            int count = 0;
            for (String line : lines) {
                if (isLegalBestMove(line)) {
                    ++count;
                }
            }
            return count;
        }

        private static boolean isLegalBestMove(String line) {
            if (!line.startsWith("bestmove ")) {
                return false;
            }
            String[] fields = line.split(" ");
            if (fields.length < 2 || "(none)".equals(fields[1])) {
                return false;
            }
            return fields[1].matches("[a-h][1-8][a-h][1-8][qrbn]?");
        }
    }
}
