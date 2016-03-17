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



#include "IttNotifyStdSrc.h"
#include "Utils.h"
#include <stdlib.h>
#include <cstdio>
#include <string.h>

#define INTEL_LIBITTNOTIFY "INTEL_LIBITTNOTIFY"

#ifdef _WIN32
    #define setenv _putenv
    #include <windows.h>
    #include "IntelSEAPI.h"
#else
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

int GlobalInit()
{
    static const char var_name[] = INTEL_LIBITTNOTIFY BIT_SUFFIX;
    sea::SModuleInfo mdlinfo = sea::Fn2Mdl((void*)GlobalInit);

    VerbosePrint("IntelSEAPI: %s=%s | Loaded from: %s\n", var_name, get_environ_value(var_name).c_str(), mdlinfo.path.c_str());

    std::string value = var_name;
    value += "=";
    value += mdlinfo.path;

    setenv(_strdup(value.c_str()));
    return 1;
}

int nSetLib = GlobalInit();

void AtExit();

void ChainGlobal(__itt_global* pRoot, __itt_global* pNew)
{
    __itt_global* pCurrent = pRoot;
    while (pCurrent->next)
    {
        if (pCurrent->next == pNew) //already chained
            return;
        pCurrent = pCurrent->next;
    }
    pCurrent->next = pNew;
}

__itt_global* GetITTGlobal(__itt_global* pGlob)
{
    static __itt_global* pGlobal = pGlob;
    assert(pGlobal);
    if (pGlob && pGlobal != pGlob)
        ChainGlobal(pGlobal, pGlob);
    return pGlobal;
}

#ifdef _WIN32
#include <windows.h>

#define FIX_STR(type, ptr, name)\
    if (!ptr->name##A) {\
        if (ptr->name##W) {\
            size_t len = lstrlenW((const wchar_t*)ptr->name##W);\
            char* dest = (char*)malloc(len + 2);\
            wcstombs_s(&len, dest, len + 1, (const wchar_t*)ptr->name##W, len + 1);\
            const_cast<type*>(ptr)->name##A = dest;\
                }\
                else\
        {\
            const_cast<type*>(ptr)->name##A = _strdup("null");\
        }\
        }

#else
#define FIX_STR(type, ptr, name)

#endif

#define FIX_DOMAIN(ptr) FIX_STR(__itt_domain, ptr, name)
#define FIX_STRING(ptr) FIX_STR(__itt_string_handle, ptr, str)


extern "C" {

    SEA_EXPORT void ITTAPI __itt_api_init(__itt_global* pGlob, __itt_group_id id)
    {
        const char* procname = sea::GetProcessName(true);
        sea::SModuleInfo mdlinfo = sea::Fn2Mdl(pGlob);
        VerbosePrint("IntelSEAPI init is called from process '%s' at module '%s'\n", procname, mdlinfo.path.c_str());
        GetITTGlobal(pGlob);
        sea::FillApiList(pGlob->api_list_ptr);
        for (___itt_domain* pDomain = pGlob->domain_list; pDomain; pDomain = pDomain->next)
        {
            FIX_DOMAIN(pDomain);
            sea::InitDomain(pDomain);
        }
        for (__itt_string_handle* pStr = pGlob->string_list; pStr; pStr = pStr->next)
        {
            FIX_STRING(pStr);
            sea::ReportString(const_cast<__itt_string_handle *>(pStr));
        }
        sea::ReportModule(pGlob);
        static bool bInitialized = false;
        if (!bInitialized)
        {
            bInitialized = true;
            sea::InitSEA();
#ifdef _WIN32
            EventRegisterIntelSEAPI();
#endif
            atexit(AtExit);
        }
    }

    SEA_EXPORT void ITTAPI __itt_api_fini(__itt_global* pGlob)
    {
        sea::FinitaLaComedia();
#ifdef _WIN32
        EventUnregisterIntelSEAPI();
#endif
    }

}

void AtExit()
{
    __itt_api_fini(nullptr);
}

