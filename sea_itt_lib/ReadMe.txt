Hello!

Thank you for interest for Intel® Single Event API (Intel® SEAPI)!

Intel SEAPI is the translator of itt_notify calls into several OS specific and third party formats.

After your code is instrumented with itt, to load up the library follow these steps:
    On Windows and Linux:
        Set environment variable INTEL_LIBITTNOTIFY32/INTEL_LIBITTNOTIFY64 to the full path to the IntelSEAPI[32/64].[dll/so]
    On OSX:
        Set environment variable DYLD_INSERT_LIBRARIES to the full path to the IntelSEAPI.dylib
    On Android:
        Write path to IntelSEAPI.so in one of these two files:
            System wide: /data/local/tmp/com.intel.itt.collector_lib
            Per package: /data/data/<package_name>/com.intel.itt.collector_lib

Intel SEAPI currently supports these formats:

* ETW - Windows:
    Cons: Only immediate tasks, markers and counters are supported (currently).
    Pros: correlation with all system metrics (more than 6 hundred providers)
    To enable:
        Use wprui.exe from 'Windows Kits\10\Windows Performance Toolkit' (if it's installed just: Win+R wprui).
        Where add this file as collector: <InstalDir>IntelSEAPI\ETW\IntelSEAPI.wprp
        After collection it will propose to open with WPA
        Inside WPA apply IntelSEAPI profile using menu Profiles->Apply->Browse, select <InstalDir>IntelSEAPI\ETW\IntelSEAPI.wpaProfile
    Kernel Mode Driver:
        Currenlty only static linkage is supported
        Include driver/sea_itt_driver.c from IntelSEAPI sources.
        Call __itt_event_start(0) in DriverEntry to init itt, AND __itt_event_end(0) in UnloadDriver to clean up everything.

* Visual Studio Concurrency Analyzer:
    Cons: Only immediate tasks and markers are supported (currently)
    Pros: correlation with all its metrics
    To enable:
        Make sure you have Concurrency Analyzer extension installed (if not, please go to Tools->Extensions and Updates)
        Set INTEL_LIBITTNOTIFY32/INTEL_LIBITTNOTIFY64 with paths as your VS project Environment
        Run Concurrency Analyzer from "ANALYZE" menu item of VS

* Systrace - Android:
    Cons: only immediate tasks and counters are supported (currently).
    Pros: corellation with all system metric systrace can collect on the phone.
    To enable: use systrace from AndroidStudio/Eclipse.

* Json google trace format - All platforms:
    Cons: no correlation with Win and OSX system events (yet)
    Pros: any platform; Corellation with ftrace (Android, Linux). Supported: object state tracing, counters, tasks (sync and async) - immediate and with clock domains...
    To enable set environment variable INTEL_SEA_SAVE_TO=<any path>/<trace name>
    Use runtool to transform the SEA directory into json format with next command:
        python <InstalDir>IntelSEAPI\bin\sea_runtool.py -o <target> -f gt -i <source folder>
    Use chrome://tracing/ to view trace <target>.json

* DTrace - for MAC OSX XCode Instruments:
    Cons: Only immediate tasks are supported (currently), no support of iOS.
    Pros: correlation with everything XCode Instruments can collect
    To enable set DYLD_INSERT_LIBRARIES in Instruments target settings

* MetricsFramework (GrandMesa) - cross platform, for System Analyzer
    Cons: Only counters are supported (due to System Analyzer nature)
    Pros: Every task is presented as two counters: task frequency and task length. Correlation with the rest of MetricsFramework publishers, remote view
    To enable install MetricsFramework from goto.intel.com/GrandMesa, and SystemAnalyzer from https://wiki.ith.intel.com/display/IntelGPA/Download+Latest+Internal+Release
    Connect using gm://127.0.0.1 or gm://<your remote host ip>

* QT Creator Profiler - cross platform
    Cons: Only tasks are supported
    Pros: Butterfly view, file&line navigation
    To enable set environment variable INTEL_SEA_SAVE_TO=<any path>/<trace name>
    Use runtool to transform the SEA directory into json format with next command:
        python <InstalDir>IntelSEAPI\bin\sea_runtool.py -o <target> -f gt -i <source folder>
    In QT Creator open "Analyze->QML Profiler Options->Load QML Trace"

Misc:
    You can also use runtool for offline collections (outside IDE).

With respect, Alexander Raud.
email: alexander.a.raud@intel.com
