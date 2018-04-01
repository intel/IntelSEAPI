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

set(CMAKE_MACOSX_RPATH 1)
OPTION(JDK "Enable Java build")
OPTION(CO_PILOT "Enable co-pilot build")
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

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/../../bin)

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

if (EXISTS "${PROJECT_SOURCE_DIR}/RadTelemetry")
    MESSAGE("Found: Rad Telemetry")
    set (RAD_TELEMETRY_DIR ${PROJECT_SOURCE_DIR}/RadTelemetry)
endif()


if (WIN32)
    TARGET_LINK_LIBRARIES(IntelSEAPI)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} /Zi /MP")
    set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} /MP")

    #SDL:
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} /GS /sdl")
    set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} /GS /sdl")
    set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} /NXCompat /DynamicBase")
    set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} /NXCompat /DynamicBase")
    if(NOT ARCH_64)
        set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} /SafeSEH")
        set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} /SafeSEH")
    endif()

    set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} /DEBUG") #in release as well
    set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} /DEBUG") #in release as well
elseif (APPLE)
    TARGET_LINK_LIBRARIES(IntelSEAPI dl)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -stdlib=libc++ -std=c++11 -fPIC -Wno-unused-parameter -fstack-protector-strong -fPIE -O2 -D_FORTIFY_SOURCE=2 -Wformat -Wformat-security")
    set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} -fPIE -Wl")
    set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -fPIE -Wl")
    set(CMAKE_OSX_ARCHITECTURES "i386;x86_64")
elseif (ANDROID_NDK)
    TARGET_LINK_LIBRARIES(IntelSEAPI dl)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -std=c++11 -fPIE -pthread -fstack-protector-strong -fPIE -O2 -D_FORTIFY_SOURCE=2 -Wformat -Wformat-security")
    set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} -fPIE -pie -Wl,--no-undefined -z noexecstack -z relro -z now")
    set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -fPIE -pie -Wl,--no-undefined -z noexecstack -z relro -z now")
    if (ARM AND ARCH_64)
        add_definitions(-DITT_ARCH=ITT_ARCH_PPC64)
    endif()
else()
    TARGET_LINK_LIBRARIES(IntelSEAPI dl)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -std=c++11 -fPIC -pthread -fstack-protector-strong -fPIE -O2 -D_FORTIFY_SOURCE=2 -Wformat -Wformat-security")
    set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} -pie -Wl,--no-undefined -z noexecstack -z relro -z now")
    set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -fPIE -pie -Wl,--no-undefined -z noexecstack -z relro -z now")
endif()

add_subdirectory(ittnotify)
add_subdirectory(sea_itt_lib)
if (WIN32)
    if(NOT ARCH_64 AND CMAKE_BUILD_TYPE STREQUAL "Debug") #Compiler Automated Instrumentation
        set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} /Gh /GH")
    endif()
else()
    #SET_TARGET_PROPERTIES(IntelSEAPI PROPERTIES COMPILE_FLAGS "-finstrument-functions")
endif()

TARGET_LINK_LIBRARIES(IntelSEAPI ittnotify)

target_include_directories(IntelSEAPI
    PUBLIC ittnotify/include
)

# add a target to generate API documentation with Doxygen
find_package(Doxygen)
if(DOXYGEN_FOUND)
    configure_file(${CMAKE_CURRENT_SOURCE_DIR}/Doxyfile.in ${CMAKE_CURRENT_BINARY_DIR}/Doxyfile @ONLY)
    add_custom_target(doc ALL
        ${DOXYGEN_EXECUTABLE} ${CMAKE_CURRENT_BINARY_DIR}/Doxyfile
        WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
        COMMENT "Generating API documentation with Doxygen" VERBATIM
    )
endif(DOXYGEN_FOUND)

################################################### INSTALLER #########################################################

