#   Intel(R) Single Event API
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
# ********************************************************************************************************************************************************************************************************************************************************************************************

import os
import imp
import sea
import sys
import time
import shutil
import struct
import tempfile
import binascii
from glob import glob
from datetime import timedelta
from subprocess import Popen, PIPE

ProgressConst = 20000


def format_time(time):
    for coeff, suffix in [(10 ** 3, 'ns'), (10 ** 6, 'us'), (10 ** 9, 'ms')]:
        if time < coeff:
            return "%.3f%s" % (time * 1000.0 / coeff, suffix)
    return "%.3fs" % (float(time) / 10 ** 9)


def format_bytes(num):
    for unit in ['', 'K', 'M', 'G']:
        if abs(num) < 1024.0:
            return "%3.1f %sB" % (num, unit)
        num /= 1024.0
    return str(num) + 'B'


class DummyWith():  # for conditional with statements
    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        return False


class Profiler():
    def __enter__(self):
        try:
            import cProfile as profile
        except:
            import profile
        self.profiler = profile.Profile()
        self.profiler.enable()
        return self

    def __exit__(self, type, value, traceback):
        self.profiler.disable()
        self.profiler.print_stats('time')
        return False


def get_extensions(name, multiple=False):
    big_name = (name + 's').upper()
    this_module = sys.modules[__name__]
    if big_name in dir(this_module):
        return getattr(this_module, big_name)
    extensions = {}
    root = os.path.join(os.path.dirname(os.path.realpath(__file__)), name + 's')
    for extension in glob(os.path.join(root, '*.py')):
        module = imp.load_source(os.path.splitext(os.path.basename(extension))[0], extension)
        for desc in getattr(module, name.upper() + '_DESCRIPTORS'):
            if desc['available']:
                if multiple:
                    extensions.setdefault(desc['format'], []).append(desc[name])
                else:
                    extensions[desc['format']] = desc[name]
    setattr(this_module, big_name, extensions)
    return extensions


def get_exporters():
    return get_extensions('exporter')


def get_importers():
    return get_extensions('importer')


def get_collectors():
    return get_extensions('collector')


def get_decoders():
    return get_extensions('decoder', multiple=True)


def parse_args(args):
    import argparse
    parser = argparse.ArgumentParser(epilog="After this command line add ! followed by command line of your program")
    format_choices = ["mfc", "mfp"] + list(get_exporters().iterkeys())
    if sys.platform == 'win32':
        format_choices.append("etw")
    elif sys.platform == 'darwin':
        format_choices.append("xcode")
    elif sys.platform == 'linux':
        format_choices.append("kernelshark")
    parser.add_argument("-f", "--format", choices=format_choices, nargs='*', required=True, help='One or many output formats.')
    parser.add_argument("-o", "--output", help='Output folder pattern -<pid> will be added to it')
    parser.add_argument("-b", "--bindir", help='If you run script not from its location')
    parser.add_argument("-i", "--input", help='Provide input folder for transformation (<the one you passed to -o>-<pid>)')
    parser.add_argument("-t", "--trace", nargs='*', help='Additional trace file in one of supported formats')
    parser.add_argument("-d", "--dir", help='Working directory for target (your program)')
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-c", "--cuts", nargs='*', help='Set "all" to merge all cuts in one trace')
    parser.add_argument("-s", "--sync")
    parser.add_argument("-m", "--multiproc", default=True, action="store_false", help='Allows to capture follow-child mode and handle several processes writing trace')
    parser.add_argument("-r", "--ring", type=int, help='Makes trace to cycle inside ring buffer of given length in seconds')
    parser.add_argument("--time_shift", type=int, default=0)
    parser.add_argument("-l", "--limit", help='define')
    parser.add_argument("--ssh")
    parser.add_argument("-p", "--password")
    parser.add_argument("--dry", action="store_true", help='Dry mode, only prints what it would do')
    parser.add_argument("--stacks", action="store_true", help='Collect stacks')
    parser.add_argument("--min_dur", type=int, default=0, help='Sets minimal task length threshold (in float, microseconds). Helps opening huge traces.')
    parser.add_argument("--sampling")
    parser.add_argument("--distinct", action="store_true")
    parser.add_argument("--memory", choices=["total", "detailed"], default="total")
    parser.add_argument("--debug", action="store_true", help='Internal: validation')
    parser.add_argument("--profile", action="store_true", help='Internal: profile runtool execution')
    parser.add_argument("--collector", choices=list(get_collectors().iterkeys()) + ['default'])
    parser.add_argument("--strip_aliens", action="store_true", help='Filters out all but target processes')
    parser.add_argument("--remove_args", action="store_true", help='Deflates trace by removing arguments')
    parser.add_argument("--rem", help="Comment out: Allows to put everything you don't need")

    if "!" in args:
        separator = args.index("!")
        parsed_args = parser.parse_args(args[:separator])
        victim = args[separator + 1:]
        victim[-1] = victim[-1].strip()  # removal of trailing '\r' - when launched from .sh
        return parsed_args, victim
    else:  # nothing to launch, transformation mode
        if args:
            args[-1] = args[-1].strip()  # removal of trailing '\r' - when launched from .sh
        parsed_args = parser.parse_args(args)
        if parsed_args.input:
            setattr(parsed_args, 'user_input', parsed_args.input)
            if not parsed_args.output:
                parsed_args.output = parsed_args.input
            return parsed_args, None
        print "--input argument is required for transformation mode."
        parser.print_help()
        sys.exit(-1)


def main():
    (args, victim) = parse_args(sys.argv[1:])  # skipping the script name
    with Profiler() if args.profile else DummyWith():
        if victim:
            if args.multiproc:
                if os.path.exists(args.output):
                    shutil.rmtree(args.output)
                os.makedirs(args.output)
            launch(args, victim)
        else:
            ext = os.path.splitext(args.input)[1] if not os.path.isdir(args.input) else None
            if not ext:
                transform_all(args)
            else:
                get_importers()[ext.lstrip('.')](args)


