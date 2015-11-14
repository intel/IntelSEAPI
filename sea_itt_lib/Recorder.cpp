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
#include <vector>
#include <cstring>
#include <fcntl.h>
#include <sys/types.h>

#ifdef _WIN32
#include <io.h>
#include <direct.h>
#include <windows.h>


#define open crossopen
#define write _write
#define close _close
int crossopen(_In_z_ const char * _Filename, _In_ int _Openflag, int perm)
{
    int fd = 0;
    _sopen_s(&fd, _Filename, _Openflag|_O_BINARY, _SH_DENYWR, perm);
    return fd;
}
//FIXME: support wide char mode
#endif

CRecorder::CRecorder()
    : m_pCurPos(nullptr)
{

}

size_t ChunkSize = 1*1020*1024;

void CRecorder::Init(const std::string& path, uint64_t time, void* pCut)
{
    m_memmap.reset(new CMemMap(path, ChunkSize));
    m_pCurPos = m_memmap->GetPtr();
    m_nWroteTotal = 0;
    m_time = time;
    ++m_counter;
    m_pCut = pCut;
}

size_t CRecorder::CheckCapacity(size_t size)
{
    size_t nWroteBytes = (char*)m_pCurPos - (char*)m_memmap->GetPtr();
    if (nWroteBytes + size > m_memmap->GetSize())
    {
        m_pCurPos = m_memmap->Remap(ChunkSize, m_nWroteTotal);
        if (!m_pCurPos)
            return 0;
    }
    return (std::max<size_t>)(m_nWroteTotal, 1);
}

void* CRecorder::Allocate(size_t size)
{
    //must be called only from one thread
    void * pCurPos = m_pCurPos;
    m_nWroteTotal += size;
    m_pCurPos = (char*)m_pCurPos + size;
    return pCurPos;
}

void CRecorder::Close()
{
    if (m_memmap)
        m_memmap->Resize(m_nWroteTotal);
    m_memmap.reset();
}

CRecorder::~CRecorder()
{
    Close();
}

static_assert(sizeof(__itt_id) == 3*8, "sizeof(__itt_id) must be 3*8");
static_assert(sizeof(CTraceEventFormat::SRegularFields().tid) == 8, "sizeof(tid) must be 8");

enum EFlags
{
    efHasId = 0x1,
    efHasParent = 0x2,
    efHasName = 0x4,
    efHasTid = 0x8,
    efHasData = 0x10,
    efHasDelta = 0x20,
    efHasFunction = 0x40,
};

#pragma pack(push, 1)
//File tree is pid/domain/tid (pid is one per dll instance)
struct STinyRecord
{
    uint64_t timestamp;
    ERecordType ert;
    uint8_t flags; //EFlags
};
#pragma pack(pop)

static_assert(sizeof(STinyRecord) == 10, "SRecord must fit in 10 bytes");

template<class T>
T* WriteToBuff(CRecorder& recorder, const T& value)
{
    T* ptr = (T*)recorder.Allocate(sizeof(T));
    if (ptr)
        *ptr = value;
    return ptr;
}

void WriteRecord(ERecordType type, const SRecord& record)
{
    CHECK_INIT_DOMAIN(&record.domain);
    CRecorder* pFile = sea::GetFile(record);
    if (!pFile) return;

    CRecorder& stream = *pFile;

    if (record.pName)
    {
        CHECK_REPORT_STRING(record.pName);
    }
    const size_t MaxSize = sizeof(STinyRecord) + 2*sizeof(__itt_id) + 3*sizeof(uint64_t) + sizeof(double) + sizeof(void*);
    size_t size = stream.CheckCapacity(MaxSize + record.length);
    if (!size)
        return;

    STinyRecord* pRecord = WriteToBuff(stream, STinyRecord{record.rf.nanoseconds, type});
    if (!pRecord) return;

    if (record.taskid.d1)
    {
        WriteToBuff(stream, record.taskid);
        pRecord->flags |= efHasId;
    }

    if (record.parentid.d1)
    {
        WriteToBuff(stream, record.parentid);
        pRecord->flags |= efHasParent;
    }

    if (record.pName)
    {
        WriteToBuff(stream, (uint64_t)record.pName);
        pRecord->flags |= efHasName;
    }

    if ((long long)record.rf.tid < 0) //only when pseudo tid
    {
        WriteToBuff(stream, record.rf.tid);
        pRecord->flags |= efHasTid;
    }

    if (record.pDelta)
    {
        WriteToBuff(stream, *record.pDelta);
        pRecord->flags |= efHasDelta;
    }

    if (record.pData)
    {
        WriteToBuff(stream, (uint64_t)record.length);

        if (void* ptr = stream.Allocate(record.length))
        {
            memcpy(ptr, record.pData, (unsigned int)record.length);

            pRecord->flags |= efHasData;
        }
    }

    if (record.function)
    {
        WriteToBuff(stream, (uint64_t)record.function);
        pRecord->flags |= efHasFunction;
    }

    if (sea::g_nAutoCut && (size >= sea::g_nAutoCut))
    {
        static size_t autocut = 0;
        sea::SetCutName(std::string("autocut#") + std::to_string(autocut++));
    }
}

