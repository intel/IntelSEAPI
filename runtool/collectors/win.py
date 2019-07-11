from __future__ import print_function
import os
import sys
import time
from datetime import datetime
import shutil
import tempfile
import platform
import traceback
import subprocess
sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))
from sea_runtool import Collector, is_domain_enabled
import sea

def relog_etl(frm, to):
    sea.ITT('win').relog(frm, to)


class WPRCollector(Collector):
    def __init__(self, args):
        Collector.__init__(self, args)
        self.wpr = self.detect()
        self.started = False
        if self.args.cuts:
            self.file = os.path.join(args.output, "wpa-%s.etl" % (self.args.cuts[0] if self.args.cuts else '0'))
        else:
            self.file = os.path.join(args.output, "wpa.etl")
        if self.wpr:
            self.start()

    @classmethod
    def detect(cls, statics={}):
        if 'res' in statics:
            return statics['res']
        wprs = cls.detect_instances('wpr')
        res = []
        for wpr in wprs:
            proc = subprocess.Popen('"%s" /?' % wpr, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            (out, err) = proc.communicate()
            if err:
                return None
            for line in out.split('\n'):
                pos = line.find('Version')
                if -1 != pos:
                    version = line[pos + len('Version '):].strip()
                    if int(version.split('.')[0]) >= 10:
                        res.append((wpr, version.split()[0]))
                    break
        if not res:
            return None
        statics['res'] = sorted(res, key=lambda __ver: [int(item) for item in __ver[1].split('.')], reverse=True)[0][0]
        return statics['res']

    @staticmethod
    def get_options():
        wpr = WPRCollector.detect()
        if not wpr:
            return
        proc = subprocess.Popen('"%s" -profiles' % wpr, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = proc.communicate()
        if err:
            return
        for line in out.split('\n'):
            if not line.startswith('\t'):
                continue
            parts = line.strip().split()
            yield parts[0], parts[0] in ['DiskIO', 'FileIO', 'GPU', 'GeneralProfile', 'Handle', 'Heap', 'Network', 'Power', 'Video', 'VirtualAllocation']

    def start(self):
        if self.is_recording():
            self.cancel()
        profile = os.path.normpath(os.path.join(self.args.bindir, '..', 'ETW', 'IntelSEAPI.wprp'))
        profiles = ['-start %s' % option for option, _ in WPRCollector.get_options() if is_domain_enabled('wpa.' + option)]
        cmd = '"%s" -start "%s" %s %s' % (self.wpr, profile, ' '.join(profiles), ('' if self.args.ring else '-filemode'))
        (out, err) = self.execute(cmd)
        if err:
            return
        self.started = True
        return self

    def cancel(self):
        return self.execute('"%s" -cancel' % self.wpr)

    @classmethod
    def is_recording(cls, statics={}):
        if not statics:
            statics['wpr'] = cls.detect()
            statics['xperf'] = os.path.normpath(os.path.join(os.path.dirname(statics['wpr']), 'xperf.exe'))
        if os.path.exists(statics['xperf']):
            (out, err) = cls.execute('"%s" -Loggers | find "WPR_"' % statics['xperf'])
            return any('WPR_' in line for line in out.split('\n'))
        else:
            (out, err) = cls.execute('"%s" -status' % statics['wpr'])
            return err or not any('WPR is not recording' in line for line in out.split('\n'))

    def stop(self, wait=True):
        if not self.started:
            return []

        self.log("Stop wait=%s" % str(wait))
        if not wait:
            cmd = 'start "WPR stop" /MIN /LOW "%s" "%s" wpa "%s" "%s"' % (sys.executable, os.path.realpath(__file__), self.file, self.args.output)
            self.log(cmd)
            subprocess.Popen(cmd, shell=True, stdin=None, stdout=None, stderr=None, creationflags=0x00000008, env=sea.prepare_environ(self.args))  # DETACHED_PROCESS
            while self.is_recording():
                self.log("is_recording")
                time.sleep(1)
            return [self.file]
        else:
            sea.prepare_environ(self.args)
            self.stop_wpr(self.wpr, self.file, self.args.output)
            return [self.file]

    @classmethod
    def stop_wpr(cls, wpr, file, output):
        (out, err) = cls.execute('"%s" -stop "%s"' % (wpr, file))
        if err:
            return []
        assert(file in out)
        tmp = os.path.join(output, 'tmp.etl')
        relog_etl(file, tmp)
        os.remove(file)
        os.rename(tmp, file)

    @classmethod
    def launch(cls, args):
        cls.stop_wpr(cls.detect(), args[0], args[1])


class GPUViewCollector(Collector):
    def __init__(self, args):
        Collector.__init__(self, args)
        self.gpuview = self.detect()
        self.started = None
        if self.args.cuts:
            self.file = os.path.join(args.output, "gpuview-%s.etl" % (self.args.cuts[0] if self.args.cuts else '0'))
        else:
            self.file = os.path.join(args.output, "gpuview.etl")
        if self.gpuview:
            self.start()

    @staticmethod
    def detect():
        wpr = WPRCollector.detect()
        if wpr:
            gpuview = os.path.join(os.path.dirname(wpr), 'gpuview', 'log.cmd')
            if os.path.exists(gpuview):
                return gpuview
        return None

    def start(self):
        self.stop(True, False)  # to cut dropped tails
        target_dir = tempfile.mkdtemp()

        # 13863eeb-81b3-4f34-8962-facafb230475 IntelSEAPI
        (out, err) = self.execute('logman start GPA_GPUVIEW -p IntelSEAPI -o "%s" -ets' % os.path.join(target_dir, 'IntelSEAPI.etl'))
        if err:
            return

        self.started = target_dir

        (out, err) = self.execute('"%s"' % self.gpuview, cwd=target_dir)
        if err:
            return

        return self

    def stop(self, wait=True, complete=True):
        if complete and not self.started:
            return []

        (out, err) = self.execute('logman stop GPA_GPUVIEW -ets')
        if err and complete:
            print(err)

        environ = os.environ.copy()
        environ['TLOG'] = 'NORMAL'
        (out, err) = self.execute('"%s"' % self.gpuview, cwd=self.started, env=environ)
        if complete and err and ('Merged.etl' not in err):
            return []

        if not complete:
            return[]

        self.merge(self.gpuview, self.file, self.started, wait, self.args)

        return [self.file]

    @classmethod
    def merge(cls, gpuview, file, started, wait, args=None):
        xperf = os.path.normpath(os.path.join(os.path.dirname(gpuview), '..', 'xperf'))
        if wait:
            cmd = '"%s" -merge Merged.etl IntelSEAPI.etl "%s"' % (xperf, os.path.basename(file))
            (out, err) = Collector.execute(cmd, cwd=started)
            if err and (os.path.basename(file) not in err):
                print(err)
            relog_etl(os.path.join(started, os.path.basename(file)), file)
            shutil.rmtree(started)
        else:
            cmd = 'start "GPUView merge" /MIN /LOW "%s" "%s" gpuview "%s" "%s"' % (sys.executable, os.path.realpath(__file__), file, started)
            cls.log(cmd)
            subprocess.Popen(cmd, shell=True, stdin=None, stdout=None, stderr=None, creationflags=0x00000008, env=sea.prepare_environ(args))  # DETACHED_PROCESS

    @classmethod
    def launch(cls, args):
        cls.merge(GPUViewCollector.detect(), args[0], args[1], True)


def is_older_win7():
    return float(platform.platform().split('-')[1]) > 7


class ETWTrace(Collector):
    def __init__(self, args):
        Collector.__init__(self, args)
        wpr = WPRCollector.detect()
        self.xperf = os.path.normpath(os.path.join(os.path.dirname(wpr), 'xperf')) if wpr else None
        if not self.xperf or not os.path.exists(self.xperf):
            variants = self.detect_instances('xperf')
            if variants:
                self.xperf = variants[0]  # TODO: select by higher version
            else:
                self.xperf = None
        self.files = []
        self.start()

    def start(self):
        self.stop()
        cmd = None

        if self.args.cuts:
            self.files.append('%s\\etw-%s.etl' % (self.args.output, (self.args.cuts[0] if self.args.cuts else '0')))
            self.files.append('%s\\kernel-%s.etl' % (self.args.output, (self.args.cuts[0] if self.args.cuts else '0')))
        else:
            self.files.append('%s\\etw.etl' % self.args.output)
            self.files.append('%s\\kernel.etl' % self.args.output)

        if is_older_win7():
            logman_pf = os.path.join(tempfile.gettempdir(), 'gpa_logman.pf')
            count = 0
            with open(logman_pf, 'w') as file:
                if is_domain_enabled('Microsoft-Windows-DxgKrnl'):
                    file.write('"Microsoft-Windows-DxgKrnl" (Base,GPUScheduler,Profiler,Resource,References,0x4000000000000001)\n')
                    count += 1
                if is_domain_enabled('Microsoft-Windows-Dwm-Core'):
                    file.write('"Microsoft-Windows-Dwm-Core" (DetailedFrameInformation)\n')
                    count += 1
                if is_domain_enabled('Microsoft-Windows-DXGI'):
                    file.write('"Microsoft-Windows-DXGI" (Events)\n')
                    count += 1
                if is_domain_enabled('SteamVR'):
                    file.write('"{8C8F13B1-60EB-4B6A-A433-DE86104115AC}"\n')
                    count += 1
                if is_domain_enabled('OculusVR'):
                    file.write('"{553787FC-D3D7-4F5E-ACB2-1597C7209B3C}"\n')
                    count += 1
            if count:
                cmd = 'logman start GPA_SEA -ct perf -bs 1024 -nb 120 480'
                cmd += ' -pf "%s" -o "%s" %s -ets' % (logman_pf, self.files[0], (('-max %d -f bincirc' % (self.args.ring * 15)) if self.args.ring else ''))
            else:
                del self.files[0]
        else:
            if self.xperf:
                cmd = '"%s" -start GPA_SEA -on DX -f "%s" -ClockType PerfCounter -BufferSize 1024 -MinBuffers 120 -MaxBuffers 480' % (self.xperf, self.files[0])
                if self.args.ring:
                    cmd += ' -MaxFile %d -FileMode Circular' % (self.args.ring * 10)  # turning seconds into megabytes...
        if cmd:
            (out, err) = self.execute(cmd)
            if err:
                return None

        if self.xperf:
            time_multiplier = 0
            kernel_logger = []  # logman query providers "Windows Kernel Trace"
            complimentary = ''
            if is_domain_enabled('Kernel::ContextSwitches'):
                time_multiplier += 10
                kernel_logger += ['PROC_THREAD', 'CSWITCH']
            if is_domain_enabled('Kernel::Stacks', self.args.stacks):
                time_multiplier += 20
                kernel_logger += ['LOADER', 'PROFILE']
                complimentary += ' -stackwalk PROFILE+CSWITCH -SetProfInt 1000000'
            if is_domain_enabled('Kernel::IO'):
                time_multiplier += 5
                kernel_logger += ['FILE_IO', 'FILE_IO_INIT', 'DISK_IO', 'DISK_IO_INIT', 'FILENAME', 'OPTICAL_IO', 'OPTICAL_IO_INIT']
            if is_domain_enabled('Kernel::Network', False):
                time_multiplier += 5
                kernel_logger += ['NETWORKTRACE']
            if is_domain_enabled('Kernel::Memory', False):
                time_multiplier += 5
                kernel_logger += ['VIRT_ALLOC', 'MEMINFO', 'VAMAP', 'POOL', 'MEMINFO_WS']  # 'FOOTPRINT', 'MEMORY'
            if is_domain_enabled('Kernel::PageFaults', False):
                time_multiplier += 5
                kernel_logger += ['ALL_FAULTS', 'HARD_FAULTS']
            if kernel_logger:
                cmd = '"%s" -on %s %s -f "%s" -ClockType PerfCounter -BufferSize 1024 -MinBuffers 120 -MaxBuffers 480' % (self.xperf, '+'.join(kernel_logger), complimentary, self.files[-1])
                if self.args.ring:
                    cmd += ' -MaxFile %d -FileMode Circular' % (self.args.ring * time_multiplier)  # turning seconds into megabytes...
                (out, err) = self.execute(cmd)
                if err or 'Error:' in out:
                    del self.files[-1]
                    return self
            else:
                del self.files[-1]
        else:
            time_multiplier = 0
            kernel_logger = []  # logman query providers "Windows Kernel Trace"
            if is_domain_enabled('Kernel::ContextSwitches'):
                time_multiplier += 10
                kernel_logger += ['process', 'thread', 'cswitch']
            if is_domain_enabled('Kernel::Stacks', self.args.stacks):
                time_multiplier += 10
                kernel_logger += ['img', 'profile']
            if is_domain_enabled('Kernel::IO'):
                time_multiplier += 5
                kernel_logger += ['fileio', 'disk']
            if is_domain_enabled('Kernel::Network', False):
                time_multiplier += 5
                kernel_logger += ['net']
            if is_domain_enabled('Kernel::Memory', False):
                time_multiplier += 5
                kernel_logger += ['virtalloc']
            if is_domain_enabled('Kernel::PageFaults', False):
                time_multiplier += 5
                kernel_logger += ['pf', 'hf']
            if kernel_logger:
                cmd = 'logman start "NT Kernel Logger" -p "Windows Kernel Trace" (%s) -ct perf -bs 1024 -nb 120 480' % ','.join(kernel_logger)
                cmd += ' -o "%s" %s -ets' % (self.files[-1], (('-max %d -f bincirc' % (self.args.ring * time_multiplier)) if self.args.ring else ''))
                (out, err) = self.execute(cmd)
                if err or 'Error:' in out:
                    del self.files[-1]
                    return self
            else:
                del self.files[-1]
        return self

    def stop(self, wait=True):  # TODO: stop without waits
        if self.xperf:
            proc = subprocess.Popen('xperf -stop', shell=True)
            if wait:
                proc.wait()
        else:
            proc = subprocess.Popen('logman stop "NT Kernel Logger" -ets', shell=True)
            if wait:
                proc.wait()
        if is_older_win7():
            proc = subprocess.Popen('logman stop "GPA_SEA" -ets', shell=True)
        else:
            proc = subprocess.Popen('xperf -stop GPA_SEA', shell=True)
        if wait:
            proc.wait()
        return self.files


class ConcurrencyVisualizerCollector(Collector):  # this collector is a dummy placeholder to do nothing while Concurrency Visualizer does its work
    def __init__(self, args):
        Collector.__init__(self, args)
        self.start()

    def start(self):
        self.stop()

    def stop(self, wait=True):
        return []

COLLECTOR_DESCRIPTORS = [
    {
        'available': sys.platform == 'win32' and WPRCollector.detect(),
        'collector': WPRCollector,
        'format': 'wpa'
    },
    {
        'available': sys.platform == 'win32',
        'collector': ETWTrace,
        'format': 'etw'
    },
    {
        'available': sys.platform == 'win32' and GPUViewCollector.detect(),
        'collector': GPUViewCollector,
        'format': 'gpuview'
    },
    {
        'available': sys.platform == 'win32',
        'collector': ConcurrencyVisualizerCollector,
        'format': 'vscv'
    }
]

if __name__ == "__main__":
    with open(os.path.join(tempfile.gettempdir(), datetime.now().strftime('sea_%H_%M_%S__%d_%m_%Y.log')), 'a') as log:
        log.write(str(sys.argv) + '\n')
        try:
            name = sys.argv[1]
            for desc in COLLECTOR_DESCRIPTORS:
                if desc['format'] == name:
                    cls = desc['collector']
                    cls.set_output(log)
                    cls.launch(sys.argv[2:])
                    break
        except:
            log.write(traceback.format_exc())
