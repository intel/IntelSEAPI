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
    }

    void AddArg(STaskDescriptor& oTask, const __itt_string_handle *pKey, const char *data, size_t length)
    {
        Cookie<CTraceEventFormat::CArgs>(oTask).Add(pKey->strA, length ? std::string(data, length).c_str() : data);
    }

    void TaskEnd(STaskDescriptor& oTask, const CTraceEventFormat::SRegularFields& rf, bool bOverlapped) override
    {
        if (!oTask.pName)
            return;
        __itt_id id = (bOverlapped || oTask.id.d1 || oTask.id.d2) ? oTask.id : __itt_id{ uint64_t(&oTask), uint64_t(&oTask) };
        uint64_t data[3] = { uint64_t(rf.pid), uint64_t(rf.tid), rf.nanoseconds };
        EventWriteTASK_COMPLETE(oTask.pDomain->nameA, oTask.pName->strA, &IdCaster{ id }.to, &IdCaster{ oTask.parent }.to, Cookie<CTraceEventFormat::CArgs>(oTask).Str().c_str(), rf.nanoseconds - oTask.rf.nanoseconds, data);
    }

    void Marker(const CTraceEventFormat::SRegularFields& rf, const __itt_domain *pDomain, __itt_id id, __itt_string_handle *pName, __itt_scope scope) override
    {
        uint64_t data[3] = { uint64_t(rf.pid), uint64_t(rf.tid), rf.nanoseconds };
        EventWriteMARKER(pDomain->nameA, pName->strA, id.d1, GetScope(scope), data);
    }

    void Counter(const CTraceEventFormat::SRegularFields& rf, const __itt_domain *pDomain, const __itt_string_handle *pName, double value) override
    {
        uint64_t data[3] = { uint64_t(rf.pid), uint64_t(rf.tid), rf.nanoseconds };
        EventWriteCOUNTER(pDomain->nameA, pName->strA, value, data);
    }

}* g_pETWHandler = IHandler::Register<CETW>(true);

