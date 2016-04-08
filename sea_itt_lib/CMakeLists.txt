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

if (WIN32)

    add_custom_command(OUTPUT "${PROJECT_BINARY_DIR}/IntelSEAPI.rc" "${PROJECT_BINARY_DIR}/IntelSEAPI.h"
        PRE_BUILD
        COMMAND mc -um ${CUR_DIR}/IntelSEAPI.man -h ${PROJECT_BINARY_DIR} -r ${PROJECT_BINARY_DIR}
        DEPENDS ${CUR_DIR}/IntelSEAPI.man
        COMMENT "Generating ${PROJECT_BINARY_DIR}/IntelSEAPI.rc ${PROJECT_BINARY_DIR}/IntelSEAPI.h"
    )

    add_custom_command(OUTPUT "${PROJECT_BINARY_DIR}/IntelSEAPI_km.h"
        PRE_BUILD
        COMMAND mc -km ${CUR_DIR}/IntelSEAPI.man -h ${PROJECT_BINARY_DIR} -r ${PROJECT_BINARY_DIR} -z IntelSEAPI_km
        DEPENDS ${CUR_DIR}/IntelSEAPI.man
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
    set(EXTRA_SOURCE
        DTraceHandler.cpp
        IntelSEAPI.instrument
        sea_itt_lib.mm
    )
elseif(ANDROID)
    set(EXTRA_SOURCE
        SystraceHandler.cpp
    )
else()
    set(EXTRA_SOURCE)
endif()

set(INCLUDE_DIRS . ..)


if(JDK)
    if (WIN32)
        set(JDK_PREFIX ${JDK}/bin/)
    else()
        set(JDK_PREFIX)
    endif()

    if(NOT ANDROID)
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
    endif()

    set(EXTRA_SOURCE ${EXTRA_SOURCE}
        ${PROJECT_SOURCE_DIR}/java/com_intel_sea_IntelSEAPI.h
        ${PROJECT_SOURCE_DIR}/java/com_intel_sea_IntelSEAPI.cpp
        ${PROJECT_SOURCE_DIR}/java/IntelSEAPI.java
    )

    if(NOT ANDROID)
        if (WIN32)
            set(INCLUDE_DIRS ${INCLUDE_DIRS} ${JDK}/include ${JDK}/include/win32)
        else()
            set(INCLUDE_DIRS ${INCLUDE_DIRS} ${JDK})
        endif()
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
    SET_TARGET_PROPERTIES(sea_itt_lib PROPERTIES OUTPUT_NAME IntelSEAPI)
else()
    if(ARCH_64)
        SET_TARGET_PROPERTIES(sea_itt_lib PROPERTIES OUTPUT_NAME IntelSEAPI64)
    else()
        SET_TARGET_PROPERTIES(sea_itt_lib PROPERTIES OUTPUT_NAME IntelSEAPI32)
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
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -std=c++11 -g -fPIC -pthread")
else()
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -std=c++11 -g -fPIC -pthread")
endif()

target_include_directories(sea_itt_lib PUBLIC
    ${INCLUDE_DIRS}
    ../ittnotify ../ittnotify/include
    ${PROJECT_BINARY_DIR}
)

TARGET_LINK_LIBRARIES(sea_itt_lib ittnotify)

################################################### INSTALLER #########################################################

set(CPACK_PACKAGE_NAME "IntelSEAPI")
set(CPACK_PACKAGE_VENDOR "Intel")
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY "Intel(R) Single Event API")
set(CPACK_PACKAGE_VERSION "1.0.0")
set(CPACK_PACKAGE_INSTALL_DIRECTORY "IntelSEAPI")
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY "Intel(R) Single Event API")
set(CPACK_PACKAGE_DESCRIPTION_FILE "${PROJECT_SOURCE_DIR}/README.txt")
set(CPACK_RESOURCE_FILE_LICENSE "${CUR_DIR}/Copyright.txt")
set(CPACK_RESOURCE_FILE_README "${PROJECT_SOURCE_DIR}/README.txt")
set(CPACK_RESOURCE_FILE_WELCOME "${PROJECT_SOURCE_DIR}/README.txt")

install(
    FILES
        ${PROJECT_SOURCE_DIR}/README.txt
    DESTINATION .
)

if (INSTALL_SOURCES)
    install(
        DIRECTORY "${PROJECT_SOURCE_DIR}"
        DESTINATION source
        COMPONENT source
        PATTERN "*build*" EXCLUDE
    )
endif()

set (INSTALL_BIN "${PROJECT_SOURCE_DIR}/runtool/sea_runtool.py")
install(
    FILES
        ${INSTALL_BIN}
    DESTINATION bin
)

install(
    DIRECTORY "${PROJECT_SOURCE_DIR}/runtool/importers"
    DESTINATION bin
    PATTERN "*.pyc" EXCLUDE
)

install(
    DIRECTORY "${PROJECT_SOURCE_DIR}/runtool/exporters"
    DESTINATION bin
    PATTERN "*.pyc" EXCLUDE
)

install(
    DIRECTORY "${PROJECT_SOURCE_DIR}/runtool/collectors"
    DESTINATION bin
    PATTERN "*.pyc" EXCLUDE
)


if (WIN32)

    install(
        DIRECTORY "${PROJECT_BINARY_DIR}/../bin"
        DESTINATION .
        PATTERN "*.exp" EXCLUDE
        PATTERN "*.ilk" EXCLUDE
        PATTERN "*IntelSEAPI*.lib" EXCLUDE
    )

    install(
        FILES
            IntelSEAPI.man
            IntelSEAPI.wprp
            IntelSEAPI_roi.xml
            IntelSEAPI.wpaProfile
            register.bat
        DESTINATION ETW
    )

    set(CPACK_GENERATOR NSIS)

    #run at exit:
    set(CPACK_NSIS_EXECUTABLES_DIRECTORY "ETW")
    set(CPACK_NSIS_MUI_FINISHPAGE_RUN "register.bat")
    set(CPACK_NSIS_DISPLAY_NAME "Intel(R) Single Event API")

    set(CPACK_NSIS_CONTACT "alexander.a.raud@intel.com")

    SET(CPACK_NSIS_INSTALL_ROOT "c:\\\\Intel")

else()

    set(CPACK_BUNDLE_NAME "IntelSEAPI")
    set(CPACK_GENERATOR STGZ)
    install(
        DIRECTORY "${PROJECT_BINARY_DIR}/../bin"
        DESTINATION .
    )

    if(APPLE)
        install(
            FILES
                IntelSEAPI.instrument
            DESTINATION dtrace
        )
    endif()
endif()

include(CPack)
