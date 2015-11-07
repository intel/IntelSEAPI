#include "IttNotifyStdSrc.h"

using namespace sea;

class CETW: public IHandler
{
public:
    CETW& operator = (const CETW&) = delete;
    void operator = (size_t cookie)
    {
        m_cookie = m_cookie;
    }
    inline unsigned short GetDepth(STaskDescriptor* pTask)
    {
        unsigned short count = 0;
        for (;pTask; pTask = pTask->prev, ++count);
        return count;
    }

    //TODO: It can be called from task_begin_ex. May be ROI allows taking time from records?
    void TaskBegin(STaskDescriptor& oTask, bool bOverlapped) override
    {
        if (bOverlapped)
        {
            EventWriteTASK_BEGIN(oTask.pDomain->nameA, oTask.pName->strA, &IdCaster{oTask.id}.to, &IdCaster{oTask.parent}.to, ~0x0, ~0x0);
        }
        else
        {
            //taskid is crucial for regions of interest mapping
            __itt_id id = (oTask.id.d1 || oTask.id.d2) ? oTask.id : __itt_id{uint64_t(&oTask), uint64_t(&oTask)};
            unsigned short depth = GetDepth(&oTask);
            EventWriteTASK_BEGIN(oTask.pDomain->nameA, oTask.pName->strA, &IdCaster{id}.to, &IdCaster{oTask.parent}.to, depth, depth - 1);
        }
    }

    void AddArg(STaskDescriptor& oTask, const __itt_string_handle *pKey, const char *data, size_t length)
    {
        Cookie<CTraceEventFormat::CArgs>(oTask).Add(pKey->strA, length ? std::string(data, length).c_str() : data);
    }

    void TaskEnd(STaskDescriptor& oTask, const CTraceEventFormat::SRegularFields& rf, bool bOverlapped) override
    {
        __itt_id id = (bOverlapped || oTask.id.d1 || oTask.id.d2) ? oTask.id : __itt_id{uint64_t(&oTask), uint64_t(&oTask)};
        EventWriteTASK_END(oTask.pDomain->nameA, &IdCaster{id}.to, Cookie<CTraceEventFormat::CArgs>(oTask).Str().c_str());
    }

    void Marker(const CTraceEventFormat::SRegularFields& rf, const __itt_domain *pDomain, __itt_id id, __itt_string_handle *pName, __itt_scope scope) override
    {
        EventWriteMARKER(pDomain->nameA, pName->strA, id.d1, GetScope(scope));
    }

    void Counter(const CTraceEventFormat::SRegularFields& rf, const __itt_domain *pDomain, const __itt_string_handle *pName, double value) override
    {
        EventWriteCOUNTER(pDomain->nameA, pName->strA, value);
    }

}* g_pETWHandler = IHandler::Register<CETW>(!!IntelSEAPI_Context.IsEnabled);

