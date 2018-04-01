import os
import sys
import shutil
import subprocess
sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))
from sea_runtool import Collector, get_decoders

dtrace_context_switch = r"""

/*
off-cpu

Probe that fires when the current CPU is about to end execution of a thread.
The curcpu variable indicates the current CPU.
The curlwpsinfo variable indicates the thread that is ending execution.
The curpsinfo variable describes the process containing the current thread.
The lwpsinfo_t structure of the thread that the current CPU will next execute is pointed to by args[0].
The psinfo_t of the process containing the next thread is pointed to by args[1].
*/

sched:::off-cpu
{
    printf(
        "%x\toff\t%x\t%x\t%x\t%s\t%x\t%x\t%s\n", machtimestamp, curcpu->cpu_id,
        curlwpsinfo->pr_lwpid, curlwpsinfo->pr_pri, curpsinfo->pr_fname,
        args[0]->pr_lwpid, args[0]->pr_pri, args[1]->pr_fname
    );
    /*{OFF_CPU}*/
}

"""

OFF_CPU_STACKS = r"""
    printf("%x\tkstack\t%x\t%x:", machtimestamp, pid, tid);
    stack();
    printf("\n%x\tustack\t%x\t%x:", machtimestamp, pid, tid);
    ustack();
    /*
    printf("\n%x\tjstack\t%x\t%x:", machtimestamp, pid, tid);
    jstack(); //TODO: enable better support for jstack-s
    */
    printf("\n");
"""

osxaskpass = r"""#!/bin/bash
osascript -e 'Tell application "System Events" to display dialog "Password:" default answer "" with hidden answer with title "DTrace requires root priveledges"' -e 'text returned of result' 2>/dev/null
"""


pid_dtrace_hooks = r"""

pid$target:Metal::entry
{
    printf(
        "%x\te\t%x\t%x\tmtl\t%s\n", machtimestamp, pid, tid, probefunc
    );
}

pid$target:Metal::return
{
    printf(
        "%x\tr\t%x\t%x\tmtl\t%s\n", machtimestamp, pid, tid, probefunc
    );
}

pid$target:OpenGL:CGLFlushDrawable:entry
{
    printf(
        "%x\te\t%x\t%x\togl\t%s\n", machtimestamp, pid, tid, probefunc
    );
}

pid$target:OpenGL:CGLFlushDrawable:return
{
    printf(
        "%x\tr\t%x\t%x\togl\t%s\n", machtimestamp, pid, tid, probefunc
    );
}

/* TODO: move under namespace check
pid$target::*dtSEAHookScope*:entry
{
    printf(
        "%x\te\t%x\t%x\t%s:%s\t%s\t%d\n",
        machtimestamp, pid, tid, probemod, copyinstr(arg0), copyinstr(arg1), arg2
    );
    printf("%x\tustack\t%x\t%x:", machtimestamp, pid, tid);
    ustack();
    printf("\n");
}

pid$target::*dtSEAHookEndScope*:entry
{
    printf(
        "%x\tr\t%x\t%x\t%s:%s\t%s\n",
        machtimestamp, pid, tid, probemod, copyinstr(arg0), copyinstr(arg1)
    );
}

pid$target::*dtSEAHookArgStr*:entry
{
    printf(
        "%x\targ\t%x\t%x\t%s\t%s\n",
        machtimestamp, pid, tid, copyinstr(arg0), copyinstr(arg1)
    );
}

pid$target::*dtSEAHookArgInt*:entry
{
    printf(
        "%x\targ\t%x\t%x\t%s\t%d\n",
        machtimestamp, pid, tid, copyinstr(arg0), arg1
    );
}
*/

"""

fbt_dtrace_hooks = r"""
/* TODO: move under namespace check
fbt::*dtSEAHookScope*:entry
{
    printf(
        "%x\te\t%x\t%x\t%s:%s\t%s\t%d\n",
        machtimestamp, pid, tid, stringof(probemod), stringof(arg0), stringof(arg1), arg2
    );
    printf("%x\tkstack\t%x\t%x:", machtimestamp, pid, tid);
    stack();
    printf("\n");
}

fbt::*dtSEAHookEndScope*:entry
{
    printf(
        "%x\tr\t%x\t%x\t%s:%s\t%s\n",
        machtimestamp, pid, tid, stringof(probemod), stringof(arg0), stringof(arg1)
    );
}

fbt::*dtSEAHookArgStr*:entry
{
    printf(
        "%x\targ\t%x\t%x\t%s\t%s\n",
        machtimestamp, pid, tid, stringof(arg0), stringof(arg1)
    );
}

fbt::*dtSEAHookArgInt*:entry
{
    printf(
        "%x\targ\t%x\t%x\t%s\t%d\n",
        machtimestamp, pid, tid, stringof(arg0), arg1
    );
}
*/

"""

