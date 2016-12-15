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
#include "Utils.h"
#include <stdlib.h>
#include <cstdio>
#include <string.h>
#include "jitprofiling.h"

#define INTEL_LIBITTNOTIFY "INTEL_LIBITTNOTIFY"
#define INTEL_JIT_PROFILER "INTEL_JIT_PROFILER"

#ifdef _WIN32
    #define setenv _putenv
    #include <windows.h>
    #include "IntelSEAPI.h"
    #undef API_VERSION
    #include <Dbghelp.h>
    #pragma comment(lib, "dbghelp")
    #include <gdiplus.h>
#else
    #define setenv putenv
    #define _strdup strdup
#endif

#if (INTPTR_MAX == INT32_MAX)
    #define BIT_SUFFIX "32"
#elif INTPTR_MAX == INT64_MAX
    #define BIT_SUFFIX "64"
#else
    #error "Environment not 32 or 64-bit!"
#endif

int GlobalInit()
{
    static const char var_name[] = INTEL_LIBITTNOTIFY BIT_SUFFIX;
    static const char jit_var_name[] = INTEL_JIT_PROFILER BIT_SUFFIX;
    sea::SModuleInfo mdlinfo = sea::Fn2Mdl((void*)GlobalInit);

    VerbosePrint("IntelSEAPI: %s=%s | Loaded from: %s\n", var_name, get_environ_value(var_name).c_str(), mdlinfo.path.c_str());

    std::string value = var_name;
    value += "=";
    value += mdlinfo.path;
    std::string jit_val = jit_var_name;
    jit_val += "=" + mdlinfo.path;

    setenv(_strdup(value.c_str()));
    setenv(_strdup(jit_val.c_str()));
    return 1;
}

int nSetLib = GlobalInit();

void AtExit();

extern "C"
{
    extern __itt_global ITT_JOIN(INTEL_ITTNOTIFY_PREFIX, _ittapi_global);
}

bool g_bInitialized = false;

__itt_global* GetITTGlobal()
{
    return &ITT_JOIN(INTEL_ITTNOTIFY_PREFIX, _ittapi_global);
}

void ChainGlobal(__itt_global* pNew)
{
    __itt_global* pCurrent = GetITTGlobal();
    while (pCurrent->next)
    {
        if (pCurrent->next == pNew) //already chained
            return;
        pCurrent = pCurrent->next;
    }
    pCurrent->next = pNew;
}

void UnchainGlobal(__itt_global* pOld)
{
    __itt_global* pCurrent = GetITTGlobal();
    while (pCurrent->next)
    {
        if (pCurrent->next == pOld)
        {
            pCurrent->next = pOld->next; //removing it from list
            return;
        }
        pCurrent = pCurrent->next;
    }
}



