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

#include "ittnotify.h"
#if defined(_DEBUG) && !defined(__ANDROID__)

#ifdef UNICODE
    __itt_heap_function g_heap = __itt_heap_function_create(L"CRT", L"Memory");
#else
    __itt_heap_function g_heap = __itt_heap_function_create("CRT", "Memory");
#endif

#ifdef _WIN32
#if _MSC_VER == 1800 //VS2013
    #define _CRTBLD //hack, no words
        #include <../crt/src/dbgint.h> //for definition of _CrtMemBlockHeader
    #undef _CRTBLD
#elif _MSC_VER >= 1900 //VS2015
    struct _CrtMemBlockHeader //it's in debug_heap.cpp now
    {
        _CrtMemBlockHeader* _block_header_next;
        _CrtMemBlockHeader* _block_header_prev;
        char const*         _file_name;
        int                 _line_number;

        int                 _block_use;
        size_t              _data_size;

        long                lRequest;
    };
#endif
    #include <crtdbg.h>

    class CRecursionScope
    {
        bool& m_bRecursion;
    public:
        CRecursionScope(bool& bRecursion)
            : m_bRecursion(bRecursion)
        {
            m_bRecursion = true;
        }
        ~CRecursionScope()
        {
            m_bRecursion = false;
        }
    };

    int AllocHook(int allocType, void *userData, size_t size, int, long requestNumber, const unsigned char *, int)
    {
        static __declspec(thread) bool bRecursion = false;
        if (bRecursion) return 1;
        CRecursionScope scope(bRecursion);

        switch (allocType)
        {
            case _HOOK_ALLOC:
            {
                //In crt hooks we don't know address of the block on allocation, using request number as id
                void* fakePtr = (void*)(uintptr_t)requestNumber;
                __itt_heap_allocate_begin(g_heap, size, 0); //since we are called before real allocation we can't measure the time of it
                __itt_heap_allocate_end(g_heap, &fakePtr, size, 0);
                break;
            }
            case _HOOK_FREE:
            {
                //requestNumber is not passed here on _HOOK_FREE, using a bit of knowledge of the internals
                requestNumber = (((_CrtMemBlockHeader*)userData)-1)->lRequest;
                void* fakePtr = (void*)(uintptr_t)requestNumber;
                __itt_heap_free_begin(g_heap, fakePtr); //since we are called before real deallocation we can't measure the time of it
                __itt_heap_free_end(g_heap, fakePtr);
                break;
            }
        }
        return 1;
    }

    bool InitMemHooks()
    {
        _CrtSetAllocHook(AllocHook);
        return true;
    }

    bool bInit = InitMemHooks();


