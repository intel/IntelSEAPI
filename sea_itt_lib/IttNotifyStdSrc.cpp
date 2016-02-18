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

#include <fcntl.h>
#include <sys/types.h>
#include <set>
#include <vector>
#include <unordered_map>
#include <algorithm>
#include <cstring>
#include <limits>

#ifdef _WIN32
    #include <io.h>
    #include <direct.h>
#endif

namespace sea {
    IHandler* g_handlers[MAX_HANDLERS] = {}; //10 is more than enough for now
}

//FIXME: in general add much more comments

std::map<std::string, size_t> g_stats; //can't be static function variable due to lifetime limits

class CIttFnStat
{
public:
    CIttFnStat(const char* name)
    {
        if (!sea::IsVerboseMode()) return;
        sea::CIttLocker locker;
        ++GetStats()[name];
    }

    static std::map<std::string, size_t>& GetStats()
    {
        return g_stats;
    }
};

#ifdef _DEBUG
    #define ITT_FUNCTION_STAT() CIttFnStat oIttFnStat(__FUNCTION__)
#else
    #define ITT_FUNCTION_STAT()
#endif


struct __itt_frame_t
{
    __itt_domain* pDomain;
    __itt_id id;
};

inline bool operator < (const __itt_id& left, const __itt_id& right)
{
    return memcmp(&left, &right, sizeof(__itt_id)) < 0;
}

inline bool operator == (const __itt_id& left, const __itt_id& right)
{
    return (left.d1 == right.d1) && (left.d2 == right.d2);
}

namespace sea {

uint64_t g_nRingBuffer = 1000000000ull * atoi(get_environ_value("INTEL_SEA_RING").c_str()); //in nanoseconds
uint64_t g_nAutoCut = 1024ull * 1024 * atoi(get_environ_value("INTEL_SEA_AUTOCUT").c_str()); //in MB
uint64_t g_features = sea::GetFeatureSet();

class DomainFilter
{
    std::string m_path;
    std::map<std::string/*domain*/, bool/*disabled*/> m_domains;
public:
    DomainFilter()
    {
        m_path = get_environ_value("INTEL_SEA_FILTER");
        if (m_path.empty()) return;
        std::ifstream ifs(m_path);
        for (std::string domain; std::getline(ifs, domain);)
        {
            if (domain[0] == '#')
                m_domains[domain.c_str() + 1] = true;
            else
                m_domains[domain] = false;
        }
    }

    operator bool() const
    {
        return !m_path.empty();
    }

    bool IsEnabled(const char* szDomain)
    {
        return !m_domains[szDomain]; //new domain gets initialized with bool() which is false, so we invert it
    }

