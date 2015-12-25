#ifdef _WIN32
    #define _In_
    #define _In_opt_
    #define _Inout_opt_
    #define _Inout_
    #include "..\build_win\64\sea_itt_etw_km.h"
#endif

#define INTEL_ITTNOTIFY_API_PRIVATE
#include "ittnotify.h"


#ifdef _WIN32
    #define UNICODE_AGNOSTIC(name) name##A
#else
    #define UNICODE_AGNOSTIC(name) name
#endif

#ifdef _WIN32

void* malloc(size_t size)
{
    return ExAllocatePoolWithTag(NonPagedPool, size, 'ISEA');
}

void free(void* ptr)
{
    ExFreePoolWithTag(ptr, 'ISEA');
}

#else

#include <linux/slab.h>

void* malloc(size_t size)
{
    return kmalloc(size, GFP_ATOMIC);
}

void free(void* ptr)
{
    kfree(ptr);
}

#endif

char* dupstr(const char* str)
{
    size_t size = 0;
    char* newstr = NULL;
    size_t i = 0;

    if (!str) return NULL;

    size = strlen(str);
    newstr = malloc(size + 1);
    for (; i < size + 1; ++i)
        newstr[i] = str[i];
    return newstr;
}

__itt_string_handle* g_pLastStrHandle = NULL;
__itt_domain *g_pLastDomain = NULL;

void driver_init_itt_notify()
{
#ifdef _WIN32
    if (!Intel_SEA_ITT_ProviderHandle)
        EventRegisterIntel_SEA_ITT_Provider();
#endif
}

void driver_fini_itt_notify()
{
    __itt_string_handle* pLastStrHandle = NULL;
    __itt_domain *pLastDomain = NULL;
#ifdef _WIN32
    if (Intel_SEA_ITT_ProviderHandle)
        EventUnregisterIntel_SEA_ITT_Provider(); //zeroes Intel_SEA_ITT_ProviderHandle
#endif
    while (g_pLastStrHandle)
    {
        free((void*)g_pLastStrHandle->strA);
        pLastStrHandle = g_pLastStrHandle->next;
        free(g_pLastStrHandle);
        g_pLastStrHandle = pLastStrHandle;
    }
    g_pLastStrHandle = NULL;

    while (g_pLastDomain)
    {
        free((void*)g_pLastDomain->nameA);
        pLastDomain = g_pLastDomain->next;
        free(g_pLastDomain);
        g_pLastDomain = pLastDomain;
    }
    g_pLastDomain = NULL;
}


int event_start(__itt_event id)
{
    if (!id)
        driver_init_itt_notify();
    return 0;
}

int event_end(__itt_event id)
{
    if (!id)
        driver_fini_itt_notify();
    return 0;
}

void task_begin(const __itt_domain *pDomain, __itt_id taskid, __itt_id parentid, __itt_string_handle *pName)
{
#ifdef _WIN32
    EventWriteTASK_BEGIN(NULL, pDomain->nameA, taskid.d1, parentid.d1, pName->strA);
#endif
}


void task_end(const __itt_domain *pDomain)
{
#ifdef _WIN32
    EventWriteTASK_END(NULL, pDomain->nameA);
#endif
}

__itt_domain* UNICODE_AGNOSTIC(domain_create)(const char* name)
{
    __itt_domain* pDomain = NULL;
    pDomain = malloc(sizeof(__itt_domain));
    memset(pDomain, 0, sizeof(__itt_domain));
    pDomain->nameA = dupstr(name);
    pDomain->flags = ~0x0;

    pDomain->next = g_pLastDomain;
    g_pLastDomain = pDomain;

    return pDomain;
}

__itt_string_handle* UNICODE_AGNOSTIC(string_handle_create)(const char* name)
{
    __itt_string_handle* pStr = NULL;
    pStr = malloc(sizeof(__itt_string_handle));
    memset(pStr, 0, sizeof(__itt_string_handle));
    pStr->strA = dupstr(name);

    pStr->next = g_pLastStrHandle;
    g_pLastStrHandle = pStr;

    return pStr;
}

void marker(const __itt_domain *pDomain, __itt_id id, __itt_string_handle *pName, __itt_scope theScope)
{
    static const char * scopes []= {
        "unknown",
        "global",
        "track_group",
        "track",
        "task",
        "marker"
    };

#ifdef _WIN32
    EventWriteMARKER(NULL, pDomain->nameA, pName->strA, id.d1, scopes[theScope]);
#endif
}

/*XXX
void free_meta(taskid)
{
}

void task_begin_overlapped(const __itt_domain* domain, __itt_id taskid, __itt_id parentid, __itt_string_handle* name)
{
    free_meta(taskid);
    EventWriteTASK_BEGIN_OVERLAPPED(NULL, domain->nameA, taskid.d1, parentid.d1, name->strA);
}

void UNICODE_AGNOSTIC(metadata_str_add)(const __itt_domain *pDomain, __itt_id id, __itt_string_handle *pKey, const char *data, size_t length)
{
}

void task_end_overlapped(const __itt_domain *domain, __itt_id taskid)
{
    const char* meta = combine_meta(taskid);
    EventWriteTASK_END_OVERLAPPED(NULL, domain->nameA, taskid.d1, meta ? meta : ""); //put arguments in third arg
    free_meta(taskid);
}
*/

#define API_MAP()\
    ITT_STUB_IMPL(UNICODE_AGNOSTIC(domain_create))\
    ITT_STUB_IMPL(UNICODE_AGNOSTIC(string_handle_create))\
    ITT_STUB_IMPL(task_begin)\
    ITT_STUB_IMPL(task_end)\
    ITT_STUB_IMPL(marker)\
    ITT_STUB_IMPL(event_start)\
    ITT_STUB_IMPL(event_end)
/*XXX
    ITT_STUB_IMPL(task_begin_overlapped)\
    ITT_STUB_IMPL(UNICODE_AGNOSTIC(metadata_str_add))\
    ITT_STUB_IMPL(task_end_overlapped)\
*/

#define ITT_STUB_IMPL(name) ITT_JOIN(ITTNOTIFY_NAME(name),_t) ITTNOTIFY_NAME(name) = name;
API_MAP()
#undef ITT_STUB_IMPL
