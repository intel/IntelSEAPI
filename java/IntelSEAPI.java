/*********************************************************************************************************************************************************************************************************************************************************************************************
#   Intel(R) Single Event API
#
#   This file is provided under a dual BSD 3-Clause license.
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

package com.intel.sea; 

import java.util.*;
import java.io.File;
import java.lang.reflect.*;

public class IntelSEAPI
{
    private static boolean s_bInitialized = false;
    static {
        //Check, this class running on Android or not
        boolean isAndroid;
        try {
            Class.forName("android.app.Activity");
            isAndroid = true;
        }
        catch (ClassNotFoundException e) {
            isAndroid = false;
        }

        String bitness = System.getProperty("os.arch").contains("64") ? "64" : "32";
        if (isAndroid) {
            try {
                String libName = "IntelSEAPI" + bitness;
                System.loadLibrary(libName);

                s_bInitialized = true;
            }
            catch (UnsatisfiedLinkError exc) {
                System.err.println("Load exception: " + exc.getMessage());
            }
        }
        else {
            String envName = "INTEL_LIBITTNOTIFY" + bitness;
            String seaPath = System.getenv(envName);
            if (seaPath != null) {
                File file = new File(seaPath);
                String os = System.getProperty("os.name");
                char sep = (os.startsWith("Windows") ? ';' : ':');

                System.setProperty("java.library.path", System.getProperty("java.library.path") + sep + file.getParent());
                try {
                    Field fieldSysPath = ClassLoader.class.getDeclaredField("sys_paths");
                    fieldSysPath.setAccessible(true);
                    fieldSysPath.set(null, null);
                    String name = file.getName();

                    String subname = name.substring(0, name.lastIndexOf('.'));
                    if (os.startsWith("Mac")) {
                        subname = subname.substring("lib".length());
                    }

                    System.loadLibrary(subname);

                    s_bInitialized = true;
                } catch (Exception exc) {
                    System.err.println("Load exception: " + exc.getMessage());
                }
            }
        }
    }

    private native static long createDomain(String name);
    private native static long createString(String name); //for names
    private native static void beginTask(long domain, long name, long id, long parent, long timestamp);
    private native static void endTask(long domain, long timestamp);
    private native static long counterCreate(long domain, long name);
    private native static void setCounter(long counter, double value, long timestamp);
    private native static void marker(long domain, long id, long name, long scope, long timestamp);
    private native static long createTrack(String group, String track);
    private native static void setTrack(long track);
    private native static long getTimestamp();

    private Map<String, Long> m_strIDMap = new HashMap<String, Long>();
    private long getStringID(String str)
    {
        if (!m_strIDMap.containsKey(str))
            m_strIDMap.put(str, createString(str));
        return m_strIDMap.get(str);
    }

    private long m_domain = 0;

    public IntelSEAPI(String domain)
    {
        if (!s_bInitialized)
            return;
        m_domain = createDomain(domain);
    }

    public enum Scope
    {
        Global,
        Process,
        Thread,
        Task
    };

    public void marker(String text, Scope scope, long timestamp, long id)
    {
        if (!s_bInitialized)
            return;
        marker(m_domain, id, getStringID(text), scope.ordinal() + 1, timestamp);
    }

    public void taskBegin(String name, long id, long parent)
    {
        if (!s_bInitialized)
            return;
        beginTask(m_domain, getStringID(name), id, parent, 0);
    }

    public void taskEnd()
    {
        if (!s_bInitialized)
            return;
        endTask(m_domain, 0);
    }

    public void taskSubmit(String name, long timestamp, long dur, long id, long parent)
    {
        beginTask(m_domain, getStringID(name), id, parent, timestamp);
        endTask(m_domain, timestamp + dur);
    }

    private Map<String, Long> m_counterIDMap = new HashMap<String, Long>();

    public void counter(String name, double value, long timestamp)
    {
        if (!s_bInitialized)
            return;
        if (!m_counterIDMap.containsKey(name))
            m_counterIDMap.put(name, Long.valueOf(counterCreate(m_domain, getStringID(name))));
        setCounter(m_counterIDMap.get(name), value, timestamp);
    }

    private Map<String, Long> m_trackIDMap = new HashMap<String, Long>();

    public void track(String group, String name)
    {
        if (!s_bInitialized)
            return;
        String key = group+ "/" + name;
        if (!m_trackIDMap.containsKey(key))
            m_trackIDMap.put(key, Long.valueOf(createTrack(group, name)));
        setTrack(m_trackIDMap.get(key));
    }

    public void track()
    {
        if (!s_bInitialized)
            return;
        setTrack(0);
    }

    public long getTime()
    {
        if (!s_bInitialized)
            return 0;
        return getTimestamp();
    }
    
    public static void main(String[] args)
    {
        IntelSEAPI itt = new IntelSEAPI("java");
        itt.marker("Begin", Scope.Process, 0, 0);
        long ts1 = itt.getTime();
        
        itt.taskBegin("Main", 0, 0);
        for (double i = 0; i < 100; i += 1.)
        {
            itt.counter("java_counter", i, 0);
        }
        itt.taskEnd();
        
        long ts2 = itt.getTime();
        itt.marker("End", Scope.Process, 0, 0);
        
        itt.track("group", "track");
        long dur = (ts2-ts1) / 100;
        for (long ts = ts1; ts < ts2; ts += dur)
        {
            itt.taskSubmit("submitted", ts, dur / 2, 0, 0);
        }
    }

};