#ifdef _WIN32
    #include <windows.h>

    #define FIX_STR(type, ptr, name)\
        if (!ptr->name##A) {\
            if (ptr->name##W) {\
                size_t len = lstrlenW((const wchar_t*)ptr->name##W);\
                char* dest = (char*)malloc(len + 2);\
                wcstombs_s(&len, dest, len + 1, (const wchar_t*)ptr->name##W, len + 1);\
                const_cast<type*>(ptr)->name##A = dest;\
            } else {\
                const_cast<type*>(ptr)->name##A = _strdup("null");\
            }\
        }

#else
    #define FIX_STR(type, ptr, name)\
        if (!ptr->name##A) {\
            if (ptr->name##W) {\
                size_t len = wcslen((const wchar_t*)ptr->name##W);\
                char* dest = (char*)malloc(len + 2);\
                wcstombs(dest, (const wchar_t*)ptr->name##W, len + 1);\
                const_cast<type*>(ptr)->name##A = dest;\
            } else{\
                const_cast<type*>(ptr)->name##A = _strdup("null");\
            }\
        }
#endif

#define FIX_DOMAIN(ptr) FIX_STR(__itt_domain, ptr, name)
#define FIX_STRING(ptr) FIX_STR(__itt_string_handle, ptr, str)
#define FIX_COUNTER(ptr)\
    FIX_STR(__itt_counter_info_t, ptr, name);\
    FIX_STR(__itt_counter_info_t, ptr, domain);\
    sea::FixCounter(ptr);


void __itt_report_error(__itt_error_code, ...){}


extern "C" {

    SEA_EXPORT void ITTAPI __itt_api_init(__itt_global* pGlob, __itt_group_id id)
    {
        if (!g_bInitialized)
        {
            g_bInitialized = true;

            __itt_global* pGlobal = GetITTGlobal();
            __itt_mutex_init(&pGlobal->mutex);
            pGlobal->mutex_initialized = 1;
            sea::CIttLocker locker;
            __itt_api_init(pGlobal, id);
            pGlobal->api_initialized = 1;
        }
        const char* procname = sea::GetProcessName(true);
        sea::SModuleInfo mdlinfo = sea::Fn2Mdl(pGlob);
        VerbosePrint("IntelSEAPI init is called from process '%s' at module '%s'\n", procname, mdlinfo.path.c_str());
        if (GetITTGlobal() != pGlob)
            ChainGlobal(pGlob);
        sea::FillApiList(pGlob->api_list_ptr);
        for (___itt_domain* pDomain = pGlob->domain_list; pDomain; pDomain = pDomain->next)
        {
            FIX_DOMAIN(pDomain);
            sea::InitDomain(pDomain);
        }
        for (__itt_string_handle* pStr = pGlob->string_list; pStr; pStr = pStr->next)
        {
            FIX_STRING(pStr);
            sea::ReportString(const_cast<__itt_string_handle *>(pStr));
        }
        for (__itt_counter_info_t* pCounter = pGlob->counter_list; pCounter; pCounter = pCounter->next)
        {
            FIX_COUNTER(pCounter);
            VerbosePrint("Fixed counter: %s | %s\n", pCounter->domainA, pCounter->nameA);
        }
        sea::ReportModule(pGlob);
        static bool bInitialized = false;
        if (!bInitialized)
        {
            bInitialized = true;
            sea::InitSEA();
#ifdef _WIN32
            EventRegisterIntelSEAPI();
#endif
            atexit(AtExit);
        }
    }

    SEA_EXPORT void ITTAPI __itt_api_fini(__itt_global* pGlob)
    {
        if (pGlob)
        {
            UnchainGlobal(pGlob);
            return;
        }

        if (!g_bInitialized) return;
        g_bInitialized = false;

        sea::FinitaLaComedia();
#ifdef _WIN32
        EventUnregisterIntelSEAPI();
#endif
    }

}

void AtExit()
{
    __itt_api_fini(nullptr);
}

#ifdef _WIN32

typedef Gdiplus::GpStatus(WINGDIPAPI * FGdipGetImageEncoders)(_In_ UINT numEncoders, _In_ UINT size, _Out_writes_bytes_(size) Gdiplus::ImageCodecInfo *encoders);
typedef Gdiplus::GpStatus(WINGDIPAPI * FGdipGetImageEncodersSize)(_Out_ UINT *numEncoders, _Out_ _Out_range_(>= , (*numEncoders) * sizeof(ImageCodecInfo)) UINT *size);
typedef Gdiplus::Status(WINAPI * FGdiplusStartup)(OUT ULONG_PTR *token, const Gdiplus::GdiplusStartupInput *input, OUT Gdiplus::GdiplusStartupOutput *output);
typedef VOID(WINAPI * FGdiplusShutdown)(ULONG_PTR token);
typedef Gdiplus::Status(WINAPI * FGdiplusStartup)(OUT ULONG_PTR *token, const Gdiplus::GdiplusStartupInput *input, OUT Gdiplus::GdiplusStartupOutput *output);
typedef Gdiplus::GpStatus(WINGDIPAPI* FGdipSaveImageToFile)(Gdiplus::GpImage *image, GDIPCONST WCHAR* filename, GDIPCONST CLSID* clsidEncoder, GDIPCONST Gdiplus::EncoderParameters* encoderParams);
typedef Gdiplus::GpStatus(WINGDIPAPI* FGdipDisposeImage)(Gdiplus::GpImage *image);
typedef Gdiplus::GpStatus(WINGDIPAPI* FGdipCreateBitmapFromHICON)(HICON hicon, Gdiplus::GpBitmap** bitmap);
typedef Gdiplus::GpStatus(WINGDIPAPI* FGdipBitmapSetPixel)(Gdiplus::GpBitmap* bitmap, INT x, INT y, Gdiplus::ARGB color);
typedef Gdiplus::GpStatus(WINGDIPAPI* FGdipBitmapGetPixel)(Gdiplus::GpBitmap* bitmap, INT x, INT y, Gdiplus::ARGB *color);
typedef Gdiplus::GpStatus(WINGDIPAPI* FGdipCreateBitmapFromHBITMAP)(HBITMAP hbm, HPALETTE hpal, Gdiplus::GpBitmap** bitmap);
typedef Gdiplus::GpStatus(WINGDIPAPI* FGdipLoadImageFromFile)(GDIPCONST WCHAR* filename, Gdiplus::GpBitmap** image);
typedef Gdiplus::GpStatus(WINGDIPAPI* FGdipGetImagePixelFormat)(Gdiplus::GpImage *image, Gdiplus::PixelFormat *format);
typedef Gdiplus::GpStatus(WINGDIPAPI* FGdipCreateBitmapFromScan0)(INT width, INT height, INT stride, Gdiplus::PixelFormat format, _In_reads_opt_(_Inexpressible_("height * stride")) BYTE* scan0, _Outptr_ Gdiplus::GpBitmap** bitmap);
typedef Gdiplus::GpStatus(WINGDIPAPI* FGdipGetImageWidth)(Gdiplus::GpImage *image, UINT *width);
typedef Gdiplus::GpStatus(WINGDIPAPI* FGdipGetImageHeight)(Gdiplus::GpImage *image, UINT *height);
typedef Gdiplus::GpStatus(WINGDIPAPI* FGdipGetImageGraphicsContext)(Gdiplus::GpImage *image, Gdiplus::GpGraphics **graphics);
typedef Gdiplus::GpStatus(WINGDIPAPI* FGdipDrawImageRect)(Gdiplus::GpGraphics *graphics, Gdiplus::GpImage *image, Gdiplus::REAL x, Gdiplus::REAL y, Gdiplus::REAL width, Gdiplus::REAL height);
typedef Gdiplus::GpStatus(WINGDIPAPI* FGdipDeleteGraphics)(Gdiplus::GpGraphics *graphics);
typedef Gdiplus::GpStatus(WINGDIPAPI* FGdipGraphicsClear)(Gdiplus::GpGraphics *graphics, Gdiplus::ARGB color);


class GdiPlusFn
{
    HMODULE m_hDll = nullptr;

    GdiPlusFn()
    {
        m_hDll = LoadLibraryA("Gdiplus.dll");
        if (!m_hDll)
            throw std::runtime_error("Module is not found");
        ULONG_PTR gdiplusPtr = 0;
        Gdiplus::GdiplusStartupInput gdiplusStart = {};
        if (Gdiplus::Ok != InternalGet<FGdiplusStartup>("GdiplusStartup")(&gdiplusPtr, &gdiplusStart, NULL))
            throw std::runtime_error("Gdiplus startup failed");
    }

    static GdiPlusFn& GetSingleton()
    {
        static GdiPlusFn caller;
        return caller;
    }

    template<typename T>
    T InternalGet(LPCSTR szName)
    {
        T fn = (T)GetProcAddress(m_hDll, szName);
        if (fn) return fn;
        throw std::runtime_error("Function is not found");
    }

public:

    template<typename T>
    static T Get(LPCSTR szName)
    {
        return GetSingleton().InternalGet<T>(szName);
    }
};

#define gdi_call(name) GdiPlusFn::Get<F##name>(#name)

bool GetEncoderClsid(const WCHAR* format, CLSID* pClsid)
{
    UINT  num = 0;
    UINT  size = 0;

    if (Gdiplus::Ok != gdi_call(GdipGetImageEncodersSize)(&num, &size) || !size)
        return false;

    std::vector<byte> data;
    data.resize(size);
    Gdiplus::ImageCodecInfo* pImageCodecInfo = (Gdiplus::ImageCodecInfo*)data.data();
    if (!pImageCodecInfo)
        return false;

    if (Gdiplus::Ok != gdi_call(GdipGetImageEncoders)(num, size, pImageCodecInfo))
        return false;

    for (UINT i = 0; i < num; ++i)
    {
        if (wcscmp(pImageCodecInfo[i].MimeType, format) == 0)
        {
            *pClsid = pImageCodecInfo[i].Clsid;
            return true;
        }
    }

    return false;
}

Gdiplus::GpBitmap* IconToBitmap(HICON hIcon)
{
    ICONINFO iconInfo;
    if (!GetIconInfo(hIcon, &iconInfo))
        return nullptr;

    Gdiplus::GpBitmap* pBitmap = nullptr;
    if (Gdiplus::Ok != gdi_call(GdipCreateBitmapFromHICON)(hIcon, &pBitmap))
        return nullptr;

    Gdiplus::GpBitmap* pBmpMask = nullptr;
    if (Gdiplus::Ok != gdi_call(GdipCreateBitmapFromHBITMAP)(iconInfo.hbmMask, NULL, &pBmpMask))
        return nullptr;

    FGdipBitmapSetPixel SetPixel = gdi_call(GdipBitmapSetPixel);
    FGdipBitmapGetPixel GetPixel = gdi_call(GdipBitmapGetPixel);

    Gdiplus::ARGB pixel, mask;
    for (UINT y = 0; y < iconInfo.yHotspot * 2; ++y)
    {
        for (UINT x = 0; x < iconInfo.xHotspot * 2; ++x)
        {
            GetPixel(pBitmap, x, y, &pixel);
            GetPixel(pBmpMask, x, y, &mask);
            SetPixel(pBitmap, x, y, pixel | mask);
        }
    }

    gdi_call(GdipDisposeImage)(pBmpMask);

    return pBitmap;
}

Gdiplus::GpBitmap* ResizeBitmap(Gdiplus::GpBitmap* pBmp, uint32_t width, uint32_t height)
{
    UINT o_width = 0;
    if (Gdiplus::Ok != gdi_call(GdipGetImageWidth)(pBmp, &o_width))
        return nullptr;

    UINT o_height = 0;
    if (Gdiplus::Ok != gdi_call(GdipGetImageHeight)(pBmp, &o_height))
        return nullptr;

    INT n_width = width;
    INT n_height = height;
    double ratio = ((double)o_width) / ((double)o_height);
    if (o_width > o_height) // Resize down by width
        n_height = static_cast<UINT>(((double)n_width) / ratio);
    else
        n_width = static_cast<UINT>(n_height * ratio);

    Gdiplus::PixelFormat format;
    if (Gdiplus::Ok != gdi_call(GdipGetImagePixelFormat)(pBmp, &format))
        return nullptr;

    Gdiplus::GpBitmap* pNewBitmap = nullptr;
    if (Gdiplus::Ok != gdi_call(GdipCreateBitmapFromScan0)(n_width, n_height, 0, format, NULL, &pNewBitmap))
        return nullptr;

    Gdiplus::GpGraphics* pGraphics = nullptr;
    if (Gdiplus::Ok != gdi_call(GdipGetImageGraphicsContext)(pNewBitmap, &pGraphics))
    {
        gdi_call(GdipDisposeImage)(pNewBitmap);
        return nullptr;
    }

    if (Gdiplus::Ok != gdi_call(GdipGraphicsClear)(pGraphics, 0xFFFFFFFF))
    {
        gdi_call(GdipDeleteGraphics)(pGraphics);
        gdi_call(GdipDisposeImage)(pNewBitmap);
        return nullptr;
    }

    if (Gdiplus::Ok != gdi_call(GdipDrawImageRect)(pGraphics, pBmp, 0, 0, (Gdiplus::REAL)n_width, (Gdiplus::REAL)n_height))
    {
        gdi_call(GdipDeleteGraphics)(pGraphics);
        gdi_call(GdipDisposeImage)(pNewBitmap);
        return nullptr;
    }

    gdi_call(GdipDeleteGraphics)(pGraphics); //don't care here, image is ready

    return pNewBitmap;
}

bool ConvertToGif(Gdiplus::GpBitmap* pBitmap, LPCWSTR szGifPath)
{
    CLSID clsid = {};
    if (!GetEncoderClsid(L"image/gif", &clsid))
        return false;

    return Gdiplus::Ok == GdiPlusFn::Get<FGdipSaveImageToFile>("GdipSaveImageToFile")(pBitmap, szGifPath, &clsid, nullptr);
}

#endif

extern "C"
{
#ifdef STANDARD_SOURCES
    typedef bool(*receive_t)(uint64_t receiver, uint64_t time, uint16_t count, const stdsrc::uchar_t** names, const stdsrc::uchar_t** values, double progress);
    typedef uint64_t(*get_receiver_t)(const stdsrc::uchar_t* provider, const stdsrc::uchar_t* opcode, const stdsrc::uchar_t* taskName);

    SEA_EXPORT bool parse_standard_source(const char* file, get_receiver_t get_receiver, receive_t receive)
    {
        STDSRC_CHECK_RET(file, false);
        class Receiver : public stdsrc::Receiver
        {
        protected:
            uint64_t m_receiver = 0;
            receive_t m_receive = nullptr;
            stdsrc::Reader& m_reader;

        public:
            Receiver(stdsrc::Reader& reader, uint64_t receiver, receive_t receive)
                : m_receiver(receiver)
                , m_reader(reader)
                , m_receive(receive)
            {
            }

            virtual bool onEvent(uint64_t time, const stdsrc::CVariantTree& props)
            {
                size_t size = props.get_bags().size();
                std::vector<const stdsrc::uchar_t*> names(size), values(size);
                std::vector<stdsrc::ustring> values_temp(size);
                names.reserve(size);
                values.reserve(size);
                size_t i = 0;
                for (const auto& pair : props.get_bags())
                {
                    const stdsrc::CVariantTree& prop = pair.second;
                    const stdsrc::CVariant& name = prop.get_variant(stdsrc::bagname::Name);
                    names[i] = name.is_empty() ? nullptr : name.get<stdsrc::ustring>().c_str();
                    const stdsrc::CVariant& value = prop.get_variant(stdsrc::bagname::Value);
                    values[i] = value.is_empty() ? nullptr : value.as_str(values_temp[i]).c_str();
                    ++i;
                }
                return m_receive(m_receiver, time, (uint16_t)size, size ? &names[0] : nullptr, size ? &values[0] : nullptr, m_reader.getProgress());
            }
        };

        class Reader : public stdsrc::Reader
        {
            get_receiver_t m_get_receiver = nullptr;
            receive_t m_receive = nullptr;
        public:
            Reader(get_receiver_t get_receiver, receive_t receive)
                : m_get_receiver(get_receiver)
                , m_receive(receive)
            {
            }
            virtual stdsrc::Receiver::Ptr getReceiver(
                const stdsrc::ustring& provider, const stdsrc::ustring& opcode, const stdsrc::ustring& taskName,
                stdsrc::CVariantTree& props)
            {
                uint64_t receiver = m_get_receiver(provider.c_str(), opcode.c_str(), taskName.c_str());
                if (!receiver) return nullptr;
                return std::make_shared<Receiver>(*this, receiver, m_receive);
            }
        };
        Reader reader(get_receiver, receive);
        std::string path(file);
#ifdef _WIN32
        if (path.substr(path.size() - 4) == ".etl")
            return stdsrc::readETLFile(reader, file, stdsrc::etuRaw);
#endif
        return false;
    };
#endif

#ifdef _WIN32
    SEA_EXPORT const char* resolve_pointer(const char* szModulePath, uint64_t addr)
    {
        static std::string res;
        res.clear();
        static HANDLE hCurProc = GetCurrentProcess();
        DWORD dwOptions = SymSetOptions((SymGetOptions() | SYMOPT_LOAD_LINES | SYMOPT_UNDNAME | SYMOPT_INCLUDE_32BIT_MODULES | SYMOPT_ALLOW_ABSOLUTE_SYMBOLS) & ~SYMOPT_DEFERRED_LOADS);
        static BOOL bInitialize = SymInitialize(hCurProc, NULL, TRUE);
        if (!bInitialize) return nullptr;
        static std::map<std::string, uint64_t> modules;
        uint64_t module = 0;
        if (modules.count(szModulePath))
        {
            module = modules[szModulePath];
        }
        else
        {
            module = SymLoadModule64(hCurProc, NULL, szModulePath, NULL, 0x800000, 0);
            modules[szModulePath] = module;
        }
        if (!module) return nullptr;
        IMAGEHLP_LINE64 line = { sizeof(IMAGEHLP_LINE64) };
        DWORD dwDisplacement = 0;
        SymGetLineFromAddr64(hCurProc, module + addr, &dwDisplacement, &line);
        if (line.FileName)
        {
            res += std::string(line.FileName) + "(" + std::to_string(line.LineNumber) + ")\n";
        }

        char buff[sizeof(SYMBOL_INFO) + 1024] = {};
        SYMBOL_INFO * symbol = (SYMBOL_INFO*)buff;
        symbol->MaxNameLen = 255;
        symbol->SizeOfStruct = sizeof(SYMBOL_INFO);
        SymFromAddr(hCurProc, module + addr, nullptr, symbol);
        res += symbol->Name;
        return res.c_str();
    }

    SEA_EXPORT bool ExportExeIconAsGif(LPCWSTR szExePath, LPCWSTR szGifPath)
    {
        UINT count = ExtractIconExW(szExePath, -1, nullptr, nullptr, 0);
        for (UINT i = 0; i < count; ++i)
        {
            HICON hIcon = nullptr;
            ExtractIconExW(szExePath, i, nullptr, &hIcon, 1);

            Gdiplus::GpBitmap* pBitmap = IconToBitmap(hIcon);
            if (!pBitmap)
                return false;
            bool res = ConvertToGif(pBitmap, szGifPath);
            GdiPlusFn::Get<FGdipDisposeImage>("GdipDisposeImage")(pBitmap);
            return res;
        }
        return false;
    }

    SEA_EXPORT bool ConvertToGif(LPCWSTR szImagePath, LPCWSTR szGifPath, long width, long height)
    {
        Gdiplus::GpBitmap* pBitmap = nullptr;
        gdi_call(GdipLoadImageFromFile)(szImagePath, &pBitmap);

        if (!pBitmap)
            return false;

        if (width > 0 && height > 0)
        {
            Gdiplus::GpBitmap* pResized = ResizeBitmap(pBitmap, width, height);
            gdi_call(GdipDisposeImage)(pBitmap);
            pBitmap = pResized;
        }

        bool res = ConvertToGif(pBitmap, szGifPath);
        gdi_call(GdipDisposeImage)(pBitmap);
        return res;
    }

    SEA_EXPORT int NotifyEvent(iJIT_JVM_EVENT event_type, void *EventSpecificData)
    {
        iJIT_Method_Load* methodData = (iJIT_Method_Load*)EventSpecificData;

        switch (event_type)
        {
            case iJVM_EVENT_TYPE_METHOD_LOAD_FINISHED:
            {
                sea::WriteJit(&(uint32_t)methodData->method_id, sizeof(uint32_t));
                sea::WriteJit(&methodData->method_load_address, sizeof(void*));
                sea::WriteJit(&(uint32_t)methodData->method_size, sizeof(uint32_t));
                sea::WriteJit(&(uint32_t)methodData->line_number_size, sizeof(uint32_t));
                for (unsigned int i = 0; i < methodData->line_number_size; ++i)
                {
                    const LineNumberInfo& lni = methodData->line_number_table[i];
                    sea::WriteJit(&(uint32_t)lni.Offset, sizeof(uint32_t));
                    sea::WriteJit(&(uint32_t)lni.LineNumber, sizeof(uint32_t));
                }

                const char * strings[] = { methodData->method_name, methodData->class_file_name, methodData->source_file_name };
                for (size_t i = 0; i < sizeof(strings) / sizeof(strings[0]); ++i)
                {
                    const char * str = strings[i] ? strings[i] : "";
                    uint16_t len = (uint16_t)strlen(str);
                    sea::WriteJit(&len, sizeof(len));
                    sea::WriteJit(str, len);
                }
                break;
            }
        default:
            break;
        }


        return 0;


    }

    SEA_EXPORT int Initialize()
    {
        __itt_api_init(GetITTGlobal(), __itt_group_none);
        sea::InitJit();

        return 1;
    }
#endif
}

#if defined(STANDARD_SOURCES) && defined(_DEBUG) && 0

bool receive(uint64_t, uint64_t time, uint16_t count, const stdsrc::uchar_t** names, const stdsrc::uchar_t** values, double progress)
{
    return true;
}

uint64_t get_receiver(const stdsrc::uchar_t* provider, const stdsrc::uchar_t* opcode, const stdsrc::uchar_t* taskName)
{
    return (uint64_t)&receive;
}

void Test()
{
    ConvertToGif(L"d:/AndroidSDK/platform-tools\\..\\platforms\\android-21\\data\\res\\mipmap-xxhdpi\\sym_def_app_icon.png", L"C:\\Users\\aaraud\\AppData\\Local\\Temp\\android.gif", 16, 16);
    return;
    ExportExeIconAsGif(LR"(c:\Program Files\IntelSWTools\GPA_16.3\PlatformAnalyzer\bin64\amplxe-gui.exe)", L"c:/temp/pa.gif");
    parse_standard_source(R"(d:\temp\SteamVR\Merged.etl)", get_receiver, receive);
}

#endif