    void Finish()
    {
        if (m_path.empty()) return;
        std::ofstream ifs(m_path);
        for (const auto& pair : m_domains)
        {
            if (pair.second)
                ifs << '#';
            ifs << pair.first << std::endl;
        }
    }
} g_oDomainFilter;

bool PathExists(const std::string& path)
{
#ifdef _WIN32
    return -1 != _access(path.c_str(), 0);
#else
    return -1 != access(path.c_str(), F_OK);
#endif
}

std::string GetDir(std::string path, const std::string& append)
{
    if (path.empty()) return path;
    path += append;
#ifdef _WIN32
    _mkdir(path.c_str());
#else
    mkdir(path.c_str(), FilePermissions);
#endif
    char lastSym = path[path.size()-1];
    if (lastSym != '/' && lastSym != '\\')
        path += "/";
    return path;
}

std::string GetSavePath()
{
    static std::string save_to = get_environ_value("INTEL_SEA_SAVE_TO");
    return GetDir(
        save_to,
        ("-" + std::to_string(CTraceEventFormat::GetRegularFields().pid))
    );
}

std::string g_savepath = GetSavePath();
std::shared_ptr<std::string> g_spCutName;

std::string Escape4Path(std::string str)
{
    std::replace_if(str.begin(), str.end(),
        [](char sym){return strchr("/\\:*?\"<>|", sym);},
        '_'
    );
    return str;
}

void InitDomain(__itt_domain* pDomain)
{
    CIttLocker locker;
    pDomain->extra2 = new DomainExtra{};
    if (g_savepath.size())
    {
        DomainExtra* pDomainExtra = reinterpret_cast<DomainExtra*>(pDomain->extra2);
        pDomainExtra->strDomainPath = GetDir(g_savepath, Escape4Path(pDomain->nameA));
        pDomainExtra->bHasDomainPath = !pDomainExtra->strDomainPath.empty();
    }

    if (!g_oDomainFilter)
        return;
    pDomain->flags = g_oDomainFilter.IsEnabled(pDomain->nameA) ? 1 : 0;
}

SThreadRecord* GetThreadRecord()
{
    static thread_local SThreadRecord* pThreadRecord = nullptr;
    if (pThreadRecord)
        return pThreadRecord;

    CIttLocker lock;

    pThreadRecord = new SThreadRecord{};
    static __itt_global* pGlobal = GetITTGlobal();

    __itt_domain* pDomain = pGlobal->domain_list;
    DomainExtra* pDomainExtra = reinterpret_cast<DomainExtra*>(pDomain->extra2);
    SThreadRecord* pRecord = pDomainExtra->pThreadRecords;
    if (pRecord)
    {
        while(pRecord->pNext) pRecord = pRecord->pNext;
        pRecord->pNext = pThreadRecord;
    }
    else
        pDomainExtra->pThreadRecords = pThreadRecord;

    return pThreadRecord;
}

void UNICODE_AGNOSTIC(thread_set_name)(const char* name)
{
    ITT_FUNCTION_STAT();

    for (size_t i = 0; (i < MAX_HANDLERS) && g_handlers[i]; ++i)
    {
        g_handlers[i]->SetThreadName(GetRegularFields(), name);
    }

#ifdef __ANDROID__
    pthread_setname_np(pthread_self(), name);
#elif defined(__APPLE__)
    pthread_setname_np(name);
#elif defined(__linux__)
    pthread_setname_np(pthread_self(), name);
#endif
}
#ifdef _WIN32
void thread_set_nameW(const wchar_t* name)
{
    UNICODE_AGNOSTIC(thread_set_name)(W2L(name).c_str());
}
#endif



inline uint64_t ConvertClockDomains(unsigned long long timestamp, __itt_clock_domain* pClock)
{
    if (!pClock) return timestamp;
    uint64_t start = *(uint64_t*)pClock->extra2;
    return start + (timestamp - pClock->info.clock_base) * SHiResClock::period::den / pClock->info.clock_freq;
}

CTraceEventFormat::SRegularFields GetRegularFields(__itt_clock_domain* clock_domain, unsigned long long timestamp)
{
    CTraceEventFormat::SRegularFields rf = CTraceEventFormat::GetRegularFields();

    __itt_track* pTrack = GetThreadRecord()->pTrack;

    if (pTrack)
    {
        CTraceEventFormat::SRegularFields& trackRF = *(CTraceEventFormat::SRegularFields*)pTrack->extra2;
        rf.pid = trackRF.pid;
        rf.tid = trackRF.tid;
    }
    if (clock_domain || timestamp)
    {
        rf.nanoseconds = ConvertClockDomains(timestamp, clock_domain);
    }
    return rf;
}


__itt_domain* UNICODE_AGNOSTIC(domain_create)(const char* name)
{
    __itt_domain *h_tail = NULL, *h = NULL;

    if (name == NULL)
    {
        return NULL;
    }
    CIttLocker locker;
    static __itt_global* pGlobal = GetITTGlobal();
    for (h_tail = NULL, h = pGlobal->domain_list; h != NULL; h_tail = h, h = h->next)
    {
        if (h->nameA != NULL && !__itt_fstrcmp(h->nameA, name)) break;
    }
    if (h == NULL)
    {
        NEW_DOMAIN_A(pGlobal,h,h_tail,name);
    }
    InitDomain(h);
    return h;
}

#ifdef _WIN32
__itt_domain* domain_createW(const wchar_t* name)
{
    return UNICODE_AGNOSTIC(domain_create)(W2L(name).c_str());
}
#endif

__itt_string_handle* ITTAPI UNICODE_AGNOSTIC(string_handle_create)(const char* name)
{
    __itt_string_handle *h_tail = NULL, *h = NULL;

    if (name == NULL)
    {
        return NULL;
    }
    CIttLocker locker;
    static __itt_global* pGlobal = GetITTGlobal();

    for (h_tail = NULL, h = pGlobal->string_list; h != NULL; h_tail = h, h = h->next)
    {
        if (h->strA != NULL && !__itt_fstrcmp(h->strA, name)) break;
    }
    if (h == NULL)
    {
        NEW_STRING_HANDLE_A(pGlobal,h,h_tail,name);
    }

    sea::ReportString(h);
    return h;
}


#ifdef _WIN32
__itt_string_handle* string_handle_createW(const wchar_t* name)
{
    return UNICODE_AGNOSTIC(string_handle_create)(W2L(name).c_str());
}
#endif

void marker(const __itt_domain *pDomain, __itt_id id, __itt_string_handle *pName, __itt_scope scope)
{
    ITT_FUNCTION_STAT();
    CTraceEventFormat::SRegularFields rf = GetRegularFields();

    for (size_t i = 0; (i < MAX_HANDLERS) && g_handlers[i]; ++i)
    {
        g_handlers[i]->Marker(rf, pDomain, id, pName, scope);
    }
}

bool IHandler::RegisterHandler(IHandler* pHandler)
{
    for (size_t i = 0; i < MAX_HANDLERS; ++i)
    {
        if (!g_handlers[i])
        {
            g_handlers[i] = pHandler;
            pHandler->SetCookieIndex(i);
            return true;
        }
    }
    return false;
}

//FIXME: Use one coding style, since itt functions are mapped, there's no problem with that
void task_begin(const __itt_domain *pDomain, __itt_id taskid, __itt_id parentid, __itt_string_handle *pName)
{
    ITT_FUNCTION_STAT();
    SThreadRecord* pThreadRecord = GetThreadRecord();

    CTraceEventFormat::SRegularFields rf = GetRegularFields();
    pThreadRecord->pTask = placement_new(STaskDescriptor)
    {
        pThreadRecord->pTask, //chaining the previous task inside
        rf,
        pDomain, pName,
        taskid, parentid
    };

    for (size_t i = 0; (i < MAX_HANDLERS) && g_handlers[i]; ++i)
    {
        g_handlers[i]->TaskBegin(*pThreadRecord->pTask, false);
    }
}

void task_begin_fn(const __itt_domain *pDomain, __itt_id taskid, __itt_id parentid, void* fn)
{
    ITT_FUNCTION_STAT();

    CTraceEventFormat::SRegularFields rf = GetRegularFields();
    SThreadRecord* pThreadRecord = GetThreadRecord();

    pThreadRecord->pTask = placement_new(STaskDescriptor)
    {
        pThreadRecord->pTask, //chaining the previous task inside
        rf,
        pDomain, nullptr,
        taskid, parentid,
        fn
    };

    for (size_t i = 0; (i < MAX_HANDLERS) && g_handlers[i]; ++i)
    {
        g_handlers[i]->TaskBegin(*pThreadRecord->pTask, false);
    }

}

void task_end(const __itt_domain *pDomain)
{
    ITT_FUNCTION_STAT();

    SThreadRecord* pThreadRecord = GetThreadRecord();
    const char* domain = pDomain->nameA;
    if (!pThreadRecord->pTask)
    {
        VerbosePrint("Uneven begin/end count for domain: %s\n", domain);
        return;
    }

    CTraceEventFormat::SRegularFields rf = GetRegularFields(); //FIXME: get from begin except for time

    for (size_t i = 0; (i < MAX_HANDLERS) && g_handlers[i]; ++i)
    {
        g_handlers[i]->TaskEnd(*pThreadRecord->pTask, rf, false);
    }

    STaskDescriptor* prev = pThreadRecord->pTask->prev;
    placement_free(pThreadRecord->pTask);
    pThreadRecord->pTask = prev;
}

void Counter(const __itt_domain *pDomain, __itt_string_handle *pName, double value, __itt_clock_domain* clock_domain, unsigned long long timestamp)
{
    CTraceEventFormat::SRegularFields rf = GetRegularFields(clock_domain, timestamp);

    for (size_t i = 0; (i < MAX_HANDLERS) && g_handlers[i]; ++i)
    {
        g_handlers[i]->Counter(rf, pDomain, pName, value);
    }
}

void counter_inc_delta_v3(const __itt_domain *pDomain, __itt_string_handle *pName, unsigned long long delta)
{
    ITT_FUNCTION_STAT();
    Counter(pDomain, pName, double(delta));//FIXME: add value tracking!
}

void counter_inc_v3(const __itt_domain *pDomain, __itt_string_handle *pName)
{
    ITT_FUNCTION_STAT();
    counter_inc_delta_v3(pDomain, pName, 1);
}

void counter_inc_delta(__itt_counter id, unsigned long long delta)
{
    ITT_FUNCTION_STAT();
    id->value += delta;
    Counter(id->pDomain, id->pName, id->value);
}

void counter_inc(__itt_counter id)
{
    ITT_FUNCTION_STAT();
    counter_inc_delta(id, 1);
}

__itt_counter ITTAPI UNICODE_AGNOSTIC(counter_create_typed)(const char *name, const char *domain, __itt_metadata_type type)
{
    ITT_FUNCTION_STAT();
    __itt_counter id = new ___itt_counter{ UNICODE_AGNOSTIC(domain_create)(domain), UNICODE_AGNOSTIC(string_handle_create)(name), type}; //just an address in memory to make sure it's process wide unique
    for (size_t i = 0; (i < MAX_HANDLERS) && g_handlers[i]; ++i)
    {
        g_handlers[i]->CreateCounter(id);
    }
    return id;
}

#ifdef _WIN32
__itt_counter counter_create_typedW(const wchar_t *name, const wchar_t *domain, __itt_metadata_type type)
{
    return UNICODE_AGNOSTIC(counter_create_typed)(W2L(name).c_str(), W2L(domain).c_str(), type);
}
#endif

__itt_counter UNICODE_AGNOSTIC(counter_create)(const char *name, const char *domain)
{
    ITT_FUNCTION_STAT();
    return UNICODE_AGNOSTIC(counter_create_typed)(name, domain, __itt_metadata_double);
}

#ifdef _WIN32
__itt_counter counter_createW(const wchar_t *name, const wchar_t *domain)
{
    return UNICODE_AGNOSTIC(counter_create)(W2L(name).c_str(), W2L(domain).c_str());
}
#endif

template<class T>
double Convert(void* ptr)
{
    return double(*reinterpret_cast<T*>(ptr));
}
typedef double(*FConvert)(void* ptr);

FConvert g_MetatypeFormatConverter[] = {
    nullptr,
    Convert<uint64_t>,
    Convert<int64_t>,
    Convert<uint32_t>,
    Convert<int32_t>,
    Convert<uint16_t>,
    Convert<int16_t>,
    Convert<float>,
    Convert<double>,
};

void counter_set_value_ex(__itt_counter id, __itt_clock_domain *clock_domain, unsigned long long timestamp, void *value_ptr)
{
    ITT_FUNCTION_STAT();
    if (id->type == __itt_metadata_unknown)
        return;
    double val = g_MetatypeFormatConverter[id->type](value_ptr);
    Counter(id->pDomain, id->pName, val, clock_domain, timestamp);
}

void counter_set_value(__itt_counter id, void *value_ptr)
{
    ITT_FUNCTION_STAT();
    counter_set_value_ex(id, nullptr, 0, value_ptr);
}

void UNICODE_AGNOSTIC(sync_create)(void *addr, const char *objtype, const char *objname, int attribute)
{
    return; //XXX
    ITT_FUNCTION_STAT();

    std::string name((attribute == __itt_attr_mutex) ? "mutex:" : "barrier:");
    name += objtype;
    name += ":";
    name += objname;
    __itt_string_handle* pName = UNICODE_AGNOSTIC(string_handle_create)(name.c_str());
    __itt_id id = __itt_id_make(addr, 0);

    CTraceEventFormat::SRegularFields rf = GetRegularFields();
    WriteRecord(ERecordType::ObjectNew, SRecord{rf, *GetITTGlobal()->domain_list, id, __itt_null, pName});
}

#ifdef _WIN32
void sync_createW(void *addr, const wchar_t *objtype, const wchar_t *objname, int attribute)
{
    UNICODE_AGNOSTIC(sync_create)(addr, W2L(objtype).c_str(), W2L(objname).c_str(), attribute);
}
#endif

void sync_destroy(void *addr)
{
    return; //XXX
    ITT_FUNCTION_STAT();

    __itt_id id = __itt_id_make(addr, 0);
    CTraceEventFormat::SRegularFields rf = GetRegularFields();
    WriteRecord(ERecordType::ObjectDelete, SRecord{rf, *GetITTGlobal()->domain_list, id, __itt_null});
}

inline void SyncState(void * addr, const char * state)
{
    return; //XXX
    __itt_id id = __itt_id_make(addr, 0);

    CTraceEventFormat::SRegularFields rf = GetRegularFields();
    WriteRecord(ERecordType::ObjectSnapshot, SRecord{rf, *GetITTGlobal()->domain_list, id, __itt_null, nullptr, nullptr, state, strlen(state)});
}

void UNICODE_AGNOSTIC(sync_rename)(void * addr, const char * name)
{
    ITT_FUNCTION_STAT();

    SyncState(addr, (std::string("name=") + name).c_str());
}
#ifdef _WIN32
void sync_renameW(void * addr, const wchar_t * name)
{
    UNICODE_AGNOSTIC(sync_rename)(addr, W2L(name).c_str());
}
#endif

void sync_prepare(void *addr)
{
    ITT_FUNCTION_STAT();

    SyncState(addr, "state=prepare");
}

void sync_cancel(void *addr)
{
    ITT_FUNCTION_STAT();

    SyncState(addr, "state=cancel");
}

void sync_acquired(void *addr)
{
    ITT_FUNCTION_STAT();
    SyncState(addr, "state=acquired");
}

void sync_releasing(void *addr)
{
    ITT_FUNCTION_STAT();
    SyncState(addr, "state=releasing");
}

//region is the same as frame only explicitly named
void region_begin(const __itt_domain *pDomain, __itt_id id, __itt_id parentid, const __itt_string_handle *pName)
{
    ITT_FUNCTION_STAT();

    CTraceEventFormat::SRegularFields rf = GetRegularFields();
    WriteRecord(ERecordType::BeginFrame, SRecord{rf, *pDomain, id, parentid, pName});
}

void region_end(const __itt_domain *pDomain, __itt_id id)
{
    ITT_FUNCTION_STAT();

    CTraceEventFormat::SRegularFields rf = GetRegularFields();
    WriteRecord(ERecordType::EndFrame, SRecord{rf, *pDomain, id, __itt_null});
}

__itt_clock_domain* clock_domain_create(__itt_get_clock_info_fn fn, void* fn_data)
{
    ITT_FUNCTION_STAT();
    CIttLocker lock;
    __itt_domain* pDomain = GetITTGlobal()->domain_list;
    DomainExtra* pDomainExtra = (DomainExtra*)pDomain->extra2;
    __itt_clock_domain** ppClockDomain = &pDomainExtra->pClockDomain;
    while (*ppClockDomain && (*ppClockDomain)->next)
    {
        ppClockDomain = &(*ppClockDomain)->next;
    }

    __itt_clock_info ci = {};
    uint64_t now1 = CTraceEventFormat::GetRegularFields().nanoseconds;
    fn(&ci, fn_data);
    uint64_t now2 = CTraceEventFormat::GetRegularFields().nanoseconds;

    *ppClockDomain = new __itt_clock_domain{
        ci, fn, fn_data, 0,
        new uint64_t((now1 + now2) / 2) //let's keep current time point in extra2
    };

    return *ppClockDomain;
}

void clock_domain_reset()
{
    TraverseDomains([](__itt_domain& domain){
        DomainExtra* pDomainExtra = (DomainExtra*)domain.extra2;
        if (!pDomainExtra) return;
        __itt_clock_domain* pClockDomain = pDomainExtra->pClockDomain;
        while(pClockDomain)
        {
            uint64_t now1 = CTraceEventFormat::GetRegularFields().nanoseconds;
            pClockDomain->fn(&pClockDomain->info, pClockDomain->fn_data);
            uint64_t now2 = CTraceEventFormat::GetRegularFields().nanoseconds;
            *(uint64_t*)pClockDomain->extra2 = (now1 + now2) / 2;
            pClockDomain = pClockDomain->next;
        }
    });
}

void task_begin_ex(const __itt_domain* pDomain, __itt_clock_domain* clock_domain, unsigned long long timestamp, __itt_id taskid, __itt_id parentid, __itt_string_handle* pName)
{
    ITT_FUNCTION_STAT();

    SThreadRecord* pThreadRecord = GetThreadRecord();

    CTraceEventFormat::SRegularFields rf = GetRegularFields(clock_domain, timestamp);

    pThreadRecord->pTask = placement_new(STaskDescriptor)
    {
        pThreadRecord->pTask, //chaining the previous task inside
        rf,
        pDomain, pName,
        taskid, parentid
    };

    for (size_t i = 0; (i < MAX_HANDLERS) && g_handlers[i]; ++i)
    {
        g_handlers[i]->TaskBegin(*pThreadRecord->pTask, false);
    }
}

void task_end_ex(const __itt_domain* pDomain, __itt_clock_domain* clock_domain, unsigned long long timestamp)
{
    ITT_FUNCTION_STAT();

    CTraceEventFormat::SRegularFields rf = GetRegularFields(clock_domain, timestamp);

    SThreadRecord* pThreadRecord = GetThreadRecord();
    if (!pThreadRecord->pTask)
    {
        VerbosePrint("Uneven begin/end count for domain: %s\n", pDomain->nameA);
        return;
    }
    for (size_t i = 0; (i < MAX_HANDLERS) && g_handlers[i]; ++i)
    {
        g_handlers[i]->TaskEnd(*pThreadRecord->pTask, rf, false);
    }
    STaskDescriptor* prev = pThreadRecord->pTask->prev;
    placement_free(pThreadRecord->pTask);
    pThreadRecord->pTask = prev;
}

void id_create(const __itt_domain *pDomain, __itt_id id)
{
    ITT_FUNCTION_STAT();
    //noting to do here yet

}

void id_destroy(const __itt_domain *pDomain, __itt_id id)
{
    ITT_FUNCTION_STAT();
    //noting to do here yet
}

void set_track(__itt_track* track)
{
    ITT_FUNCTION_STAT();
    GetThreadRecord()->pTrack = track;
}

int64_t g_lastPseudoThread = -1;
int64_t g_lastPseudoProcess = -1;


__itt_track_group* track_group_create(__itt_string_handle* pName, __itt_track_group_type track_group_type)
{
    ITT_FUNCTION_STAT();
    CIttLocker lock;
    __itt_domain* pDomain = GetITTGlobal()->domain_list;
    DomainExtra* pDomainExtra = (DomainExtra*)pDomain->extra2;
    __itt_track_group** ppTrackGroup = &pDomainExtra->pTrackGroup;
    while (*ppTrackGroup && (*ppTrackGroup)->next)
    {
        if ((*ppTrackGroup)->name == pName)
            return *ppTrackGroup;
        ppTrackGroup = &(*ppTrackGroup)->next;
    }
    if (pName)
    {
        WriteGroupName(g_lastPseudoProcess, pName->strA);
    }
    //zero name means current process
    return *ppTrackGroup = new __itt_track_group{ pName, nullptr, track_group_type, int(pName ? g_lastPseudoProcess-- : g_PID) };
}

__itt_track* track_create(__itt_track_group* track_group, __itt_string_handle* name, __itt_track_type track_type)
{
    ITT_FUNCTION_STAT();
    CIttLocker locker;

    if (!track_group)
    {
        track_group = track_group_create(nullptr, __itt_track_group_type_normal);
    }

    __itt_track** ppTrack = &track_group->track;
    while (*ppTrack && (*ppTrack)->next)
    {
        if ((*ppTrack)->name == name)
            return *ppTrack;
        ppTrack = &(*ppTrack)->next;
    }

    CTraceEventFormat::SRegularFields* pRF = new CTraceEventFormat::SRegularFields{int64_t(track_group->extra1), g_lastPseudoThread--};

    for (size_t i = 0; (i < MAX_HANDLERS) && g_handlers[i]; ++i)
    {
        g_handlers[i]->SetThreadName(*pRF, name->strA);
    }


    return *ppTrack = new __itt_track{name, track_group, track_type, 0, pRF};
}

class COverlapped //FIXME: use pool for std::map as well
{
public:
    static COverlapped& Get()
    {
        SThreadRecord* pThreadRecord = GetThreadRecord();
        if (pThreadRecord->pOverlapped)
            return *pThreadRecord->pOverlapped;
        return *(pThreadRecord->pOverlapped = new COverlapped);
    }