CMemMap::CMemMap(const std::string &path, size_t size, size_t offset)
{
#ifdef _WIN32
    m_hFile = CreateFile(path.c_str(), GENERIC_READ|GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, 0, NULL);
    if (INVALID_HANDLE_VALUE == m_hFile)
    {
        m_hFile = NULL;
        throw std::runtime_error("Failed to open file: " + path + " err=" + std::to_string(GetLastError()));
    }
#else
    m_fdin = open(path.c_str(), O_CREAT|O_TRUNC|O_RDWR, sea::FilePermissions);
    if (-1 == m_fdin)
    {
        m_fdin = 0;
        throw std::runtime_error("Failed to open file: " + path + " err=" + std::to_string(errno));
    }
#endif
    Remap(size, offset);
}

void* CMemMap::Remap(size_t size, size_t offset)
{
    Resize(size + offset);
    static const size_t PageSize = GetMemPageSize();
    size_t nRoundOffset = offset / PageSize * PageSize; //align by memory page size
    m_size = size + offset % PageSize;
#ifdef _WIN32
    m_hMapping = CreateFileMapping(m_hFile, NULL, PAGE_READWRITE, 0,0, NULL);
    ULARGE_INTEGER uliOffset = {};
    uliOffset.QuadPart = nRoundOffset;
    m_pView = ::MapViewOfFile(m_hMapping, FILE_MAP_WRITE, uliOffset.HighPart, uliOffset.LowPart, m_size);
#else
    m_pView = mmap(0, m_size, PROT_READ|PROT_WRITE, MAP_SHARED, m_fdin, nRoundOffset);
    if (m_pView == MAP_FAILED)
        throw std::runtime_error("Failed to map file: err=" + std::to_string(errno));

#endif
    return (char*)m_pView + offset % PageSize;
}

void CMemMap::Unmap()
{
#ifdef _WIN32
    if (m_pView)
    {
        UnmapViewOfFile(m_pView);
        m_pView = nullptr;
    }
    if (m_hMapping)
    {
        CloseHandle(m_hMapping);
        m_hMapping = nullptr;
    }
#else
    if (m_pView)
    {
        munmap(m_pView, m_size);
        m_pView = nullptr;
    }
#endif
}

using namespace sea;

class CSEARecorder: public IHandler
{
    void Init(const CTraceEventFormat::SRegularFields& main) override
    {
        //write process name into trace
        __itt_string_handle* pKey = UNICODE_AGNOSTIC(string_handle_create)("__process__");
        const char * name = GetProcessName(true);
        __itt_global* pGlobal = GetITTGlobal();
        if (!pGlobal->domain_list)
        {
            UNICODE_AGNOSTIC(domain_create)("IntelSEAPI");
            assert(pGlobal->domain_list);
        }
        WriteRecord(ERecordType::Metadata, SRecord{main, *pGlobal->domain_list, __itt_null, __itt_null, pKey, nullptr, name, strlen(name)});
    }

