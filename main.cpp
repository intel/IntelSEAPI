/*********************************************************************************************************************************************************************************************************************************************************************************************
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
**********************************************************************************************************************************************************************************************************************************************************************************************/
#include "itt_notify.hpp"

#include <thread>
#include <chrono>
#include <vector>
#include <deque>
#include <cstdlib>
#include <iostream>
#include <functional>
#include <condition_variable>
#include <stdlib.h>
#include <cstdint>
#include <cstdio>
#include <atomic>
#include <string>
#include <cmath>
#include <string.h>

#ifdef _WIN32
    #define setenv _putenv
    #include <windows.h>
    #undef API_VERSION
    #include <Dbghelp.h>
    #pragma comment(lib, "dbghelp")
#else
    #include <sys/types.h>
    #include <unistd.h>

    #define setenv putenv
    #define _strdup strdup
#endif

#if (INTPTR_MAX == INT32_MAX)
    #define BIT_SUFFIX "32"
#elif INTPTR_MAX == INT64_MAX
    #define BIT_SUFFIX "64"
#else
    #error "Environment not 32 or 64-bit!"
#endif

#define INTEL_LIBITTNOTIFY "INTEL_LIBITTNOTIFY" BIT_SUFFIX

#ifdef __APPLE__ //fat binary is produced, so no bitness is suffixed to dylib name
    #define LIB_ITT_NAME "./libIntelSEAPI"
#elif _WIN32
	#define LIB_ITT_NAME "./IntelSEAPI" BIT_SUFFIX
#else
    #define LIB_ITT_NAME "./libIntelSEAPI" BIT_SUFFIX
#endif

#ifdef _WIN32
    #define LIB_ITT LIB_ITT_NAME ".dll"
#elif defined(__APPLE__)
    #define LIB_ITT LIB_ITT_NAME ".dylib"
#else
    #define LIB_ITT LIB_ITT_NAME ".so"
#endif

static std::string get_environ_value(const std::string& name)
{
#ifdef _WIN32
    size_t sz = 0;
    char *v = NULL;
    _dupenv_s(&v, &sz, name.c_str());

    std::string ret = v ? v : "";
    free(v);

    return ret;
#else
    const char *v = std::getenv(name.c_str());
    return v ? v : "";
#endif
}

bool IsVerboseMode()
{
    static bool bVerboseMode = !!get_environ_value("INTEL_SEA_VERBOSE").size();
    return bVerboseMode;
}
#define VerbosePrint(...) {if (IsVerboseMode()) printf(__VA_ARGS__);}


int GlobalInit()
{
    std::string val = get_environ_value(INTEL_LIBITTNOTIFY);
    if (val.size() && get_environ_value("INTEL_FORCE_SEA").empty())
    {
        VerbosePrint("MAIN: %s was already set to %s\n", INTEL_LIBITTNOTIFY, val.c_str());
    }
    else
    {
#ifndef __ANDROID__
        setenv(_strdup(INTEL_LIBITTNOTIFY "=" LIB_ITT));
        VerbosePrint("MAIN: setting %s = %s\n", INTEL_LIBITTNOTIFY, LIB_ITT);
#endif
    }

#ifdef __ANDROID__
    if (get_environ_value("INTEL_SEA_SAVE_TO").empty())
        setenv(_strdup("INTEL_SEA_SAVE_TO=/data/local/tmp/ISEA"));
#elif defined(__linux__)
    if (get_environ_value("INTEL_SEA_SAVE_TO").empty())
        setenv(_strdup("INTEL_SEA_SAVE_TO=/tmp/ISEA"));
#endif
    return 1;
}

int nSetLib = GlobalInit();

#if defined(__ANDROID__)
#include <sstream>
namespace std { //android NDK is missing this functionality
    template <typename T>
    std::string to_string(T value)
    {
        std::ostringstream os;
        os << value;
        return os.str();
    }
}
#endif

extern bool g_done;


#ifdef _WIN32

