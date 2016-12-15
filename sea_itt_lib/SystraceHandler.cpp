#include "IttNotifyStdSrc.h"

using namespace sea;

std::string MakeName(const __itt_id& parent, const char* name, const __itt_id& id)
{
    std::stringstream ss;
    if (parent.d1)
    {
        ss << "0x" << std::hex << uint64_t(parent.d1) << "->";
    }
    ss << name;
    if (id.d1)
    {
        ss << ":0x" << std::hex << uint64_t(id.d1);
    }
    return ss.str();
}

class CSystrace: public IHandler
{
    CTraceEventFormat m_oTraceEventFormat;

    void TaskBegin(STaskDescriptor& oTask, bool bOverlapped) override
    {
        if (bOverlapped || !oTask.pName) //bOverlapped will be sent on End as complete event
            return;

        m_oTraceEventFormat.WriteEvent(
            CTraceEventFormat::Begin,
            oTask.pName->strA,
            CTraceEventFormat::CArgs(),
            &oTask.rf,
            oTask.pDomain->nameA
        );

    }

    void AddArg(STaskDescriptor& oTask, const __itt_string_handle *pKey, const char *data, size_t length) override
    {
        Cookie<CTraceEventFormat::CArgs>(oTask).Add(pKey->strA, length ? std::string(data, length).c_str() : data);
    }

    void TaskEnd(STaskDescriptor& oTask, const CTraceEventFormat::SRegularFields& rf, bool bOverlapped) override
    {
        if (bOverlapped)
        {
            uint64_t dur = rf.nanoseconds - oTask.rf.nanoseconds;
            uint64_t id = oTask.id.d1;
            m_oTraceEventFormat.WriteEvent(CTraceEventFormat::Complete, MakeName(oTask.parent, oTask.pName->strA, oTask.id),
                Cookie<CTraceEventFormat::CArgs>(oTask), &oTask.rf,
                oTask.pDomain->nameA, //gets into categories to filter
                &id, &dur
            );
        }
        else if (oTask.pName)
        {
            m_oTraceEventFormat.WriteEvent(CTraceEventFormat::End, oTask.pName->strA, Cookie<CTraceEventFormat::CArgs>(oTask), &rf, oTask.pDomain->nameA);
        }
    }

    void Marker(const CTraceEventFormat::SRegularFields& rf, const __itt_domain *pDomain, __itt_id id, __itt_string_handle *pName, __itt_scope scope) override
    {
        CTraceEventFormat::SRegularFields rf_copy = rf;
        if (scope == __itt_scope_global)
            rf_copy.tid = ~0x0;
        else if (scope == __itt_scope_marker)
            rf_copy.tid = 0x0;

        const char* domain = pDomain->nameA;
        const char* name = pName->strA;
        uint64_t id_addr = id.d1;


        m_oTraceEventFormat.WriteEvent(
            CTraceEventFormat::Instant, pName->strA,
            CTraceEventFormat::CArgs(),
            &rf_copy,
            pDomain->nameA, //gets into categories to filter
            (id_addr ? &id_addr : nullptr)
        );
    }

    void Counter(const CTraceEventFormat::SRegularFields& rf, const __itt_domain *pDomain, const __itt_string_handle *pName, double value) override
    {
        m_oTraceEventFormat.WriteEvent(
            CTraceEventFormat::Counter, pDomain->nameA,
            CTraceEventFormat::CArgs(pName->strA, value),
            &rf,
            pDomain->nameA //gets into categories to filter
        );
    }

    void SetThreadName(const CTraceEventFormat::SRegularFields& rf, const char* name) override
    {
        m_oTraceEventFormat.WriteEvent(CTraceEventFormat::Metadata, "thread_name", CTraceEventFormat::CArgs("name", name), &rf);
    }

} * g_pSystraceHandler = IHandler::Register<CSystrace>(true);

