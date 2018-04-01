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

#include <pcp/pmapi.h>
#include <pcp/mmv_stats.h>
#include "IttNotifyStdSrc.h"
#include <vector>
//http://pcp.io/man/man5/mmv.5.html
using namespace sea;

class CMMVStats : public IHandler
{
    std::vector<mmv_metric2_t> m_metrics;
    std::vector<mmv_indom2_t> m_indoms;
    typedef std::vector<mmv_instances2_t> TInstances;
    std::map<uint32_t, TInstances> m_instances;
    void* m_pMMV = nullptr;
    TCritSec m_cs;

public:
    CMMVStats()
    {
        mmv_indom2_t indom = {};
        indom.serial = m_indoms.size() + 1;
        TInstances& instances = m_instances[indom.serial];
        mmv_instances2_t instance = {(int32_t)instances.size() + 1, const_cast<char*>("value")};
        instances.push_back(instance);
        indom.instances = instances.data();
        indom.count = instances.size();
        indom.shorttext = indom.helptext = const_cast<char*>("SEA Indom");
        m_indoms.push_back(indom);
    }

    void RecreateCounters()
    {
        std::lock_guard<TCritSec> lock(m_cs);
        if (m_pMMV)
            mmv_stats_stop("IntelSEAPI", m_pMMV);
        m_pMMV = mmv_stats2_init("IntelSEAPI", 0, MMV_FLAG_PROCESS, m_metrics.data(), m_metrics.size(), m_indoms.data(), m_indoms.size());
    }

    void CreateCounter(const __itt_counter& id) override
    {
        __itt_counter_info_t* pInfo = reinterpret_cast<__itt_counter_info_t*>(id);
        CreateCounter(pInfo->nameA, (__itt_metadata_type)pInfo->type);
    }

    void CreateCounter(const char* name, __itt_metadata_type type)
    {
        std::lock_guard<TCritSec> lock(m_cs);
        mmv_metric2_t metric = {};
        metric.name = metric.shorttext = metric.helptext = const_cast<char*>(name);
        metric.item = m_metrics.size() + 1;

        switch(type)
        {
            case __itt_metadata_u64:     /**< Unsigned 64-bit integer */
                metric.type = MMV_TYPE_U64;
                break;
            case __itt_metadata_s64:     /**< Signed 64-bit integer */
                metric.type = MMV_TYPE_I64;
                break;
            case __itt_metadata_u32:     /**< Unsigned 32-bit integer */
                metric.type = MMV_TYPE_U32;
                break;
            case __itt_metadata_s32:     /**< Signed 32-bit integer */
                metric.type = MMV_TYPE_I32;
                break;
            case __itt_metadata_u16:     /**< Unsigned 16-bit integer */
                metric.type = MMV_TYPE_U32;
                break;
            case __itt_metadata_s16:     /**< Signed 16-bit integer */
                metric.type = MMV_TYPE_I32;
                break;
            case __itt_metadata_float:   /**< Signed 32-bit floating-point */
                metric.type = MMV_TYPE_FLOAT;
                break;
            case __itt_metadata_double:  /**< SIgned 64-bit floating-point */
                metric.type = MMV_TYPE_DOUBLE;
                break;
            default:
                assert(false);
                return;
        }
        metric.semantics = MMV_SEM_INSTANT;
        metric.dimension = MMV_UNITS(0,0,1,0,0,PM_COUNT_ONE);

        m_metrics.push_back(metric);
        RecreateCounters();
    }

    void Counter(const CTraceEventFormat::SRegularFields& rf, const __itt_domain *pDomain, const __itt_string_handle *pName, double value) override
    {
        std::lock_guard<TCritSec> lock(m_cs);
        pmAtomValue* pValue = mmv_lookup_value_desc(m_pMMV, pName->strA, "value");
        if (!pValue)
        {
            CreateCounter(pName->strA, __itt_metadata_double);
            pValue = mmv_lookup_value_desc(m_pMMV, pName->strA, "value");
        }
        mmv_set_value(m_pMMV, pValue, value);
    }

} * g_pMMVStats = IHandler::Register<CMMVStats>(true);