def os_lib_ext():
    if sys.platform == 'win32':
        return '.dll'
    elif sys.platform == 'darwin':
        return '.dylib'
    elif 'linux' in sys.platform:
        return '.so'
    assert (not "Unsupported platform")


class Remote:
    def __init__(self, args):
        self.args = args
        if sys.platform == 'win32':
            self.execute_prefix = 'plink.exe -ssh %s' % args.ssh
            self.copy_prefix = 'pscp.exe'
            if args.password:
                self.execute_prefix += ' -pw %s' % args.password
                self.copy_prefix += ' -pw %s' % args.password
        else:
            self.execute_prefix = 'ssh %s' % args.ssh
            self.copy_prefix = 'scp'
            if args.password:
                self.execute_prefix = 'sshpass -p %s %s' % (args.password, self.execute_prefix)
                self.copy_prefix = 'sshpass -p %s %s' % (args.password, self.copy_prefix)

    def execute(self, cmd):
        command = '%s "%s"' % (self.execute_prefix, cmd)
        if self.args.verbose:
            print command
        out, err = Popen(command, shell=True, stdout=PIPE, stderr=PIPE).communicate()
        if err:
            print "Error:", err
            raise Exception(err)
        return out

    def copy(self, source, target):
        if self.args.verbose:
            print "%s %s %s" % (self.copy_prefix, source, target)
        out, err = Popen("%s %s %s" % (self.copy_prefix, source, target), shell=True, stdout=PIPE, stderr=PIPE).communicate()
        if err:
            print "Error:", err
            raise Exception(err)
        return out


def launch_remote(args, victim):
    if not args.bindir:
        print "--bindir must be set for remotes"
        sys.exit(-1)
    remote = Remote(args)

    print 'Getting target uname...',
    unix = remote.execute("uname")
    print ':', unix
    if 'darwin' in unix.lower():
        search = os.path.join(args.bindir, '*IntelSEAPI.dylib')
        files = glob(search)
        load_lib = 'DYLD_INSERT_LIBRARIES'
    else:
        file = remote.execute('file %s' % victim[0])
        bits = '64' if '64' in file else '32'
        search = os.path.join(args.bindir, '*IntelSEAPI' + bits + '.so')
        files = glob(search)
        load_lib = 'INTEL_LIBITTNOTIFY' + bits
    target = '/tmp/' + os.path.basename(files[0])

    print 'Copying corresponding library...'
    print remote.copy(files[0], '%s:%s' % (args.ssh, target))

    print 'Making temp dir...',
    trace = remote.execute('mktemp -d' + (' -t SEA_XXX' if 'darwin' in unix.lower() else '')).strip()
    print ':', trace

    output = args.output
    args.output = trace + '/nop'

    print 'Starting ftrace...'

    ftrace = get_collectors()['ftrace'](args, remote)
    print 'Executing:', ' '.join(victim), '...'

    variables = dict()
    variables[load_lib] = target
    variables['INTEL_SEA_SAVE_TO'] = trace
    if args.verbose:
        variables['INTEL_SEA_VERBOSE'] = '1'
    if args.ring:
        variables['INTEL_SEA_RING'] = str(args.ring)
    suffix = ' '.join(['%s=%s' % pair for pair in variables.iteritems()])
    print remote.execute(suffix + ' '.join(victim))
    if ftrace:
        args.trace = ftrace.stop()
    args.output = output

    local_tmp = tempfile.mkdtemp()
    print 'Copying result:'
    print remote.copy('-r %s:%s' % (args.ssh, trace), local_tmp)

    print 'Removing temp dir...'
    remote.execute('rm -r %s' % trace)

    print 'Transformation...'
    files = glob(os.path.join(local_tmp, '*', 'pid-*'))
    if not files:
        print "Error: Nothing captured"
        sys.exit(-1)
    args.input = files[0]
    if args.trace:
        args.trace = [glob(os.path.join(local_tmp, '*', 'nop*.ftrace'))[0]]
    output = transform(args)
    output = join_gt_output(args, output)
    shutil.rmtree(local_tmp)
    print "result:", output


def launch(args, victim):
    if args.ssh:
        return launch_remote(args, victim)
    env = {}
    script_dir = os.path.abspath(args.bindir) if args.bindir else os.path.dirname(os.path.realpath(__file__))
    paths = []
    macosx = sys.platform == 'darwin'
    for bits in (['32', '64'] if not macosx else ['']):
        search = os.path.sep.join([script_dir, "*IntelSEAPI" + bits + os_lib_ext()])
        files = glob(search)
        if not len(files):
            print "Warning: didn't find any files for:", search
            continue
        paths.append((bits, files[0]))
    if not len(paths):
        print "Error: didn't find any *IntelSEAPI%s files. Please check that you run from bin directory, or use --bindir." % os_lib_ext()
        sys.exit(-1)
    if macosx:
        env["DYLD_INSERT_LIBRARIES"] = paths[0][1]
    else:
        paths = dict(paths)
        if '32' in paths:
            env["INTEL_LIBITTNOTIFY32"] = paths['32']
        if '64' in paths:
            env["INTEL_LIBITTNOTIFY64"] = paths['64']

    env["INTEL_SEA_FEATURES"] = os.environ['INTEL_SEA_FEATURES'] if os.environ.has_key('INTEL_SEA_FEATURES') else ""
    env["INTEL_SEA_FEATURES"] += (" " + str(args.format)) if args.format else ""
    env["INTEL_SEA_FEATURES"] += " stacks" if args.stacks else ""
    if args.ring:
        env["INTEL_SEA_RING"] = str(args.ring)

    if args.output:
        env["INTEL_SEA_SAVE_TO"] = os.path.join(args.output, 'pid') if args.multiproc else args.output

    if args.dry:
        for key, val in env.iteritems():
            if val:
                print key + "=" + val
        return

    if args.verbose:
        print "Running:", victim
        print "Environment:", str(env)

    os.environ.update(env)

    if 'kernelshark' in args.format:
        victim = 'trace-cmd record -e IntelSEAPI/* ' + victim

    tracer = None
    if args.collector:
        tracer = get_collectors()[args.collector](args)

    proc = Popen(victim, env=os.environ, shell=False, cwd=args.dir)
    setattr(args, 'target', proc.pid)
    if not tracer:
        if 'gt' in args.format and args.output:
            if 'linux' in sys.platform:
                tracer = get_collectors()['ftrace'](args)
            elif 'win32' == sys.platform:
                tracer = get_collectors()['etw'](args)
            elif 'darwin' in sys.platform:
                tracer = get_collectors()['dtrace'](args)

    proc.wait()
    if tracer:
        args.trace = tracer.stop()

    if not args.output:
        return []

    args.input = "%s-%d" % (args.output, proc.pid)
    return transform_all(args)


