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
    #define LIB_ITT_NAME "./IntelSEAPI"
#else
    #define LIB_ITT_NAME "./IntelSEAPI" BIT_SUFFIX
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

// Forward declaration of a thread function.
bool g_done = false;
// Create a domain that is visible globally: we will use it in our example.
__itt_domain* domain = __itt_domain_create("Example");
ITT_DOMAIN("Example");
__itt_domain* domain2 = __itt_domain_create("Domain2");
// Create string handles which associates with the "main" task.

__itt_string_handle* handle_exe_name = __itt_string_handle_create("ExeName");
__itt_string_handle* handle_region1 = __itt_string_handle_create("region1");
__itt_id region1id = __itt_id_make(handle_region1, 2);
__itt_string_handle* handle_region2 = __itt_string_handle_create("region2");
__itt_id region2id = __itt_id_make(handle_region2, 3);
__itt_string_handle* handle_overlapped = __itt_string_handle_create("overlapped");
__itt_string_handle* metadata_handle = __itt_string_handle_create("image");


// Create string handle for the work task.
__itt_string_handle* handle_work = __itt_string_handle_create("work");
__itt_string_handle* handle_worker = __itt_string_handle_create("worker");
__itt_string_handle* handle_gpu = __itt_string_handle_create("gpu task");


typedef std::chrono::high_resolution_clock TClock;

void ITTAPI get_clock_info(__itt_clock_info* clock_info, void*)
{
    __itt_clock_info data = {
        (unsigned long long)(TClock::period::den / TClock::period::num),
        (unsigned long long)(TClock::now().time_since_epoch().count())
    };
    *clock_info = data;
}


__itt_clock_domain* clock_domain = nullptr;
__itt_string_handle* handle_stacked = __itt_string_handle_create("stacked");


#ifndef _WIN32
#define sprintf_s sprintf
#endif

#ifdef __linux__
thread_local bool g_bCAIRecursion = false;
extern "C" {
    void __cyg_profile_func_enter (void *, void *) __attribute__((no_instrument_function));
    void __cyg_profile_func_enter (void * fn, void *)
    {
        if (clock_domain && !g_bCAIRecursion)
        {
            g_bCAIRecursion = true;
            __itt_task_begin_fn(domain, __itt_null, __itt_null, fn);
            g_bCAIRecursion = false;
        }
    }
    void __cyg_profile_func_exit (void *, void *) __attribute__((no_instrument_function));
    void __cyg_profile_func_exit (void *, void *)
    {
        if (clock_domain && !g_bCAIRecursion)
        {
            g_bCAIRecursion = true;
            __itt_task_end(domain);
            g_bCAIRecursion = false;
        }
    }
}
#endif

#ifdef _WIN32

#if INTPTR_MAX == INT32_MAX
extern "C"
{
    void __declspec(naked) __cdecl _penter()
    {
        __asm pushad // Push all of the registers on to the stack
        if (clock_domain)
        {
            static void* instrumented_function = 0; //not thread safe at all!

            __asm
            {
                // Get the address of the return address which is 4 * 8 bytes into
                // the stack ("asm pushad" pushed 8 32-bit register values)
                mov  eax, esp
                add  eax, 32
                // Load the return address of the call to _penter
                mov  eax, dword ptr[eax]
                // Since _penter is always called 5 bytes after the function address, we can simply subtract
                // 1 (call inst) + 4 bytes (32-bit address) to set eax to the instrumented functionís address
                sub  eax, 5
                mov instrumented_function, eax
            }
            __itt_task_begin_fn(domain, __itt_null, __itt_null, (void*)instrumented_function);
        }
        __asm popad // Pop all of the registers off of the stack
        __asm ret
    }
    void __declspec(naked) __cdecl _pexit()
    {
        __asm pushad // Push all of the registers on to the stack
        if (clock_domain) __itt_task_end(domain);
        __asm popad // Pop all of the registers off of the stack
        __asm ret

    }
}
#endif

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

int ResolveSymbol(char* request)
{
    char* addr = strrchr(request, ':') + 1;
    *(addr - 1) = 0;
    std::string res = GetFunctionName(_atoi64(addr), request);
    std::cout << res;
    return res.size() ? 0 : -1;
}

