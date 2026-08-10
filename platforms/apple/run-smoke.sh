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

xcrun simctl uninstall "${simulator}" "${bundle_id}" >/dev/null 2>&1 || true
xcrun simctl install "${simulator}" "${app_dir}"
data_dir="$(xcrun simctl get_app_container "${simulator}" "${bundle_id}" data)"
result_file="${data_dir}/Documents/arasan-smoke-result.txt"
rm -f "${result_file}"
xcrun simctl launch --terminate-running-process "${simulator}" "${bundle_id}" >/dev/null

for _ in {1..120}; do
    if [[ -f "${result_file}" ]]; then
        result="$(<"${result_file}")"
        echo "${result}"
        xcrun simctl terminate "${simulator}" "${bundle_id}" >/dev/null 2>&1 || true
        [[ "${result}" == PASS:* ]]
        exit
    fi
    sleep 1
done

xcrun simctl spawn "${simulator}" log show \
    --last 2m \
    --style compact \
    --predicate "process == 'ArasanAppleSmoke'" || true
echo "timed out waiting for the Apple smoke application" >&2
exit 1
