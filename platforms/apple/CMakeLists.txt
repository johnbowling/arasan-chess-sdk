cmake_minimum_required(VERSION 3.20 FATAL_ERROR)
project(arasan_apple LANGUAGES CXX)

if(NOT APPLE OR NOT CMAKE_SYSTEM_NAME STREQUAL "iOS")
    message(FATAL_ERROR "Configure this target with CMAKE_SYSTEM_NAME=iOS")
endif()
if(CMAKE_OSX_DEPLOYMENT_TARGET VERSION_LESS "16.0")
    message(FATAL_ERROR "The supported iOS deployment target is 16.0 or newer")
endif()

get_filename_component(ARASAN_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)
set(ARASAN_EMBED_NETWORK arasan.nnue)
include("${ARASAN_ROOT}/cmake/ArasanEmbedded.cmake")

add_arasan_embedded_library(arasan_embed_apple)
target_compile_definitions(arasan_embed_apple PRIVATE
    _MAC
    ARASAN_EMBED_APPLE
    SIMD
)
set_target_properties(arasan_embed_apple PROPERTIES
    OUTPUT_NAME arasan_embed
    POSITION_INDEPENDENT_CODE ON
    PUBLIC_HEADER "${ARASAN_ROOT}/src/embed/arasan_embed.h"
)

if(CMAKE_OSX_ARCHITECTURES MATCHES "(^|;)arm64($|;)")
    target_compile_definitions(arasan_embed_apple PRIVATE NEON)
elseif(CMAKE_OSX_ARCHITECTURES MATCHES "(^|;)x86_64($|;)")
    target_compile_definitions(arasan_embed_apple PRIVATE SSE2)
    target_compile_options(arasan_embed_apple PRIVATE -msse2)
else()
    message(FATAL_ERROR
        "Build one Apple architecture at a time (arm64 or x86_64); got: "
        "${CMAKE_OSX_ARCHITECTURES}")
endif()

install(TARGETS arasan_embed_apple
    ARCHIVE DESTINATION lib
    PUBLIC_HEADER DESTINATION include
)