#endif

void TaskStack(int level)
{
    ITT_FUNCTION_TASK();
    std::this_thread::sleep_for(std::chrono::milliseconds(rand() % 100));
    if (level) TaskStack(level - 1);
    std::this_thread::sleep_for(std::chrono::milliseconds(rand() % 100));
}

void workerthread(int data)
{
    // Set the name of this thread so it shows  up in the UI as something meaningful
    char threadname[32] = {};
    sprintf_s(threadname, "Worker Thread %d", data);
    __itt_thread_set_name(threadname);
    __itt_task_begin_fn(domain, __itt_null, __itt_null, (void*)&workerthread);
    TaskStack(5);
    __itt_id id = __itt_id_make(threadname, data);
    __itt_id_create(domain, id);
    // Each worker thread does some number of "work" tasks
    uint64_t counter = 0;
    while (!g_done)
    {
        __itt_sync_acquired((void*)&workerthread);

        ITT_COUNTER("random", rand());
        ITT_COUNTER("sinus", std::abs(10000. * sin(counter / 3.14)));
        bool bOverlapped = !(rand() % 2);
        unsigned long long start = TClock::now().time_since_epoch().count();
        __itt_task_begin(domain, id, __itt_null, handle_work);
        std::this_thread::sleep_for(std::chrono::milliseconds(rand() % 10));
        __itt_sync_releasing((void*)&workerthread);

        if (rand() % 5 == 1)
        {
            ITT_SCOPE_TRACK(nullptr, "GPU");
            unsigned long long end = TClock::now().time_since_epoch().count();
            unsigned long long length = end - start;
            __itt_task_begin_ex(domain, clock_domain, start + length / 4, __itt_null, id, handle_gpu);
            __itt_relation_add_to_current(domain, __itt_relation_is_continuation_of, id);
            __itt_task_end_ex(domain, clock_domain, end - length / 4);
        }
        __itt_id id = __itt_null;
        if (bOverlapped)
        {
            id = __itt_id_make(&bOverlapped + counter++, 0);
            __itt_task_begin_overlapped(domain, id, __itt_null, handle_overlapped);
            __itt_metadata_str_add(domain, id, metadata_handle, "file:///Users/aaraud/Downloads/SEA.png", 0);
        }
        __itt_task_end(domain);
        if (bOverlapped)
        {
            __itt_task_end_overlapped(domain, id);
        }
    }
    TaskStack(5);
    __itt_id_destroy(domain, id);
    __itt_task_end(domain);
}

void ChangePaths()
{
    std::string path = get_environ_value("INTEL_SEA_SAVE_TO");
    if (path.empty()) return;
    __itt_string_handle* handle = __itt_string_handle_create("__sea_set_folder");
    int counter = 0;
    while (!g_done)
    {
        std::this_thread::sleep_for(std::chrono::seconds(5));
        __itt_metadata_str_add(domain, __itt_null, handle, (!(counter % 2) ? "" : (path + std::to_string(counter)).c_str()), 0);
        ++counter;
    }
}

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
#ifdef INTELSEA_ITT_TASK_END_ENABLED
    if (INTELSEA_ITT_TASK_END_ENABLED())
        INTELSEA_ITT_TASK_END(domain->nameA);
#endif
    const char* version2 = __itt_api_version();
    (void)version2;
    char path[] =
#ifdef _WIN32
                "c:/temp/trace.json";
#else
                "/tmp/trace.json";