    void TaskBegin(STaskDescriptor& oTask, bool bOverlapped) override
    {
        if (bOverlapped)
        {
            WriteRecord(ERecordType::BeginOverlappedTask, SRecord{oTask.rf, *oTask.pDomain, oTask.id, oTask.parent, oTask.pName, nullptr, nullptr, 0, oTask.fn});
        }
        else
        {
            WriteRecord(ERecordType::BeginTask, SRecord{oTask.rf, *oTask.pDomain, oTask.id, oTask.parent, oTask.pName, nullptr, nullptr, 0, oTask.fn});
        }
    }
    void TaskBeginFn(STaskDescriptor& oTask, void* fn) override
    {
        WriteRecord(ERecordType::BeginTask, SRecord{oTask.rf, *oTask.pDomain, oTask.id, oTask.parent, nullptr, nullptr, nullptr, 0, fn});
    }
    void AddArg(STaskDescriptor& oTask, const __itt_string_handle *pKey, const char *data, size_t length) override
    {
        WriteRecord(ERecordType::Metadata, SRecord{oTask.rf, *oTask.pDomain, oTask.id, __itt_null, pKey, nullptr, data, length});
    }

    void AddArg(STaskDescriptor& oTask, const __itt_string_handle *pKey, double value) override
    {
        WriteRecord(ERecordType::Metadata, SRecord{ oTask.rf, *oTask.pDomain, oTask.id, __itt_null, pKey, &value});
    }

    void TaskEnd(STaskDescriptor& oTask, const CTraceEventFormat::SRegularFields& rf, bool bOverlapped) override
    {
        if (bOverlapped)
        {
            WriteRecord(ERecordType::EndOverlappedTask, SRecord{rf, *oTask.pDomain, oTask.id, __itt_null});
        }
        else
        {
            WriteRecord(ERecordType::EndTask, SRecord{rf, *oTask.pDomain, __itt_null, __itt_null});
        }
    }
    void Marker(const CTraceEventFormat::SRegularFields& rf, const __itt_domain *pDomain, __itt_id id, __itt_string_handle *pName, __itt_scope theScope) override
    {
        const char* scope = GetScope(theScope);
        WriteRecord(ERecordType::Marker, SRecord{rf, *pDomain, id, __itt_null, pName, nullptr, scope, strlen(scope)});
    }

    void Counter(const CTraceEventFormat::SRegularFields& rf, const __itt_domain *pDomain, const __itt_string_handle *pName, double value)
    {
        WriteRecord(ERecordType::Counter, SRecord{rf, *pDomain, __itt_null, __itt_null, pName, &value});
    }

    void SetThreadName(const CTraceEventFormat::SRegularFields& rf, const char* name) override
    {
        WriteThreadName(rf.tid, name);
    }

}* g_pSEARecorder = IHandler::Register<CSEARecorder>(true);

IHandler& GetSEARecorder()
{
    return *g_pSEARecorder;
}

namespace sea {

void WriteThreadName(uint64_t tid, const char* name)
{
    if (g_savepath.empty()) return;
    std::string path = g_savepath + "/";
    path += std::to_string(tid) + ".tid";
    int fd = open(path.c_str(), O_WRONLY|O_CREAT|O_EXCL, FilePermissions);
    if (-1 == fd) return; //file already exists, other thread was faster
    write(fd, name, (unsigned int)strlen(name));
    close(fd);
}

void ReportString(__itt_string_handle* pStr)
{
    CIttLocker lock;
    pStr->extra1 = 1;
    if (g_savepath.empty()) return;
    std::string path = g_savepath + "/";
    path += std::to_string((uint64_t)pStr) + ".str";
    int fd = open(path.c_str(), O_WRONLY|O_CREAT|O_EXCL, FilePermissions);
    if (-1 == fd) return; //file already exists, other thread was faster
    write(fd, pStr->strA, (unsigned int)strlen(pStr->strA));
    close(fd);
}

void ReportModule(void* fn)
{
    CIttLocker lock;
    if (g_savepath.empty())
        return;

    TMdlInfo module_info = Fn2Mdl(fn);

    std::string path = GetDir(g_savepath, "") + std::to_string((uint64_t)module_info.first) + ".mdl";
    int fd = open(path.c_str(), O_WRONLY|O_CREAT|O_EXCL, FilePermissions);
    if (-1 == fd) return; //file already exists
    write(fd, module_info.second.c_str(), (unsigned int)module_info.second.size());
    close(fd);
}

} //namespace sea
