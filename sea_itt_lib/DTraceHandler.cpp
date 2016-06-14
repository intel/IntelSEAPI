#include "IttNotifyStdSrc.h"
using namespace sea;
#ifdef __APPLE__

void DTraceTaskBegin(const char* domain, uint64_t taskid, uint64_t parentid, const char* name);
void DTraceTaskEnd(const char* domain, uint64_t taskid, const char* meta, const char* name);
void DTraceTaskBeginOverlapped(const char* domain, uint64_t taskid, uint64_t parentid, const char* name);
void DTraceTaskEndOverlapped(const char* domain, uint64_t taskid, const char* meta, const char* name);
void DTraceTaskCounter(const char* domain, int64_t value, const char* name);
void DTraceMarker(const char* domain, uint64_t id, const char* name, const char* scope);

class CDTrace: public IHandler
{
    void TaskBegin(STaskDescriptor& oTask, bool bOverlapped) override
    {
        if (!oTask.pName) //TODO: task_begin_fn is not yet supported
            return;
        if (bOverlapped)
        {
            DTraceTaskBeginOverlapped(oTask.pDomain->nameA, oTask.id.d1, oTask.parent.d1, oTask.pName->strA);
        }
        else
        {
            //TODO: use id generator as in CETW, this can increase dtrace collection speed
            DTraceTaskBegin(oTask.pDomain->nameA, oTask.id.d1, oTask.parent.d1, oTask.pName->strA);
        }
    }

    void AddArg(STaskDescriptor& oTask, const __itt_string_handle *pKey, const char *data, size_t length) override
    {
        Cookie<CTraceEventFormat::CArgs>(oTask).Add(pKey->strA, length ? std::string(data, length).c_str() : data);
    }


    void TaskEnd(STaskDescriptor& oTask, const CTraceEventFormat::SRegularFields&, bool bOverlapped) override
    {
        if (!oTask.pName) //TODO: task_begin_fn is not yet supported
            return;
        if (bOverlapped)
        {
            DTraceTaskEndOverlapped(oTask.pDomain->nameA, oTask.id.d1, Cookie<CTraceEventFormat::CArgs>(oTask).Str().c_str(), oTask.pName->strA);
        }
        else
        {
            DTraceTaskEnd(oTask.pDomain->nameA, oTask.id.d1, Cookie<CTraceEventFormat::CArgs>(oTask).Str().c_str(), oTask.pName->strA);
        }
    }

    void Marker(const CTraceEventFormat::SRegularFields&, const __itt_domain *pDomain, __itt_id id, __itt_string_handle *pName, __itt_scope scope) override
    {
        DTraceMarker(pDomain->nameA, id.d1, pName->strA, GetScope(scope));
    }

    void Counter(const CTraceEventFormat::SRegularFields&, const __itt_domain *pDomain, const __itt_string_handle *pName, double value) override
    {
        DTraceTaskCounter(pDomain->nameA, (int64_t)value, pName->strA);
    }

}* g_pDTraceHandler = IHandler::Register<CDTrace>(true);
#endif