HOTSPOTS = r"""
pid$target:::entry
{
    printf(
        "%x\te\t%x\t%x\t%s\t%s\n", machtimestamp, pid, tid, probemod, probefunc
    );
    /*{UMD_STACKS}*/
}

pid$target:::return
{
    printf(
        "%x\tr\t%x\t%x\t%s\t%s\n", machtimestamp, pid, tid, probemod, probefunc
    );
    /*{UMD_STACKS}*/
}
"""

UMD_STACKS = r"""
    printf("%x\tustack\t%x\t%x:", machtimestamp, pid, tid);
    ustack();
    printf("\n");
"""

KMD_STACKS = r"""
    printf("%x\tkstack\t%x\t%x:", machtimestamp, pid, tid);
    stack();
    printf("\n");
"""


class DTraceCollector(Collector):
    class Subcollector:
        @staticmethod
        def get_hooks(args):
            return None

        @staticmethod
        def collect(collector, on):
            pass

    def __init__(self, args):
        Collector.__init__(self, args)

        self.pid = None
        self.files = []
        self.subcollectors = set()

        decoders = get_decoders()
        for decoder_group in decoders.itervalues():
            for decoder_class in decoder_group:
                if any('Subcollector' in str(name) for name in decoder_class.__bases__):
                    self.subcollectors.add(decoder_class)

        if 'SUDO_ASKPASS' not in os.environ:
            os.environ['SUDO_ASKPASS'] = self.create_ask_pass()
        if 'DYLD_INSERT_LIBRARIES' in os.environ:
            del os.environ['DYLD_INSERT_LIBRARIES']
        self.execute('sudo -A pkill dtrace', env=os.environ)
        self.start()

    @staticmethod
    def create_ask_pass():
        path = '/tmp/osxaskpass.sh'
        if os.path.exists(path):
            return path
        with open(path, 'w') as file:
            file.write(osxaskpass)
        os.chmod(path, 0700)
        return path

    def gen_gpu_hooks(self, text):  # TODO: check /System/Library/Extensions/AppleIntelSKLGraphics.kext/Contents/Info.plist
        probes = ''
        driver = None
        for line in text.split('\n'):
            parts = line.split()
            signature = ' '.join(parts[4:-1])
            arity = signature.count(',') + 1
            name = signature.split('(')[0][1:]
            if 'dtHook' in name and parts[-1] == 'entry':
                probe = '%s::%s:entry{' % (parts[1], parts[3])
                probe += r'printf("%x\t' + name + r'\t%x\t%x'
                probe += r'\t%x' * arity
                probe += r'\n", machtimestamp, pid, tid, '
                probe += ', '.join(['arg'+str(i) for i in range(0, arity)])
                stack = '' if not self.args.debug else r'printf("%x\tkstack\t%x\t%x:", machtimestamp, pid, tid); stack(); printf("\n%x\tustack\t%x\t%x:", machtimestamp, pid, tid); ustack(); printf("\n");'
                probe += '); %s}\n' % stack
                probes += probe
                if not driver:
                    driver = parts[2]
                    DTraceCollector.check_graphics_firmware(driver)
            if 'process_token_' in name:
                probe = '%s::%s:%s{' % (parts[1], parts[3], parts[-1])
                probe += r'printf("%x\t' + parts[-1][0] + r'\t%x\t%x\tigfx\t' + name.replace('process_token_', '')
                probe += r'\n", machtimestamp, pid, tid'
                probe += ');}\n'
                probes += probe
        return probes

    @staticmethod
    def check_graphics_firmware(driver):
        driver = driver.split('.')[-1]
        if 'SKL' not in driver and 'BDW' not in driver:
            return
        import xml.dom.minidom as minidom
        file_name = '/System/Library/Extensions/%s.kext/Contents/Info.plist' % driver
        if not os.path.exists(file_name):
            return
        dom = minidom.parse(file_name)

        def find_by_content(el, content):
            if el.nodeValue == content:
                return el
            for child in el.childNodes:
                found = find_by_content(child, content)
                if found:
                    return found
            return None

        el = find_by_content(dom.documentElement, 'GraphicsFirmwareSelect')
        if el:
            value = None
            sibling = el.parentNode.nextSibling
            while sibling:
                if sibling.nodeName == 'integer':
                    value = sibling.childNodes[0].nodeValue
                    break
                else:
                    sibling = sibling.nextSibling
            if value != '0':
                print "Warning: To enable Graphics profiling, set GraphicsFirmwareSelect to 0 in: %s\n\tThen: sudo kextcache -i / & reboot" % file_name

    @staticmethod
    def gen_options(options):
        return '\n'.join('#pragma D option %s=%s' % (key, str(value)) for key, value in options) + '\n'

    def start(self):
        # spawn dtrace tracers and exit, all means to stop it must be saved to self members:
        # launch command line with dtrace script and remember pid
        script = os.path.join(self.args.output, 'script.d')

        self.files = [os.path.join(self.args.output, 'data-%s.dtrace' % (self.args.cuts[0] if self.args.cuts else '0'))]
        if os.path.exists(self.files[0]):
            os.remove(self.files[0])

        cmd = 'sudo -A dtrace -Z -q -o "%s" -s "%s"' % (self.files[0], script)

        dtrace_script = []

        if self.args.ring:
            dtrace_script.append(self.gen_options([
                ('bufpolicy', 'ring'),
                ('bufresize', 'auto'),
                ('bufsize', '%dm' % (self.args.ring * 10))
            ]))

        dtrace_script.append(dtrace_context_switch)
        dtrace_script.append(fbt_dtrace_hooks)

        (probes, err) = self.execute('sudo -A dtrace -l -m *com.apple.driver.AppleIntel*Graphics*', env=os.environ)
        if probes:
            dtrace_script.append(self.gen_gpu_hooks(probes))

        if self.args.target:
            dtrace_script.append(pid_dtrace_hooks)
            cmd += " -p %s" % self.args.target
            if self.args.hotspots:
                dtrace_script.append(HOTSPOTS)

        for subcollector in self.subcollectors:
            hooks = subcollector.get_hooks(self.args)
            if hooks:
                dtrace_script.append(hooks)
            subcollector.collect(self, True)

        dtrace_script = '\n'.join(dtrace_script)

        if self.args.stacks:
            dtrace_script = dtrace_script.replace('/*{OFF_CPU}*/', OFF_CPU_STACKS)
            dtrace_script = dtrace_script.replace('/*{KMD_STACKS}*/', KMD_STACKS)
            dtrace_script = dtrace_script.replace('/*{UMD_STACKS}*/', UMD_STACKS)

        with open(script, 'w') as file:
            file.write(dtrace_script)

        self.collect_system_info()
        proc = subprocess.Popen(cmd, shell=True, stdin=None, stdout=self.output, stderr=self.output, env=os.environ)
        self.pid = proc.pid
        self.log(cmd)
        self.log("pid: %d" % proc.pid)

    @staticmethod
    def get_pid_children(parent):
        (out, err) = DTraceCollector.execute('ps -o pid,ppid -ax', log=False)
        if err:
            print err
            return
        for line in out.split('\n'):
            if not line:
                continue
            parts = line.split()
            if len(parts) != 2:
                continue
            pid, ppid = line.split()
            if str(parent) == ppid:
                yield int(pid)

    def collect_system_info(self):
        with open(os.path.join(self.args.output, 'sysinfo.txt'), 'w') as file:
            (probes, err) = self.execute('sysctl -a', env=os.environ, stdout=file)

    def stop(self, wait=True):
        self.log("pid: %s" % str(self.pid))
        for subcollector in self.subcollectors:
            subcollector.collect(self, False)
        if not self.pid:
            return []
        dtrace_pids = [self.pid] + list(self.get_pid_children(self.pid))
        for pid in dtrace_pids:  # FIXME: check if it has parent pid as well. Looks as we kill only children.
            self.execute("sudo -A kill -2 %d" % pid, env=os.environ)
        for pid in dtrace_pids:
            try:
                os.waitpid(pid, 0)
            except:
                pass
        return self.files

    @classmethod
    def available(cls):
        if 'darwin' not in sys.platform:
            return False
        (out, err) = cls.execute('csrutil status')
        if 'disabled' not in out:
            print 'Please do: "csrutil disable" from Recovery OS terminal to be able using dtrace...'
            return False
        return True


COLLECTOR_DESCRIPTORS = [{
    'format': 'dtrace',
    'available': DTraceCollector.available(),
    'collector': DTraceCollector
}]



