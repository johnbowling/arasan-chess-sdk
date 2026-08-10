package org.arasanchess.sdk;

import android.content.Context;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.Executor;
import java.util.concurrent.atomic.AtomicBoolean;

/** A single in-process Arasan engine that exchanges complete UCI lines. */
public final class ArasanEngine implements AutoCloseable {
    /** Receives one complete UCI output line without a trailing newline. */
    public interface OutputListener {
        void onLine(String line);
    }

    private static final Object RESOURCE_LOCK = new Object();

    static {
        System.loadLibrary("arasan_android");
    }

    private final Executor callbackExecutor;
    private final OutputListener outputListener;
    private final AtomicBoolean closed = new AtomicBoolean(false);

    private ArasanEngine(Executor callbackExecutor, OutputListener outputListener) {
        this.callbackExecutor = callbackExecutor;
        this.outputListener = outputListener;
    }

    /**
     * Copies and verifies the packaged NNUE asset, then initializes Arasan.
     * Only one engine may be open in a process at a time.
     */
    public static ArasanEngine open(
            Context context,
            Executor callbackExecutor,
            OutputListener outputListener
    ) throws IOException {
        Objects.requireNonNull(context, "context");
        Objects.requireNonNull(callbackExecutor, "callbackExecutor");
        Objects.requireNonNull(outputListener, "outputListener");

        File resourceRoot = prepareResources(context.getApplicationContext());
        ArasanEngine engine = new ArasanEngine(callbackExecutor, outputListener);
        if (!engine.nativeInitialize(resourceRoot.getAbsolutePath())) {
            engine.closed.set(true);
            throw new IllegalStateException(
                    "Arasan initialization failed; another process-wide engine may already be open"
            );
        }
        return engine;
    }

    public static String version() {
        return BuildConfig.ENGINE_VERSION;
    }

    /** Sends one UCI command. Bounded go commands execute synchronously. */
    public boolean send(String command) {
        Objects.requireNonNull(command, "command");
        if (command.isEmpty() || command.indexOf('\n') >= 0 || command.indexOf('\r') >= 0) {
            throw new IllegalArgumentException("command must contain exactly one non-empty UCI line");
        }
        return !closed.get() && nativeSend(command);
    }

    public boolean isReady() {
        return !closed.get() && nativeIsReady();
    }

    public boolean isSearching() {
        return !closed.get() && nativeIsSearching();
    }

    @Override
    public void close() {
        if (closed.compareAndSet(false, true)) {
            nativeShutdown();
        }
    }

    @SuppressWarnings("unused") // Called from JNI on engine/search threads.
    private void dispatchNativeLine(String line) {
        if (closed.get()) {
            return;
        }
        try {
            callbackExecutor.execute(() -> {
                if (!closed.get()) {
                    outputListener.onLine(line);
                }
            });
        } catch (RuntimeException ignored) {
            // A rejected callback must not leave the JNI thread with an exception pending.
        }
    }

    private static File prepareResources(Context context) throws IOException {
        synchronized (RESOURCE_LOCK) {
            String identity = BuildConfig.ENGINE_VERSION + "-"
                    + BuildConfig.NETWORK_SHA256.substring(0, 12).toLowerCase(Locale.ROOT);
            File root = new File(context.getNoBackupFilesDir(), "arasan-sdk/" + identity);
            if (!root.isDirectory() && !root.mkdirs()) {
                throw new IOException("could not create Arasan resource directory: " + root);
            }

            File network = new File(root, BuildConfig.NETWORK_ASSET);
            if (isExpectedNetwork(network)) {
                return root;
            }

            File temporary = new File(
                    root,
                    BuildConfig.NETWORK_ASSET + ".tmp-" + android.os.Process.myPid()
            );
            if (temporary.exists() && !temporary.delete()) {
                throw new IOException("could not remove stale temporary network: " + temporary);
            }

            MessageDigest digest = newSha256();
            long copied = 0;
            try (InputStream input = context.getAssets().open(
                    "arasan/" + BuildConfig.NETWORK_ASSET
            ); FileOutputStream output = new FileOutputStream(temporary)) {
                byte[] buffer = new byte[64 * 1024];
                int count;
                while ((count = input.read(buffer)) != -1) {
                    output.write(buffer, 0, count);
                    digest.update(buffer, 0, count);
                    copied += count;
                }
                output.getFD().sync();
            } catch (IOException error) {
                temporary.delete();
                throw error;
            }

            String copiedSha256 = toHex(digest.digest());
            if (copied != BuildConfig.NETWORK_BYTES
                    || !BuildConfig.NETWORK_SHA256.equalsIgnoreCase(copiedSha256)) {
                temporary.delete();
                throw new IOException("packaged Arasan network failed integrity validation");
            }
            if (network.exists() && !network.delete()) {
                temporary.delete();
                throw new IOException("could not replace invalid Arasan network: " + network);
            }
            if (!temporary.renameTo(network)) {
                temporary.delete();
                throw new IOException("could not install Arasan network: " + network);
            }
            return root;
        }
    }

    private static boolean isExpectedNetwork(File network) throws IOException {
        if (!network.isFile() || network.length() != BuildConfig.NETWORK_BYTES) {
            return false;
        }
        MessageDigest digest = newSha256();
        try (FileInputStream input = new FileInputStream(network)) {
            byte[] buffer = new byte[64 * 1024];
            int count;
            while ((count = input.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
            }
        }
        return BuildConfig.NETWORK_SHA256.equalsIgnoreCase(toHex(digest.digest()));
    }

    private static MessageDigest newSha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException impossible) {
            throw new AssertionError("Android runtime does not provide SHA-256", impossible);
        }
    }

    private static String toHex(byte[] bytes) {
        StringBuilder result = new StringBuilder(bytes.length * 2);
        for (byte value : bytes) {
            result.append(String.format(Locale.ROOT, "%02x", value & 0xff));
        }
        return result.toString();
    }

    private native boolean nativeInitialize(String resourceRoot);
    private native boolean nativeSend(String command);
    private native boolean nativeIsReady();
    private native boolean nativeIsSearching();
    private native void nativeShutdown();
}