std::string GetFunctionName(DWORD64 addr, const char* szModulePath)
{
    std::string res;
    HANDLE hCurProc = GetCurrentProcess();
    SymSetOptions(SymGetOptions()|SYMOPT_LOAD_LINES|SYMOPT_UNDNAME|SYMOPT_INCLUDE_32BIT_MODULES);
    SymInitialize(hCurProc, NULL, TRUE);
    uint64_t module = SymLoadModule64(hCurProc, NULL, szModulePath, NULL, 0, 0);
    if (!module) return res;
    IMAGEHLP_LINE64 line = {sizeof(IMAGEHLP_LINE64)};
    DWORD dwDisplacement = 0;
    SymGetLineFromAddr64(hCurProc, module + addr, &dwDisplacement, &line);
    if (line.FileName)
    {
        res += std::string(line.FileName) + "(" + std::to_string(line.LineNumber) + ")\n";
    }

    char buff[sizeof(SYMBOL_INFO) + 1024] = {};
    SYMBOL_INFO * symbol = (SYMBOL_INFO*)buff;
    symbol->MaxNameLen   = 255;
    symbol->SizeOfStruct = sizeof(SYMBOL_INFO);
    SymFromAddr(hCurProc, module + addr, nullptr, symbol);
    res += symbol->Name;
    return res;
}

BOOL CALLBACK EnumSymbolsCallback(_In_ PSYMBOL_INFO pSymInfo, _In_ ULONG SymbolSize, _In_opt_ PVOID UserContext)
{
    if (!pSymInfo) // || pSymInfo->Tag != 5/*SymTagFunction*/
        return TRUE;

    std::cout << (pSymInfo->Address - pSymInfo->ModBase) << "\t" << pSymInfo->Size << "\t" << pSymInfo->Name;
    IMAGEHLP_LINE64 line = { sizeof(IMAGEHLP_LINE64) };
    DWORD dwDisplacement = 0;
    SymGetLineFromAddr64(UserContext, pSymInfo->Address, &dwDisplacement, &line);
    if (line.FileName)
    {
        std::cout << "\t" << std::string(line.FileName) + "(" + std::to_string(line.LineNumber) + ")";
    }

    std::cout << std::endl;

    return TRUE;
}

bool DumpModule(const char* szModulePath)
{
    std::string res;
    HANDLE hCurProc = GetCurrentProcess();
    SymSetOptions(SymGetOptions() | SYMOPT_LOAD_LINES | SYMOPT_UNDNAME | SYMOPT_INCLUDE_32BIT_MODULES);
    SymInitialize(hCurProc, NULL, TRUE);
    uint64_t module = SymLoadModule64(hCurProc, NULL, szModulePath, NULL, 0, 0);
    if (!module) return false;
    return !!::SymEnumSymbols(hCurProc, module, NULL, EnumSymbolsCallback, hCurProc/*context*/);
}

int ResolveSymbol(char* request)
{
    char* addr_pos = strrchr(request, ':') + 1;
    DWORD64 addr = _atoi64(addr_pos);
    if (addr)
    {
        *(addr_pos - 1) = 0;
        std::string res = GetFunctionName(addr, request);
        std::cout << res << std::endl;
        return res.size() ? 0 : -1;
    }
    else
    {
        return DumpModule(request) ? 0 : -1;
    }
}

#endif

extern __itt_domain* g_domain;

void ChangePaths()
{
    std::string path = get_environ_value("INTEL_SEA_SAVE_TO");
    if (path.empty()) return;
    __itt_string_handle* handle = __itt_string_handle_create("__sea_set_folder");
    int counter = 0;
    while (!g_done)
    {
        std::this_thread::sleep_for(std::chrono::seconds(5));
        __itt_metadata_str_add(g_domain, __itt_null, handle, (!(counter % 2) ? "" : (path + std::to_string(counter)).c_str()), 0);
        ++counter;
    }
}

int MeasurePerformance(int work_seconds);
void Main(int work_seconds);


#ifdef _WIN32
int _tmain(int argc, _TCHAR* argv[])
#else
int main(int argc, char* argv[])
#endif
{
    int work_seconds = 3;
    if (argc > 1)
    {
#ifdef _WIN32
        if (strchr(argv[1], ':'))
            return ResolveSymbol(argv[1]);
#endif
        work_seconds = std::atoi(argv[1]);
    }
    std::string mode;
    if (argc > 2)
        mode = argv[2];

    const char* version2 = __itt_api_version();
    (void)version2;
    char path[] =
#ifdef _WIN32
                "c:/temp/trace.json";
#else
                "/tmp/trace.json";
#endif

    VerbosePrint("Mode: %s\n", mode.c_str());

    if (std::string::npos != mode.find("perf"))
        return MeasurePerformance(work_seconds);

    const char* api_ver = __itt_api_version();
    VerbosePrint("ITT Version: %s\n", api_ver ? api_ver : "Not loaded");

    //std::thread thrd(ChangePaths); //only for stress testing
    Main(work_seconds);
    //thrd.join();
    return 0;
}