    void Begin(__itt_id taskid, const CTraceEventFormat::SRegularFields& rf, const __itt_domain* domain, __itt_string_handle* name, __itt_id parentid)
    {
        m_map[taskid].reset(placement_new(STaskDescriptor){
            nullptr, //chaining the previous task inside
            rf,
            domain, name,
            taskid, parentid
        }, placement_free<STaskDescriptor>);

        for (size_t i = 0; (i < MAX_HANDLERS) && g_handlers[i]; ++i)
        {
            g_handlers[i]->TaskBegin(*m_map[taskid], true);
        }
    }

    bool AddArg(const __itt_domain *domain, __itt_id id, __itt_string_handle *key, const char *data, size_t length)
    {
        TTaskMap::iterator it = m_map.find(id);
        if (m_map.end() == it)
            return false;
        for (size_t i = 0; (i < MAX_HANDLERS) && g_handlers[i]; ++i)
        {
            g_handlers[i]->AddArg(*m_map[id], key, data, length);
        }
        return true;
    }

    bool AddArg(const __itt_domain *domain, __itt_id id, __itt_string_handle *key, double value)
    {
        TTaskMap::iterator it = m_map.find(id);
        if (m_map.end() == it)
            return false;
        for (size_t i = 0; (i < MAX_HANDLERS) && g_handlers[i]; ++i)
        {
            g_handlers[i]->AddArg(*m_map[id], key, value);
        }
        return true;
    }

