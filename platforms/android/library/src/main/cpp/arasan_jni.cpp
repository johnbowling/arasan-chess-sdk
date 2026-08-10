#include <jni.h>

#include "arasan_embed.h"

#include <memory>
#include <mutex>

namespace {

struct AndroidCallback {
    JavaVM *vm = nullptr;
    jobject engine = nullptr;
    jmethodID dispatchLine = nullptr;
};

std::mutex bridgeMutex;
AndroidCallback *bridgeCallback = nullptr;

void dispatchOutput(const char *line, void *opaque) {
    auto *callback = static_cast<AndroidCallback *>(opaque);
    if (callback == nullptr || line == nullptr) {
        return;
    }

    JNIEnv *environment = nullptr;
    bool attached = false;
    const jint state = callback->vm->GetEnv(
        reinterpret_cast<void **>(&environment),
        JNI_VERSION_1_6
    );
    if (state == JNI_EDETACHED) {
        if (callback->vm->AttachCurrentThread(&environment, nullptr) != JNI_OK) {
            return;
        }
        attached = true;
    } else if (state != JNI_OK) {
        return;
    }

    jstring javaLine = environment->NewStringUTF(line);
    if (javaLine != nullptr) {
        environment->CallVoidMethod(callback->engine, callback->dispatchLine, javaLine);
        environment->DeleteLocalRef(javaLine);
    }
    if (environment->ExceptionCheck()) {
        environment->ExceptionClear();
    }
    if (attached) {
        callback->vm->DetachCurrentThread();
    }
}

void releaseCallback(JNIEnv *environment, AndroidCallback *callback) {
    if (callback != nullptr) {
        if (callback->engine != nullptr) {
            environment->DeleteGlobalRef(callback->engine);
        }
        delete callback;
    }
}

} // namespace

extern "C" JNIEXPORT jboolean JNICALL
Java_org_arasanchess_sdk_ArasanEngine_nativeInitialize(
    JNIEnv *environment,
    jobject engine,
    jstring resourceRoot
) {
    if (resourceRoot == nullptr) {
        return JNI_FALSE;
    }

    std::lock_guard<std::mutex> lock(bridgeMutex);
    if (bridgeCallback != nullptr) {
        return JNI_FALSE;
    }

    auto callback = std::make_unique<AndroidCallback>();
    if (environment->GetJavaVM(&callback->vm) != JNI_OK) {
        return JNI_FALSE;
    }
    callback->engine = environment->NewGlobalRef(engine);
    if (callback->engine == nullptr) {
        return JNI_FALSE;
    }
    jclass engineClass = environment->GetObjectClass(engine);
    if (engineClass == nullptr) {
        releaseCallback(environment, callback.release());
        return JNI_FALSE;
    }
    callback->dispatchLine = environment->GetMethodID(
        engineClass,
        "dispatchNativeLine",
        "(Ljava/lang/String;)V"
    );
    environment->DeleteLocalRef(engineClass);
    if (callback->dispatchLine == nullptr) {
        if (environment->ExceptionCheck()) {
            environment->ExceptionClear();
        }
        releaseCallback(environment, callback.release());
        return JNI_FALSE;
    }

    const char *root = environment->GetStringUTFChars(resourceRoot, nullptr);
    if (root == nullptr) {
        releaseCallback(environment, callback.release());
        return JNI_FALSE;
    }
    const int initialized = arasan_embed_initialize(root, dispatchOutput, callback.get());
    environment->ReleaseStringUTFChars(resourceRoot, root);
    if (!initialized) {
        releaseCallback(environment, callback.release());
        return JNI_FALSE;
    }

    bridgeCallback = callback.release();
    return JNI_TRUE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_org_arasanchess_sdk_ArasanEngine_nativeSend(
    JNIEnv *environment,
    jobject,
    jstring command
) {
    if (command == nullptr) {
        return JNI_FALSE;
    }
    const char *value = environment->GetStringUTFChars(command, nullptr);
    if (value == nullptr) {
        return JNI_FALSE;
    }
    const int accepted = arasan_embed_send(value);
    environment->ReleaseStringUTFChars(command, value);
    return accepted ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_org_arasanchess_sdk_ArasanEngine_nativeIsReady(JNIEnv *, jobject) {
    return arasan_embed_is_ready() ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_org_arasanchess_sdk_ArasanEngine_nativeIsSearching(JNIEnv *, jobject) {
    return arasan_embed_is_searching() ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT void JNICALL
Java_org_arasanchess_sdk_ArasanEngine_nativeShutdown(JNIEnv *environment, jobject) {
    std::lock_guard<std::mutex> lock(bridgeMutex);
    if (bridgeCallback == nullptr) {
        return;
    }
    arasan_embed_shutdown();
    releaseCallback(environment, bridgeCallback);
    bridgeCallback = nullptr;
}
