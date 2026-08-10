include_guard(GLOBAL)

function(add_arasan_embedded_library target)
    if(NOT ARASAN_ROOT)
        message(FATAL_ERROR "ARASAN_ROOT must point to the repository root")
    endif()
    file(READ "${ARASAN_ROOT}/sdk/upstream.json" arasan_upstream_json)
    string(JSON arasan_manifest_version GET "${arasan_upstream_json}" engineVersion)
    string(JSON arasan_manifest_network GET "${arasan_upstream_json}" network packagedName)
    if(NOT ARASAN_EMBED_VERSION)
        set(ARASAN_EMBED_VERSION "${arasan_manifest_version}")
    endif()
    if(NOT ARASAN_EMBED_NETWORK)
        set(ARASAN_EMBED_NETWORK "${arasan_manifest_network}")
    endif()

    set(arasan_src "${ARASAN_ROOT}/src")
    set(arasan_sources
        tester.cpp
        bench.cpp
        protocol.cpp
        input.cpp
        globals.cpp
        board.cpp
        boardio.cpp
        material.cpp
        chess.cpp
        attacks.cpp
        bitutil.cpp
        chessio.cpp
        epdrec.cpp
        bhash.cpp
        scoring.cpp
        see.cpp
        movearr.cpp
        notation.cpp
        options.cpp
        bitprobe.cpp
        bookread.cpp
        bookwrit.cpp
        search.cpp
        searchc.cpp
        learn.cpp
        movegen.cpp
        hash.cpp
        calctime.cpp
        eco.cpp
        legal.cpp
        stats.cpp
        threadp.cpp
        threadc.cpp
        evaluate.cpp
        embed/arasan_embed.cpp
    )
    list(TRANSFORM arasan_sources PREPEND "${arasan_src}/")

    add_library(${target} STATIC ${arasan_sources})
    target_include_directories(${target}
        PUBLIC "${arasan_src}/embed"
        PRIVATE "${arasan_src}" "${arasan_src}/nnue"
    )
    target_compile_features(${target} PUBLIC cxx_std_17)
    target_compile_definitions(${target} PRIVATE
        ARASAN_EMBED_BUILD
        ARASAN_VERSION=${ARASAN_EMBED_VERSION}
        NETWORK=${ARASAN_EMBED_NETWORK}
        SMP_STATS
        USE_INTRINSICS
        _64BIT
    )
endfunction()