    void End(__itt_id taskid, const CTraceEventFormat::SRegularFields& rf, const __itt_domain* domain)
    {
        TTaskMap::iterator it = m_map.find(taskid);
        if (m_map.end() == it) return;
        for (size_t i = 0; (i < MAX_HANDLERS) && g_handlers[i]; ++i)
        {
            g_handlers[i]->TaskEnd(*m_map[taskid], rf, true);
        }
        m_map.erase(it);
    }

    static void FinishAll() //close the open tasks on exit
    {
        TraverseThreadRecords([](SThreadRecord& record){
            if (record.pOverlapped)
                record.pOverlapped->Finish();
        });
    }

protected:
    void Finish()
    {
        CTraceEventFormat::SRegularFields rf = CTraceEventFormat::GetRegularFields();
        for (const auto& pair: m_map)
        {
            for (size_t i = 0; (i < MAX_HANDLERS) && g_handlers[i]; ++i)
            {
                g_handlers[i]->TaskEnd(*pair.second, rf, true);
            }
        }
        m_map.clear();
    }

    typedef std::map<__itt_id, std::shared_ptr<STaskDescriptor>> TTaskMap;
    TTaskMap m_map;
};

void task_begin_overlapped_ex(const __itt_domain* pDomain, __itt_clock_domain* clock_domain, unsigned long long timestamp, __itt_id taskid, __itt_id parentid, __itt_string_handle* pName)
{
    ITT_FUNCTION_STAT();

    COverlapped::Get().Begin(taskid, GetRegularFields(clock_domain, timestamp), pDomain, pName, parentid);
}

void task_begin_overlapped(const __itt_domain* pDomain, __itt_id taskid, __itt_id parentid, __itt_string_handle* pName)
{
    ITT_FUNCTION_STAT();

    task_begin_overlapped_ex(pDomain, nullptr, 0, taskid, parentid, pName);
}

void task_end_overlapped_ex(const __itt_domain* pDomain, __itt_clock_domain* clock_domain, unsigned long long timestamp, __itt_id taskid)
{
    ITT_FUNCTION_STAT();

    COverlapped::Get().End(taskid, GetRegularFields(clock_domain, timestamp), pDomain);
}

void task_end_overlapped(const __itt_domain *pDomain, __itt_id taskid)
{
    ITT_FUNCTION_STAT();

    task_end_overlapped_ex(pDomain, nullptr, 0, taskid);
}

std::map<__itt_id, __itt_string_handle*> g_namedIds;

void SetIdName(const __itt_id& id, const char *data)
{
    CIttLocker lock;
    g_namedIds[id] = UNICODE_AGNOSTIC(string_handle_create)(data);
}

template<class ... Args>
void MetadataAdd(const __itt_domain *pDomain, __itt_id id, __itt_string_handle *pKey, Args ... args)
{
    CTraceEventFormat::SRegularFields rf = GetRegularFields();

    if (id.d1 || id.d2) //task can have id and not be overlapped, it would be stored in pThreadRecord->pTask then
    {
        SThreadRecord* pThreadRecord = GetThreadRecord();
        if (!COverlapped::Get().AddArg(pDomain, id, pKey, args...) && pThreadRecord->pTask->id == id)
        {
            for (size_t i = 0; (i < MAX_HANDLERS) && g_handlers[i]; ++i)
            {
                g_handlers[i]->AddArg(*pThreadRecord->pTask, pKey, args...);
            }
        }
    }
}

void UNICODE_AGNOSTIC(metadata_str_add)(const __itt_domain *pDomain, __itt_id id, __itt_string_handle *pKey, const char *data, size_t length)
{
    ITT_FUNCTION_STAT();

    if (id == __itt_null) //special codes
    {
        if (0 == strcmp(pKey->strA, "__sea_cut"))
        {
            marker(pDomain, id, pKey, __itt_marker_scope_process);
            SetCutName(data);
            return;
        }
        if (0 == strcmp(pKey->strA, "__sea_set_folder"))
        {
            SetFolder(data);
            return;
        }
        if (0 == strcmp(pKey->strA, "__sea_set_ring"))
        {
            SetRing(1000000000ull * atoi(data));
            return;
        }
        if (0 == strcmp(pKey->strA, "__sea_ftrace_sync"))
        {
#ifdef __linux__
            WriteFTraceTimeSyncMarkers();
#endif
            return;
        }
    }
    if (!length)
        length = data ? strlen(data) : 0;
    if (!pKey)
        SetIdName(id, data);
    else
        MetadataAdd(pDomain, id, pKey, data, length);
}

#ifdef _WIN32
void metadata_str_addW(const __itt_domain *pDomain, __itt_id id, __itt_string_handle *pKey, const wchar_t *data, size_t length)
{
    UNICODE_AGNOSTIC(metadata_str_add)(pDomain, id, pKey, W2L(data).c_str(), length);
}
#endif

void metadata_add(const __itt_domain *pDomain, __itt_id id, __itt_string_handle *pKey, __itt_metadata_type type, size_t count, void *data)
{
    ITT_FUNCTION_STAT();

    if (id.d1 || id.d2)
    {
        if (data)
        {
            if (__itt_metadata_unknown != type)
            {
                double res = g_MetatypeFormatConverter[type](data);
                MetadataAdd(pDomain, id, pKey, res);
            }
            else
            {
                MetadataAdd(pDomain, id, pKey, (const char *)data, count);
            }
        }
    }
    else //it's a counter
    {
        if (__itt_metadata_unknown == type)
            return;
        Counter(pDomain, pKey, g_MetatypeFormatConverter[type](data));
    }
}

const char* api_version(void)
{
    ITT_FUNCTION_STAT();
    return "IntelSEAPI";
}

void frame_begin_v3(const __itt_domain *pDomain, __itt_id *id)
{
    ITT_FUNCTION_STAT();

    CTraceEventFormat::SRegularFields rf = GetRegularFields();
    WriteRecord(ERecordType::BeginFrame, SRecord{rf, *pDomain, id ? *id : __itt_null, __itt_null});
}

void frame_end_v3(const __itt_domain *pDomain, __itt_id *id)
{
    ITT_FUNCTION_STAT();

    CTraceEventFormat::SRegularFields rf = GetRegularFields();
    WriteRecord(ERecordType::EndFrame, SRecord{rf, *pDomain, id ? *id : __itt_null, __itt_null});
}

__itt_frame UNICODE_AGNOSTIC(frame_create)(const char *domain)
{
    ITT_FUNCTION_STAT();
    return new __itt_frame_t{
        UNICODE_AGNOSTIC(domain_create)(domain),
        __itt_id_make(const_cast<char*>(domain), 0)
    };
}

#ifdef _WIN32
__itt_frame frame_createW(const wchar_t* domain)
{
    return UNICODE_AGNOSTIC(frame_create)(W2L(domain).c_str());
}
#endif

void frame_begin(__itt_frame frame)
{
    ITT_FUNCTION_STAT();
    frame_begin_v3(frame->pDomain, &frame->id);
}

void frame_end(__itt_frame frame)
{
    ITT_FUNCTION_STAT();
    frame_end_v3(frame->pDomain, &frame->id);
}

void frame_submit_v3(const __itt_domain *pDomain, __itt_id *pId, __itt_timestamp begin, __itt_timestamp end)
{
    ITT_FUNCTION_STAT();

    CTraceEventFormat::SRegularFields rf = GetRegularFields();
    if (__itt_timestamp_none == end)
        end = rf.nanoseconds;
    const __itt_string_handle *pName = nullptr;
    if (pId)
    {
        if (pId->d3)
        {
            pName = reinterpret_cast<__itt_string_handle *>(pId->d3);
        }
        else
        {
            CIttLocker lock;
            auto it = g_namedIds.find(*pId);
            if (g_namedIds.end() != it)
            {
                pName = it->second;
                pId->d3 = (unsigned long long)pName;
            }
        }
    }
    rf.nanoseconds = begin;
    WriteRecord(ERecordType::BeginFrame, SRecord{ rf, *pDomain, pId ? *pId : __itt_null, __itt_null, pName });
    rf.nanoseconds = end;
    WriteRecord(ERecordType::EndFrame, SRecord{rf, *pDomain, pId ? *pId : __itt_null, __itt_null});
}

__itt_timestamp get_timestamp()
{
    ITT_FUNCTION_STAT();
    return GetRegularFields().nanoseconds;
}

void Pause()
{
    static __itt_global* pGlobal = GetITTGlobal();
    while (pGlobal)
    {
        pGlobal->state = __itt_collection_paused;
        ___itt_domain* pDomain = pGlobal->domain_list;
        while(pDomain)
        {
            pDomain->flags = 0; //this flag is analyzed by static part of ITT to decide where to call dynamic part or not
            pDomain = pDomain->next;
        }
        pGlobal = pGlobal->next;
    }
}

void pause()
{
    ITT_FUNCTION_STAT();
    static __itt_string_handle* pPause = UNICODE_AGNOSTIC(string_handle_create)("PAUSE");
    static __itt_global* pGlobal = GetITTGlobal();
    static __itt_id id = __itt_id_make(pGlobal, 0);
    region_begin(pGlobal->domain_list, id, __itt_null, pPause);
    Pause();
}

void Resume()
{
    static __itt_global* pGlobal = GetITTGlobal();

    while (pGlobal)
    {
        ___itt_domain* pDomain = pGlobal->domain_list;
        while(pDomain)
        {
            pDomain->flags = 1; //this flag is analyzed by static part of ITT to decide where to call dynamic part or not
            pDomain = pDomain->next;
        }
        pGlobal->state = __itt_collection_normal;
        pGlobal = pGlobal->next;
    }
}

void resume()
{
    ITT_FUNCTION_STAT();
    static __itt_global* pGlobal = GetITTGlobal();
    static __itt_id id = __itt_id_make(pGlobal, 0);
    region_end(pGlobal->domain_list, id);
    Resume();
}

using TRelations = __itt_string_handle* [__itt_relation_is_predecessor_to + 1];
//it's not static member of function to avoid racing
TRelations g_relations = {}; //will be filled in InitSEA

void relation_add_ex(const __itt_domain *pDomain, __itt_clock_domain* clock_domain, unsigned long long timestamp, __itt_id head, __itt_relation relation, __itt_id tail)
{
    ITT_FUNCTION_STAT();
    CTraceEventFormat::SRegularFields rf = GetRegularFields(clock_domain, timestamp);
    WriteRecord(ERecordType::Relation, SRecord{rf, *pDomain, head, tail, g_relations[relation]});
}

void relation_add_to_current(const __itt_domain *pDomain, __itt_relation relation, __itt_id tail)
{
    ITT_FUNCTION_STAT();
    relation_add_ex(pDomain, nullptr, 0, __itt_null, relation, tail);
}

void relation_add(const __itt_domain *pDomain, __itt_id head, __itt_relation relation, __itt_id tail)
{
    ITT_FUNCTION_STAT();
    relation_add_ex(pDomain, nullptr, 0, head, relation, tail);
}

void relation_add_to_current_ex(const __itt_domain *pDomain, __itt_clock_domain* clock_domain, unsigned long long timestamp, __itt_relation relation, __itt_id tail)
{
    ITT_FUNCTION_STAT();
    relation_add_ex(pDomain, clock_domain, timestamp, __itt_null, relation, tail);
}

struct SHeapFunction
{
    __itt_domain* pDomain;
    std::string name;
    ___itt_string_handle* pName;
};

__itt_heap_function ITTAPI UNICODE_AGNOSTIC(heap_function_create)(const char* name, const char* domain)
{
    ITT_FUNCTION_STAT();
    std::string counter_name = std::string(name) + ":ALL(bytes)";
    return new SHeapFunction
    {
        UNICODE_AGNOSTIC(domain_create)(domain),
        name,
        UNICODE_AGNOSTIC(string_handle_create)(counter_name.c_str())
    };
}

#ifdef _WIN32
__itt_heap_function ITTAPI heap_function_createW(const wchar_t* name, const wchar_t* domain)
{
    return UNICODE_AGNOSTIC(heap_function_create)(W2L(name).c_str(), W2L(domain).c_str());
}
#endif

class CMemoryTracker
{
protected:
    TCritSec m_cs;
    std::map<const void*, size_t> m_size_map;
    typedef std::pair<__itt_string_handle*, size_t/*count*/> TBlockData;
    std::map<size_t/*block size*/, TBlockData> m_counter_map;
    bool m_bInitialized = false;
public:
    CMemoryTracker()
        : m_bInitialized(true)
    {}
    void Alloc(SHeapFunction* pHeapFunction, const void* addr, size_t size)
    {
        if (!m_bInitialized) return;
        TBlockData block;
        {
            std::lock_guard<TCritSec> lock(m_cs);
            m_size_map[addr] = size;
            auto it = m_counter_map.find(size);
            if (m_counter_map.end() == it)
            {
                std::string name = pHeapFunction->name + std::string(":size<") + std::to_string(size) + ">(count)";
                __itt_string_handle* pName = UNICODE_AGNOSTIC(string_handle_create)(name.c_str());
                it = m_counter_map.insert(m_counter_map.end(), std::make_pair(size, std::make_pair(pName, size_t(1))));
            }
            else
            {
                ++it->second.second;
            }
            block = it->second;
        }
        Counter(pHeapFunction->pDomain, block.first, double(block.second));
    }

