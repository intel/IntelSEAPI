import os
import sys
import subprocess
from sea_runtool import Collector

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
}

"""

osxaskpass = r"""#!/bin/bash
osascript -e 'Tell application "System Events" to display dialog "Password:" default answer "" with hidden answer with title "DTrace requires root priveledges"' -e 'text returned of result' 2>/dev/null
"""


dtrace_metal = r"""
pid$target:Metal::entry
{
    printf(
        "%x\te\t%x\t%x\t%s\n", machtimestamp, pid, tid, probefunc
    );
}

pid$target:Metal::return
{
    printf(
        "%x\tr\t%x\t%x\t%s\n", machtimestamp, pid, tid, probefunc
    );
}
"""

class DTraceCollector(Collector):
    def __init__(self, args):
        Collector.__init__(self, args)
        self.pid = None
        self.files = []
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

    @staticmethod
    def gen_gpu_hooks(text):
        probes = ''
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
                probe += ');}\n'
                probes += probe
            if 'process_token_' in name:
                probe = '%s::%s:%s{' % (parts[1], parts[3], parts[-1])
                probe += r'printf("%x\t' + parts[-1][0] + r'\t%x\t%x\t' + name.replace('process_token_', '')
                probe += r'\n", machtimestamp, pid, tid'
                probe += ');}\n'
                probes += probe
        return probes

    @staticmethod
    def gen_options(options):
        return '\n'.join('#pragma D option %s=%s' % (key, str(value)) for key, value in options) + '\n'

    def start(self):
        # spawn dtrace tracers and exit, all means to stop it must be saved to self members:
        # launch command line with dtrace script and remember pid
        script = os.path.join(self.args.output, 'script.d')

        (probes, err) = self.execute('sudo -A dtrace -l -m *com.apple.driver.AppleIntel*Graphics*', env=os.environ)
        if err:
            return

        self.files = [os.path.join(self.args.output, 'data-%s.dtrace' % (self.args.cuts[0] if self.args.cuts else '0'))]
        if os.path.exists(self.files[0]):
            os.remove(self.files[0])
        cmd = 'sudo -A dtrace -q -o "%s" -s "%s"' % (self.files[0], script)

        dtrace_script = []

        if self.args.ring:
            dtrace_script.append(self.gen_options([
                ('bufpolicy', 'ring'),
                ('bufresize', 'auto'),
                ('bufsize', '%dm' % (self.args.ring * 10))
            ]))
        dtrace_script.append(dtrace_context_switch)
        dtrace_script.append(self.gen_gpu_hooks(probes))

        if self.args.target:
            dtrace_script.append(dtrace_metal)
            cmd += " -p %s" % self.args.target

        with open(script, 'w') as file:
            file.write('\n'.join(dtrace_script))

        proc = subprocess.Popen(cmd, shell=True, stdin=None, stdout=None, stderr=None, env=os.environ)
        self.pid = proc.pid
        self.log(cmd)
        self.log("pid: %d" % proc.pid)


    @staticmethod
    def get_pid_children(parent):
        (out, err) = DTraceCollector.execute('ps -o pid,ppid -ax')
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

    def stop(self, wait=True):
        self.log("pid: %s" % str(self.pid))
        if not self.pid:
            return []
        for pid in self.get_pid_children(self.pid):
            self.execute("sudo -A kill -2 %d" % pid, env=os.environ)
        return self.files


COLLECTOR_DESCRIPTORS = [{
    'format': 'dtrace',
    'available': 'darwin' in sys.platform,
    'collector': DTraceCollector
}]

if __name__ == "__main__":
    """
    with open('/tmp/gpu.txt') as file:
        dt_hook = file.read()
    print DTraceCollector.gen_gpu_hooks()
    """
    pass

