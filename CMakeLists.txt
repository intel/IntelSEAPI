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

project(IntelSEAPI)

OPTION(JDK "Enable Java build")
OPTION(FORCE_32 "Force a 32bit compile on 64bit" OFF)

if (ANDROID_ARCH_NAME MATCHES "arm\\.*")
    set(ARM 1)
endif()

IF(FORCE_32 AND UNIX AND NOT ARM)
    SET(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -m32")
    SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -m32")
ENDIF()

if(CMAKE_SIZEOF_VOID_P MATCHES "8" AND NOT(FORCE_32))
    set(ARCH_64 1)
endif()

if(CMAKE_BUILD_TYPE STREQUAL "Debug")
    add_definitions(-D_DEBUG)
    if (NOT WIN32)
        set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -g")
        set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -g")
    endif()
else()
    if (NOT WIN32)
        set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -O2")
        set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -O2")
    endif()
    add_definitions(-DNDEBUG)
endif()

# Replace /MD with /MT. IntelSEAPI must have own/static CRT
set (Flags
    CMAKE_CXX_FLAGS
    CMAKE_CXX_FLAGS_DEBUG
    CMAKE_CXX_FLAGS_RELEASE
    CMAKE_C_FLAGS
    CMAKE_C_FLAGS_DEBUG
    CMAKE_C_FLAGS_RELEASE
    )
foreach (Flag ${Flags})
    string(REPLACE "/MD" "/MT" ${Flag} "${${Flag}}")
    message(STATUS "${Flag} = ${${Flag}}")
endforeach()

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/../bin)

set(EXECUTABLE_OUTPUT_PATH ${CMAKE_RUNTIME_OUTPUT_DIRECTORY})
set(LIBRARY_OUTPUT_PATH ${CMAKE_RUNTIME_OUTPUT_DIRECTORY})
set(ARCHIVE_OUTPUT_PATH ${CMAKE_RUNTIME_OUTPUT_DIRECTORY})

foreach( OUTPUTCONFIG ${CMAKE_CONFIGURATION_TYPES} )
    string( TOUPPER ${OUTPUTCONFIG} OUTPUTCONFIG )
    set( CMAKE_RUNTIME_OUTPUT_DIRECTORY_${OUTPUTCONFIG}     ${CMAKE_RUNTIME_OUTPUT_DIRECTORY} )
    set( CMAKE_LIBRARY_OUTPUT_DIRECTORY_${OUTPUTCONFIG}     ${CMAKE_RUNTIME_OUTPUT_DIRECTORY} )
    set( CMAKE_EXECUTABLE_OUTPUT_DIRECTORY_${OUTPUTCONFIG}  ${CMAKE_RUNTIME_OUTPUT_DIRECTORY} )
    set( CMAKE_ARCHIVE_OUTPUT_DIRECTORY_${OUTPUTCONFIG}     ${CMAKE_RUNTIME_OUTPUT_DIRECTORY} )
endforeach( OUTPUTCONFIG CMAKE_CONFIGURATION_TYPES )

add_executable(IntelSEAPI
    main.cpp
    memory.cpp
    InstrumentationExample.cpp
    CompilerAutomatedInstrumentation.cpp
    itt_notify.hpp
    buildall.py
    runtool/sea.py
    runtool/sea_runtool.py
    README.txt
)

if(APPLE)
    SET_TARGET_PROPERTIES(IntelSEAPI PROPERTIES OUTPUT_NAME TestIntelSEAPI)
else()
    if(ARCH_64)
        SET_TARGET_PROPERTIES(IntelSEAPI PROPERTIES OUTPUT_NAME TestIntelSEAPI64)
    else()
        SET_TARGET_PROPERTIES(IntelSEAPI PROPERTIES OUTPUT_NAME TestIntelSEAPI32)
    endif()
endif()

add_subdirectory(sea_itt_lib)
add_subdirectory(ittnotify)

TARGET_LINK_LIBRARIES(IntelSEAPI ittnotify)

target_include_directories(IntelSEAPI
    PUBLIC ittnotify/include
)

if (WIN32)
    TARGET_LINK_LIBRARIES(IntelSEAPI)
    if(NOT ARCH_64 AND CMAKE_BUILD_TYPE STREQUAL "Debug") #Compiler Automated Instrumentation
        set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} /Gh /GH")
    endif()
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} /Zi") #in release as well
    set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} /DEBUG") #in release as well
    set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} /DEBUG") #in release as well
elseif (APPLE)
    TARGET_LINK_LIBRARIES(IntelSEAPI dl)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -stdlib=libc++ -std=c++11 -fPIC -Wno-unused-parameter")
    set(CMAKE_OSX_ARCHITECTURES "i386;x86_64")
elseif (ANDROID_NDK)
    TARGET_LINK_LIBRARIES(IntelSEAPI dl)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -std=c++11 -fPIE -pthread")
    set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} -fPIE -pie -Wl,--no-undefined")
    set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -fPIE -pie")
else()
    TARGET_LINK_LIBRARIES(IntelSEAPI dl)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -std=c++11 -fPIC -pthread")
    set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} -pie -Wl,--no-undefined")
    #SET_TARGET_PROPERTIES(IntelSEAPI PROPERTIES COMPILE_FLAGS "-finstrument-functions")
endif()