    void Free(SHeapFunction* pHeapFunction, const void* addr)
    {
        if (!m_bInitialized) return;
        std::lock_guard<TCritSec> lock(m_cs);
        size_t size = m_size_map[addr];
        m_size_map.erase(addr);
        auto it = m_counter_map.find(size);
        if (m_counter_map.end() == it)
        {
            return; //how come?
        }
        else
        {
            --it->second.second;
        }
        Counter(pHeapFunction->pDomain, it->second.first, double(it->second.second));
    }

    ~CMemoryTracker()
    {
        m_bInitialized = false;
    }
} g_oMemoryTracker;

void heap_allocate_begin(__itt_heap_function h, size_t size, int initialized)
{
    ITT_FUNCTION_STAT();
}

void heap_allocate_end(__itt_heap_function h, void** addr, size_t size, int)
{
    ITT_FUNCTION_STAT();
    g_oMemoryTracker.Alloc(reinterpret_cast<SHeapFunction*>(h), *addr, size);
}

void heap_free_begin(__itt_heap_function h, void* addr)
{
    ITT_FUNCTION_STAT();
    g_oMemoryTracker.Free(reinterpret_cast<SHeapFunction*>(h), addr);
}

void heap_free_end(__itt_heap_function h, void* addr)
{
    ITT_FUNCTION_STAT();
}

#ifdef _WIN32
    #define WIN(something) something
#else
    #define WIN(nothing)
#endif

#define _AW(macro, name) macro(UNICODE_AGNOSTIC(name)) WIN(macro(ITT_JOIN(name,W)))

#define ORIGINAL_FUNCTIONS()\
    ITT_STUB_IMPL_ORIG(UNICODE_AGNOSTIC(domain_create))\
WIN(ITT_STUB_IMPL_ORIG(domain_createW))\
    ITT_STUB_IMPL_ORIG(UNICODE_AGNOSTIC(string_handle_create))\
WIN(ITT_STUB_IMPL_ORIG(string_handle_createW))

#define API_MAP()\
_AW(ITT_STUB_IMPL,thread_set_name)\
    ITT_STUB_IMPL(task_begin)\
    ITT_STUB_IMPL(task_begin_fn)\
    ITT_STUB_IMPL(task_end)\
_AW(ITT_STUB_IMPL,metadata_str_add)\
    ITT_STUB_IMPL(marker)\
    ITT_STUB_IMPL(counter_inc_delta_v3)\
    ITT_STUB_IMPL(counter_inc_v3)\
    ITT_STUB_IMPL(counter_inc_delta)\
    ITT_STUB_IMPL(counter_inc)\
_AW(ITT_STUB_IMPL,counter_create)\
_AW(ITT_STUB_IMPL,counter_create_typed)\
    ITT_STUB_IMPL(counter_set_value)\
    ITT_STUB_IMPL(counter_set_value_ex)\
    ITT_STUB_IMPL(clock_domain_create)\
    ITT_STUB_IMPL(clock_domain_reset)\
    ITT_STUB_IMPL(task_begin_ex)\
    ITT_STUB_IMPL(task_end_ex)\
    ITT_STUB_IMPL(id_create)\
    ITT_STUB_IMPL(set_track)\
    ITT_STUB_IMPL(track_create)\
    ITT_STUB_IMPL(track_group_create)\
    ITT_STUB_IMPL(task_begin_overlapped)\
    ITT_STUB_IMPL(task_begin_overlapped_ex)\
    ITT_STUB_IMPL(task_end_overlapped)\
    ITT_STUB_IMPL(task_end_overlapped_ex)\
    ITT_STUB_IMPL(id_destroy)\
    ITT_STUB_IMPL(api_version)\
    ITT_STUB_IMPL(frame_begin_v3)\
    ITT_STUB_IMPL(frame_end_v3)\
    ITT_STUB_IMPL(frame_submit_v3)\
_AW(ITT_STUB_IMPL,frame_create)\
    ITT_STUB_IMPL(frame_begin)\
    ITT_STUB_IMPL(frame_end)\
    ITT_STUB_IMPL(region_begin)\
    ITT_STUB_IMPL(region_end)\
    ITT_STUB_IMPL(pause)\
    ITT_STUB_IMPL(resume)\
    ITT_STUB_IMPL(get_timestamp)\
    ITT_STUB_IMPL(metadata_add)\
_AW(ITT_STUB_IMPL,sync_create)\
    ITT_STUB_IMPL(sync_destroy)\
    ITT_STUB_IMPL(sync_acquired)\
    ITT_STUB_IMPL(sync_releasing)\
_AW(ITT_STUB_IMPL,sync_rename)\
    ITT_STUB_IMPL(sync_prepare)\
    ITT_STUB_IMPL(sync_cancel)\
    ITT_STUB_IMPL(relation_add_to_current)\
    ITT_STUB_IMPL(relation_add)\
    ITT_STUB_IMPL(relation_add_to_current_ex)\
    ITT_STUB_IMPL(relation_add_ex)\
_AW(ITT_STUB_IMPL,heap_function_create)\
    ITT_STUB_IMPL(heap_allocate_begin)\
    ITT_STUB_IMPL(heap_allocate_end)\
    ITT_STUB_IMPL(heap_free_begin)\
    ITT_STUB_IMPL(heap_free_end)\
    ORIGINAL_FUNCTIONS()\
    ITT_STUB_NO_IMPL(thread_ignore)\
_AW(ITT_STUB_NO_IMPL,thr_name_set)\
    ITT_STUB_NO_IMPL(thr_ignore)\
    ITT_STUB_NO_IMPL(enable_attach)\
    ITT_STUB_NO_IMPL(suppress_push)\
    ITT_STUB_NO_IMPL(suppress_pop)\
    ITT_STUB_NO_IMPL(suppress_mark_range)\
    ITT_STUB_NO_IMPL(suppress_clear_range)\
    ITT_STUB_NO_IMPL(model_site_beginA)\
WIN(ITT_STUB_NO_IMPL(model_site_beginW))\
    ITT_STUB_NO_IMPL(model_site_beginAL)\
    ITT_STUB_NO_IMPL(model_site_end)\
_AW(ITT_STUB_NO_IMPL,model_task_begin)\
    ITT_STUB_NO_IMPL(model_task_end)\
    ITT_STUB_NO_IMPL(model_lock_acquire)\
    ITT_STUB_NO_IMPL(model_lock_release)\
    ITT_STUB_NO_IMPL(model_record_allocation)\
    ITT_STUB_NO_IMPL(model_record_deallocation)\
    ITT_STUB_NO_IMPL(model_induction_uses)\
    ITT_STUB_NO_IMPL(model_reduction_uses)\
    ITT_STUB_NO_IMPL(model_observe_uses)\
    ITT_STUB_NO_IMPL(model_clear_uses)\
    ITT_STUB_NO_IMPL(model_site_begin)\
    ITT_STUB_NO_IMPL(model_site_beginA)\
WIN(ITT_STUB_NO_IMPL(model_site_beginW))\
    ITT_STUB_NO_IMPL(model_site_beginAL)\
    ITT_STUB_NO_IMPL(model_task_begin)\
    ITT_STUB_NO_IMPL(model_task_beginA)\
WIN(ITT_STUB_NO_IMPL(model_task_beginW))\
    ITT_STUB_NO_IMPL(model_task_beginAL)\
    ITT_STUB_NO_IMPL(model_iteration_taskA)\
WIN(ITT_STUB_NO_IMPL(model_iteration_taskW))\
    ITT_STUB_NO_IMPL(model_iteration_taskAL)\
    ITT_STUB_NO_IMPL(model_site_end_2)\
    ITT_STUB_NO_IMPL(model_task_end_2)\
    ITT_STUB_NO_IMPL(model_lock_acquire_2)\
    ITT_STUB_NO_IMPL(model_lock_release_2)\
    ITT_STUB_NO_IMPL(model_aggregate_task)\
    ITT_STUB_NO_IMPL(model_disable_push)\
    ITT_STUB_NO_IMPL(model_disable_pop)\
    ITT_STUB_NO_IMPL(heap_reallocate_begin)\
    ITT_STUB_NO_IMPL(heap_reallocate_end)\
    ITT_STUB_NO_IMPL(heap_internal_access_begin)\
    ITT_STUB_NO_IMPL(heap_internal_access_end)\
    ITT_STUB_NO_IMPL(heap_record_memory_growth_begin)\
    ITT_STUB_NO_IMPL(heap_record_memory_growth_end)\
    ITT_STUB_NO_IMPL(heap_reset_detection)\
    ITT_STUB_NO_IMPL(heap_record)\
    ITT_STUB_NO_IMPL(task_group)\
    ITT_STUB_NO_IMPL(counter_inc_v3)\
_AW(ITT_STUB_NO_IMPL,event_create)\
    ITT_STUB_NO_IMPL(event_start)\
    ITT_STUB_NO_IMPL(event_end)\
_AW(ITT_STUB_NO_IMPL,sync_set_name)\
_AW(ITT_STUB_NO_IMPL,notify_sync_name)\
    ITT_STUB_NO_IMPL(notify_sync_prepare)\
    ITT_STUB_NO_IMPL(notify_sync_cancel)\
    ITT_STUB_NO_IMPL(notify_sync_acquired)\
    ITT_STUB_NO_IMPL(notify_sync_releasing)\
    ITT_STUB_NO_IMPL(memory_read)\
    ITT_STUB_NO_IMPL(memory_write)\
    ITT_STUB_NO_IMPL(memory_update)\
    ITT_STUB_NO_IMPL(state_get)\
    ITT_STUB_NO_IMPL(state_set)\
    ITT_STUB_NO_IMPL(obj_mode_set)\
    ITT_STUB_NO_IMPL(thr_mode_set)\
    ITT_STUB_NO_IMPL(counter_destroy)\
    ITT_STUB_NO_IMPL(counter_inc)\
_AW(ITT_STUB_NO_IMPL,mark_create)\
_AW(ITT_STUB_NO_IMPL,mark)\
    ITT_STUB_NO_IMPL(mark_off)\
_AW(ITT_STUB_NO_IMPL,mark_global)\
    ITT_STUB_NO_IMPL(mark_global_off)\
    ITT_STUB_NO_IMPL(stack_caller_create)\
    ITT_STUB_NO_IMPL(stack_caller_destroy)\
    ITT_STUB_NO_IMPL(stack_callee_enter)\
    ITT_STUB_NO_IMPL(stack_callee_leave)\
    ITT_STUB_NO_IMPL(id_create_ex)\
    ITT_STUB_NO_IMPL(id_destroy_ex)\
    ITT_STUB_NO_IMPL(task_begin_fn_ex)\
    ITT_STUB_NO_IMPL(marker_ex)\
    ITT_STUB_NO_IMPL(metadata_add_with_scope)\
_AW(ITT_STUB_NO_IMPL,metadata_str_add_with_scope)\
_AW(ITT_STUB_NO_IMPL,av_save)

void FillApiList(__itt_api_info* api_list_ptr)
{
#define ITT_STUB_IMPL(fn) if (0 == strcmp("__itt_" ITT_TO_STR(fn), api_list_ptr[i].name)) {*api_list_ptr[i].func_ptr = (void*)sea::fn; continue;}
#define ITT_STUB_IMPL_ORIG(name) ITT_STUB_IMPL(name)
#ifdef _DEBUG //dangerous stub that doesn't return anything (even when expected) but records the function call for statistics sake
    #define ITT_STUB_NO_IMPL(fn) if (0 == strcmp("__itt_" ITT_TO_STR(fn), api_list_ptr[i].name)) {\
        struct local{\
            static void stub(...){CIttFnStat oIttFnStat("NO IMPL:\t" ITT_TO_STR(fn));}\
        };\
        *api_list_ptr[i].func_ptr = (void*)local::stub;\
        continue;\
    }
#else
    #define ITT_STUB_NO_IMPL(fn)
#endif