def transform_all(args):
    if not args.trace:  # no itt trace
        args.trace = []
        for ext in ['etl', 'ftrace', 'dtrace']:
            for file in glob(os.path.join(args.input, '*.' + ext)):
                if not any(sub in file for sub in ['.etl.', '.dtrace.']):
                    args.trace.append(file)
    if args.multiproc:
        multi_out = []
        saved_output = args.output
        setattr(args, 'user_input', args.output)
        for folder in glob(os.path.join(args.output, 'pid-*')):
            if not os.path.isdir(folder):
                continue
            args.input = folder
            args.output = saved_output + '.' + os.path.basename(folder)
            multi_out += transform(args)
            if multi_out:
                args.trace = None
        output = join_gt_output(args, multi_out)
        args.output = saved_output
    else:
        setattr(args, 'user_input', args.input)
        output = transform(args)
        output = join_gt_output(args, output)
    print "result:", [os.path.abspath(path).replace('\\', '/') for path in output]
    return output


def join_gt_output(args, output):
    google_traces = [item for item in output if os.path.splitext(item)[1] in ['.json', '.ftrace']]
    if google_traces:
        res = get_exporters()['gt'].join_traces(google_traces, args.output, args)
        output = list(set(output) - set(google_traces)) + [res]
    return output


def split_filename(path):
    (dir, name) = os.path.split(path)
    (name, ext) = os.path.splitext(name)
    ring = None
    cut = None
    if '-' in name:
        (name, ring) = name.split("-")
    if '!' in name:
        (name, cut) = name.split("!")
    return {'dir': dir, 'name': name, 'cut': cut, 'ring':ring, 'ext': ext}


def default_tree():
    return {"strings": {}, "domains": {}, "threads": {}, "groups": {}, "modules": {}, "ring_buffer": False, "cuts": set()}


def build_tid_map(args, path):
    tid_map = {}

    def parse_process(src):
        if not os.path.isdir(src):
            return
        pid = src.rsplit('-', 1)[1]
        if not pid.isdigit():
            return
        pid = int(pid)
        for folder in glob(os.path.join(src, '*', '*.sea')):
            tid = int(os.path.basename(folder).split('!')[0].split('-')[0].split('.')[0])
            tid_map[tid] = pid

    if args.multiproc:
        for folder in glob(os.path.join(path, '*-*')):
            parse_process(folder)
    else:
        parse_process(path)
    return tid_map


def sea_reader(folder):  # reads the structure of .sea format folder into dictionary
    if not os.path.exists(folder):
        print """Error: folder "%s" doesn't exist""" % folder
    tree = default_tree()
    pos = folder.rfind("-")  # pid of the process is encoded right in the name of the folder
    tree["pid"] = int(folder[pos + 1:])
    folder = folder.replace("\\", "/").rstrip("/")
    toplevel = os.walk(folder).next()
    for filename in toplevel[2]:
        with open("/".join([folder, filename]), "r") as file:
            if filename.endswith(".str"):  # each string_handle_create writes separate file, name is the handle, content is the value
                tree["strings"][int(filename.replace(".str", ""))] = file.readline()
            elif filename.endswith(".tid"):  # named thread makes record: name is the handle and content is the value
                tree["threads"][filename.replace(".tid", "")] = file.readline()
            elif filename.endswith(".pid"):  # named groups (pseudo pids) makes record: group is the handle and content is the value
                tree["groups"][filename.replace(".pid", "")] = file.readline()
            elif filename.endswith(".mdl"):  # registered modules - for symbol resolving
                parts = file.readline().split()
                tree["modules"][int(filename.replace(".mdl", ""))] = [' '.join(parts[0:-1]), parts[-1]]
            elif filename == "process.dct":  # process info
                tree["process"] = eval(file.read())
    for domain in toplevel[1]:  # data from every domain gets recorded into separate folder which is named after the domain name
        tree["domains"][domain] = {"files": []}
        for file in os.walk("/".join([folder, domain])).next()[2]:  # each thread of this domain has separate file with data
            if not file.endswith(".sea"):
                print "Warning: weird file found:", file
                continue
            filename = file[:-4]

            tree["ring_buffer"] = tree["ring_buffer"] or ('-' in filename)
            tid = int(filename.split("!")[0].split("-")[0])
            tree["cuts"].add(split_filename(filename)['cut'])

            tree["domains"][domain]["files"].append((tid, "/".join([folder, domain, file])))

        def time_sort(item):
            with open(item[1], "rb") as file:
                tuple = read_chunk_header(file)
                return tuple[0]

        tree["domains"][domain]["files"].sort(key=time_sort)
    return tree


g_progress_interceptor = None


