#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
apk="${ARASAN_ANDROID_SMOKE_APK:-${script_dir}/smoke/build/outputs/apk/debug/smoke-debug.apk}"
package="org.arasanchess.sdk.smoke"
activity="${package}/.SmokeActivity"
result_file="files/arasan-smoke-result.txt"

if ! command -v adb >/dev/null 2>&1; then
    echo "adb is required to run the Android smoke suite" >&2
    exit 1
fi
if [[ ! -f "${apk}" ]]; then
    echo "build the Android smoke application before running it" >&2
    exit 1
fi
if ! adb get-state 2>/dev/null | grep -q '^device$'; then
    echo "no Android device or emulator is ready" >&2
    exit 1
fi

adb install --replace "${apk}" >/dev/null

run_cycle() {
    local cycle="$1"
    echo "Running Android smoke cycle ${cycle}"
    adb shell am force-stop "${package}" >/dev/null 2>&1 || true
    adb shell run-as "${package}" rm -f "${result_file}" >/dev/null 2>&1 || true
    adb shell am start -W -n "${activity}" >/dev/null

    local result=""
    for _ in {1..180}; do
        result="$(adb shell run-as "${package}" cat "${result_file}" 2>/dev/null | tr -d '\r' || true)"
        case "${result}" in
            PASS:*)
                echo "${result}"
                return
                ;;
            FAIL:*)
                echo "${result}" >&2
                adb logcat -d -v brief "${TAG:-ArasanAndroidSmoke}:V" '*:S' >&2 || true
                return 1
                ;;
        esac
        sleep 1
    done

    adb logcat -d -v brief "${TAG:-ArasanAndroidSmoke}:V" '*:S' >&2 || true
    echo "timed out waiting for Android smoke cycle ${cycle}" >&2
    return 1
}

run_cycle 1
run_cycle 2
adb shell am force-stop "${package}" >/dev/null 2>&1 || true