    for (int i = 0; (api_list_ptr[i].name != NULL) && (*api_list_ptr[i].name != 0); ++i)
    {
        API_MAP(); //continue is called inside when function is found
        VerbosePrint("Not bound: %s\n", api_list_ptr[i].name);
    }
#undef ITT_STUB_IMPL
#undef ITT_STUB_IMPL_ORIG
#undef ITT_STUB_NO_IMPL
}

uint64_t GetFeatureSet()
{
    static std::string env = get_environ_value("INTEL_SEA_FEATURES");
    static std::string save = get_environ_value("INTEL_SEA_SAVE_TO");

    static uint64_t features =
        (std::string::npos != env.find("mfp") ? sfMetricsFrameworkPublisher : 0)
    |
        (std::string::npos != env.find("mfc") ? sfMetricsFrameworkConsumer : 0)
    |
        (save.size() ? sfSEA : 0)
#ifdef __ANDROID__
    |   sfSystrace
#endif
    |   (std::string::npos != env.find("stack") ? sfStack : 0)
    ;
    return features;
}

void TraverseDomains(const std::function<void(___itt_domain&)>& callback)
{
    for (__itt_global* pGlobal = GetITTGlobal(); pGlobal; pGlobal = pGlobal->next)
    {
        for(___itt_domain* pDomain = pGlobal->domain_list; pDomain; pDomain = pDomain->next)
        {
            callback(*pDomain);
        }
    }
}

