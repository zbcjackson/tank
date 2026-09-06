# Vendored libopus 1.4 (fixed-point) for ESP32-S3 — protocol plan P1-2 Step 5.
# Source: https://github.com/xiph/opus tag v1.4, trimmed to the fixed-point
# build (no x86/arm/mips asm, no float silk, no float analysis/mlp, no demos).
file(GLOB CELT_SRCS celt/*.c)
list(REMOVE_ITEM CELT_SRCS ${CMAKE_CURRENT_LIST_DIR}/celt/opus_custom_demo.c)
file(GLOB SILK_SRCS silk/*.c)
file(GLOB SILK_FIXED_SRCS silk/fixed/*.c)
file(GLOB SRC_SRCS src/*.c)

idf_component_register(
    SRCS ${CELT_SRCS} ${SILK_SRCS} ${SILK_FIXED_SRCS} ${SRC_SRCS}
    INCLUDE_DIRS include
    PRIV_INCLUDE_DIRS . celt silk silk/fixed src
)

target_compile_definitions(${COMPONENT_LIB} PRIVATE HAVE_CONFIG_H)
# Fixed-point build: float analysis/MLP sources are excluded; opus_encoder.c
# and the public float API entry points are gated on this.
target_compile_definitions(${COMPONENT_LIB} PUBLIC DISABLE_FLOAT_API)
# GCC 13 false positive on silk NSQ array reads (fixed upstream after 1.4).
target_compile_options(${COMPONENT_LIB} PRIVATE
    -Wno-unused-parameter -Wno-float-conversion
    -Wno-implicit-float-conversion -Wno-stringop-overread)
