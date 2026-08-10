cmake_minimum_required(VERSION 3.20 FATAL_ERROR)
project(arasan_wasm LANGUAGES CXX)

if(NOT EMSCRIPTEN)
    message(FATAL_ERROR "Use emcmake to configure the WebAssembly target")
endif()

get_filename_component(ARASAN_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)
set(ARASAN_EMBED_NETWORK arasan.nnue)
include("${ARASAN_ROOT}/cmake/ArasanEmbedded.cmake")

add_arasan_embedded_library(arasan_embed_wasm)
target_compile_definitions(arasan_embed_wasm PRIVATE SIMD SSE2)
target_compile_options(arasan_embed_wasm PRIVATE
    -msimd128
    -msse2
    -fexceptions
)

add_executable(arasan_wasm arasan_wasm.cpp)
target_link_libraries(arasan_wasm PRIVATE arasan_embed_wasm)
target_compile_features(arasan_wasm PRIVATE cxx_std_17)
target_compile_options(arasan_wasm PRIVATE -msimd128 -msse2 -fexceptions)
set_target_properties(arasan_wasm PROPERTIES
    OUTPUT_NAME arasan
    SUFFIX ".js"
)

target_link_options(arasan_wasm PRIVATE
    --no-entry
    -msimd128
    -msse2
    -fexceptions
    -sALLOW_MEMORY_GROWTH=1
    -sMAXIMUM_MEMORY=536870912
    -sINITIAL_MEMORY=134217728
    -sSTACK_SIZE=5242880
    -sNO_EXIT_RUNTIME=1
    -sFILESYSTEM=1
    -sMODULARIZE=1
    -sEXPORT_NAME=createArasanModule
    -sENVIRONMENT=worker
    -sDISABLE_EXCEPTION_CATCHING=0
    "-sEXPORTED_FUNCTIONS=['_arasan_wasm_initialize','_arasan_wasm_command','_arasan_wasm_is_ready','_arasan_wasm_is_searching','_arasan_wasm_shutdown']"
    "-sEXPORTED_RUNTIME_METHODS=['ccall','FS']"
)
