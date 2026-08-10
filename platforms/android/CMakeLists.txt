cmake_minimum_required(VERSION 3.20 FATAL_ERROR)
project(arasan_android LANGUAGES CXX)

if(NOT ANDROID)
    message(FATAL_ERROR "Configure this target with the Android NDK toolchain")
endif()
if(NOT ANDROID_ABI STREQUAL "arm64-v8a" AND NOT ANDROID_ABI STREQUAL "x86_64")
    message(FATAL_ERROR "Supported Android ABIs are arm64-v8a and x86_64; got ${ANDROID_ABI}")
endif()

get_filename_component(ARASAN_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)
include("${ARASAN_ROOT}/cmake/ArasanEmbedded.cmake")

add_arasan_embedded_library(arasan_embed_android)
set_target_properties(arasan_embed_android PROPERTIES
    POSITION_INDEPENDENT_CODE ON
)
target_compile_definitions(arasan_embed_android PRIVATE ARASAN_EMBED_ANDROID SIMD)

if(ANDROID_ABI STREQUAL "arm64-v8a")
    target_compile_definitions(arasan_embed_android PRIVATE NEON)
else()
    target_compile_definitions(arasan_embed_android PRIVATE SSE2)
    target_compile_options(arasan_embed_android PRIVATE -msse2)
endif()

add_library(arasan_android SHARED src/main/cpp/arasan_jni.cpp)
target_link_libraries(arasan_android PRIVATE arasan_embed_android)
target_compile_features(arasan_android PRIVATE cxx_std_17)
set_target_properties(arasan_android PROPERTIES
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN YES
)