void TraverseThreadRecords(const std::function<void(SThreadRecord&)>& callback)
{
    TraverseDomains(
        [&](___itt_domain& domain){
            if (DomainExtra* pDomainExtra = reinterpret_cast<DomainExtra*>(domain.extra2))
                for(SThreadRecord* pThreadRecord = pDomainExtra->pThreadRecords; pThreadRecord; pThreadRecord = pThreadRecord->pNext)
                    callback(*pThreadRecord);
        }
    );
}

void SetCutName(const std::string& name)
{
    CIttLocker lock;
    g_spCutName = std::make_shared<std::string>(Escape4Path(name));
    TraverseThreadRecords([](SThreadRecord& record){
        record.nSpeedupCounter = (std::numeric_limits<int>::max)(); //changing number is safer than changing pointer to last recorder
    });
}

//in global scope variables are initialized from main thread
//that's the simplest way to get tid of Main Thread
CTraceEventFormat::SRegularFields g_rfMainThread = CTraceEventFormat::GetRegularFields();

void SetFolder(const std::string& path)
{
    CIttLocker lock;

    std::string new_path = path.size() ? (path + "-" + std::to_string(CTraceEventFormat::GetRegularFields().pid) + "/") : "";

    if (g_savepath == new_path)
        return;

    //To move into a new folder we must make sure next things:
    //1. per thread files are closed and reopened with new folder
    //2. strings are reported to new folder
    //3. domain paths are updated, so that any newly created files would be in right place
    //4. modules are reported to new folder
    //5. write process info to the new trace

    g_savepath = new_path;

    for (__itt_global* pGlobal = GetITTGlobal(); pGlobal; pGlobal = pGlobal->next)
    {
        ReportModule(pGlobal); //4. we move to new folder and need to notify modules there

        for (___itt_domain* pDomain = pGlobal->domain_list; pDomain; pDomain = pDomain->next)
        {
            DomainExtra* pDomainExtra = reinterpret_cast<DomainExtra*>(pDomain->extra2);
            if (pDomainExtra)
            {
                pDomainExtra->strDomainPath = g_savepath.size() ? GetDir(g_savepath, Escape4Path(pDomain->nameA)) : ""; //3.
                pDomainExtra->bHasDomainPath = !pDomainExtra->strDomainPath.empty();
                for (SThreadRecord* pThreadRecord = pDomainExtra->pThreadRecords; pThreadRecord; pThreadRecord = pThreadRecord->pNext)
                {
                    if (g_savepath.size()) //thread safe
                    {
                        pThreadRecord->bRemoveFiles = true; //1. on next attempt to get a file it will recreate all files with new paths
                    }
                    else //not thread safe!!! Caller must make sure no one writes at this time
                    {
                        pThreadRecord->files.clear();
                    }
                }
            }
        }

        if (g_savepath.size())
            for (___itt_string_handle* pString = pGlobal->string_list; pString; pString = pString->next)
                sea::ReportString(const_cast<__itt_string_handle *>(pString)); //2. making string to be reported again - into the new folder
    }

    if (g_savepath.size())
        GetSEARecorder().Init(g_rfMainThread); //5.

    if (g_savepath.size())
        g_features |= sfSEA;
    else
        g_features &=~ sfSEA;
}

