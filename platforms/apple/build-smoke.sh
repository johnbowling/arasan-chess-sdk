#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd "${script_dir}/../.." && pwd)"
build_dir="${ARASAN_APPLE_BUILD_DIR:-${repo_dir}/build/apple}"
dist_dir="${ARASAN_APPLE_DIST_DIR:-${repo_dir}/dist/apple}"
deployment_target="${ARASAN_IOS_DEPLOYMENT_TARGET:-16.0}"
host_architecture="$(uname -m)"

case "${host_architecture}" in
    arm64|x86_64) ;;
    *)
        echo "unsupported simulator host architecture: ${host_architecture}" >&2
        exit 1
        ;;
esac

xcframework="${dist_dir}/Arasan.xcframework"
simulator_slices=("${xcframework}"/ios-*-simulator)
simulator_slice="${simulator_slices[0]}"
app_dir="${build_dir}/smoke/ArasanAppleSmoke.app"
sdk_path="$(xcrun --sdk iphonesimulator --show-sdk-path)"

if [[ ! -d "${simulator_slice}" ]]; then
    echo "build the Apple package before building the smoke application" >&2
    exit 1
fi
simulator_libraries=("${simulator_slice}"/*.a)
simulator_library="${simulator_libraries[0]}"
if [[ ! -f "${simulator_library}" ]]; then
    echo "the Apple package does not contain a simulator library" >&2
    exit 1
fi

rm -rf "${app_dir}"
mkdir -p "${app_dir}"
xcrun --sdk iphonesimulator swiftc \
    -swift-version 5 \
    -parse-as-library \
    -O \
    -sdk "${sdk_path}" \
    -target "${host_architecture}-apple-ios${deployment_target}-simulator" \
    -I "${simulator_slice}/Headers" \
    "${script_dir}/smoke/AppDelegate.swift" \
    "${simulator_library}" \
    -lc++ \
    -framework UIKit \
    -o "${app_dir}/ArasanAppleSmoke"
cp "${script_dir}/smoke/Info.plist" "${app_dir}/Info.plist"
plutil -replace MinimumOSVersion -string "${deployment_target}" "${app_dir}/Info.plist"
cp "${dist_dir}/resources/arasan.nnue" "${app_dir}/arasan.nnue"
codesign --force --sign - --timestamp=none "${app_dir}"

echo "Arasan Apple smoke application: ${app_dir}"
