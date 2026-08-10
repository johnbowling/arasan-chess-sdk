#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd "${script_dir}/../.." && pwd)"
build_dir="${ARASAN_APPLE_BUILD_DIR:-${repo_dir}/build/apple}"
app_dir="${build_dir}/smoke/ArasanAppleSmoke.app"
bundle_id="org.arasanchess.sdk.smoke"
simulator="${ARASAN_SIMULATOR_UDID:-booted}"

if [[ ! -d "${app_dir}" ]]; then
    echo "build the smoke application before running it" >&2
    exit 1
fi

if ! xcrun simctl list devices booted | grep -q "(Booted)"; then
    echo "no booted iOS simulator; boot one or set ARASAN_SIMULATOR_UDID" >&2
    exit 1
fi

echo "Preparing simulator ${simulator}"
xcrun simctl uninstall "${simulator}" "${bundle_id}" >/dev/null 2>&1 || true
echo "Installing smoke application"
xcrun simctl install "${simulator}" "${app_dir}"
echo "Locating smoke application data"
data_dir="$(xcrun simctl get_app_container "${simulator}" "${bundle_id}" data)"
result_file="${data_dir}/Documents/arasan-smoke-result.txt"
rm -f "${result_file}"
echo "Launching smoke application"
xcrun simctl launch --terminate-running-process "${simulator}" "${bundle_id}"
echo "Waiting for smoke result"

last_result=""
for _ in {1..120}; do
    if [[ -f "${result_file}" ]]; then
        result="$(<"${result_file}")"
        if [[ "${result}" != "${last_result}" ]]; then
            echo "${result}"
            last_result="${result}"
        fi
        case "${result}" in
            PASS:*)
                xcrun simctl terminate "${simulator}" "${bundle_id}" >/dev/null 2>&1 || true
                exit
                ;;
            FAIL:*)
                xcrun simctl terminate "${simulator}" "${bundle_id}" >/dev/null 2>&1 || true
                exit 1
                ;;
        esac
    fi
    sleep 1
done

xcrun simctl terminate "${simulator}" "${bundle_id}" >/dev/null 2>&1 || true
echo "timed out waiting for the Apple smoke application" >&2
exit 1