#endif
    clock_domain = __itt_clock_domain_create(get_clock_info, nullptr);

    __itt_timestamp begin_frame = __itt_get_timestamp();
    VerbosePrint("Mode: %s\n", mode.c_str());

    if (std::string::npos != mode.find("perf"))
    {
        std::atomic<uint64_t> total_count;
        std::vector<std::thread*> threads;
        unsigned int thread_count = std::thread::hardware_concurrency();
        while(thread_count--)
        {
            threads.push_back(new std::thread(
                [&total_count](){
                    const uint64_t count = 1000000;
                    for(;;)
                    {
                        for (uint64_t i = 0; i < count; ++i)
                        {
                            __itt_id id = __itt_id_make(const_cast<uint64_t*>(&count), i);
                            __itt_task_begin(domain, id, __itt_null, handle_work);
                            double value = double(i);
                            __itt_metadata_add(domain, id, metadata_handle, __itt_metadata_double, 1, &value);
                            __itt_task_end(domain);
                        }
                        total_count += count;
                    }
                }
            ));
        }

        using namespace std::chrono;
        high_resolution_clock::time_point start = high_resolution_clock::now();
        uint64_t prev_count = 0;
        for(int sec = 0; sec < work_seconds; ++sec)
        {
            std::this_thread::sleep_for(seconds(1));
            high_resolution_clock::time_point end = high_resolution_clock::now();
            uint64_t count = total_count;
            std::cout << "Events per second:" << std::fixed << ((count - prev_count) * 1000000000. / duration_cast<nanoseconds>(end-start).count()) << std::endl;
            prev_count = count;
            start = end;
        }
        clock_domain = nullptr;

        return 0;
    }
    const char* api_ver = __itt_api_version();
    VerbosePrint("ITT Version: %s\n", api_ver ? api_ver : "Not loaded");

    __itt_mark(0, "AAA!!!");

    __itt_timestamp end_frame = __itt_get_timestamp();
    __itt_frame_submit_v3(domain, nullptr, begin_frame, end_frame);

    __itt_id id = __itt_id_make(domain, 0); //just any arbitrary id, domain here is just a pointer
    __itt_metadata_str_add(domain, id, nullptr, "Named before call", 0); //it's possible to assign name to id (if key==nullptr)
    __itt_frame_submit_v3(domain, &id, begin_frame, end_frame); //this name is later used as name of submitted frame

    __itt_region_begin(domain, region1id, __itt_null, handle_region1);
#ifdef _WIN32
    __itt_sync_createW((void*)&workerthread, L"SyncObj", L"sync_obj_instance", __itt_attr_mutex);
#else
    __itt_sync_create((void*)&workerthread, "SyncObj", "sync_obj_instance", __itt_attr_mutex);
#endif
    __itt_sync_rename((void*)&workerthread, "NewName");

    ITT_MARKER("MARKER", scope_global);

    std::this_thread::sleep_for(std::chrono::milliseconds(500));
    // Create a task associated with the "main" routine.

    ITT_SCOPE_TASK("main");

#ifdef _WIN32
    static long long frequency = 0;
    if (!frequency)
        QueryPerformanceFrequency((LARGE_INTEGER*)&frequency);
    ITT_ARG("freq", frequency);

    LARGE_INTEGER qpc = {};
    QueryPerformanceCounter(&qpc);
    ITT_ARG("begin", qpc.QuadPart);
#endif
    // Save the name of the app's exe that we can show when analyzing traces.
    __itt_metadata_str_add(domain, __itt_null, handle_exe_name, argv[0], 0);
    // Now we'll create 3 worker threads
    std::vector<std::thread*> threads;
    for (int i = 0; i < 3; i++)
    {
        // We might be curious about the cost of CreateThread. We add tracing to do the measurement.
        ITT_SCOPE_TASK("CreateThread");
        threads.push_back(new std::thread(workerthread, i));
    }

    threads.push_back(new std::thread(ChangePaths));

    __itt_region_end(domain, region1id);

    TaskStack(5);

    // Wait a while,...
    std::this_thread::sleep_for(std::chrono::seconds(work_seconds));
    __itt_region_begin(domain, region2id, __itt_null, handle_region2);

    g_done = true;
#ifdef _WIN32
    QueryPerformanceCounter(&qpc);
    ITT_ARG("end", qpc.QuadPart);
#endif

    ITT_MARKER("MARKER", scope_thread);

    __itt_frame frame = __itt_frame_create("Frame");
    __itt_frame_begin(frame);

    for (std::thread* pThread: threads)
    {
        pThread->join();
    }
    __itt_frame_end(frame);

    TaskStack(5);

    __itt_frame_begin_v3(domain, nullptr);
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    __itt_frame_end_v3(domain, nullptr);

    __itt_sync_destroy((void*)&workerthread);
    __itt_region_end(domain, region2id);

    __itt_clock_domain_reset();
    clock_domain = nullptr;
    return 0;
}

