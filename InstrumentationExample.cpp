/*********************************************************************************************************************************************************************************************************************************************************************************************
#   Intel� Single Event API
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
    #include <windows.h>
#else
    #include <sys/types.h>
    #include <unistd.h>
#endif

#define INTEL_ITTNOTIFY_ENABLE_LEGACY
#ifdef _WIN32
    #define message(ignore) //suffocates #pragma message("WARNING!!!... about using "INTEL_ITTNOTIFY_ENABLE_LEGACY"
#elif defined(__APPLE__)
    #pragma GCC diagnostic push
    #pragma GCC diagnostic ignored "-W#warnings"
#else
    #pragma GCC diagnostic push
    #pragma GCC diagnostic ignored "-Wcpp"
#endif

#include "itt_notify.hpp"

#ifdef _WIN32
    #undef message
#else
    #pragma GCC diagnostic pop
#endif


bool g_done = false;
// Forward declaration of a thread function.
// Create a g_domain that is visible globally: we will use it in our example.
__itt_domain* g_domain = __itt_domain_create("Example");

// Create string handles which associates with the "main" task.
__itt_string_handle* handle_exe_name = __itt_string_handle_create("ExeName");
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

ITT_DOMAIN("Example2");

void TaskStack(int level)
{
    ITT_FUNCTION_TASK();
    std::this_thread::sleep_for(std::chrono::milliseconds(rand() % 100));
    void* pMem = malloc(rand() % 100);
    if (level) TaskStack(level - 1);
    free(pMem);
    std::this_thread::sleep_for(std::chrono::milliseconds(rand() % 100));
}

void workerthread(int data)
{
    // Set the name of this thread so it shows  up in the UI as something meaningful
    char threadname[32] = {};
    sprintf_s(threadname, "Worker Thread %d", data);
    __itt_thread_set_name(threadname);
    __itt_task_begin_fn(g_domain, __itt_null, __itt_null, (void*)&workerthread);
    TaskStack(5);
    __itt_id id = __itt_id_make(threadname, data);
    __itt_id_create(g_domain, id);
    // Each worker thread does some number of "work" tasks
    uint64_t counter = 0;
    while (!g_done)
    {
        __itt_sync_acquired((void*)&workerthread);

        ITT_COUNTER("random", rand());
        bool bOverlapped = !(rand() % 2);
        unsigned long long start = TClock::now().time_since_epoch().count();
        __itt_task_begin(g_domain, id, __itt_null, handle_work);
        std::this_thread::sleep_for(std::chrono::milliseconds(rand() % 10));
        __itt_sync_releasing((void*)&workerthread);

        if (rand() % 5 == 1)
        {
            ITT_SCOPE_TRACK(nullptr, "USER_SCOPE");
            unsigned long long end = TClock::now().time_since_epoch().count();
            unsigned long long length = end - start;
            __itt_task_begin_ex(g_domain, clock_domain, start + length / 4, __itt_null, id, handle_gpu);
            __itt_relation_add_to_current(g_domain, __itt_relation_is_continuation_of, id);
            __itt_task_end_ex(g_domain, clock_domain, end - length / 4);
        }
        __itt_id id = __itt_null;
        if (bOverlapped)
        {
            id = __itt_id_make(&bOverlapped + counter++, 0);
            __itt_task_begin_overlapped(g_domain, id, __itt_null, handle_overlapped);
            __itt_metadata_str_add(g_domain, id, metadata_handle, "https://ru.wikipedia.org/wiki/PNG#/media/File:PNG_transparency_demonstration_1.png", 0);
        }
        __itt_task_end(g_domain);
        if (bOverlapped)
        {
            __itt_task_end_overlapped(g_domain, id);
        }
    }
    TaskStack(5);
    __itt_id_destroy(g_domain, id);
    __itt_task_end(g_domain);
}


int MeasurePerformance(int work_seconds)
{
    std::atomic<uint64_t> total_count;
    std::vector<std::thread*> threads;
    unsigned int thread_count = std::thread::hardware_concurrency();
    while (thread_count--)
    {
        threads.push_back(new std::thread([&total_count](){
            const uint64_t count = 1000000;
            for (;;)
            {
                for (uint64_t i = 0; i < count; ++i)
                {
                    __itt_id id = __itt_id_make(const_cast<uint64_t*>(&count), i);
                    __itt_task_begin(g_domain, id, __itt_null, handle_work);
                    double value = double(i);
                    __itt_metadata_add(g_domain, id, metadata_handle, __itt_metadata_double, 1, &value);
                    __itt_task_end(g_domain);
                }
                total_count += count;
            }
        }));
    }

    using namespace std::chrono;
    high_resolution_clock::time_point start = high_resolution_clock::now();
    high_resolution_clock::time_point global_start = start;
    uint64_t prev_count = 0;
    for (int sec = 0; sec < work_seconds; ++sec)
    {
        std::this_thread::sleep_for(seconds(1));
        high_resolution_clock::time_point end = high_resolution_clock::now();
        uint64_t count = total_count;
        std::cout << "Events per second:" << std::fixed << ((count - prev_count) * 1000000000. / duration_cast<nanoseconds>(end - start).count()) << std::endl;
        prev_count = count;
        start = end;
    }
    clock_domain = nullptr;
    uint64_t count = total_count;
    std::cout << "Total events per second:" << std::fixed << (count * 1000000000. / duration_cast<nanoseconds>(start - global_start).count()) << std::endl;

    return 0;
}

void Main(int work_seconds)
{
    clock_domain = __itt_clock_domain_create(get_clock_info, nullptr);

    __itt_timestamp begin_frame = __itt_get_timestamp();

    __itt_mark(0, "AAAh!!!");

    __itt_timestamp end_frame = __itt_get_timestamp();
    __itt_frame_submit_v3(g_domain, nullptr, begin_frame, end_frame);

    __itt_id id = __itt_id_make(g_domain, 0); //just any arbitrary id, g_domain here is just a pointer
    __itt_metadata_str_add(g_domain, id, nullptr, "Named before call", 0); //it's possible to assign name to id (if key==nullptr)
    __itt_frame_submit_v3(g_domain, &id, begin_frame, end_frame); //this name is later used as name of submitted frame

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

    std::vector<std::thread*> threads;

    {
        ITT_SCOPE_REGION("region1");
        // Now we'll create 3 worker threads
        for (int i = 0; i < 3; i++)
        {
            // We might be curious about the cost of CreateThread. We add tracing to do the measurement.
            ITT_SCOPE_TASK("CreateThread");
            threads.push_back(new std::thread(workerthread, i));
        }
    }

    TaskStack(5);

    // Wait a while,...
    std::this_thread::sleep_for(std::chrono::seconds(work_seconds));

    {
        ITT_SCOPE_REGION("region2");

        g_done = true;

        ITT_MARKER("MARKER", scope_thread);

        __itt_frame frame = __itt_frame_create("Frame");
        __itt_frame_begin(frame);
        for (std::thread* pThread: threads)
        {
            pThread->join();
        }
        __itt_frame_end(frame);

        TaskStack(5);

        __itt_frame_begin_v3(g_domain, nullptr);
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        __itt_frame_end_v3(g_domain, nullptr);

        __itt_sync_destroy((void*)&workerthread);
    }

#ifdef _WIN32
    QueryPerformanceCounter(&qpc);
    ITT_ARG("end", qpc.QuadPart);
#endif

    __itt_clock_domain_reset();
    clock_domain = nullptr;
}
