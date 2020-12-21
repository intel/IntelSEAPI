#ifndef SEA_ITT_NOTIFY_HEADER
#define SEA_ITT_NOTIFY_HEADER

#if defined(SEA_USE_DTRACE) || defined(SEA_USE_DTRACE_IMPL)
#ifdef KERNEL
    #include <libkern/c++/OSString.h>
#else
    #include <cstring>
#endif

void dtSEAHookScope(int type, const char* domain, const char* name) __attribute__ ((noinline));
void dtSEAHookArgInt(const char* name, int value) __attribute__ ((noinline));
void dtSEAHookArgStr(const char* name, const char* value) __attribute__ ((noinline));
void dtSEAHookArgAddr(const char* name, const void* value) __attribute__ ((noinline));

void dtSEAHookArgBlobStart(int size, const char* name) /*never use directly*/ __attribute__ ((noinline));
void dtSEAHookArgBlob1024(const void* ptr) /*never use directly*/ __attribute__ ((noinline));
void dtSEAHookArgBlobEnd() /*never use directly*/ __attribute__ ((noinline));

void dtSEAHookEndScope(const char* domain, const char* name) __attribute__ ((noinline));
void dtSEAHookMarker(const char* domain, const char* name, int scope) __attribute__ ((noinline));
void dtSEAHookCounter(const char* domain, const char* name, double value) __attribute__ ((noinline));

namespace itt_notify {

    class Scope
    {
    public:
        enum Type
        {
            Task,
            Region,
            Log
        };
        
        inline Scope(bool task, const char* domain, const char* name)
            : m_name(name)
            , m_domain(domain)
        {
#ifdef KERNEL
            OSString * pStr = OSString::withCString(name);
            dtSEAHookScope(task ? 0 : 1, pStr->getCStringNoCopy(), pStr->getCStringNoCopy());
            pStr->free();
#else
            dtSEAHookScope(task ? 0 : 1, m_domain, m_name);
#endif
        }

        inline void Arg(const char* name, int val){dtSEAHookArgInt(name, val);}
        inline void Arg(const char* name, const char* val){dtSEAHookArgStr(name, val);}
        inline void Arg(const char* name, void* val){dtSEAHookArgAddr(name, val);}
        inline void ArgBlob(const char* name, const void* val, int size)
        {
            const char* ptr = static_cast<const char*>(val);
#ifdef KERNEL
            OSString * pStr = OSString::withCString(name);
            dtSEAHookArgBlobStart(size, pStr->getCStringNoCopy());
            pStr->free();
#else
            dtSEAHookArgBlobStart(size, name);
#endif
            for (int i = 0; i < (size / 1024); ++i)
            {
                dtSEAHookArgBlob1024(ptr);
                ptr += 1024;
            }
            char buff[1024] = {};
            memcpy(buff, ptr, size % 1024);
            dtSEAHookArgBlob1024(buff);
            dtSEAHookArgBlobEnd();
        }
        ~Scope(){
            dtSEAHookEndScope(m_domain, m_name);
        }
    protected:
        const char* m_name = nullptr;
        const char* m_domain = nullptr;
    };

    #define ITT_DOMAIN(/*const char* */domain)\
        static const char __sea_domain_name[] = domain

    //'group' defines virtual process (null means current process), track defines virtual thread
    #define ITT_SCOPE_TRACK(/*const char* */group, /*const char* */ track)

    #define ITT_COUNTER(/*const char* */name, /*double */value) dtSEAHookCounter(__sea_domain_name, name, value)

    enum MarkerScope
    {
        scope_global,
        scope_process,
        scope_thread,
        scope_task, //means a task that will long until another marker with task scope in this thread occurs
    };

    #define ITT_MARKER(/*const char* */name, /*enum Scope*/scope) dtSEAHookMarker(__sea_domain_name, name, itt_notify::scope)
    #define ITT_ARG(/*const char* */name, /*number or string*/ value) __sea_scope__.Arg(name, value)
    #define ITT_ARG_BLOB(/*const char* */name, ptr, size) __sea_scope__.ArgBlob(name, ptr, size)
    #define ITT_SCOPE(/*bool*/task, /*const char* */name) itt_notify::Scope __sea_scope__(task, __sea_domain_name, name)
    #define ITT_SCOPE_TASK(/*const char* */name) ITT_SCOPE(true, name);// XXX ITT_ARG("__file__", __FILE__); ITT_ARG("__line__", __LINE__)
    #define ITT_SCOPE_REGION(/*const char* */name) ITT_SCOPE(false, name);//XXX ITT_ARG("__file__", __FILE__); ITT_ARG("__line__", __LINE__)
    #define ITT_FUNCTION_TASK() ITT_SCOPE_TASK(__FUNCTION__); //XXX ITT_ARG("__file__", __FILE__); ITT_ARG("__line__", __LINE__)
}

