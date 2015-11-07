#include "IttNotifyStdSrc.h"

#include "cvmarkersobj.h"

using namespace sea;

class CMarkerSeries
{
public:
    static CMarkerSeries& Instance()
    {
        static CMarkerSeries oMarkerSeries;
        return oMarkerSeries;
    }
    Concurrency::diagnostic::marker_series& Get(const std::string& name)
    {
        std::lock_guard<TCritSec> lock(m_cs);
        auto it = m_markers.find(name);
        if (it != m_markers.end())
            return *m_markers[name].get();
        m_markers[name] = std::make_shared<Concurrency::diagnostic::marker_series>(name.substr(0, 24).c_str());
        return *m_markers[name].get();
    }

    bool IsEnabled()
    {
        static Concurrency::diagnostic::marker_series marker_series;
        return marker_series.is_enabled();
    }

protected:
    TCritSec m_cs;
    std::map<std::string, std::shared_ptr<Concurrency::diagnostic::marker_series>> m_markers;
};


class CConcurrencyVisualizer: public IHandler
{
    CMarkerSeries& m_oMarkerSeries = CMarkerSeries::Instance();

    void TaskBegin(STaskDescriptor& oTask, bool bOverlapped) override
    {
        if (!oTask.pName) //TODO: we don't handle the task_begin_fn case yet
            return;
        Concurrency::diagnostic::marker_series& series = m_oMarkerSeries.Get(std::string(oTask.pDomain->nameA));
        Cookie<Concurrency::diagnostic::span>(oTask, series, oTask.pName->strA); //first access creates the cookie
    }

    void AddArg(STaskDescriptor& oTask, const __itt_string_handle *pKey, const char *data, size_t length) override
    {
        m_oMarkerSeries.Get(std::string(oTask.pDomain->nameA) + "/" + oTask.pName->strA).write_flag("%s = %s", pKey->strA, data);
    }

    //nothing to do in TaskEnd: the removal of STaskDescriptor will remove the Concurrency::diagnostic::span allocated in cookies, this will finish the task

    void Marker(const CTraceEventFormat::SRegularFields& rf, const __itt_domain *pDomain, __itt_id, __itt_string_handle *pName, __itt_scope scope) override
    {
        m_oMarkerSeries.Get(pDomain->nameA).write_flag(pName->strA);
    }


}* g_ConcurrencyVisualizer = IHandler::Register<CConcurrencyVisualizer>(CMarkerSeries::Instance().IsEnabled());
