Hi!

Thank you for visiting Intel® Single Event API (Intel® SEAPI) Open Source page!

Intel® SEAPI is the translator of itt_notify calls into several OS specific and third party formats.
itt_notify is open source cross platform plain C library. Some documentation can be found here: https://software.intel.com/en-us/node/544201
For usage examples please see main.cpp of Intel® SEAPI package

After your code is instrumented with itt, to load up the library follow these steps:
    On Windows and Linux:
        Set environment variable INTEL_LIBITTNOTIFY32/INTEL_LIBITTNOTIFY64 to the full path to the IntelSEAPI[32/64].[dll/so]
    On OSX:
        Set environment variable DYLD_INSERT_LIBRARIES to the full path to the IntelSEAPI.dylib
    On Android:
        Write path to IntelSEAPI.so in one of these two files:
            System wide: /data/local/tmp/com.intel.itt.collector_lib
            Per package: /data/data/<package_name>/com.intel.itt.collector_lib

Bulding:
    All platforms except Android:
        >> python buildall.py -i
        this will produce installer
        on Windows demands Visual Studio 2013 and NSIS (http://nsis.sourceforge.net/) installed
    Android:
        demands ANDROID_NDK to be set in environment to the Android NDK path
        >> python buildall.py -a
        this will produce .so to be put into your application folder manually
        on windows demands Ninja to be in PATH
            
Open Source Intel® SEAPI currently supports these formats:

* Windows Performance Analyzer - Windows (ETW): https://msdn.microsoft.com/en-us/library/windows/hardware/hh448170.aspx
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

* Visual Studio Concurrency Visualizer: https://msdn.microsoft.com/en-us/library/dd537632.aspx
    Cons: Only immediate tasks and markers are supported (currently)
    Pros: correlation with all its metrics
    To enable:
        Make sure you have Concurrency Visualizer extension installed (if not, please go to Tools->Extensions and Updates)
        Generate headers and put them to <Intel® SEAPI source code Project Root>/ConcurrencyVisualizerSDK folder, build Intel® SEAPI
        Set INTEL_LIBITTNOTIFY32/INTEL_LIBITTNOTIFY64 with paths as your Visual Studio project Environment
        Run Concurrency Visualizer from "ANALYZE" menu item of VS

* Systrace - Android: http://developer.android.com/tools/help/systrace.html
    Cons: only immediate tasks and counters are supported (currently).
    Pros: corellation with all system metric systrace can collect on the phone.
    To enable: use systrace from AndroidStudio/Eclipse.

* Json google trace format - All platforms: https://www.chromium.org/developers/how-tos/trace-event-profiling-tool
    Cons: no correlation with Win and OSX system events (yet)
    Pros: any platform; Corellation with ftrace (Android, Linux). Supported: object state tracing, counters, tasks (sync and async) - immediate and with clock domains...
    To enable set environment variable INTEL_SEA_SAVE_TO=<any path>/<trace name>
    Use runtool to transform the SEA directory into json format with next command:
        python <InstalDir>IntelSEAPI\bin\sea_runtool.py -o <target> -f gt -i <source folder>
    Use chrome://tracing/ to view trace <target>.json

* DTrace - for MAC OS X XCode Instruments: https://developer.apple.com/library/watchos/documentation/DeveloperTools/Conceptual/InstrumentsUserGuide/index.html
    Cons: Only immediate tasks are supported (currently), no support of iOS.
    Pros: correlation with everything XCode Instruments can collect
    To enable set DYLD_INSERT_LIBRARIES in Instruments target settings

* QT Creator Profiler - cross platform: http://doc.qt.io/qtcreator/creator-qml-performance-monitor.html
    Cons: Only tasks are supported
    Pros: Butterfly view, file&line navigation
    To enable set environment variable INTEL_SEA_SAVE_TO=<any path>/<trace name>
    Use runtool to transform the SEA directory into json format with next command:
        python <InstalDir>IntelSEAPI\bin\sea_runtool.py -o <target> -f gt -i <source folder>
    In QT Creator open "Analyze->QML Profiler Options->Load QML Trace"

* Trace Compass - cross platform: https://projects.eclipse.org/projects/tools.tracecompass
    Initial implementation, thanks for Adrian Negreanu contribution
    To enable set environment variable INTEL_SEA_SAVE_TO=<any path>/<trace name>
    Use runtool to transform the SEA directory into json format with next command:
        python <InstalDir>IntelSEAPI\bin\sea_runtool.py -o <target> -f btf -i <source folder>
    
Misc:
    You can also use runtool for offline collections (outside IDE).

Contribution is highly appreciated.
    
With respect, Alexander Raud.
email: alexander.a.raud@intel.com