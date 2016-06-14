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
#include "itt_notify.hpp"

extern __itt_domain* g_domain;
extern __itt_clock_domain* clock_domain;

#if defined(__linux__) && !defined(__ANDROID__)
thread_local bool g_bCAIRecursion = false;
extern "C" {
    void __cyg_profile_func_enter (void *, void *) __attribute__((no_instrument_function));
    void __cyg_profile_func_enter (void * fn, void *)
    {
        if (clock_domain && !g_bCAIRecursion)
        {
            g_bCAIRecursion = true;
            __itt_task_begin_fn(g_domain, __itt_null, __itt_null, fn);
            g_bCAIRecursion = false;
        }
    }
    void __cyg_profile_func_exit (void *, void *) __attribute__((no_instrument_function));
    void __cyg_profile_func_exit (void *, void *)
    {
        if (clock_domain && !g_bCAIRecursion)
        {
            g_bCAIRecursion = true;
            __itt_task_end(g_domain);
            g_bCAIRecursion = false;
        }
    }
}

#elif defined(_WIN32)

#if INTPTR_MAX == INT32_MAX //64 bits compiler doesn't support asm inlines
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
                // 1 (call inst) + 4 bytes (32-bit address) to set eax to the instrumented functions address
                sub  eax, 5
                mov instrumented_function, eax
            }
            __itt_task_begin_fn(g_domain, __itt_null, __itt_null, (void*)instrumented_function);
        }
        __asm popad // Pop all of the registers off of the stack
        __asm ret
    }
    void __declspec(naked) __cdecl _pexit()
    {
        __asm pushad // Push all of the registers on to the stack
        if (clock_domain) __itt_task_end(g_domain);
        __asm popad // Pop all of the registers off of the stack
        __asm ret

    }
}
#endif
#endif