class Progress:
    def __init__(self, total, steps, message=""):
        self.total = total
        self.steps = steps
        self.shown_steps = 0
        self.message = message
        print message, "[",

    def __enter__(self):
        return self

    def tick(self, current):
        if g_progress_interceptor:
            g_progress_interceptor(self.message, current, self.total)
        if self.total:
            self.show_progress(int(self.steps * current / self.total))

    def show_progress(self, show_steps):
        if self.shown_steps < show_steps:
            for i in range(show_steps - self.shown_steps):
                print ".",
            self.shown_steps = show_steps

    def __exit__(self, type, value, traceback):
        if g_progress_interceptor:
            g_progress_interceptor(self.message, self.total, self.total)
        self.show_progress(self.steps)
        print "]"
        return False

    @staticmethod
    def set_interceptor(interceptor):
        global g_progress_interceptor
        g_progress_interceptor = interceptor


class PseudoProgress(Progress):

    def profiler(self, frame, event, arg):
        if 'return' not in event:
            return
        cur_time = time.time()
        if cur_time - self.time > 0.2:
            self.time = cur_time
            self.tick(cur_time)

    def __init__(self, message=""):
        self.time = None
        Progress.__init__(self, 0, 0, message)
        self.old_profiler = sys.getprofile()

    def __enter__(self):
        self.time = time.time()
        sys.setprofile(self.profiler)
        return self

    def __exit__(self, type, value, traceback):
        sys.setprofile(self.old_profiler)
        return Progress.__exit__(self, type, value, traceback)


def read_chunk_header(file):
    chunk = file.read(10)  # header of the record, see STinyRecord in Recorder.cpp
    if chunk == '':
        return 0, 0, 0
    return struct.unpack('Qbb', chunk)


def transform(args):
    if args.verbose:
        print "Transform:", str(args)
    tree = sea_reader(args.input)  # parse the structure
    if args.cuts and args.cuts == ['all'] or not args.cuts:
        return transform2(args, tree)
    else:
        result = []
        output = args.output[:]  # deep copy
        for current_cut in tree['cuts']:
            if args.cuts and current_cut not in args.cuts:
                continue
            args.output = (output + "!" + current_cut) if current_cut else output
            print "Cut #", current_cut if current_cut else "<None>"

            def skip_fn(path):
                filename = os.path.split(path)[1]
                if current_cut:  # read only those having this cut name in filename
                    if current_cut != split_filename(filename)['cut']:
                        return True
                else:  # reading those having not cut name in filename
                    if "!" in filename:
                        return True
                return False

            result += transform2(args, tree, skip_fn)
        args.output = output
        return result


TaskTypes = [
    "task_begin", "task_end",
    "task_begin_overlapped", "task_end_overlapped",
    "metadata_add",
    "marker",
    "counter",
    "frame_begin", "frame_end",
    "object_new", "object_snapshot", "object_delete",
    "relation"
]


class Callbacks:
    def __init__(self, args, tree):
        self.args = args
        self.callbacks = []  # while parsing we might have one to many 'listeners' - output format writers
        for fmt in args.format:
            self.callbacks.append(get_exporters()[fmt](args, tree))
        self.parse_limits()
        self.allowed_pids = set()
        if hasattr(self.args, 'user_input') and os.path.isdir(self.args.user_input):
            tid_map = build_tid_map(self.args, self.args.user_input)
            self.allowed_pids = set(tid_map.itervalues())

    def is_empty(self):
        return 0 == len(self.callbacks)

    def __enter__(self):
        [callback.__enter__() for callback in self.callbacks]
        return self

    def __exit__(self, type, value, traceback):
        [callback.__exit__(type, value, traceback) for callback in self.callbacks]  # emulating 'with' statement
        return False

    def on_event(self, type, data):
        if self.check_pid_allowed(data['pid']) and self.check_time_in_limits(data['time']):
            if self.args.remove_args and 'args' in data:
                del data['args']
            # copy here as handler can change the data for own good - this shall not affect other handlers
            [callback(type, data.copy()) for callback in self.callbacks]

    def complete_task(self, type, begin, end):
        if self.check_pid_allowed(begin['pid']) and (self.check_time_in_limits(begin['time']) or self.check_time_in_limits(end['time'])):
            if self.args.remove_args:
                if 'args' in begin:
                    del begin['args']
                if 'args' in end:
                    del end['args']
            # copy here as handler can change the data for own good - this shall not affect other handlers
            [callback.complete_task(type, begin.copy(), end.copy()) for callback in self.callbacks]

    def get_result(self):
        res = []
        for callback in self.callbacks:
            res += callback.get_targets()
        return res

    def check_pid_allowed(self, pid):
        if not self.args.strip_aliens or pid < 0 or pid in self.allowed_pids:
            return True
        return False

    def check_time_in_limits(self, time):
        left, right = self.limits
        if left != None and time < left:
            return False
        if right != None and time > right:
            return False
        return True

    def parse_limits(self):
        left_limit = None
        right_limit = None
        if self.args.limit:
            limits = self.args.limit.split(":")
            if limits[0]:
                left_limit = int(limits[0])
            if limits[1]:
                right_limit = int(limits[1])
        self.limits = (left_limit, right_limit)

    def get_limits(self):
        return self.limits


