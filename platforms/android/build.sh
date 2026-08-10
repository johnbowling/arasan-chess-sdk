#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd "${script_dir}/../.." && pwd)"
dist_dir="${ARASAN_ANDROID_DIST_DIR:-${repo_dir}/dist/android}"
gradle_command="${ARASAN_GRADLE:-gradle}"

for tool in "${gradle_command}" java node unzip; do
    if ! command -v "${tool}" >/dev/null 2>&1; then
        echo "${tool} is required to build the Android package" >&2
        exit 1
    fi
done

"${gradle_command}" \
    --no-daemon \
    --project-dir "${script_dir}" \
    :library:clean \
    :smoke:clean \
    :library:assembleRelease \
    :smoke:assembleDebug

node "${script_dir}/package.mjs" \
    "${script_dir}/library/build/outputs/aar/library-release.aar" \
    "${dist_dir}"

echo "Arasan Android package: ${dist_dir}"
