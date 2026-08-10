#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd "${script_dir}/../.." && pwd)"
build_dir="${ARASAN_WASM_BUILD_DIR:-${repo_dir}/build/wasm}"
dist_dir="${ARASAN_WASM_DIST_DIR:-${repo_dir}/dist/wasm}"

if ! command -v emcmake >/dev/null 2>&1; then
    echo "emcmake is not on PATH; activate Emscripten 6.0.6 first" >&2
    exit 1
fi

emcmake cmake \
    -S "${script_dir}" \
    -B "${build_dir}" \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release
cmake --build "${build_dir}" --parallel
node "${script_dir}/package.mjs" "${build_dir}" "${dist_dir}"

echo "Arasan WASM package: ${dist_dir}"