class FileWrapper:
    def __init__(self, path, args, tree, domain, tid):
        self.args = args
        self.tree = tree
        self.domain = domain
        self.tid = tid
        self.next_wrapper = None
        self.file = open(path, "rb")
        self.record = self.read()

    def __del__(self):
        self.file.close()

    def next(self):
        self.record = self.read()

    def get_record(self):
        return self.record

    def get_pos(self):
        return self.file.tell()

    def get_size(self):
        return os.path.getsize(self.file.name)

    def get_path(self):
        return self.file.name

    def read(self):
        call = {"tid": self.tid, "pid": self.tree["pid"], "domain": self.domain}

        tuple = read_chunk_header(self.file)
        if tuple == (0, 0, 0):  # mem mapping wasn't trimed on close, zero padding goes further
            return None
        call["time"] = tuple[0]

        assert (tuple[1] < len(TaskTypes))  # sanity check
        call["type"] = tuple[1]

        flags = tuple[2]
        if flags & 0x1:  # has id
            chunk = self.file.read(2 * 8)
            call["id"] = struct.unpack('QQ', chunk)[0]
        if flags & 0x2:  # has parent
            chunk = self.file.read(2 * 8)
            call["parent"] = struct.unpack('QQ', chunk)[0]
        if flags & 0x4:  # has string
            chunk = self.file.read(8)
            str_id = struct.unpack('Q', chunk)[0]  # string handle
            call["str"] = self.tree["strings"][str_id]
        if flags & 0x8:  # has tid, that differs from the calling thread (virtual tracks)
            chunk = self.file.read(8)
            call["tid"] = int(struct.unpack('q', chunk)[0])

        if flags & 0x10:  # has data
            chunk = self.file.read(8)
            length = struct.unpack('Q', chunk)[0]
            call["data"] = self.file.read(length)

        if flags & 0x20:  # has delta
            chunk = self.file.read(8)
            call["delta"] = struct.unpack('d', chunk)[0]

        if flags & 0x40:  # has pointer
            chunk = self.file.read(8)
            ptr = struct.unpack('Q', chunk)[0]
            if not resolve_pointer(self.args, self.tree, ptr, call):
                call["pointer"] = ptr

        if flags & 0x80:  # has pseudo pid
            chunk = self.file.read(8)
            call["pid"] = struct.unpack('q', chunk)[0]

        return call

    def set_next(self, wrapper):
        self.next_wrapper = wrapper

    def get_next(self):
        return self.next_wrapper


def transform2(args, tree, skip_fn=None):
    with Callbacks(args, tree) as callbacks:
        if callbacks.is_empty():
            return callbacks.get_result()

        wrappers = {}
        for domain, content in tree["domains"].iteritems():  # go thru domains
            for tid, path in content["files"]:  # go thru per thread files
                parts = split_filename(path)
                wrappers.setdefault(parts['dir'] + '/' + parts['name'], []).append(FileWrapper(path, args, tree, domain, tid))

        for unordered in wrappers.itervalues():  # chain wrappers by time
            ordered = sorted(unordered, key=lambda wrapper: wrapper.get_record()['time'])
            prev = None
            for wrapper in ordered:
                if prev:
                    prev.set_next(wrapper)
                prev = wrapper

        files = []
        (left_limit, right_limit) = callbacks.get_limits()
        for unordered in wrappers.itervalues():
            for wrapper in unordered:
                if right_limit and wrapper.get_record()['time'] > right_limit:
                    continue
                next = wrapper.get_next()
                if left_limit and next and next.get_record()['time'] < left_limit:
                    continue
                if skip_fn and skip_fn(wrapper.get_path()):  # for "cut" support
                    continue
                files.append(wrapper)

        if args.verbose:
            print path
            progress = DummyWith()
        else:
            size = sum([file.get_size() for file in files])
            progress = Progress(size, 50, 'Translation: %s (%s)' % (os.path.basename(args.input), format_bytes(size)))

        with progress:
            count = 0
            while True:  # records iteration
                record = None
                earliest = None
                for file in files:
                    rec = file.get_record()
                    if not rec:  # finished
                        continue
                    if not record or rec['time'] < record['time']:
                        record = rec
                        earliest = file
                if not record:  # all finished
                    break
                earliest.next()

                if args.verbose:
                    print "%d\t%s\t%s" % (count, TaskTypes[record['type']], record)
                elif count % ProgressConst == 0:
                    progress.tick(sum([file.get_pos() for file in files]))
                callbacks.on_event(TaskTypes[record['type']], record)
                count += 1
        for callback in callbacks.callbacks:
            callback("metadata_add", {'domain': 'IntelSEAPI', 'str': '__process__', 'pid': tree["pid"], 'tid': -1, 'delta': -1})
            for pid, name in tree['groups'].iteritems():
                callback("metadata_add", {'domain': 'IntelSEAPI', 'str': '__process__', 'pid': int(pid), 'tid': -1, 'delta': -1, 'data': name})

    return callbacks.get_result()


def get_module_by_ptr(tree, ptr):
    keys = list(tree['modules'].iterkeys())
    keys.sort()  # looking for first bigger the address, previous is the module we search for
    item = keys[0]
    for key in keys[1:]:
        if key > ptr:
            break
        item = key
    module = tree['modules'][item]
    if item < ptr < item + int(module[1]):
        return item, module[0]
    else:
        return None, None


def resolve_cmd(args, path, load_addr, ptr, cache={}):
    if sys.platform == 'win32':
        """ XXX
        if not cache:
            sea.prepare_environ(args)
            cache['stack'] = sea.ITT('stack')
        result = cache['stack'].resolve_pointer(path, ptr - load_addr)
        return result if result else ''
        print path, ptr - load_addr, result
        """
        script_dir = os.path.abspath(args.bindir) if args.bindir else os.path.dirname(os.path.realpath(__file__))
        executable = os.path.sep.join([script_dir, 'TestIntelSEAPI32.exe'])
        cmd = '"%s" "%s":%d' % (executable, path, ptr - load_addr)
    elif sys.platform == 'darwin':
        cmd = 'atos -o "%s" -l %s %s' % (path, to_hex(load_addr), to_hex(ptr))
    elif 'linux' in sys.platform:
        cmd = 'addr2line %s -e "%s" -i -p -f -C' % (to_hex(ptr), path)
    else:
        assert (not "Unsupported platform!")

    env = dict(os.environ)
    if "INTEL_SEA_VERBOSE" in env:
        del env["INTEL_SEA_VERBOSE"]

    proc = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE, env=env)
    (symbol, err) = proc.communicate()
    if err:
        print err
        return ''
    """ XXX
    if symbol and not result:
        print symbol, result
        assert symbol == result
    """
    return symbol


