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

#include "rad_tm.h"
#include "IttNotifyStdSrc.h"

using namespace sea;

class CRadTelemetry : public IHandler
{
    std::vector<char> m_memory;

    bool ErrorCheck(tm_error err)
    {
        if (err == TM_OK)
        {
            return true;
        }
        else if (err == TMERR_DISABLED)
        {
            VerbosePrint("Telemetry is disabled via #define NTELEMETRY\n");
        }
        else if (err == TMERR_UNINITIALIZED)
        {
            VerbosePrint("tmInitialize failed or was not called\n");
        }
        else if (err == TMERR_NETWORK_NOT_INITIALIZED)
        {
            VerbosePrint("WSAStartup was not called before tmOpen! Call WSAStartup or pass TMOF_INIT_NETWORKING.\n");
        }
        else if (err == TMERR_NULL_API)
        {
            VerbosePrint("There is no RAD Telemetry API (the DLL isn't in the EXE's path)!\n");
        }
        else if (err == TMERR_COULD_NOT_CONNECT)
        {
            VerbosePrint("There is no Telemetry server running\n");
        }
        return false;
    }
public:
    static bool Init()
    {
#ifdef _DEBUG
        tmLoadLibrary(TM_DEBUG);
#else
        tmLoadLibrary(TM_RELEASE);
#endif
        return !!(TM_API_PTR);
    }
    CRadTelemetry& operator = (const CRadTelemetry&) = delete;
    CRadTelemetry()
    {
        m_memory.resize(4 * 1024 * 1024);
        tm_error err = tmInitialize((uint32_t)m_memory.size(), m_memory.data());
        if (!ErrorCheck(err)) return;
        // Connect to a telemetry server and start profiling
        // On Windows platforms TMOF_INIT_NETWORKING will initialize WinSock ... if you already do this for your game then just pass 0
        err = tmOpen(
            0,                              // unused
            "Intel(R) Single Event API",    // program name, don't use slashes or weird character that will screw up a filename
            __DATE__ " " __TIME__,          // identifier, could be date time, or a build number ... whatever you want
            "localhost",                    // telemetry server address
            TMCT_TCP,                       // network capture
            4719,                           // telemetry server port
            TMOF_INIT_NETWORKING,           // flags
            100);                           // timeout in milliseconds ... pass -1 for infinite
        if (!ErrorCheck(err)) return;
    }

    void SetThreadName(const CTraceEventFormat::SRegularFields& rf, const char* name) override
    {
        // Naming your threads makes things clearer in the visualizer
        tmThreadName(
            0,                        // Capture mask (0 means capture everything)
            (uint32_t)rf.tid,         // Thread id (0 means use the current thread)
            name                      // Name of the thread
        );
    }

    void TaskBegin(STaskDescriptor& oTask, bool bOverlapped) override
    {
        if (!oTask.pName) return;
        if (bOverlapped)
        {
            tmBeginTimeSpan(0, oTask.id.d1, 0, oTask.pName->strA);
        }
        else
        {
            tmEnter(0, 0, oTask.pName->strA);
        }
    }

    void AddArg(STaskDescriptor& oTask, const __itt_string_handle *pKey, const char *data, size_t length) override
    {
        if (!length || data[length] == 0)
        {
            tmMessage(0, TMMF_ZONE_SHOW_IN_PARENTS, "%s: %s", pKey->strA, data);
        }
    }

    void AddArg(STaskDescriptor& oTask, const __itt_string_handle *pKey, double value) override
    {
        tmMessage(0, TMMF_ZONE_SHOW_IN_PARENTS, "%s: %f", pKey->strA, value);
    }

    void TaskEnd(STaskDescriptor& oTask, const CTraceEventFormat::SRegularFields& rf, bool bOverlapped) override
    {
        if (!oTask.pName) return;
        if (bOverlapped)
        {
            tmEndTimeSpan(0, oTask.id.d1);
        }
        else
        {
            tmLeave(0);
        }
    }

    void Marker(const CTraceEventFormat::SRegularFields& rf, const __itt_domain *pDomain, __itt_id id, __itt_string_handle *pName, __itt_scope scope) override
    {
        tmMessage(0, TMMF_ICON_EXCLAMATION, "%s::%s", pDomain->nameA, pName->strA);
    }

    void Counter(const CTraceEventFormat::SRegularFields& rf, const __itt_domain *pDomain, const __itt_string_handle *pName, double value) override
    {
        tmPlot(0, TM_PLOT_UNITS_REAL, TM_PLOT_DRAW_LINE, value, pName->strA);
    }

    void Alloc(const CTraceEventFormat::SRegularFields& rf, const void* addr, size_t size, const char* domain, const char* name) override
    {
        tmAlloc(0, addr, size, name);
    }

    void Free(const CTraceEventFormat::SRegularFields& rf, const void* addr, size_t size, const char* domain, const char* name) override
    {
        tmFree(0, addr);
    }


    ~CRadTelemetry()
    {
        tmClose(0);
        tmShutdown();
    }

}*g_pRadTelemetryHandler = IHandler::Register<CRadTelemetry>((GetFeatureSet() & sfRadTelemetry) && CRadTelemetry::Init());