void SetRing(uint64_t nanoseconds)
{
    if (g_nRingBuffer == nanoseconds)
        return;
    g_nRingBuffer = nanoseconds;
    TraverseThreadRecords([](SThreadRecord& record){
        record.bRemoveFiles = true;
    });
}

#ifdef __linux__
    bool WriteFTraceTimeSyncMarkers()
    {
        int fd = open("/sys/kernel/debug/tracing/trace_marker", O_WRONLY);
        if (-1 == fd)
        {
            VerbosePrint("Warning: failed to access /sys/kernel/debug/tracing/trace_marker\n");
            return false;
        }
        for (size_t i = 0; i < 5; ++i)
        {
            char buff[100] = {};
            int size = sprintf(buff, "IntelSEAPI_Time_Sync: %llu\n", (long long unsigned int)CTraceEventFormat::GetTimeNS());
            int res = write(fd, buff, (unsigned int)size);
            if (-1 == res) return false;
        }
        close(fd);
        return true;
    }
#endif

void InitSEA()
{
    for (size_t i = 0; (i < MAX_HANDLERS) && g_handlers[i]; ++i)
    {
        g_handlers[i]->Init(g_rfMainThread);
    }
#ifdef __linux__
    WriteFTraceTimeSyncMarkers();
#endif

    const char* relations[] =
    {
        nullptr,
        ("dependent_on"),         /**< "A is dependent on B" means that A cannot start until B completes */
        ("sibling_of"),           /**< "A is sibling of B" means that A and B were created as a group */
        ("parent_of"),            /**< "A is parent of B" means that A created B */
        ("continuation_of"),      /**< "A is continuation of B" means that A assumes the dependencies of B */
        ("child_of"),             /**< "A is child of B" means that A was created by B (inverse of is_parent_of) */
        ("continued_by"),         /**< "A is continued by B" means that B assumes the dependencies of A (inverse of is_continuation_of) */
        ("predecessor_to")        /**< "A is predecessor to B" means that B cannot start until A completes (inverse of is_dependent_on) */
    };

    size_t i = 0;
    for (auto ptr: relations)
        g_relations[i++] = ptr ? UNICODE_AGNOSTIC(string_handle_create)(ptr) : nullptr;
}

void FinitaLaComedia()
{
    COverlapped::FinishAll();

    for (size_t i = 0; (i < MAX_HANDLERS) && g_handlers[i]; ++i)
    {
        delete g_handlers[i];
        g_handlers[i] = nullptr;
    }

    __itt_global* pGlobal = GetITTGlobal();
    if (!pGlobal) return;

    {
        CIttLocker locker;
        if (sea::IsVerboseMode())
        {
            VerbosePrint("Call statistics:\n");
            const auto& map = CIttFnStat::GetStats();
            for (const auto& pair: map)
            {
                VerbosePrint("%d\t%s\n", (int)pair.second, pair.first.c_str());
            }
        }

        TraverseThreadRecords([](SThreadRecord& tr){tr.files.clear();});
    }
#ifdef __linux__
    WriteFTraceTimeSyncMarkers();
#endif

    g_oDomainFilter.Finish();
}

} //namespace sea

extern "C" //plain C interface for languages like python
{
    SEA_EXPORT void* itt_create_domain(const char* str)
    {
        return UNICODE_AGNOSTIC(__itt_domain_create)(str);
    }
    SEA_EXPORT void* itt_create_string(const char* str)
    {
        return UNICODE_AGNOSTIC(__itt_string_handle_create)(str);
    }
    SEA_EXPORT void itt_marker(void* domain, uint64_t id, void* name, int scope, uint64_t timestamp)
    {
        __itt_marker_ex(
            reinterpret_cast<__itt_domain*>(domain),
            nullptr, //zero clock domain means that given time is already a correct timestamp
            timestamp,
            id ? __itt_id_make(domain, id) : __itt_null,
            reinterpret_cast<__itt_string_handle*>(name),
            (__itt_scope)scope
        );
    }
    SEA_EXPORT void itt_task_begin(void* domain, uint64_t id, uint64_t parent, void* name, uint64_t timestamp)
    {
        __itt_task_begin_ex(
            reinterpret_cast<__itt_domain*>(domain),
            nullptr,
            timestamp,
            id ? __itt_id_make(domain, id) : __itt_null,
            parent ? __itt_id_make(domain, parent) : __itt_null,
            reinterpret_cast<__itt_string_handle*>(name)
        );
    }
    SEA_EXPORT void itt_task_end(void* domain, uint64_t timestamp)
    {
        __itt_task_end_ex(
            reinterpret_cast<__itt_domain*>(domain),
            nullptr,
            timestamp
        );
    }

    SEA_EXPORT void* itt_counter_create(void* domain, void* name)
    {
        return __itt_counter_create_typed(
            reinterpret_cast<__itt_string_handle*>(name)->strA,
            reinterpret_cast<__itt_domain*>(domain)->nameA,
            __itt_metadata_double
        );
    }

    SEA_EXPORT void itt_set_counter(void* id, double value, uint64_t timestamp)
    {
        __itt_counter_set_value_ex(reinterpret_cast<__itt_counter>(id), nullptr, timestamp, &value);
    }

    SEA_EXPORT void* itt_create_track(const char* group, const char* track)
    {
        return __itt_track_create(
            __itt_track_group_create(((group) ? __itt_string_handle_create(group) : nullptr), __itt_track_group_type_normal),
            __itt_string_handle_create(track),
            __itt_track_type_normal
        );
    }

    SEA_EXPORT void itt_set_track(void* track)
    {
        __itt_set_track(reinterpret_cast<__itt_track*>(track));
    }

    SEA_EXPORT uint64_t itt_get_timestamp()
    {
        return (uint64_t)__itt_get_timestamp();
    }
};