def resolve_pointer(args, tree, ptr, call, cache={}):
    if not cache.has_key(ptr):
        (load_addr, path) = get_module_by_ptr(tree, ptr)
        if path is None or not os.path.exists(path):
            return False
        symbol = resolve_cmd(args, path, load_addr, ptr)
        cache[ptr] = {'module': path, 'symbol': symbol}

    lines = cache[ptr]['symbol'].splitlines()
    if not lines:
        return False
    call['module'] = cache[ptr]['module']

    if sys.platform == 'win32':
        if len(lines) == 1:
            call['str'] = lines[0]
        elif len(lines) == 2:
            call['str'] = lines[1]
            (call['__file__'], call['__line__']) = lines[0].rstrip(")").rsplit("(", 1)
    elif sys.platform == 'darwin':
        if '(in' in lines[0]:
            parts = lines[0].split(" (in ")
            call['str'] = parts[0]
            if ') (' in parts[1]:
                (call['__file__'], call['__line__']) = parts[1].split(') (')[1].split(':')
                call['__line__'] = call['__line__'].strip(')')
        else:
            return False
    else:
        if ' at ' in lines[0]:
            (call['str'], fileline) = lines[0].split(' at ')
            (call['__file__'], call['__line__']) = fileline.strip().split(':')
        else:
            return False
    return True


def resolve_stack(args, tree, data):
    if tree['process']['bits'] == 64:
        frames = struct.unpack('Q' * (len(data) / 8), data)
    else:
        frames = struct.unpack('I' * (len(data) / 4), data)
    stack = []
    for frame in frames:
        res = {'ptr': frame}
        if resolve_pointer(args, tree, frame, res):
            stack.append(res)
    return stack


def attachme():
    print "Attach me!"
    while not sys.gettrace():
        pass
    import time
    time.sleep(1)


def D3D11_DEPTH_STENCILOP_DESC(data):
    """
    struct D3D11_DEPTH_STENCILOP_DESC
    {
        D3D11_STENCIL_OP StencilFailOp; #long
        D3D11_STENCIL_OP StencilDepthFailOp; #long
        D3D11_STENCIL_OP StencilPassOp; #long
        D3D11_COMPARISON_FUNC StencilFunc; #long
    };
    """
    (StencilFailOp, StencilDepthFailOp, StencilPassOp, StencilFunc) = struct.unpack('LLLL', data[:D3D11_DEPTH_STENCILOP_DESC.SIZE])
    return {'StencilFailOp':StencilFailOp, 'StencilDepthFailOp':StencilDepthFailOp, 'StencilPassOp':StencilPassOp, 'StencilFunc':StencilFunc}
D3D11_DEPTH_STENCILOP_DESC.SIZE = 4 * 4


def D3D11_DEPTH_STENCIL_DESC(data):
    """
    struct D3D11_DEPTH_STENCIL_DESC
    {
        BOOL DepthEnable; #long
        D3D11_DEPTH_WRITE_MASK DepthWriteMask; #long
        D3D11_COMPARISON_FUNC DepthFunc; #long
        BOOL StencilEnable; #long
        UINT8 StencilReadMask; #char
        UINT8 StencilWriteMask; #char
        D3D11_DEPTH_STENCILOP_DESC FrontFace;
        D3D11_DEPTH_STENCILOP_DESC BackFace;
    }
    """
    OWN_SIZE = 4 * 4 + 2  # Before start of other structures 4 Longs, 2 Chars
    (DepthEnable, DepthWriteMask, DepthFunc, StencilEnable, StencilReadMask, StencilWriteMask) = struct.unpack('LLLLBB', data[:OWN_SIZE])
    pos = OWN_SIZE + 2  # +2 for alignment because of 2 chars before
    FrontFace = D3D11_DEPTH_STENCILOP_DESC(data[pos: pos + D3D11_DEPTH_STENCILOP_DESC.SIZE])
    pos += D3D11_DEPTH_STENCILOP_DESC.SIZE
    BackFace = D3D11_DEPTH_STENCILOP_DESC(data[pos: pos + D3D11_DEPTH_STENCILOP_DESC.SIZE])
    return {'DepthEnable': DepthEnable, 'DepthWriteMask':DepthWriteMask, 'DepthFunc':DepthFunc, 'StencilEnable':StencilEnable, 'StencilReadMask':StencilReadMask, 'StencilWriteMask':StencilWriteMask, 'FrontFace': FrontFace, 'BackFace': BackFace};
D3D11_DEPTH_STENCIL_DESC.SIZE = 4 * 4 + 2 + 2 + 2 * D3D11_DEPTH_STENCILOP_DESC.SIZE

struct_decoders = {
    'D3D11_DEPTH_STENCIL_DESC': D3D11_DEPTH_STENCIL_DESC,
    'D3D11_DEPTH_STENCILOP_DESC': D3D11_DEPTH_STENCILOP_DESC
}


def represent_data(tree, name, data):
    for key in struct_decoders.iterkeys():
        if key in name:
            return struct_decoders[key](data)
    if all((31 < ord(chr) < 128) or (chr in ['\t', '\r', '\n']) for chr in data):  # string we will show as string
        return data
    return binascii.hexlify(data)  # the rest as hex buffer


