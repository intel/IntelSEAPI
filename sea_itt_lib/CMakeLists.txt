#   Intel® Single Event API
#
#   This file is provided under the BSD 3-Clause license.
#   Copyright (c) 2015, Intel Corporation
#   All rights reserved.
#
#   Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
#       Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
#       Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
#       Neither the name of the Intel Corporation nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.
#
#   THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
#   IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
#   HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
#********************************************************************************************************************************************************************************************************************************************************************************************

cmake_minimum_required(VERSION 2.8)

SET(CUR_DIR "${PROJECT_SOURCE_DIR}/sea_itt_lib")

set(INCLUDE_DIRS . ..)


if (WIN32)

    add_custom_command(OUTPUT "${PROJECT_BINARY_DIR}/IntelSEAPI.rc" "${PROJECT_BINARY_DIR}/IntelSEAPI.h"
        PRE_BUILD
        COMMAND mc -um ${CUR_DIR}/IntelSEAPI.man -h ${PROJECT_BINARY_DIR} -r ${PROJECT_BINARY_DIR}
        DEPENDS ${CUR_DIR}/IntelSEAPI.man
        MAIN_DEPENDENCY IttNotifyStdSrc.h
        COMMENT "Generating ${PROJECT_BINARY_DIR}/IntelSEAPI.rc ${PROJECT_BINARY_DIR}/IntelSEAPI.h"
    )

    add_custom_command(OUTPUT "${PROJECT_BINARY_DIR}/IntelSEAPI_km.h"
        PRE_BUILD
        COMMAND mc -km ${CUR_DIR}/IntelSEAPI.man -h ${PROJECT_BINARY_DIR} -r ${PROJECT_BINARY_DIR} -z IntelSEAPI_km
        DEPENDS ${CUR_DIR}/IntelSEAPI.man
        MAIN_DEPENDENCY IttNotifyStdSrc.h
        COMMENT "Generating ${PROJECT_BINARY_DIR}/IntelSEAPI_km.h"
    )

    set(EXTRA_SOURCE
        ETWHandler.cpp
        ETLRelogger.cpp
        ${PROJECT_BINARY_DIR}/IntelSEAPI.rc
        ${PROJECT_BINARY_DIR}/IntelSEAPI.h
        ${PROJECT_BINARY_DIR}/IntelSEAPI_km.h
        IntelSEAPI.man
        IntelSEAPI.wprp
        IntelSEAPI_roi.xml
        IntelSEAPI.wpaProfile
        register.bat
    )
    
elseif(APPLE)
    set(INCLUDE_DIRS ${INCLUDE_DIRS} /usr/local/include)
    link_directories(/usr/local/lib)

    set(EXTRA_SOURCE
        DTraceHandler.cpp
        IntelSEAPI.instrument
        sea_itt_lib.mm
    )
    if (CO_PILOT)
        set(EXTRA_SOURCE mmv_stats.cpp)
        set(LINK_LIBS ${LINK_LIBS} pcp_mmv pcp)
    endif()
elseif(ANDROID)
    set(EXTRA_SOURCE
        SystraceHandler.cpp
    )
else()
    if (CO_PILOT)
        set(EXTRA_SOURCE mmv_stats.cpp)
        set(LINK_LIBS ${LINK_LIBS} pcp_mmv pcp)
    endif()
endif()


if(RAD_TELEMETRY_DIR)
    set(INCLUDE_DIRS ${INCLUDE_DIRS} ${RAD_TELEMETRY_DIR}/include)
    if(APPLE)
        set(LINK_LIBS ${LINK_LIBS} ${RAD_TELEMETRY_DIR}/lib/librad_tm_mac_x64_link.a)
        set(LINK_LIBS ${LINK_LIBS} ${RAD_TELEMETRY_DIR}/lib/librad_tm_mac_x86_link.a)
        set(EXTRA_SOURCE ${EXTRA_SOURCE} RadTelemetry.cpp)
    elseif (WIN32)
        set(RAD_LIB_NAME "rad_tm_win")
        if (ARCH_64)
            set(RAD_LIB_NAME "${RAD_LIB_NAME}64")
        else()
            set(RAD_LIB_NAME "${RAD_LIB_NAME}32")
        endif()
        if (CMAKE_BUILD_TYPE STREQUAL "Debug")
            set(RAD_LIB_NAME "${RAD_LIB_NAME}_d")
        endif()
        set(LINK_LIBS ${LINK_LIBS} ${RAD_TELEMETRY_DIR}/lib/${RAD_LIB_NAME}.lib)
        set(EXTRA_SOURCE ${EXTRA_SOURCE} RadTelemetry.cpp)
    endif()
endif()