set(CPACK_PACKAGE_NAME "IntelSEAPI")
set(CPACK_PACKAGE_VENDOR "Intel")
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY "Intel(R) Single Event API")
set(CPACK_PACKAGE_VERSION "1.0.0")
set(CPACK_PACKAGE_INSTALL_DIRECTORY "IntelSEAPI")
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY "Intel(R) Single Event API")
set(CPACK_PACKAGE_DESCRIPTION_FILE "${PROJECT_SOURCE_DIR}/README.txt")
set(CPACK_RESOURCE_FILE_LICENSE "${PROJECT_SOURCE_DIR}/sea_itt_lib/Copyright.txt")
set(CPACK_RESOURCE_FILE_README "${PROJECT_SOURCE_DIR}/README.txt")
set(CPACK_RESOURCE_FILE_WELCOME "${PROJECT_SOURCE_DIR}/README.txt")

install(
    FILES
        ${PROJECT_SOURCE_DIR}/README.txt
    DESTINATION .
)

install(
    DIRECTORY "${PROJECT_SOURCE_DIR}/ittnotify/include"
    DESTINATION .
)

install(
    FILES
        "${PROJECT_SOURCE_DIR}/itt_notify.hpp"
    DESTINATION include
)

set(SEA_PROJECT_BIN ${PROJECT_SOURCE_DIR}/bin)

function(InstallWildCard what where)
    install(
        CODE "
            file(GLOB SEA_INSTALL_FILES ${what})
            file(INSTALL DESTINATION \"\${CMAKE_INSTALL_PREFIX}/${where}\" TYPE FILE FILES \${SEA_INSTALL_FILES})
            string(REGEX REPLACE \";\" \"\\n\\t\\t\" SEA_INSTALL_FILES_MSG \"\${SEA_INSTALL_FILES}\")
            message(\"\\n###\tInstall ${what} to ${where}:\\n\\t\\t\${SEA_INSTALL_FILES_MSG}\")
        "
    )
endfunction()

InstallWildCard("${PROJECT_SOURCE_DIR}/runtool/*.py" "runtool")
InstallWildCard("${PROJECT_SOURCE_DIR}/runtool/importers/*.py" "runtool/importers")
InstallWildCard("${PROJECT_SOURCE_DIR}/runtool/importers/pprof_importer/*.py" "runtool/importers/pprof_importer")
InstallWildCard("${PROJECT_SOURCE_DIR}/runtool/exporters/*.py" "runtool/exporters")
InstallWildCard("${PROJECT_SOURCE_DIR}/runtool/collectors/*.py" "runtool/collectors")
InstallWildCard("${PROJECT_SOURCE_DIR}/runtool/decoders/*.py" "runtool/decoders")

if (EXISTS "${PROJECT_SOURCE_DIR}/catapult.zip")
    install(
        FILES
            ${PROJECT_SOURCE_DIR}/catapult.zip
        DESTINATION bin
    )
endif()

if (WIN32)
    InstallWildCard("${SEA_PROJECT_BIN}/*ittnotify*.lib" "lib")
    InstallWildCard("${SEA_PROJECT_BIN}/*.dll" "bin")
    InstallWildCard("${SEA_PROJECT_BIN}/*.exe" "bin")
    InstallWildCard("${SEA_PROJECT_BIN}/*.pdb" "bin")

    install(
        FILES
            sea_itt_lib/IntelSEAPI.man
            sea_itt_lib/IntelSEAPI.wprp
            sea_itt_lib/IntelSEAPI_roi.xml
            sea_itt_lib/IntelSEAPI.wpaProfile
            sea_itt_lib/register.bat
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
        DIRECTORY "${SEA_PROJECT_BIN}"
        DESTINATION .
        PATTERN "*.a" EXCLUDE
    )

    InstallWildCard("${SEA_PROJECT_BIN}/*ittnotify*.a" "lib")

    if(APPLE)
        install(
            FILES
                "${PROJECT_SOURCE_DIR}/sea_itt_lib/IntelSEAPI.instrument"
            DESTINATION dtrace
        )
    endif()
endif()

include(CPack)