class TaskCombiner:
    disable_handling_leftovers = False

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.handle_leftovers()
        self.finish()
        return False

    def __init__(self, args, tree):
        self.no_begin = []  # for the ring buffer case when we get task end but no task begin
        self.time_bounds = [2 ** 64, 0]  # left and right time bounds
        self.tree = tree
        self.args = args
        self.domains = {}
        self.events = []
        self.event_map = {}
        self.prev_sample = 0
        self.memory = {}
        self.total_memory = 0
        self.prev_memory = None
        (self.source_scale_start, self.target_scale_start, self.ratio) = tuple([0, 0, 1. / 1000])  # nanoseconds to microseconds
        if self.args.sync:
            self.set_sync(*self.args.sync)

    def set_sync(self, *sync):
        (self.source_scale_start, self.target_scale_start, self.ratio) = tuple(sync)

    def convert_time(self, time):
        return (time - self.source_scale_start) * self.ratio + self.target_scale_start

    def global_metadata(self, data):
        pass

    def relation(self, data, head, tail):
        pass

    def handle_leftovers(self):
        if TaskCombiner.disable_handling_leftovers:
            return
        for end in self.no_begin:
            begin = end.copy()
            begin['time'] = self.time_bounds[0]
            self.complete_task(TaskTypes[begin['type']].split("_")[0], begin, end)
        for domain, threads in self.domains.iteritems():
            for tid, records in threads['tasks'].iteritems():
                for id, per_id_records in records['byid'].iteritems():
                    for begin in per_id_records:
                        end = begin.copy()
                        end['time'] = self.time_bounds[1]
                        self.complete_task(TaskTypes[begin['type']].split("_")[0], begin, end)
                for begin in records['stack']:
                    end = begin.copy()
                    end['time'] = self.time_bounds[1]
                    self.complete_task(TaskTypes[begin['type']].split("_")[0], begin, end)
            if self.prev_sample:
                self.flush_counters(threads, {'tid': 0, 'pid': self.tree['pid'], 'domain': domain})

    def __call__(self, fn, data):
        domain = self.domains.setdefault(data['domain'], {'tasks': {}, 'counters': {}})
        thread = domain['tasks'].setdefault(data['tid'], {'byid': {}, 'stack': [], 'args': {}})

        def get_tasks(id):
            if not id:
                return thread['stack']
            return thread['byid'].setdefault(id, [])

        def get_task(id):
            if id:
                tasks = get_tasks(id)
                if not tasks:  # they can be stacked
                    tasks = get_tasks(None)
                    if not tasks or not tasks[-1].has_key('id') or tasks[-1]['id'] != id:
                        return None
            else:
                tasks = get_tasks(None)
            if tasks:
                return tasks[-1]
            else:
                return None

        def find_task(id):
            for thread_stacks in domain['tasks'].itervalues():  # look in all threads
                if thread_stacks['byid'].has_key(id) and thread_stacks['byid'][id]:
                    return thread_stacks['byid'][id][-1]
                else:
                    for item in thread_stacks['stack']:
                        if item.has_key('id') and item['id'] == id:
                            return item

        def get_stack(tid):
            stack = []
            for domain in self.domains.itervalues():
                if not domain['tasks'].has_key(tid):
                    continue
                thread = domain['tasks'][tid]
                for byid in thread['byid'].itervalues():
                    stack += byid
                if thread['stack']:
                    stack += thread['stack']
            stack.sort(key=lambda item: item['time'])
            return stack

        def get_last_index(tasks, type):
            if not len(tasks):
                return None
            index = len(tasks) - 1
            while index > -1 and tasks[index]['type'] != type:
                index -= 1
            if index > -1:
                return index
            return None

        if fn == "task_begin" or fn == "task_begin_overlapped":
            if not (data.has_key('str') or data.has_key('pointer')):
                data['str'] = 'Unknown'
            self.time_bounds[0] = min(self.time_bounds[0], data['time'])
            get_tasks(None if fn == "task_begin" else data['id']).append(data)
        elif fn == "task_end" or fn == "task_end_overlapped":
            if data.has_key('delta'):  # turbo mode, only ends are written
                self.time_bounds[0] = min(self.time_bounds[0], data['time'])
                end = data.copy()
                end['time'] = data['time'] + data['delta']
                if not (data.has_key('str') or data.has_key('pointer')):
                    data['str'] = 'Unknown'
                if data.has_key('id') and thread['args'].has_key(data['id']):
                    data['args'] = thread['args'][data['id']]
                    del thread['args'][data['id']]
                self.time_bounds[1] = max(self.time_bounds[1], end['time'])
                self.complete_task('task', data, end)
            else:
                self.time_bounds[1] = max(self.time_bounds[1], data['time'])
                tasks = get_tasks(None if fn == "task_end" else data['id'])
                index = get_last_index(tasks, data['type'] - 1)
                if index is not None:
                    item = tasks.pop(index)
                    self.complete_task('task', item, data)
                else:
                    assert (self.tree["ring_buffer"] or self.tree['cuts'])
                    if data.has_key('str'):  # nothing to show without name
                        self.no_begin.append(data)
        elif fn == "frame_begin":
            get_tasks(data['id'] if data.has_key('id') else None).append(data)
        elif fn == "frame_end":
            frames = get_tasks(data['id'] if data.has_key('id') else None)
            index = get_last_index(frames, 7)
            if index is not None:
                item = frames.pop(index)
                self.complete_task("frame", item, data)
            else:
                assert (self.tree["ring_buffer"] or self.tree['cuts'])
        elif fn == "metadata_add":
            if data.has_key('id'):
                task = get_task(data['id'])
                if task:
                    args = task.setdefault('args', {})
                else:
                    args = thread['args'].setdefault(data['id'], {})

                args[data['str']] = data['delta'] if data.has_key('delta') else represent_data(self.tree, data['str'], data['data']) if data.has_key('data') else '0x0'
            else:  # global metadata
                self.global_metadata(data)
        elif fn == "object_snapshot":
            if data.has_key('args'):
                args = data['args'].copy()
            else:
                args = {'snapshot': {}}
            if data.has_key('data'):
                state = data['data']
                for pair in state.split(","):
                    (key, value) = tuple(pair.split("="))
                    args['snapshot'][key] = value
            data['args'] = args
            self.complete_task(fn, data, data)
        elif fn in ["marker", "counter", "object_new", "object_delete"]:
            if fn == "marker" and data['data'] == 'task':
                markers = get_tasks("marker_" + (data['id'] if data.has_key('id') else ""))
                if markers:
                    item = markers.pop()
                    item['type'] = 7  # frame_begin
                    item['domain'] += ".continuous_markers"
                    item['time'] += 1
                    self.complete_task("frame", item, data)
                markers.append(data)
            elif fn == "counter" and self.args.sampling:
                if (data['time'] - self.prev_sample) > (int(self.args.sampling) * 1000):
                    if not self.prev_sample:
                        self.prev_sample = data['time']
                    else:
                        self.flush_counters(domain, data)
                        self.prev_sample = data['time']
                        domain['counters'] = {}
                counter = domain['counters'].setdefault(data['str'], {'begin':data['time'], 'end': data['time'], 'values': []})
                counter['values'].append(data['delta'])
                counter['begin'] = min(counter['begin'], data['time'])
                counter['end'] = max(counter['end'], data['time'])
            else:
                if data['domain'] == 'Memory':
                    size = int(data['str'].split('<')[1].split('>')[0])
                    prev_value = 0.
                    if self.memory.has_key(size):
                        prev_value = self.memory[size]
                    delta = data['delta'] - prev_value  # data['delta'] has current value of the counter
                    self.total_memory += delta * size
                    self.memory[size] = data['delta']
                    stack = get_stack(data['tid'])
                    if stack:
                        current = stack[-1]
                        values = current.setdefault('memory', {None: 0}).setdefault(size, [])
                        values.append(delta)
                        for parent in stack[:-1]:
                            values = parent.setdefault('memory', {None: 0})
                            values[None] += delta * size
                    if self.args.memory == "total":
                        if (self.prev_memory is None) or ((self.convert_time(data['time']) - self.convert_time(self.prev_memory['time'])) > self.args.min_dur * 10):
                            data['str'] = "CRT:Memory:Total(bytes)"
                            data['delta'] = self.total_memory
                            self.complete_task(fn, data, data)
                            self.prev_memory = data
                        return
                if data.has_key('id') and thread['args'].has_key(data['id']):
                    data['args'] = thread['args'][data['id']]
                    del thread['args'][data['id']]
                self.complete_task(fn, data, data)
        elif fn == "relation":
            self.relation(
                data,
                get_task(data['id'] if data.has_key('id') else None),
                get_task(data['parent']) or find_task(data['parent'])
            )
        else:
            assert (not "Unsupported type:" + fn)

    def flush_counters(self, domain, data):
        for name, counter in domain['counters'].iteritems():
            common_data = data.copy()
            common_data['time'] = counter['begin'] + (counter['end'] - counter['begin']) / 2
            common_data['str'] = name
            common_data['delta'] = sum(counter['values']) / len(counter['values'])
            self.complete_task('counter', common_data, common_data)


