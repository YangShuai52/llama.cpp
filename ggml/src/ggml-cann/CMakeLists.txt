if ("cann${CANN_INSTALL_DIR}" STREQUAL "cann" AND DEFINED ENV{ASCEND_TOOLKIT_HOME})
    set(CANN_INSTALL_DIR $ENV{ASCEND_TOOLKIT_HOME})
    message(STATUS "CANN: updated CANN_INSTALL_DIR from ASCEND_TOOLKIT_HOME=$ENV{ASCEND_TOOLKIT_HOME}")
endif()

# Auto-detech Soc type and Soc version, if detect failed, will abort build
set(SOC_VERSION "")
function(detect_ascend_soc_type SOC_VERSION)
    execute_process(
        COMMAND bash -c "npu-smi info|awk -F' ' 'NF > 0 && NR==7 {print $3}'"
        OUTPUT_VARIABLE npu_info
        RESULT_VARIABLE npu_result
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    if("${npu_info}" STREQUAL "" OR ${npu_result})
        message(FATAL_ERROR "Auto-detech ascend soc type failed, please specify manually or check ascend device working normally.")
    endif()
    set(${SOC_VERSION} "Ascend${npu_info}" PARENT_SCOPE)
endfunction()

if(NOT SOC_TYPE)
    detect_ascend_soc_type(SOC_VERSION)
    set(SOC_TYPE "${SOC_VERSION}")
    message(STATUS "CANN: SOC_VERSION auto-detected is:${SOC_VERSION}")
endif()

string(TOLOWER ${SOC_TYPE} SOC_VERSION) # SOC_VERSION need lower

# Construct Soc specify compile option: ASCEND_#Soc_Major_SN. Such as ASCEND_910B, ASCEND_310P.
string(REGEX MATCH "[0-9]+[a-zA-Z]" SOC_TYPE_MAJOR_SN "${SOC_VERSION}")
set(SOC_TYPE_COMPILE_OPTION "ASCEND_${SOC_TYPE_MAJOR_SN}")
string(TOUPPER ${SOC_TYPE_COMPILE_OPTION} SOC_TYPE_COMPILE_OPTION)
message(STATUS "CANN: SOC_VERSION =  ${SOC_VERSION}")
option(USE_ACL_GRAPH "Enable CANN graph execution (ACL graph mode)" OFF)

if(USE_ACL_GRAPH AND (SOC_TYPE_MAJOR_SN STREQUAL "310P" OR SOC_TYPE_COMPILE_OPTION STREQUAL "ASCEND_310P"))
    message(FATAL_ERROR
        "CANN Graph (ACL graph mode) is not supported on 310P devices. "
        "Please build with -DUSE_ACL_GRAPH=OFF or use a supported SOC.")
endif()

if (CANN_INSTALL_DIR)
    # Only Support Linux.
    if (NOT UNIX)
        message(FATAL_ERROR "CANN: CANN toolkit supports unix but not ${CMAKE_SYSTEM_NAME}")
    endif()

    # Supported platforms: x86-64, arm64
    if (CMAKE_SYSTEM_PROCESSOR STREQUAL "aarch64")
    elseif (CMAKE_SYSTEM_PROCESSOR STREQUAL "x86_64" OR CMAKE_SYSTEM_PROCESSOR STREQUAL "amd64")
    else()
        message(FATAL_ERROR "CANN: CANN toolkit supports x86-64 and arm64 but not ${CMAKE_SYSTEM_PROCESSOR}")
    endif()

    # Set header and libs
    set(CANN_INCLUDE_DIRS
        ${CANN_INSTALL_DIR}/include
        ${CANN_INSTALL_DIR}/include/aclnn
        ${CANN_INSTALL_DIR}/acllib/include
    )

    # Custom transformer ops (v310 GDN, conv1d, etc.)
    # Option 1: Set CANN_CUSTOM_OP_DIR to a pre-installed vendor directory
    # Option 2: Set CANN_BUILD_CUSTOM_OPS=ON to build from source in custom_ops/
    set(CANN_CUSTOM_OP_DIR "" CACHE PATH "Path to custom transformer ops (contains vendors/custom_transformer)")
    option(CANN_BUILD_CUSTOM_OPS "Build custom transformer ops from source" OFF)

    if(CANN_BUILD_CUSTOM_OPS)
        # Build custom ops from source using build_custom_ops.sh
        set(CUSTOM_OPS_SRC_DIR ${CMAKE_CURRENT_SOURCE_DIR}/custom_ops)
        set(CUSTOM_OPS_INSTALL_DIR ${CMAKE_BINARY_DIR}/custom_ops_install)
        set(CANN_CUSTOM_OP_DIR ${CUSTOM_OPS_INSTALL_DIR})

        if(EXISTS ${CUSTOM_OPS_SRC_DIR}/recurrent_gated_delta_rule_v310)
            message(STATUS "CANN: Building custom ops from source at ${CUSTOM_OPS_SRC_DIR}")
            find_program(BASH_EXEC bash REQUIRED)
            execute_process(
                COMMAND ${BASH_EXEC} ${CUSTOM_OPS_SRC_DIR}/build_custom_ops.sh
                        ${CUSTOM_OPS_SRC_DIR} ${CUSTOM_OPS_INSTALL_DIR} ${SOC_VERSION}
                RESULT_VARIABLE BUILD_RESULT
                OUTPUT_VARIABLE BUILD_OUTPUT
                ERROR_VARIABLE BUILD_OUTPUT
            )
            if(NOT BUILD_RESULT EQUAL 0)
                message(WARNING "CANN: Custom ops build failed (code ${BUILD_RESULT}). Falling back.")
                message("${BUILD_OUTPUT}")
            else()
                message(STATUS "CANN: Custom ops built and installed to ${CUSTOM_OPS_INSTALL_DIR}")
            endif()
        else()
            message(STATUS "CANN: No custom_ops source directory found, skipping build")
        endif()
    endif()

    if(NOT CANN_CUSTOM_OP_DIR)
        file(GLOB CANN_CUSTOM_OP_DIR_CANDIDATES
            ${CMAKE_BINARY_DIR}/custom_ops_install
            /vllm-workspace/vllm-ascend/vllm_ascend/_cann_ops_custom
            /usr/local/Ascend/opp/vendors/custom_transformer
        )
        foreach(dir ${CANN_CUSTOM_OP_DIR_CANDIDATES})
            if(EXISTS "${dir}/vendors/custom_transformer/op_api/include/aclnnop")
                set(CANN_CUSTOM_OP_DIR ${dir})
                message(STATUS "CANN: Found custom transformer ops at ${CANN_CUSTOM_OP_DIR}")
                break()
            endif()
        endforeach()
    endif()
    if(CANN_CUSTOM_OP_DIR AND EXISTS "${CANN_CUSTOM_OP_DIR}/vendors/custom_transformer/op_api/include/aclnnop")
        list(APPEND CANN_INCLUDE_DIRS
            ${CANN_CUSTOM_OP_DIR}/vendors/custom_transformer/op_api/include
        )
        set(CANN_CUSTOM_OP_LIB ${CANN_CUSTOM_OP_DIR}/vendors/custom_transformer/op_api/lib/libcust_opapi.so)
        message(STATUS "CANN: Custom op include: ${CANN_CUSTOM_OP_DIR}/vendors/custom_transformer/op_api/include")
        message(STATUS "CANN: Custom op lib: ${CANN_CUSTOM_OP_LIB}")
        # Set RPATH so the .so is found at runtime without LD_LIBRARY_PATH
        set(CANN_CUSTOM_OP_RPATH ${CANN_CUSTOM_OP_DIR}/vendors/custom_transformer/op_api/lib)
    else()
        message(WARNING "CANN: Custom transformer ops not found. GDN v310 ops will not be available.")
    endif()

    list(APPEND CANN_LIBRARIES
        ascendcl
        nnopbase
        opapi
        acl_op_compiler
    )

    file(GLOB GGML_SOURCES_CANN "*.cpp")

    ggml_add_backend_library(ggml-cann ${GGML_SOURCES_CANN})
    target_link_libraries(ggml-cann PRIVATE ${CANN_LIBRARIES})
    target_include_directories(ggml-cann PRIVATE ${CANN_INCLUDE_DIRS})
    target_link_directories(ggml-cann PRIVATE ${CANN_INSTALL_DIR}/lib64)
    if(CANN_CUSTOM_OP_LIB)
        target_link_libraries(ggml-cann PRIVATE ${CANN_CUSTOM_OP_LIB})
    endif()
    if(CANN_CUSTOM_OP_RPATH)
        set_target_properties(ggml-cann PROPERTIES BUILD_RPATH "${CANN_CUSTOM_OP_RPATH}")
    endif()

    target_compile_definitions(ggml-cann PRIVATE "-D${SOC_TYPE_COMPILE_OPTION}")

    if (USE_ACL_GRAPH)
        target_compile_definitions(ggml-cann PRIVATE USE_ACL_GRAPH)
        message(STATUS "CANN: USE_ACL_GRAPH is enabled.")
    else()
        message(STATUS "CANN: USE_ACL_GRAPH is disabled.")
    endif()

    message(STATUS "CANN: CANN_INCLUDE_DIRS =  ${CANN_INCLUDE_DIRS}")
    message(STATUS "CANN: CANN_LIBRARIES =  ${CANN_LIBRARIES}")
else()
    message(FATAL_ERROR "CANN: Can't find CANN_INSTALL_DIR, did you forget to source set_var.sh?")
endif()
