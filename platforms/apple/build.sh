#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd "${script_dir}/../.." && pwd)"
build_dir="${ARASAN_APPLE_BUILD_DIR:-${repo_dir}/build/apple}"
dist_dir="${ARASAN_APPLE_DIST_DIR:-${repo_dir}/dist/apple}"
deployment_target="${ARASAN_IOS_DEPLOYMENT_TARGET:-16.0}"

for tool in cmake ninja xcodebuild xcrun lipo node; do
    if ! command -v "${tool}" >/dev/null 2>&1; then
        echo "${tool} is required to build the Apple package" >&2
        exit 1
    fi
done

configure_and_build() {
    local name="$1"
    local sdk="$2"
    local architecture="$3"
    local sdk_path
    sdk_path="$(xcrun --sdk "${sdk}" --show-sdk-path)"

    cmake \
        -S "${script_dir}" \
        -B "${build_dir}/${name}" \
        -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_SYSTEM_NAME=iOS \
        -DCMAKE_OSX_SYSROOT="${sdk_path}" \
        -DCMAKE_OSX_ARCHITECTURES="${architecture}" \
        -DCMAKE_OSX_DEPLOYMENT_TARGET="${deployment_target}" \
        -DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY
    cmake --build "${build_dir}/${name}" --parallel
}

configure_and_build device iphoneos arm64
configure_and_build simulator-arm64 iphonesimulator arm64

simulator_library="${build_dir}/simulator-arm64/libarasan_embed.a"
if [[ "${ARASAN_APPLE_X86_64_SIMULATOR:-1}" == "1" ]]; then
    configure_and_build simulator-x86_64 iphonesimulator x86_64
    simulator_library="${build_dir}/libarasan_embed-simulator.a"
    lipo -create \
        "${build_dir}/simulator-arm64/libarasan_embed.a" \
        "${build_dir}/simulator-x86_64/libarasan_embed.a" \
        -output "${simulator_library}"
fi

node "${script_dir}/package.mjs" \
    "${build_dir}/device/libarasan_embed.a" \
    "${simulator_library}" \
    "${dist_dir}" \
    "${deployment_target}"

echo "Arasan Apple package: ${dist_dir}"