#else

    #include <stdint.h>
    #include <string>
    #include <type_traits>
    #include <thread>
    #include <sstream>

    #define INTEL_ITTNOTIFY_API_PRIVATE
    #include "ittnotify.h"


    template <typename T>
    auto is_streamable_impl(int)
    -> decltype (T{},
        void(), // Handle evil operator ,
        std::declval<std::istringstream &>() >> std::declval<T&>(),
        void(), // Handle evil operator ,
        std::true_type{});

    template <typename T> // fallback, ... has less priority than int
    std::false_type is_streamable_impl(...); // fallback, ... has less priority than int

    template <typename T>
    using is_streamable = decltype(is_streamable_impl<T>(0));


#ifdef __OBJC__
    template<typename T, typename V = bool>
    struct is_objc_class : std::false_type { };

    template<typename T>
    struct is_objc_class<T, typename std::enable_if<std::is_convertible<T, id>::value, bool>::type>: std::true_type { };

    template <class T, class = typename std::enable_if<is_objc_class<T>::value>::type>
    std::ostream& operator<< (std::ostream& stream, T const & t) {
        stream << [[t description] UTF8String];
        return stream;
    }
#endif

    namespace itt_notify {


    template<bool bRegion = true>
    class Task
    {
    protected:
        __itt_id m_id = __itt_null;
        const __itt_domain* m_pDomain;
    public:
        Task(const __itt_domain* pDomain, __itt_string_handle* pName)
            : m_pDomain(pDomain)
        {
            if (!m_pDomain || !m_pDomain->flags) return;
            m_id = __itt_id_make(const_cast<__itt_domain*>(m_pDomain), reinterpret_cast<unsigned long long>(pName));
            if (bRegion)
            {
                __itt_region_begin(m_pDomain, m_id, __itt_null, pName);
            }
            else
            {
                __itt_task_begin(m_pDomain, m_id, __itt_null, pName);
            }
        }

        template<class T>
        typename std::enable_if<std::is_floating_point<T>::value, void>::type AddArg(__itt_string_handle* pName, const T& value)
        {
            if (!m_pDomain || !m_pDomain->flags) return;
            double double_value = value;
            __itt_metadata_add(m_pDomain, m_id, pName, __itt_metadata_double, 1, &double_value);
        }

        void AddArg(__itt_string_handle* pName, int64_t value)
        {
            if (!m_pDomain || !m_pDomain->flags) return;
            __itt_metadata_add(m_pDomain, m_id, pName, __itt_metadata_s64, 1, &value);
        }

        void AddArg(__itt_string_handle* pName, const char* value)
        {
            if (!m_pDomain || !m_pDomain->flags) return;
            __itt_metadata_str_add(m_pDomain, m_id, pName, value, 0);
        }

        void AddArg(__itt_string_handle* pName, void const* const pValue)
        {
            if (!m_pDomain || !m_pDomain->flags) return;
            __itt_metadata_add(m_pDomain, m_id, pName, __itt_metadata_unknown, 1, const_cast<void*>(pValue));
        }

        template<class T>
        void AddArg(__itt_string_handle* pName, const T& val, std::enable_if<is_streamable<T>::value>)
        {
            if (!m_pDomain || !m_pDomain->flags) return;
            std::ostringstream os;
            os << val;
            __itt_metadata_str_add(m_pDomain, m_id, pName, os.str().c_str(), 0);
        }

        void AddArg(__itt_string_handle* pName, ...)
        {
            if (!m_pDomain || !m_pDomain->flags) return;
            va_list vl;
            va_start(vl, pName);
            __itt_metadata_add(m_pDomain, m_id, pName, __itt_metadata_unknown, 1, reinterpret_cast<void*>(vl));
            va_end(vl);
        }

        ~Task()
        {
            if (!m_pDomain || !m_pDomain->flags) return;
            if (bRegion)
            {
                __itt_region_end(m_pDomain, m_id);
            }
            else
            {
                __itt_task_end(m_pDomain);
            }
        }
    };

#ifdef ITT_PROTECT_SCOPE
    #define ITT_TOKEN_PASTE(x, y) x ## y
    #define ITT_TOKEN_PASTE2(x, y) ITT_TOKEN_PASTE(x, y)
    #define ITT_LINE_NAME(name) ITT_TOKEN_PASTE2(name, __LINE__)
#else
    #define ITT_LINE_NAME(name) name
#endif

    #ifdef _WIN32
        #define UNICODE_AGNOSTIC(name) name##A
    #else
        #define UNICODE_AGNOSTIC(name) name
    #endif

    #define ITT_DOMAIN(/*const char* */domain)\
        static const __itt_domain* __itt_domain_name = UNICODE_AGNOSTIC(__itt_domain_create)(domain)

    #if defined(_MSC_VER) && _MSC_VER >= 1900 //since VS 2015 magic statics are supported, TODO: check with other compilers
        #define ITT_MAGIC_STATIC(static_variable)
    #else
    //the 'while' below is to protect code from crash in multi-threaded environment under compiler without magic statics support
        #define ITT_MAGIC_STATIC(static_variable) while(!(static_variable)) std::this_thread::yield();
    #endif

    #define ITT_SCOPE(region, name)\
        static __itt_string_handle* ITT_LINE_NAME(__itt_scope_name) = UNICODE_AGNOSTIC(__itt_string_handle_create)(name);\
        ITT_MAGIC_STATIC(ITT_LINE_NAME(__itt_scope_name));\
        itt_notify::Task<region> ITT_LINE_NAME(__itt_scope_item)(__itt_domain_name, ITT_LINE_NAME(__itt_scope_name))

    #define ITT_SCOPE_TASK(/*const char* */name) ITT_SCOPE(false, name)
    #define ITT_SCOPE_REGION(/*const char* */name) ITT_SCOPE(true, name)

    #define ITT_FUNCTION_TASK() ITT_SCOPE_TASK(__FUNCTION__); ITT_ARG("__file__", __FILE__); ITT_ARG("__line__", __LINE__)

    #define ITT_ARG(/*const char* */name, /*number or string*/ value) {\
        static __itt_string_handle* __itt_arg_name = UNICODE_AGNOSTIC(__itt_string_handle_create)(name);\
        ITT_MAGIC_STATIC(__itt_arg_name);\
        ITT_LINE_NAME(__itt_scope_item).AddArg(__itt_arg_name, value);\
    }

    enum MarkerScope
    {
        scope_global = __itt_scope_global,
        scope_process = __itt_scope_track_group,
        scope_thread =__itt_scope_track,
        scope_task =__itt_scope_task, //means a task that will long until another marker with task scope in this thread occurs
    };

    #define ITT_MARKER(/*const char* */name, /*enum Scope*/scope) {\
        static __itt_string_handle* __itt_marker_name = UNICODE_AGNOSTIC(__itt_string_handle_create)(name);\
        ITT_MAGIC_STATIC(__itt_marker_name);\
        __itt_marker(__itt_domain_name, __itt_null, __itt_marker_name, (__itt_scope)itt_notify::scope);\
    }

    #define ITT_COUNTER(/*const char* */name, /*double */value) { \
        static __itt_string_handle* __itt_counter_name = UNICODE_AGNOSTIC(__itt_string_handle_create)(name);\
        ITT_MAGIC_STATIC(__itt_counter_name);\
        double counter_value = value;\
        __itt_metadata_add(__itt_domain_name, __itt_null, __itt_counter_name, __itt_metadata_double, 1, &counter_value);\
    }

    class ScopeTrack
    {
    public:
        ScopeTrack(__itt_track* track)
        {
            __itt_set_track(track);
        }
        ~ScopeTrack()
        {
            __itt_set_track(nullptr);
        }
    };

    //'group' defines virtual process (null means current process), track defines virtual thread
    #define ITT_SCOPE_TRACK(/*const char* */group, /*const char* */ track)\
        static __itt_track* itt_track_name = __itt_track_create(__itt_track_group_create(((group) ? UNICODE_AGNOSTIC(__itt_string_handle_create)(group) : nullptr), __itt_track_group_type_normal), UNICODE_AGNOSTIC(__itt_string_handle_create)(track), __itt_track_type_normal);\
        ITT_MAGIC_STATIC(itt_track_name);\
        itt_notify::ScopeTrack itt_track(itt_track_name);

    //TODO: objects

    } //namespace itt_notify
#endif

#endif //SEA_ITT_NOTIFY_HEADER


#ifdef SEA_USE_DTRACE_IMPL //must be included only in one cpp file of module
    void dtSEAHookScope(int type, const char* domain, const char* name) {__asm__ __volatile__ ("");}
    void dtSEAHookArgInt(const char* name, int value) {__asm__ __volatile__ ("");}
    void dtSEAHookArgStr(const char* name, const char* value) {__asm__ __volatile__ ("");}
    void dtSEAHookArgAddr(const char* name, const void* value) {__asm__ __volatile__ ("");}
    void dtSEAHookEndScope(const char* domain, const char* name) {__asm__ __volatile__ ("");}
    void dtSEAHookMarker(const char* domain, const char* name, int scope) {__asm__ __volatile__ ("");}
    void dtSEAHookCounter(const char* domain, const char* name, double value) {__asm__ __volatile__ ("");}
    void dtSEAHookArgBlobStart(int size, const char* name) /*never use directly*/  {__asm__ __volatile__ ("");}
    void dtSEAHookArgBlob1024(const void* ptr) /*never use directly*/  {__asm__ __volatile__ ("");}
    void dtSEAHookArgBlobEnd() /*never use directly*/ {__asm__ __volatile__ ("");}

#endif