if(JDK)
    if (${CMAKE_HOST_SYSTEM_NAME} MATCHES "Linux")
        set(JDK_PREFIX)
    elseif (${CMAKE_HOST_SYSTEM_NAME} MATCHES "Darwin")
        if(EXISTS ${JDK}/bin/javac)
            set(JDK_PREFIX ${JDK}/bin/)
        elseif(EXISTS ${JDK}/Commands/javac)
            set(JDK_PREFIX ${JDK}/Commands/)
        else()
            set(JDK_PREFIX)
        endif()
    else()
        set(JDK_PREFIX ${JDK}/bin/)
    endif()

    add_custom_command(
        OUTPUT ${PROJECT_SOURCE_DIR}/java/com/intel/sea/IntelSEAPI.class PRE_BUILD
        COMMAND ${JDK_PREFIX}javac -verbose ${PROJECT_SOURCE_DIR}/java/IntelSEAPI.java -d ${PROJECT_SOURCE_DIR}/java
        DEPENDS ${PROJECT_SOURCE_DIR}/java/IntelSEAPI.java
    )
    add_custom_command(
        OUTPUT ${PROJECT_SOURCE_DIR}/java/com_intel_sea_IntelSEAPI.h PRE_BUILD
        COMMAND ${JDK_PREFIX}javah -v -classpath ${PROJECT_SOURCE_DIR}/java -d ${PROJECT_SOURCE_DIR}/java com.intel.sea.IntelSEAPI
        DEPENDS ${PROJECT_SOURCE_DIR}/java/com/intel/sea/IntelSEAPI.class
    )

    set(EXTRA_SOURCE ${EXTRA_SOURCE}
        ${PROJECT_SOURCE_DIR}/java/com_intel_sea_IntelSEAPI.h
        ${PROJECT_SOURCE_DIR}/java/com_intel_sea_IntelSEAPI.cpp
        ${PROJECT_SOURCE_DIR}/java/IntelSEAPI.java
    )

    if (WIN32)
        set(INCLUDE_DIRS ${INCLUDE_DIRS} ${JDK}/include ${JDK}/include/win32)
    elseif(APPLE)
        set(INCLUDE_DIRS ${INCLUDE_DIRS} ${JDK}/include ${JDK}/include/darwin ${JDK}/Headers)
    elseif(NOT ANDROID)
        set(INCLUDE_DIRS ${INCLUDE_DIRS} ${JDK} ${JDK}/include ${JDK}/include/linux)
    endif()

endif()

add_library(sea_itt_lib SHARED
    sea_itt_lib.cpp
    IttNotifyStdSrc.cpp
    IttNotifyStdSrc.h
    Recorder.cpp
    Recorder.h
    TraceEventFormat.h
    Utils.cpp
    Utils.h
    Copyright.txt
    ${EXTRA_SOURCE}
)

SET_TARGET_PROPERTIES(sea_itt_lib PROPERTIES PREFIX "")
if(APPLE)
    SET_TARGET_PROPERTIES(sea_itt_lib PROPERTIES OUTPUT_NAME libIntelSEAPI)
elseif (WIN32)
    if(ARCH_64)
        SET_TARGET_PROPERTIES(sea_itt_lib PROPERTIES OUTPUT_NAME IntelSEAPI64)
    else()
        SET_TARGET_PROPERTIES(sea_itt_lib PROPERTIES OUTPUT_NAME IntelSEAPI32)
    endif()
else()
    if(ARCH_64)
        SET_TARGET_PROPERTIES(sea_itt_lib PROPERTIES OUTPUT_NAME libIntelSEAPI64)
    else()
        SET_TARGET_PROPERTIES(sea_itt_lib PROPERTIES OUTPUT_NAME libIntelSEAPI32)
    endif()
endif()

if (ARCH_64)
    set(METRICSFRAMEWORK_LIBRARY "x64")
else()
    set(METRICSFRAMEWORK_LIBRARY "x86")
endif()

if (WIN32)
    TARGET_LINK_LIBRARIES(sea_itt_lib
        ws2_32.lib Shlwapi.lib Dbghelp.lib
    )
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} /Zi") #in release as well
    set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} /DEBUG") #in release as well
elseif (APPLE)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -stdlib=libc++ -std=c++11 -g -fPIC -framework Cocoa")
elseif (ANDROID)
    TARGET_LINK_LIBRARIES(sea_itt_lib log)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -std=c++11 -g -fPIC -pthread")
else()
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -std=c++11 -g -fPIC -pthread")
    TARGET_LINK_LIBRARIES(sea_itt_lib dl)
endif()

target_include_directories(sea_itt_lib PUBLIC
    ${INCLUDE_DIRS}
    ../ittnotify ../ittnotify/include
    ${PROJECT_BINARY_DIR}
)

TARGET_LINK_LIBRARIES(sea_itt_lib ittnotify ${LINK_LIBS})

