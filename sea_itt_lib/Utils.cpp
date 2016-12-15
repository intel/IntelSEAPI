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
#include "IttNotifyStdSrc.h"
#include <string.h>

#ifdef _WIN32
    #include <Psapi.h>
#else
    #include <cxxabi.h>
    #include <dlfcn.h>

    #ifndef __ANDROID__
        #include <execinfo.h>
    #endif

#endif

#ifdef __APPLE__
    #include <mach-o/dyld.h>
#endif

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

std::string GetStackString()
{
    std::string res;
    TStack stack;
    size_t size = GetStack(stack);
    for (size_t i = 2; i < size; ++i)
    {
        if (res.size())
            res += "<-";
        Dl_info dl_info = {};
        dladdr(stack[i], &dl_info);
        if (dl_info.dli_sname)
            res += dl_info.dli_sname;
        else
            res += std::to_string(stack[i]);
    }
    return res;
}

#else

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

std::string GetStackString()
{
    return std::string();
}

#endif

namespace sea {

#ifdef _WIN32
const char* GetProcessName(bool bFullPath)
{
    assert(bFullPath);
    static char process_name[1024] = {};
    if (!process_name[0])
        GetModuleFileNameA(NULL, process_name, sizeof(process_name) - 1);
    return process_name;
}

SModuleInfo Fn2Mdl(void* fn)
{
    HMODULE hModule = NULL;
    GetModuleHandleEx(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS, (LPCTSTR)fn, &hModule);
    char filename[1024] = {};
    GetModuleFileNameA(hModule, filename, sizeof(filename) - 1);
    MODULEINFO mi = {};
    GetModuleInformation(GetCurrentProcess(), hModule, &mi, sizeof(MODULEINFO));
    return SModuleInfo{hModule, mi.SizeOfImage, filename};
}

#else

#include <sys/stat.h>

size_t GetFileSize(const char *path) {
    struct stat st = {};

    if (0 == stat(path, &st))
        return st.st_size;

    return -1;
}

sea::SModuleInfo Fn2Mdl(void* fn)
{
    //FIXME: Linux: dl_iterate_phdr(), OSX: http://stackoverflow.com/questions/28846503/getting-sizeofimage-and-entrypoint-of-dylib-module
    Dl_info dl_info = {};
    dladdr(fn, &dl_info);
    if (!dl_info.dli_fname)
        return SModuleInfo{dl_info.dli_fbase, 0, dl_info.dli_fname};

    if (dl_info.dli_fname[0] == '/')
    { //path is absolute
        return SModuleInfo{dl_info.dli_fbase, GetFileSize(dl_info.dli_fname), dl_info.dli_fname};
    }
    else
    {
        if (const char * absolute = realpath(dl_info.dli_fname, nullptr))
        {
            SModuleInfo mdlInfo{dl_info.dli_fbase, GetFileSize(absolute), absolute};
            free((void*) absolute);
            return mdlInfo;
        }
        else
        {
            return SModuleInfo{dl_info.dli_fbase, GetFileSize(dl_info.dli_fname), dl_info.dli_fname};
        }
    }
}

const char* GetProcessName(bool bFullPath)
{
    static char process_name[1024] = {};
#ifdef __APPLE__
    uint32_t size = 1023;
    _NSGetExecutablePath(process_name, &size);
#else
    if (!process_name[0])
        process_name[readlink("/proc/self/exe", process_name, sizeof(process_name)/sizeof(process_name[0]) - 1 )] = 0;
#endif //__APPLE__
    if (bFullPath) return process_name;
    return strrchr(process_name, '/') + 1;
}

#endif

} //namespace sea