def to_hex(value):
    return "0x" + hex(value).rstrip('L').replace("0x", "").upper()


def get_name(begin):
    if begin.has_key('str'):
        return begin['str']
    elif begin.has_key('pointer'):
        return "func<" + to_hex(begin['pointer']) + ">"
    else:
        return "<unknown>"


class GraphCombiner(TaskCombiner):
    def __init__(self, args, tree):
        TaskCombiner.__init__(self, args, tree)
        self.args = args
        self.per_domain = {}
        self.relations = {}
        self.threads = set()

    def complete_task(self, type, begin, end):
        tid = begin['tid'] if 'tid' in begin else None
        self.threads.add(tid)
        domain = self.per_domain.setdefault(begin['domain'], {'counters': {}, 'objects':{}, 'frames': {}, 'tasks': {}, 'markers': {}})
        if type == 'task':
            task = domain['tasks'].setdefault(get_name(begin), {'time': []})
            task['time'].append(end['time'] - begin['time'])
            if begin.has_key('__file__'):
                task['src'] = begin['__file__'] + ":" + begin['__line__']
            stack = self.domains[begin['domain']]['tasks'][tid]['stack']
            if len(stack):
                parent = stack[-1]
                self.add_relation({'label':'calls', 'from': self.make_id(parent['domain'], get_name(parent)), 'to': self.make_id(begin['domain'], get_name(begin))})
            else:
                self.add_relation({'label':'executes', 'from': self.make_id("threads", str(tid)), 'to': self.make_id(begin['domain'], get_name(begin)), 'color': 'gray'})
        elif type == 'marker':
            domain['markers'].setdefault(begin['str'], [])
        elif type == 'frame':
            pass
        elif type == 'counter':
            domain['counters'].setdefault(begin['str'], []).append(begin['delta'])
        elif 'object' in type:
            if 'snapshot' in type:
                return
            objects = domain['objects'].setdefault(begin['str'], {})
            object = objects.setdefault(begin['id'], {})
            if 'new' in type:
                object['create'] = begin['time']
            elif 'delete' in type:
                object['destroy'] = begin['time']
        else:
            print "Unhandled:", type

    def make_id(self, domain, name):
        import re
        res = "%s_%s" % (domain, name)
        return re.sub("[^a-z0-9]", "_", res.lower())

    def relation(self, data, head, tail):
        if head and tail:
            self.add_relation({'label': data['str'], 'from': self.make_id(head['domain'], head['str']), 'to': self.make_id(tail['domain'], tail['str']), 'color': 'red'})

    def add_relation(self, relation):
        key = frozenset(relation.iteritems())
        if self.relations.has_key(key):
            return
        self.relations[key] = relation


class Collector:
    output = None

    def __init__(self, args):
        self.args = args

    @classmethod
    def set_output(cls, output):
        cls.output = output

    @classmethod
    def log(cls, msg):
        if cls.output:
            cls.output.write(msg + '\n')
        else:
            print msg

    @classmethod
    def execute(cls, cmd, **kwargs):
        start_time = time.time()
        (out, err) = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE, **kwargs).communicate()
        cls.log("\n%s:\n%s\n%s\nTime: %s" % (cmd, out, err, str(timedelta(seconds=(time.time() - start_time)))))
        return out, err

    def start(self):
        raise NotImplementedError('Collector.start is not implemented!')

    def stop(self, wait=True):
        raise NotImplementedError('Collector.stop is not implemented!')

if __name__ == "__main__":
    start_time = time.time()
    main()
    elapsed = time.time() - start_time
    print "Time Elapsed:", str(timedelta(seconds=elapsed)).split('.')[0]

