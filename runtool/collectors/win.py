import os
import sys
import time
from datetime import datetime, timedelta
import shutil
import tempfile
import platform
import traceback
import subprocess
from sea_runtool import Collector
sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))
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

    @staticmethod
    def detect():
        proc = subprocess.Popen('where wpr', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = proc.communicate()
        if err:
            return None
        wprs = []
        for line in out.split('\n'):
            line = line.strip()
            if line:
                wprs.append(line)
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
                    res.append((wpr, version))
        if not res:
            return None
        return sorted(res, key=lambda(_, ver): ver, reverse=True)[0][0]

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
        self.cancel()
        bin_dir = os.path.abspath(self.args.bindir) if self.args.bindir else os.path.join(os.path.dirname(os.path.realpath(__file__)), '..')
        profile = os.path.normpath(os.path.join(bin_dir, '..', 'ETW', 'IntelSEAPI.wprp'))
        profiles = ['-start %s' % option for option, _ in WPRCollector.get_options() if is_domain_enabled('wpa.' + option)]
        cmd = '"%s" -start "%s" %s %s' % (self.wpr, profile, ' '.join(profiles), ('' if self.args.ring else '-filemode'))
        (out, err) = self.execute(cmd)
        if err:
            return
        self.started = True
        return self

    def cancel(self):
        return self.execute('"%s" -cancel' % self.wpr)

    def stop(self, wait=True):
        if not self.started:
            return []
        (out, err) = self.execute('"%s" -stop "%s"' % (self.wpr, self.file))
        if err:
            return []
        assert(self.file in out)
        tmp = os.path.join(self.args.output, 'tmp.etl')
        sea.prepare_environ(self.args)
        relog_etl(self.file, tmp)
        os.remove(self.file)
        os.rename(tmp, self.file)
        return [self.file]


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
            print err

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
                print err
            relog_etl(os.path.join(started, os.path.basename(file)), file)
            shutil.rmtree(started)
        else:
            cmd = 'start "GPUView merge" /MIN /LOW "%s" "%s" gpuview "%s" "%s"' % (sys.executable, os.path.realpath(__file__), file, started)
            cls.log(cmd)
            subprocess.Popen(cmd, shell=True, stdin=None, stdout=None, stderr=None, creationflags=0x00000008, env=sea.prepare_environ(args))  # DETACHED_PROCESS

    @classmethod
    def launch(cls, args):
        cls.merge(GPUViewCollector.detect(), args[0], args[1], True)


def is_domain_enabled(domain, default=True):
    if 'INTEL_SEA_FILTER' not in os.environ:
        return default
    filter = os.environ['INTEL_SEA_FILTER']
    filter = os.path.expandvars(filter) if sys.platform == 'win32' else os.path.expanduser(filter)
    with open(filter) as file:
        for line in file:
            enabled = not line.startswith('#')
            if domain == line.strip(' #\n\r'):
                return enabled
    return default


class ETWTrace(Collector):
    def __init__(self, args):
        Collector.__init__(self, args)
        wpr = WPRCollector.detect()
        self.xperf = os.path.normpath(os.path.join(os.path.dirname(wpr), 'xperf')) if wpr else None
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

        if 'Windows-8' in platform.platform():
            logman_pf = os.path.join(tempfile.gettempdir(), 'gpa_logman.pf')
            count = 0
            with open(logman_pf, 'w') as file:
                if is_domain_enabled('Microsoft-Windows-DxgKrnl'):
                    file.write('"Microsoft-Windows-DxgKrnl" (Base,GPUScheduler,Profiler,Resource,References)\n')
                    count += 1
                if is_domain_enabled('Microsoft-Windows-Dwm-Core'):
                    file.write('"Microsoft-Windows-Dwm-Core" (DetailedFrameInformation)\n')
                    count += 1
                if is_domain_enabled('Microsoft-Windows-DXGI'):
                    file.write('"Microsoft-Windows-DXGI" (Events)\n')
                    count += 1
            if count:
                cmd = 'logman start GPA_SEA -ct perf -bs 1024 -nb 120 480'
                cmd += ' -pf "%s" -o "%s" %s -ets' % (logman_pf, self.files[0], (('-max %d -f bincirc' % (self.args.ring * 10)) if self.args.ring else ''))
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
            kernel_logger = []  # logman query providers "Windows Kernel Trace"
            complimentary = ''
            if is_domain_enabled('Kernel::ContextSwitches'):
                kernel_logger += ['PROC_THREAD', 'CSWITCH']
            if is_domain_enabled('Kernel::Stacks', False):
                kernel_logger += ['LOADER', 'PROFILE']
                complimentary += ' -stackwalk PROFILE+CSWITCH -SetProfInt 1000000'
            if is_domain_enabled('Kernel::IO'):
                kernel_logger += ['FILE_IO', 'FILE_IO_INIT', 'DISK_IO', 'DISK_IO_INIT', 'FILENAME', 'OPTICAL_IO', 'OPTICAL_IO_INIT']
            if is_domain_enabled('Kernel::Network', False):
                kernel_logger += ['NETWORKTRACE']
            if is_domain_enabled('Kernel::Memory', False):
                kernel_logger += ['VIRT_ALLOC', 'MEMORY', 'MEMINFO', 'VAMAP', 'POOL', 'FOOTPRINT', 'MEMINFO_WS']
            if is_domain_enabled('Kernel::PageFaults', False):
                kernel_logger += ['ALL_FAULTS', 'HARD_FAULTS']
            if kernel_logger:
                cmd = '"%s" -on %s %s -f "%s" -ClockType PerfCounter -BufferSize 1024 -MinBuffers 120 -MaxBuffers 480' % (self.xperf, '+'.join(kernel_logger), complimentary, self.files[-1])
                if self.args.ring:
                    cmd += ' -MaxFile %d -FileMode Circular' % (self.args.ring * 10)  # turning seconds into megabytes...
                (out, err) = self.execute(cmd)
                if err or 'Error:' in out:
                    del self.files[-1]
                    return self
            else:
                del self.files[-1]
        else:
            kernel_logger = []  # logman query providers "Windows Kernel Trace"
            if is_domain_enabled('Kernel::ContextSwitches'):
                kernel_logger += ['process', 'thread', 'cswitch']
            if is_domain_enabled('Kernel::Stacks', False):
                kernel_logger += ['img', 'profile']
            if is_domain_enabled('Kernel::IO'):
                kernel_logger += ['fileio', 'disk']
            if is_domain_enabled('Kernel::Network', False):
                kernel_logger += ['net']
            if is_domain_enabled('Kernel::Memory', False):
                kernel_logger += ['virtalloc']
            if is_domain_enabled('Kernel::PageFaults', False):
                kernel_logger += ['pf', 'hf']
            if kernel_logger:
                cmd = 'logman start "NT Kernel Logger" -p "Windows Kernel Trace" (%s) -ct perf -bs 1024 -nb 120 480' % ','.join(kernel_logger)
                cmd += ' -o "%s" %s -ets' % (self.files[-1], (('-max %d -f bincirc' % (self.args.ring * 5)) if self.args.ring else ''))
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
        if 'Windows-8' in platform.platform():
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
