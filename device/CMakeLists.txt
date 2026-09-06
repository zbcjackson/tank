cmake_minimum_required(VERSION 3.16)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)

# Route LVGL's builtin allocator pool (64 KB) into PSRAM — the internal-RAM
# budget is fully allocated and this pool was its largest static consumer.
# Applied globally via force-include so the LVGL component's
# lv_mem_core_builtin.c sees the macro (see main/lv_mem_psram_pool.h).
add_compile_options("$<$<COMPILE_LANGUAGE:C,CXX>:-include${CMAKE_CURRENT_LIST_DIR}/main/lv_mem_psram_pool.h>")

project(tank-device)