#else

    #include <pthread.h>
    #include <assert.h>
    #include <execinfo.h>
    #include <dlfcn.h>
    #include <string.h>

    pthread_key_t AllocTLSKey()
    {
        pthread_key_t key = -1;
        int res = pthread_key_create(&key, nullptr);
        assert(0 == res);
        return key;
    }
    pthread_key_t tls_key = AllocTLSKey();

    class CRecursionScope
    {
    public:
        CRecursionScope()
        {
            int res = pthread_setspecific(tls_key, &tls_key);
            assert(0 == res);
        }
        ~CRecursionScope()
        {
            int res = pthread_setspecific(tls_key, nullptr);
            assert(0 == res);
        }
    };

    bool HasSEAInStack()
    {
        const size_t stack_depth = 100;
        void *trace[stack_depth] = {};

    #ifdef __APPLE__
        const int frames_to_skip = 3;
    #else
        const int frames_to_skip = 7;
    #endif
        int trace_size = backtrace(trace, stack_depth);
        for (int i = frames_to_skip; i < trace_size; ++i)
        {
            Dl_info dl_info = {};
            dladdr(trace[i], &dl_info);
            if (dl_info.dli_fname && strstr(dl_info.dli_fname, "/IntelSEAPI."))
                return true;
        }
        return false;
    }

    #if defined(__APPLE__) && defined(_DEBUG)
        #include <malloc/malloc.h>
        #include <mach/mach.h>
        #include <sys/syscall.h>
        #include <unistd.h>

        void* (*g_origMalloc)(struct _malloc_zone_t *zone, size_t size) = nullptr;
        void* MallocHook(struct _malloc_zone_t *zone, size_t size)
        {
            if (pthread_getspecific(tls_key) || HasSEAInStack())
                return g_origMalloc(zone, size);
            CRecursionScope scope;

            __itt_heap_allocate_begin(g_heap, size, 0);
            void* res = g_origMalloc(zone, size);
            __itt_heap_allocate_end(g_heap, &res, size, 0);

            return res;
        }

        void (*g_origFree)(struct _malloc_zone_t *zone, void *ptr) = nullptr;
        void FreeHook(struct _malloc_zone_t *zone, void *ptr)
        {
            if (pthread_getspecific(tls_key) || HasSEAInStack())
                return g_origFree(zone, ptr);
            CRecursionScope scope;

            __itt_heap_free_begin(g_heap, ptr);
            g_origFree(zone, ptr);
            __itt_heap_free_end(g_heap, ptr);
        }

        void (*g_origFreeDefSize)(struct _malloc_zone_t *zone, void *ptr, size_t size);
        void FreeDefSizeHook(struct _malloc_zone_t *zone, void *ptr, size_t)
        {
            FreeHook(zone, ptr);
        }

        bool InitMemHooks()
        {
            malloc_zone_t* pMallocZone = malloc_default_zone();
            if (!pMallocZone) return false;

            vm_protect(mach_task_self(), (uintptr_t)pMallocZone, sizeof(malloc_zone_t), 0, VM_PROT_READ | VM_PROT_WRITE);//remove the write protection

            g_origMalloc = pMallocZone->malloc;
            pMallocZone->malloc = MallocHook;

            g_origFree = pMallocZone->free;
            pMallocZone->free = FreeHook;

            g_origFreeDefSize = pMallocZone->free_definite_size;
            pMallocZone->free_definite_size = FreeDefSizeHook;

            vm_protect(mach_task_self(), (uintptr_t)pMallocZone, sizeof(malloc_zone_t), 0, VM_PROT_READ);//put the write protection back

            return true;
        }

        bool bInit = InitMemHooks();

    #elif defined(__linux__) && defined(_DEBUG)

        #include <stdio.h>
        #include <dlfcn.h>
        #include <malloc.h>
        #ifdef __MALLOC_DEPRECATED

            void *malloc(size_t size)
            {
                static void* (*g_origMalloc)(size_t) = (void*(*)(size_t))dlsym(RTLD_NEXT, "malloc");
                if (pthread_getspecific(tls_key) || HasSEAInStack())
                    return g_origMalloc(size);
                CRecursionScope scope;

                __itt_heap_allocate_begin(g_heap, size, 0);
                void* res = g_origMalloc(size);
                __itt_heap_allocate_end(g_heap, &res, size, 0);

                return res;
            }

            void free(void *ptr)
            {
                static void (*g_origFree)(void *ptr) = (void (*)(void *))dlsym(RTLD_NEXT, "free");
                if (pthread_getspecific(tls_key) || HasSEAInStack())
                    return g_origFree(ptr);
                CRecursionScope scope;

                __itt_heap_free_begin(g_heap, ptr);
                g_origFree(ptr);
                __itt_heap_free_end(g_heap, ptr);
            }


        #else
            void (*g_origFree) (void *__ptr, const void *) = nullptr;
            void *(*g_origMalloc)(size_t __size, const void *) = nullptr;

            void InitHooks()
            {
                g_origMalloc = __malloc_hook;
                g_origFree = __free_hook;
                __malloc_hook = MallocHook;
                __free_hook = FreeHook;
            }
            void (* volatile __malloc_initialize_hook)() = InitHooks;

            void* MallocHook(size_t size, const void * context)
            {
                if (pthread_getspecific(tls_key) || HasSEAInStack())
                    return g_origMalloc(size, context);
                CRecursionScope scope;

                __itt_heap_allocate_begin(g_heap, size, 0);
                void* res = g_origMalloc(size, context);
                __itt_heap_allocate_end(g_heap, &res, size, 0);

                return res;
            }

            void FreeHook(void* ptr, const void* context)
            {
                if (pthread_getspecific(tls_key) || HasSEAInStack())
                    return g_origFree(ptr, context);
                CRecursionScope scope;

                __itt_heap_free_begin(g_heap, ptr);
                g_origFree(ptr, context);
                __itt_heap_free_end(g_heap, ptr);
            }
        #endif

     #endif
#endif

#endif// _DEBUG
