/*********************************************************************************************************************************************************************************************************************************************************************************************
#   Intel(R) Single Event API
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

#include "Utils.h"

#ifdef __ANDROID__

#include <unwind.h>

struct BacktraceState
{
    void** current;
    void** end;
};

_Unwind_Reason_Code Unwind(struct _Unwind_Context* ctx, void* arg)
{
    BacktraceState* state = static_cast<BacktraceState*>(arg);
    uintptr_t frame = _Unwind_GetIP(ctx);
    if (frame)
    {
        if (state->current == state->end)
            return _URC_END_OF_STACK;
        else
        {
            *state->current = reinterpret_cast<void*>(frame);
            ++state->current;
        }
    }
    return _URC_NO_REASON;
}

size_t GetStack(TStack& stack)
{
    BacktraceState state = {stack, stack + StackSize};
    _Unwind_Backtrace(Unwind, &state);
    return state.current - stack;
}

#else

#ifndef _WIN32
    #include <execinfo.h>
#endif

size_t GetStack(TStack& stack)
{
#ifdef _WIN32
    typedef USHORT (WINAPI *FCaptureStackBackTrace)(__in ULONG, __in ULONG, __out PVOID*, __out_opt PULONG);
    static FCaptureStackBackTrace CaptureStackBackTrace = (FCaptureStackBackTrace)(GetProcAddress(LoadLibraryA("kernel32.dll"), "RtlCaptureStackBackTrace"));
    return CaptureStackBackTrace ? CaptureStackBackTrace(0, StackSize, stack, NULL) : 0;
#else
    return backtrace(stack, StackSize);
#endif
}
#endif
