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

#pragma once
#include <cstdlib>
#include <vector>

#ifdef _MSC_VER
    #define thread_local __declspec(thread)
#else
    #define thread_local __thread
#endif

template<size_t size>
class CPlacementPool
{
    static CPlacementPool& GetPool()
    {
        static thread_local CPlacementPool* pPool = nullptr;
        if (!pPool)
            pPool = new CPlacementPool;
        return *pPool;
    }

    void* AllocMem()
    {
        if (m_free.size())
        {
            void* ptr = m_free.back();
            m_free.pop_back();
            return ptr;
        }
        return malloc(size);
    }

    void FreeMem(void* ptr)
    {
        m_free.push_back(ptr);
    }

    std::vector<void*> m_free;

public:
    static void* Alloc()
    {
        return GetPool().AllocMem();
    }

    template<class T>
    static void Free(T* ptr)
    {
        if (!ptr) return;
        ptr->~T();
        return GetPool().FreeMem(ptr);
    }
    ~CPlacementPool()
    {
        for (void* ptr : m_free)
        {
            free(ptr);
        }
    }
};

#define placement_new(T) new (CPlacementPool<sizeof(T)>::Alloc()) T
template<class T>
inline void placement_free(T* ptr)
{
    CPlacementPool<sizeof(T)>::Free(ptr);
}


