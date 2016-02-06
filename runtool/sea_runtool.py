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
#********************************************************************************************************************************************************************************************************************************************************************************************

import os
import sys
import cgi #for escaping XML
import json
import shutil
import struct
import tempfile
import binascii
from glob import glob
from subprocess import Popen, PIPE

ProgressConst = 10000

def format_time(time):
    for coeff, suffix in [(10**3, 'ns'), (10**6, 'us'), (10**9, 'ms')]:
        if time < coeff:
            return "%.3f%s" % (time * 1000.0 / coeff , suffix)
    return "%.3fs" % (float(time) / 10**9)

class DummyWith(): #for conditional with statements
    def __enter__(self):
        return self
    def __exit__(self, type, value, traceback):
        return False

def parse_args(args):
    import argparse
    parser = argparse.ArgumentParser(epilog="After this command line add ! followed by command line of your program")
    format_choices = ["gt", "mfc", "mfp", "qt", "fd", "btf", "gv", "dgml"]
    if sys.platform == 'win32':
        format_choices.append("etw")
    elif sys.platform == 'darwin':
        format_choices.append("xcode")
    elif sys.platform == 'linux':
        format_choices.append("kernelshark")
    parser.add_argument("-f", "--format", choices=format_choices, nargs='*')
    parser.add_argument("-o", "--output")
    parser.add_argument("-b", "--bindir")
    parser.add_argument("-i", "--input")
    parser.add_argument("-t", "--trace")
    parser.add_argument("-d", "--dir")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-c", "--cuts", nargs='*')
    parser.add_argument("-s", "--sync")
    parser.add_argument("-l", "--limit", nargs='*')
    parser.add_argument("--ssh")
    parser.add_argument("-p", "--password")
    parser.add_argument("--dry", action="store_true")
    parser.add_argument("--stacks", action="store_true")
    parser.add_argument("--min_dur", type=int, default=0)
    parser.add_argument("--sampling")
    parser.add_argument("--debug", action="store_true")

    if "!" in args:
        separator = args.index("!")
        parsed_args = parser.parse_args(args[:separator])
        victim = args[separator + 1:]
        victim[-1] = victim[-1].strip() #removal of trailing '\r' - when launched from .sh
        return (parsed_args, victim)
    else: #nothing to launch, transformation mode
        args[-1] = args[-1].strip() #removal of trailing '\r' - when launched from .sh
        parsed_args = parser.parse_args(args)
        if parsed_args.input:
            if not parsed_args.output:
                parsed_args.output = parsed_args.input
            return (parsed_args, None)
        print "--input argument is required for transformation mode."
        parser.print_help()
        sys.exit(-1)

def main():
    (args, victim) = parse_args(sys.argv[1:]) #skipping the script name
    if victim:
        launch(args, victim)
    else:
        if args.input.endswith(".xml"):
            transform_etw_xml(args)
        else:
            transform(args)

def os_lib_ext():
    if sys.platform == 'win32':
        return '.dll'
    elif sys.platform == 'darwin':
        return '.dylib'
    elif 'linux' in sys.platform:
        return '.so'
    assert(not "Unsupported platform")

class FTrace:
    def __init__(self, args, remote):
        self.args = args
        self.file = args.output + ".ftrace"
        self.remote = remote

    def echo(self, what, where):
        try:
            if self.remote:
                self.remote.execute('echo %s > %s' % (what, where))
            else:
                with open(where, "w") as file:
                    file.write(what)
        except:
            return False
        return True

    def start(self):
        self.echo("0", "/sys/kernel/debug/tracing/tracing_on")
        self.echo("", "/sys/kernel/debug/tracing/trace") #cleansing ring buffer (we need it's header only)
        if self.remote:
            Popen('%s "cat /sys/kernel/debug/tracing/trace > %s"' % (self.remote.execute_prefix, self.file), shell=True).wait()
            self.proc = Popen('%s "cat /sys/kernel/debug/tracing/trace_pipe >> %s"' % (self.remote.execute_prefix, self.file), shell=True)
        else:
            Popen('cat /sys/kernel/debug/tracing/trace > %s' % self.file, shell=True).wait()
            self.proc = Popen('cat /sys/kernel/debug/tracing/trace_pipe >> %s' % self.file, shell=True)
        self.echo("*:*", "/sys/kernel/debug/tracing/set_event") #enabling all events
        self.echo("1", "/sys/kernel/debug/tracing/tracing_on")

    def stop(self):
        self.echo("0", "/sys/kernel/debug/tracing/tracing_on")
        self.proc.wait()
        return self.file

def start_ftrace(args, remote = None):
    ftrace = FTrace(args, remote)
    if not ftrace.echo("nop", "/sys/kernel/debug/tracing/current_tracer"):
        print "Warning: failed to access ftrace subsystem"
        return None
    ftrace.start()
    return ftrace

class ETWTrace:
    def __init__(self, args):
        self.file = args.output + ".etl"

    def start(self):
        process = Popen('logman start "NT Kernel Logger" -p "Windows Kernel Trace" (process,thread,cswitch) -ct perf -o "%s" -ets' % (self.file), shell=True)
        process.wait()
        return 0 == process.returncode

    def stop(self):
        Popen('logman stop "NT Kernel Logger" -ets', shell=True).wait()
        return self.file

def start_etw(args):
    trace = ETWTrace(args)
    return trace if trace.start() else None

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
    trace = remote.execute('mktemp -d' + (' -t SEA_XXX'if 'darwin' in unix.lower() else '')).strip()
    print ':', trace

    output = args.output
    args.output = trace + '/nop'

    print 'Starting ftrace...'
    ftrace = start_ftrace(args, remote)
    print 'Executing:', ' '.join(victim), '...'
    print remote.execute("%s=%s INTEL_SEA_SAVE_TO=%s/pid %s %s" % (load_lib, target, trace, ('INTEL_SEA_VERBOSE=1' if args.verbose else ''), ' '.join(victim)))
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
        args.trace = glob(os.path.join(local_tmp, '*', 'nop.ftrace'))[0]
    output = transform(args)
    output = join_output(args, output)
    shutil.rmtree(local_tmp)
    print "result:", output


def launch(args, victim):
    if args.ssh:
        return launch_remote(args, victim)
    env={}
    script_dir = os.path.abspath(args.bindir) if args.bindir else os.path.dirname(os.path.realpath(__file__))
    paths = []
    macosx = sys.platform == 'darwin'
    for bits in (['32', '64'] if not macosx else ['']):
        search = os.path.sep.join([script_dir, "*IntelSEAPI" + bits + os_lib_ext()])
        files = glob(search)
        if not len(files):
            print "Error: didn't find any files for:", search
            sys.exit(-1)
        paths.append(files[0])
    if macosx:
        env["DYLD_INSERT_LIBRARIES"] = paths[0]
    else:
        env["INTEL_LIBITTNOTIFY32"] = paths[0]
        env["INTEL_LIBITTNOTIFY64"] = paths[1]

    env["INTEL_SEA_FEATURES"] = os.environ['INTEL_SEA_FEATURES'] if os.environ.has_key('INTEL_SEA_FEATURES') else ""
    env["INTEL_SEA_FEATURES"] += (" " + str(args.format)) if args.format else ""
    env["INTEL_SEA_FEATURES"] += " stacks" if args.stacks else ""

    if args.output:
        env["INTEL_SEA_SAVE_TO"] = args.output

    if (args.dry):
        for key, val in env.iteritems():
            if val:
                print key + "=" + val
        return

    if args.verbose:
        print "Running:", victim
        print "Environment:", str(env)

    new_env = dict(os.environ)
    new_env.update(env)
    env = new_env

    if 'kernelshark' in args.format:
        victim = 'trace-cmd record -e IntelSEAPI/* ' + victim

    tracer = None
    if ('gt' in args.format and args.output):
        if 'linux' in sys.platform:
            tracer = start_ftrace(args)
        elif 'win32' == sys.platform:
            tracer = start_etw(args)

    proc = Popen(victim, env=env, shell=False, cwd=args.dir)
    proc.wait()
    if tracer:
        args.trace = tracer.stop()
    if args.output:
        args.input = "%s-%d" % (args.output, proc.pid)
        output = transform(args)
        output = join_output(args, output)
        print "result:", output

def join_output(args, output):
    google_traces = [item for item in output if os.path.splitext(item)[1] in ['.json','.ftrace']]
    if google_traces:
        res = GoogleTrace.join_traces(google_traces, args.output)
        output = list(set(output) - set(google_traces)) + [res]
    return output


def extract_cut(filename):
    return (filename.split("!")[1].split("-")[0]) if ('!' in filename) else None

def default_tree():
    return {"strings":{}, "domains": {}, "threads":{}, "groups":{}, "modules":{}, "ring_buffer": False, "cuts":set()}

def sea_reader(folder): #reads the structure of .sea format folder into dictionary
    tree = default_tree()
    pos = folder.rfind("-") #pid of the process is encoded right in the name of the folder
    tree["pid"] = int(folder[pos+1:])
    folder = folder.replace("\\", "/").rstrip("/")
    toplevel = os.walk(folder).next()
    for filename in toplevel[2]:
        with open("/".join([folder, filename]), "r") as file:
            if filename.endswith(".str"): #each string_handle_create writes separate file, name is the handle, content is the value
                tree["strings"][int(filename.replace(".str", ""))] = file.readline()
            elif filename.endswith(".tid"): #named thread makes record: name is the handle and content is the value
                tree["threads"][filename.replace(".tid", "")] = file.readline()
            elif filename.endswith(".pid"): #named groups (pseudo pids) makes record: group is the handle and content is the value
                tree["groups"][filename.replace(".pid", "")] = file.readline()
            elif filename.endswith(".mdl"): #registered modules - for symbol resolving
                tree["modules"][int(filename.replace(".mdl", ""))] = file.readline().split()
            elif filename == "process.dct": #process info
                tree["process"] = eval(file.read())
    for domain in toplevel[1]:#data from every domain gets recorded into separate folder which is named after the domain name
        tree["domains"][domain] = {"files":[]}
        for file in os.walk("/".join([folder, domain])).next()[2]: #each thread of this domain has separate file with data
            if not file.endswith(".sea"):
                print "Warning: weird file found:", file
                continue
            filename = file[:-4]

            tree["ring_buffer"] = tree["ring_buffer"] or ('-' in filename)
            tid = int(filename.split("!")[0].split("-")[0])
            tree["cuts"].add(extract_cut(filename))

            tree["domains"][domain]["files"].append((tid, "/".join([folder, domain, file])))
        def time_sort(item):
            with open(item[1], "rb") as file:
                tuple = read_chunk_header(file)
                return tuple[0]
        tree["domains"][domain]["files"].sort(key=time_sort)
    return tree

g_progress_interceptor = None

class Progress:
    def __init__(self, total, steps, message = ""):
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


def read_chunk_header(file):
    chunk = file.read(10) #header of the record, see STinyRecord in Recorder.cpp
    if chunk == '':
        return (0,0,0)
    return struct.unpack('Qbb', chunk)

def transform(args):
    if args.verbose:
        print "Transform:", str(args)
    tree = sea_reader(args.input) #parse the structure
    if args.cuts and args.cuts == ['all']:
        return transform2(args, tree)
    else:
        result = []
        output = args.output[:] #deep copy
        for current_cut in tree['cuts']:
            if args.cuts and current_cut not in args.cuts:
                continue
            args.output = (output + "!" + current_cut) if current_cut else output
            print "Cut #", current_cut if current_cut else "<None>"
            def skip_fn(path):
                filename = os.path.split(path)[1]
                if current_cut: #read only those having this cut name in filename
                    if current_cut != extract_cut(filename[:-4]):
                        return True
                else: #reading those haveing not cut name in filename
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
        self.callbacks = [] #while parsing we might have one to many 'listeners' - output format writers
        if "qt" in args.format:
            self.callbacks.append(QTProfiler(args, tree))
        if "gt" in args.format:
            self.callbacks.append(GoogleTrace(args, tree))
        if "fd" in args.format:
            self.callbacks.append(FrameDebugger(args, tree))
        if "btf" in args.format:
            self.callbacks.append(BestTraceFormat(args, tree))
        if "gv" in args.format:
            self.callbacks.append(GraphViz(args, tree))
        if "dgml" in args.format:
            self.callbacks.append(DGML(args, tree))
        self.get_limits()

    def is_empty(self):
        return 0 == len(self.callbacks)

    def __enter__(self):
        [callback.__enter__() for callback in self.callbacks]
        return self

    def __exit__(self, type, value, traceback):
        [callback.__exit__(type, value, traceback) for callback in self.callbacks] #emulating 'with' statement
        return False

    def on_event(self, type, data):
        if self.check_time_in_limits(data['time']):
            #copy here as handler can change the data for own good - this shall not affect other handlers
            [callback(type, data.copy()) for callback in self.callbacks]

    def get_result(self):
        res = []
        for callback in self.callbacks:
            res += callback.get_targets()
        return res

    def check_time_in_limits(self, time):
        left, right = self.limits
        if left != None and time < left:
            return False
        if right != None and time > right:
            return False
        return True

    def get_limits(self):
        left_limit = None
        right_limit = None
        if self.args.limit:
            limits = self.args.limit.split(":")
            if limits[0]:
                left_limit = int(limits[0])
            if limits[1]:
                right_limit = int(limits[1])
        self.limits = (left_limit, right_limit)


class FileWrapper:
    def __init__(self, path, args, tree, domain, tid):
        self.args = args
        self.tree = tree
        self.domain = domain
        self.tid = tid
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

    def read(self):
        call = {"tid": self.tid, "pid": self.tree["pid"], "domain": self.domain}

        tuple = read_chunk_header(self.file)
        if tuple == (0,0,0): #mem mapping wasn't trimed on close, zero padding goes further
            return None
        call["time"] = tuple[0]

        assert(tuple[1] < len(TaskTypes)); #sanity check
        call["type"] = tuple[1]

        flags = tuple[2]
        if flags & 0x1: #has id
            chunk = self.file.read(2*8)
            call["id"] = struct.unpack('QQ', chunk)[0]
        if flags & 0x2: #has parent
            chunk = self.file.read(2*8)
            call["parent"] = struct.unpack('QQ', chunk)[0]
        if flags & 0x4: #has string
            chunk = self.file.read(8)
            str_id = struct.unpack('Q', chunk)[0] #string handle
            call["str"] = self.tree["strings"][str_id]
        if flags & 0x8: #has tid, that differs from the calling thread (virtual tracks)
            chunk = self.file.read(8)
            call["tid"] = int(struct.unpack('q', chunk)[0])

        if flags & 0x10: #has data
            chunk = self.file.read(8)
            length = struct.unpack('Q', chunk)[0]
            call["data"] = self.file.read(length)

        if flags & 0x20: #has delta
            chunk = self.file.read(8)
            call["delta"] = struct.unpack('d', chunk)[0]

        if flags & 0x40: #has pointer
            chunk = self.file.read(8)
            ptr = struct.unpack('Q', chunk)[0]
            if not resolve_pointer(self.args, self.tree, ptr, call):
                call["pointer"] = ptr

        if flags & 0x80: #has pseudo pid
            chunk = self.file.read(8)
            call["pid"] = struct.unpack('q', chunk)[0]

        return call

def transform2(args, tree, skip_fn = None):
    with Callbacks(args, tree) as callbacks:
        if callbacks.is_empty():
            return callbacks.get_result()

        files = []
        for domain, content in tree["domains"].iteritems(): #go thru domains
            for tid, path in content["files"]: #go thru per thread files
                if skip_fn and skip_fn(path): #for "cut" support
                    continue
                files.append(FileWrapper(path, args, tree, domain, tid))

        if args.verbose:
            print path
            progress = DummyWith()
        else:
            progress = Progress(sum([file.get_size() for file in files]), 50, "Translation: " + os.path.basename(args.input))

        with progress:
            count = 0
            while True: #records iteration
                record = None
                earliest = None
                for file in files:
                    rec = file.get_record()
                    if not rec: #finished
                        continue
                    if not record or rec['time'] < record['time']:
                        record = rec
                        earliest = file
                if not record: ##all finished
                    break
                earliest.next()

                if args.verbose:
                    print "%d\t%s\t%s" % (count, TaskTypes[record['type']], record)
                elif count % ProgressConst == 0:
                    progress.tick(sum([file.get_pos() for file in files]))
                callbacks.on_event(TaskTypes[record['type']], record)
                count += 1
        for callback in callbacks.callbacks:
            callback("metadata_add", {'domain':'IntelSEAPI', 'str':'__process__', 'pid':tree["pid"], 'tid':-1, 'delta': -1})
            for pid, name in tree['groups'].iteritems():
                callback("metadata_add", {'domain':'IntelSEAPI', 'str':'__process__', 'pid':int(pid), 'tid':-1, 'delta': -1, 'data': name})

    return callbacks.get_result()

def get_module_by_ptr(tree, ptr):
    keys = list(tree['modules'].iterkeys())
    keys.sort() #looking for first bigger the address, previous is the module we search for
    item = keys[0]
    for key in keys[1:]:
        if key > ptr:
            break;
        item = key
    module = tree['modules'][item]
    if item < ptr < item + int(module[1]):
        return (item, module[0])
    else:
        return (None, None)

def resolve_pointer(args, tree, ptr, call, cache = {}):
    if not cache.has_key(ptr):
        (load_addr, path) = get_module_by_ptr(tree, ptr)
        if path == None or not os.path.exists(path):
            return False
        if sys.platform == 'win32':
            script_dir = os.path.abspath(args.bindir) if args.bindir else os.path.dirname(os.path.realpath(__file__))
            executable = os.path.sep.join([script_dir, 'TestIntelSEAPI32.exe'])
            cmd = "%s %s:%d" % (executable, path, ptr-load_addr)
        elif sys.platform == 'darwin':
            cmd = "atos -o %s -l %s %s" % (path, to_hex(load_addr), to_hex(ptr))
        elif 'linux' in sys.platform:
            cmd = "addr2line %s -e %s -i -p -f -C" % (to_hex(ptr), path)
        else:
            assert(not "Unsupported platform!")

        env=dict(os.environ)
        if env.has_key("INTEL_SEA_VERBOSE"):
            del env["INTEL_SEA_VERBOSE"]
        proc = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE, env=env)

        (symbol, err) = proc.communicate()

        cache[ptr] = {'module': path, 'symbol': symbol}
        assert(not err)
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
            (call['__file__'], call['__line__']) = parts[1].split(") (")[1].split(':')
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
        frames = struct.unpack('Q'*(len(data)/8), data)
    else:
        frames = struct.unpack('I'*(len(data)/4), data)
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
D3D11_DEPTH_STENCILOP_DESC.SIZE = 4*4

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
    OWN_SIZE = 4*4+2 #Before start of other structures 4 Longs, 2 Chars
    (DepthEnable, DepthWriteMask, DepthFunc, StencilEnable, StencilReadMask, StencilWriteMask) = struct.unpack('LLLLBB', data[:OWN_SIZE])
    pos = OWN_SIZE + 2 #+2 for alignment because of 2 chars before
    FrontFace = D3D11_DEPTH_STENCILOP_DESC(data[pos : pos + D3D11_DEPTH_STENCILOP_DESC.SIZE])
    pos += D3D11_DEPTH_STENCILOP_DESC.SIZE
    BackFace = D3D11_DEPTH_STENCILOP_DESC(data[pos : pos + D3D11_DEPTH_STENCILOP_DESC.SIZE])
    return {'DepthEnable': DepthEnable, 'DepthWriteMask':DepthWriteMask, 'DepthFunc':DepthFunc, 'StencilEnable':StencilEnable, 'StencilReadMask':StencilReadMask, 'StencilWriteMask':StencilWriteMask, 'FrontFace': FrontFace, 'BackFace': BackFace};
D3D11_DEPTH_STENCIL_DESC.SIZE = 4*4 + 2 + 2 + 2*D3D11_DEPTH_STENCILOP_DESC.SIZE

struct_decoders = {
    'D3D11_DEPTH_STENCIL_DESC': D3D11_DEPTH_STENCIL_DESC,
    'D3D11_DEPTH_STENCILOP_DESC': D3D11_DEPTH_STENCILOP_DESC
}

def represent_data(name, data):
    for key in struct_decoders.iterkeys():
        if key in name:
            return struct_decoders[key](data)
    if (all(31 < ord(chr) < 128 for chr in data)): #string we will show as string
        return data
    return binascii.hexlify(data) #the rest as hex buffer

class TaskCombiner:
    disable_handling_leftovers = False
    def __enter__(self):
        return self
    def __exit__(self, type, value, traceback):
        self.handle_leftovers()
        self.finish()
        return False

    def __init__(self, tree):
        self.no_begin = [] #for the ring buffer case when we get task end but no task begin
        self.time_bounds = [2**64, 0] #left and right time bounds
        self.tree = tree
        self.domains = {}
        self.events = []
        self.event_map = {}
        self.prev_sample = 0
        self.memory = {}

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
                self.flush_counters(threads, {'tid':0, 'pid': self.tree['pid'], 'domain': domain})

    def __call__(self, fn, data):
        domain = self.domains.setdefault(data['domain'], {'tasks': {}, 'counters':{}})
        thread = domain['tasks'].setdefault(data['tid'], {'byid':{}, 'stack':[], 'args': {}})

        def get_tasks(id):
            if not id:
                return thread['stack']
            return thread['byid'].setdefault(id, [])

        def get_task(id):
            if id:
                tasks = get_tasks(id)
                if not tasks: #they can be stacked
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
            for thread_stacks in domain['tasks'].itervalues(): #look in all threads
                if thread_stacks['byid'].has_key(id) and thread_stacks['byid'][id]:
                    return thread_stacks['byid'][id][-1]
                else:
                    for item in thread_stacks['stack']:
                        if item.has_key('id') and item['id'] == id:
                            return item

        def current_task(tid):
            candidates = []
            for domain in self.domains.itervalues():
                if not domain['tasks'].has_key(tid):
                    continue
                thread = domain['tasks'][tid]
                for byid in thread['byid'].itervalues():
                    if byid:
                        candidates.append(byid[-1])
                if thread['stack']:
                    candidates.append(thread['stack'][-1])
            candidates.sort(key=lambda item: item['time'])
            return candidates[-1] if candidates else None

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
            if data.has_key('delta'):
                self.time_bounds[0] = min(self.time_bounds[0], data['time'])
                end = data.copy()
                end['time'] = data['time'] + data['delta']
                if not (data.has_key('str') or data.has_key('pointer')):
                    data['str'] = 'Unknown'
                if data.has_key('id') and thread['args'].has_key(data['id']):
                    data['args'] = thread['args'][data['id']]
                    del thread['args'][data['id']]
                self.time_bounds[1] = max(self.time_bounds[1], end['time'])
                self.complete_task("task", data, end)
            else:
                self.time_bounds[1] = max(self.time_bounds[1], data['time'])
                tasks = get_tasks(None if fn == "task_end" else data['id'])
                index = get_last_index(tasks, data['type'] - 1)
                if index != None:
                    item = tasks.pop(index)
                    self.complete_task("task", item, data)
                else:
                    assert(self.tree["ring_buffer"] or self.tree['cuts'])
                    if data.has_key('str'): #nothing to show without name
                        self.no_begin.append(data)
        elif fn == "frame_begin":
            get_tasks(data['id'] if data.has_key('id') else None).append(data)
        elif fn == "frame_end":
            frames = get_tasks(data['id'] if data.has_key('id') else None)
            index = get_last_index(frames, 7)
            if index != None:
                item = frames.pop(index)
                self.complete_task("frame", item, data)
            else:
                assert(self.tree["ring_buffer"] or self.tree['cuts'])
        elif fn=="metadata_add":
            if data.has_key('id'):
                task = get_task(data['id'])
                if task:
                    args = task.setdefault('args', {})
                else:
                    args = thread['args'].setdefault(data['id'], {})

                args[data['str']] = data['delta'] if data.has_key('delta') else represent_data(data['str'], data['data']) if data.has_key('data') else '0x0'
            else:#global metadata
                self.global_metadata(data)
        elif fn == "object_snapshot":
            if data.has_key('args'):
                args = data['args'].copy()
            else:
                args = {'snapshot':{}}
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
                    item['type'] = 7 #frame_begin
                    item['domain'] += ".continuous_markers"
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
                    counter_name = data['str']
                    prev_value = 0.
                    if self.memory.has_key(counter_name):
                        prev_value = self.memory[counter_name]
                    delta = data['delta'] - prev_value #data['delta'] has current value of the counter
                    self.memory[counter_name] = data['delta']
                    current = current_task(data['tid'])
                    if current:
                        values = current.setdefault('memory',{}).setdefault(counter_name, [])
                        values.append(delta)
                self.complete_task(fn, data, data)
        elif fn == "relation":
            self.relation(
                data,
                get_task(data['id'] if data.has_key('id') else None),
                get_task(data['parent']) or find_task(data['parent'])
            )
        else:
            assert(not "Unsupported type:" + fn)

    def flush_counters(self, domain, data):
        for name, counter in domain['counters'].iteritems():
            common_data = data.copy()
            common_data['time'] = counter['begin'] + (counter['end'] - counter['begin']) / 2
            common_data['str'] = name
            common_data['delta'] = sum(counter['values']) / len(counter['values'])
            self.complete_task('counter', common_data, common_data)

def to_hex(value):
    return "0x" + hex(value).rstrip('L').replace("0x", "").upper()

MAX_GT_SIZE = 50*1024*1024
GT_FLOAT_TIME = False

class GoogleTrace(TaskCombiner):
    def __init__(self, args, tree):
        TaskCombiner.__init__(self, tree)
        self.args = args
        self.target_scale_start = 0
        self.source_scale_start = 0
        self.ratio = 1 / 1000. #nanoseconds to microseconds
        self.size_keeper = None
        self.targets = []
        self.trace_number = 0
        self.counters = {}
        self.frames = {}
        self.samples = []
        if self.args.trace:
            if self.args.trace.endswith(".etl"):
                self.handle_etw_trace(self.args.trace)
            else:
                self.args.sync = self.handle_ftrace(self.args.trace)
        self.start_new_trace()

    def start_new_trace(self):
        self.targets.append("%s-%d.json" % (self.args.output, self.trace_number))
        self.trace_number += 1
        self.file = open(self.targets[-1], "w")
        self.file.write('{')
        if self.args.sync:
            self.apply_time_sync(self.args.sync)
        self.file.write('\n"traceEvents": [\n')

        for key, value in self.tree["threads"].iteritems():
            pid_tid = key.split(',')
            self.file.write(
                '{"name": "thread_name", "ph":"M", "pid":%s, "tid":%s, "args": {"name":"%s(%s)"}},\n' % (pid_tid[0], pid_tid[1], value, pid_tid[1])
            )

    def get_targets(self):
        return self.targets

    def convert_time(self, time):
        return (time - self.source_scale_start) * self.ratio + self.target_scale_start

    @staticmethod
    def read_ftrace_lines(trace, time_sync):
        write_chrome_time_sync = True
        with open(trace) as file:
            count = 0
            with Progress(os.path.getsize(trace), 50, "Loading ftrace") as progress:
                for line in file:
                    if 'IntelSEAPI_Time_Sync' in line:
                        parts = line.split()
                        time_sync.append((float(parts[-4].strip(":")), int(parts[-1]))) #target (ftrace), source (nanosecs)
                        if write_chrome_time_sync: #chrome time sync, pure zero doesn't work, so we shift on very little value
                            yield "%strace_event_clock_sync: parent_ts=%s\n" % (line.split("IntelSEAPI_Time_Sync")[0], line.split(":")[-4].split()[-1])
                            write_chrome_time_sync = False #one per trace is enough
                    else:
                        yield line
                    if count % ProgressConst == 0:
                        progress.tick(file.tell())
                    count += 1

    def handle_ftrace(self, trace):
        time_sync = []
        self.targets.append(self.args.output + '.cut.ftrace')
        with open(self.targets[-1], 'w') as file:
            for line in GoogleTrace.read_ftrace_lines(trace, time_sync):
                if line.startswith('#') or 0 < len(time_sync) < 10: #we don't need anything outside proc execution but comments
                    file.write(line)
        return time_sync

    def handle_etw_trace(self, trace):
        assert(not "Implemented")

    def apply_time_sync(self, time_sync):
        if len(time_sync) < 2: #too few markers to sync
            return
        Target = 0
        Source = 1
        #looking for closest time points to calculate start points
        diffs = []
        for i in range(1, len(time_sync)):
            diff = (time_sync[i][Target] - time_sync[i-1][Target], time_sync[i][Source] - time_sync[i-1][Source])
            diffs.append((diff, i))
        diffs.sort()
        (diff, index) = diffs[0] #it's the width between two closest measurements

        #source measurement is the fisrt, target is second
        #Target time is always after the source, due to workflow
        #one measurement is begin -> begin and another is end -> end
        #if nothing interferes begin -> begin measurement should take same time as end -> end

        #run 1: most ballanced case - everything is even
        #S   /b  |  |  I  /e
        #T          /b  I  |  |  /e

        #run 2: takes more time after Target measurement
        #S   /b  |  |  I  /e
        #T      /b  I  |  |  /e

        #run 3: takes more time before Targer measurement
        #S   /b  |  |  I  /e
        #T              /b  I  |  |  /e

        #From these runs obvious that in all cases the closest points (I) of global timeline are:
        #   Quater to end of Source and Quater after begin of Target
        self.source_scale_start = time_sync[index - 1][Source] + int(diff[Source] * 0.75) #to keep the precision
        self.target_scale_start = (time_sync[index - 1][Target] + (diff[Target] * 0.25)) * 1000000. #multiplying by 1000000. to have time is microseconds (ftrace/target time was in seconds)

        print "Timelines correlation precision is +- %f us" % (diff[Target] / 2. * 1000000.)

        #taking farest time points to calculate frequencies
        diff = (time_sync[-1][Target] - time_sync[0][Target], time_sync[-1][Source] - time_sync[0][Source])
        self.ratio = 1000000. * diff[Target] / diff[Source] # when you multiply Source value with this ratio you get Target units, multiplying by 1000000. to have time is microseconds (ftrace/target time was in seconds)

    def global_metadata(self, data):
        if data['str'] == "__process__": #this is the very first record in the trace
            if data.has_key('data'):
                self.file.write(
                    '{"name": "process_name", "ph":"M", "pid":%d, "tid":%s, "args": {"name":"%s"}},\n' % (data['pid'], data['tid'], data['data'].replace("\\", "\\\\"))
                )
            if data.has_key('delta'):
                self.file.write(
                    '{"name": "process_sort_index", "ph":"M", "pid":%d, "tid":%s, "args": {"sort_index":%d}},\n' % (data['pid'], data['tid'], data['delta'])
                )
            if data['tid'] >= 0 and not self.tree['threads'].has_key('%d,%d' % (data['pid'], data['tid'])): #marking the main thread
                self.file.write(
                    '{"name": "thread_name", "ph":"M", "pid":%d, "tid":%s, "args": {"name":"%s"}},\n' % (data['pid'], data['tid'], "<main>")
                )

    def relation(self, data, head, tail):
        if not head or not tail:
            return
        items = sorted([head, tail], key=lambda item: item['time']) #we can't draw lines in backward direction, so we sort them by time
        if GT_FLOAT_TIME:
            template = '{"ph":"%s", "name": "relation", "pid":%d, "tid":%s, "ts":%.3f, "id":%s, "args":{"name": "%s"}, "cat":"%s"},\n'
        else:
            template = '{"ph":"%s", "name": "relation", "pid":%d, "tid":%s, "ts":%d, "id":%s, "args":{"name": "%s"}, "cat":"%s"},\n'
        if not data.has_key('str'):
            data['str'] = "unknown"
        self.file.write(template % ("s", items[0]['pid'], items[0]['tid'], self.convert_time(items[0]['time']), data['parent'], data['str'], data['domain']))
        self.file.write(template % ("f", items[1]['pid'], items[1]['tid'], self.convert_time(items[1]['time']), data['parent'], data['str'], data['domain']))

    def format_value(self, arg): #this function must add quotes if value is string, and not number/float, do this recursively for dictionary
        if type(arg) == type({}):
            return "{" + ", ".join(['"%s":%s' % (key, self.format_value(value)) for key, value in arg.iteritems()]) + "}"
        try:
            val = float(arg)
            if float('inf') != val:
                if val.is_integer():
                    return int(val)
                else:
                    return val
        except:
            pass
        return '"%s"' % str(arg).replace("\\", "\\\\")

    Phase = {'task':'X', 'counter':'C', 'marker':'i', 'object_new':'N', 'object_snapshot':'O', 'object_delete':'D', 'frame':'X'}

    def complete_task(self, type, begin, end):
        assert(GoogleTrace.Phase.has_key(type))
        if begin['type'] == 7: #frame_begin
            begin['id'] = begin['tid'] if begin.has_key('tid') else 0 #Async events are groupped by cat & id
            res = self.format_task('b', 'frame', begin, {})
            res += [',\n']
            end_begin = begin.copy()
            end_begin['time'] = end['time']
            res += self.format_task('e', 'frame', end_begin, {})
        else:
            res = self.format_task(GoogleTrace.Phase[type], type, begin, end)

        if not res:
            return
        if type in ['task', 'counter'] and begin.has_key('data') and begin.has_key('str'): #FIXME: move closer to the place where stack is demanded
            self.handle_stack(begin, resolve_stack(self.args, self.tree, begin['data']), begin['str'])
        if self.args.debug:
            res = "".join(res)
            try:
                json.loads(res)
            except Exception as exc:
                print "\n" + exc.message + ":\n" + res + "\n"
            res += ',\n'
        else:
            res = "".join(res + [',\n'])
        self.file.write(res)
        if (self.file.tell() > MAX_GT_SIZE):
            self.finish()
            self.start_new_trace()

    def handle_stack(self, task, stack, name='stack'):
    	if not stack:
    		return
        parent = None
        for frame in reversed(stack): #going from parents to childs
            if parent == None:
                frame_id = '%d' % frame['ptr']
            else:
                frame_id = '%d:%s' % (frame['ptr'], parent)
            if not self.frames.has_key(frame_id):
                data = {'category': os.path.basename(frame['module']), 'name': frame['str']}
                if parent != None:
                    data['parent'] = parent
                self.frames[frame_id] = data
            parent = frame_id
        time = self.convert_time(task['time'])
        self.samples.append({
            'tid': task['tid'],
            'ts': time if GT_FLOAT_TIME else int(time),
            'sf': frame_id, 'name':name
        })

    Markers = {
        "unknown":"t",
        "global":"g",
        "track_group":"p",
        "track":"t",
        "task":"t",
        "marker":"t"
    }

    def format_task(self, phase, type, begin, end):
        res = []
        res.append('{"ph":"%s"' % (phase))
        res.append(', "pid":%(pid)d' % begin)
        if begin.has_key('tid'):
            res.append(', "tid":%(tid)d' % begin)
        if GT_FLOAT_TIME:
            res.append(', "ts":%.3f' % (self.convert_time(begin['time'])))
        else:
            res.append(', "ts":%d' % (self.convert_time(begin['time'])))
        if "counter" == type: #workaround of chrome issue with forgetting the last counter value
            self.counters.setdefault(begin['domain'], {})[begin['str']] = begin #remember the last counter value
        if "marker" == type:
            name = begin['str']
            res.append(', "s":"%s"' % (GoogleTrace.Markers[begin['data']]))
        elif "object_" in type:
            if begin.has_key('str'):
                name = begin['str']
            else:
                name = ""
        elif "frame" == type:
            if begin.has_key('str'):
                name = begin['str']
            else:
                name = begin['domain']
        else:
            if type not in ["counter", "task", "overlapped"]:
                name = type + ":"
            else:
                name = ""

            if begin.has_key('parent'):
                name += to_hex(begin['parent']) + "->"
            if begin.has_key('str'):
                name += begin['str'] + ":"
            if begin.has_key('pointer'):
                name += "func<"+ to_hex(begin['pointer']) + ">:"
            if begin.has_key('id') and type != "overlapped":
                name += "(" + to_hex(begin['id']) + ")"
            else:
                name = name.rstrip(":")

        assert(name or "object_" in type)
        res.append(', "name":"%s"' % (name))
        res.append(', "cat":"%s"' % (begin['domain']))

        if begin.has_key('id'):
            res.append(', "id":%s' % (begin['id']))
        if type in ['task']:
            dur = self.convert_time(end['time']) - self.convert_time(begin['time'])
            if GT_FLOAT_TIME:
                res.append(', "dur":%.3f' % (dur))
            else:
                if dur < self.args.min_dur:
                    return [] # google misbehaves on tasks of 0 length
                res.append(', "dur":%d' % (dur))
        args = {}
        if begin.has_key('args'):
            args = begin['args'].copy()
        if end.has_key('args'):
            args.update(end['args'])
        if begin.has_key('__file__'):
            args["__file__"] = begin["__file__"]
            args["__line__"] = begin["__line__"]
        if 'counter' == type:
            args[name] = begin['delta']
        if begin.has_key('memory'):
            total = 0
            breakdown = {}
            for name, values in begin['memory'].iteritems():
                size = int(name.split('<')[1].split('>')[0])
                all = sum(values)
                total += size * all
                if all:
                    breakdown[size] = all
            breakdown['TOTAL'] = total
            args['CRT:Memory'] = breakdown
        if args:
            res.append(', "args":')
            res.append(self.format_value(args))
        res.append('}');
        return res

    def handle_leftovers(self):
        TaskCombiner.handle_leftovers(self)
        for counters in self.counters.itervalues(): #workaround: google trace forgets counter last value
            for counter in counters.itervalues():
                counter['time'] += 1 #so, we repeat it on the end of the trace
                self.complete_task("counter", counter, counter)

    def finish(self):
        if self.samples:
            self.file.write('{}],\n"stackFrames":\n')
            self.file.write(json.dumps(self.frames))
            self.file.write(',\n"samples":\n')
            self.file.write(json.dumps(self.samples))
            self.file.write('}')
            self.samples = []
        else:
            self.file.write("{}]}")
        self.file.close()

    @staticmethod
    def join_traces(traces, output):
        import zipfile
        with zipfile.ZipFile(output + ".zip", 'w', zipfile.ZIP_DEFLATED, allowZip64 = True) as zip:
            count = 0
            with Progress(len(traces), 50, "Merging traces") as progress:
                ftrace = [] #ftrace files have to be joint by time: chrome reads them in unpredictable order and complains about time
                for file in traces:
                    if file.endswith('.ftrace'):
                        if 'merged.ftrace' != os.path.basename(file):
                            ftrace.append(file)
                    else:
                        progress.tick(count)
                        zip.write(file, os.path.basename(file))
                        count += 1
                if len(ftrace) > 0: #just concatenate all files in order of creation
                    if len(ftrace) == 1:
                        zip.write(ftrace[0], os.path.basename(ftrace[0]))
                    else:
                        ftrace.sort() #name defines sorting
                        merged = os.path.join(os.path.dirname(ftrace[0]), 'merged.ftrace')
                        with open(merged, 'w') as output_file:
                            for file_name in ftrace:
                                with open(file_name) as input_file:
                                    for line in input_file.readlines():
                                        output_file.write(line)
                                progress.tick(count)
                                count += 1
                        zip.write(merged, os.path.basename(merged))
        return output + ".zip"

def get_name(begin):
    if begin.has_key('str'):
        return begin['str']
    elif begin.has_key('pointer'):
        return "func<"+ to_hex(begin['pointer']) + ">"
    else:
        return "<unknown>"

class QTProfiler(TaskCombiner): #https://github.com/danimo/qt-creator/blob/master/src/plugins/qmlprofiler/qmlprofilertracefile.cpp https://github.com/danimo/qt-creator/blob/master/src/plugins/qmlprofiler/qv8profilerdatamodel.cpp
    def __init__(self, args, tree):
        TaskCombiner.__init__(self, tree)
        self.args = args
        self.file_name = self.get_targets()[-1]
        self.file = open(self.file_name, "w")
        self.notes = []
        self.start_time = None
        self.end_time = None

    def get_targets(self):
        return [self.args.output + ".qtd"]

    def set_times(self, start, end):
        if self.start_time is None:
            self.start_time = start
        else:
            self.start_time = min(start, self.start_time)
        if self.end_time is None:
            self.end_time = end
        else:
            self.end_time = max(end, self.end_time)

    def complete_task(self, type, begin, end):
        name = get_name(begin)

        details = (type + ":") if type != 'task' else ""
        if begin.has_key('parent'):
            details += to_hex(begin['parent']) + "->"
        details += name + ":"
        if begin.has_key('id'):
            details += "(" + to_hex(begin['id']) + ")"
        else:
            details = details.rstrip(":")

        if type == 'counter' or type == 'marker':
            kind = 'Painting'
        elif type == 'frame' or 'object_' in type:
            kind = 'Creating'
        else:
            kind = 'Javascript'

        pid_tid = "%d,%d" % (begin['pid'], begin['tid'])
        if self.tree["threads"].has_key(pid_tid):
            thread_name = '%s(%d)' % (self.tree["threads"][pid_tid], begin["tid"])
        else:
            thread_name = str(begin['tid'])

        record = (
            begin['__file__'].replace("\\", "/") if begin.has_key('__file__') else "",
            begin['__line__'] if begin.has_key('__line__') else "0",
            kind,
            "%s | %s | %s" % (details, thread_name, begin['domain']),
            name
        )
        record = tuple([cgi.escape(item) for item in record])

        if self.event_map.has_key(record):
            index = self.event_map[record]
        else:
            index = len(self.events)
            self.events.append(record)
            self.event_map[record] = index
        start_time = round(begin['time'] / 1000) #sad but it's limiter to milliseconds only
        end_time = round(end['time'] / 1000)
        dur = end_time - start_time
        if not dur or dur < 0: #QT Creator doesn't show notes on objects with zero duration
            dur = 1
        tag = '<range startTime="%d" duration="%d" eventIndex="%d"/>\n' % (start_time, dur, index)

        args = {}
        if type == "counter":
            args['value'] = begin['delta']
        if begin.has_key('args'):
            args = begin['args']
            if end.has_key('args'):
                args.update(end['args'])
        if args:
            self.notes.append((start_time, dur, index, args))

        self.set_times(start_time, end_time)
        self.file.write(tag)

    def write_header(self):
        #at this moment print is redirected to output file
        print '<?xml version="1.0" encoding="UTF-8"?>'
        print '<trace version="1.02" traceStart="%d" traceEnd="%d">' % (self.start_time, self.end_time)
        print '<eventData totalTime="%d">' % (self.end_time - self.start_time)
        counter = 0
        for event in self.events:
            print '<event index="%d"><filename>%s</filename><line>%s</line><type>%s</type><details>%s</details><displayname>%s</displayname></event>'\
                % (counter, event[0], event[1], event[2], event[3], event[4])
            counter += 1
        print '</eventData><profilerDataModel>'

    def write_footer(self, file):
        file.write('</profilerDataModel><noteData>\n')
        for note in self.notes:
            args = "\n".join([key + " = " + str(val).replace("{","").replace("}","") for key, val in note[3].iteritems()])
            file.write('<note startTime="%d" duration="%d" eventIndex="%d">%s</note>\n' % (note[0], note[1], note[2], cgi.escape(args)))
        file.write('</noteData><v8profile totalTime="0"/></trace>\n')

    def finish(self):
        import fileinput
        self.file.close()
        fi = fileinput.input(self.file_name, inplace=1)
        for line in fi:
            if fi.isfirstline():
                self.write_header()
            print line,
        with open(self.file_name, "a") as file:
            self.write_footer(file)

    @staticmethod
    def join_traces(traces, output): #TODO: implement progress
        import xml.dom.minidom as minidom
        output += ".qtd"
        with open(output, "w") as file: #FIXME: doesn't work on huge traces, consider using "iterparse" approach
            print >>file, '<?xml version="1.0" encoding="UTF-8"?>'
            traces = [minidom.parse(trace) for trace in traces] #parse all traces right away
            traceStarts = sorted([int(dom.documentElement.attributes['traceStart'].nodeValue) for dom in traces]) #earliest start time
            traceEnds = sorted([int(dom.documentElement.attributes['traceEnd'].nodeValue) for dom in traces], reverse = True)#latest end time
            print >>file, '<trace version="1.02" traceStart="%d" traceEnd="%d">' % (traceStarts[0], traceEnds[0])
            print >>file, '<eventData totalTime="%d">' % (traceEnds[0] - traceStarts[0])
            event_count = [] #accumulate event count to map indices
            for dom in traces: #first we go by events
                events = dom.getElementsByTagName('eventData')[0].getElementsByTagName('event')
                for event in events: #and correct each event index, adding count of events in previous files
                    index = int(event.attributes['index'].nodeValue) + sum(event_count)
                    event.setAttribute('index', str(index))
                    print >>file, event.toxml()
                event_count.append(len(events)) #for next traces to adjust index start
            print >>file, '</eventData><profilerDataModel>'
            index = 0
            for dom in traces:
                ranges = dom.getElementsByTagName('profilerDataModel')[0].getElementsByTagName('range')
                for range in ranges:
                    eventIndex = int(range.attributes['eventIndex'].nodeValue) + sum(event_count[:index])
                    range.setAttribute('eventIndex', str(eventIndex))
                    print >>file, range.toxml()
                index += 1
            print >>file, '</profilerDataModel><noteData>'
            index = 0
            for dom in traces:
                notes = dom.getElementsByTagName('noteData')[0].getElementsByTagName('note')
                for note in notes:
                    eventIndex = int(note.attributes['eventIndex'].nodeValue) + sum(event_count[:index])
                    note.setAttribute('eventIndex', str(eventIndex))
                    print >>file, note.toxml()
                index += 1
            print >>file, '</noteData><v8profile totalTime="0"/></trace>'
        return output

class FrameDebugger(TaskCombiner):
    def __init__(self, args, tree):
        TaskCombiner.__init__(self, tree)
        sefl.args = args
        self.file = open(self.get_targets()[-1], "w+b")
        self.file.write('name, time\n')

    def get_targets(self):
        return [self.args.output + ".gpa_csv"]

    def complete_task(self, type, begin, end):
        start_time = round(begin['time'] / 1000)
        end_time = round(end['time'] / 1000)
        self.file.write('%s, %d\n' % (begin['str'], round((end['time'] - begin['time']) / 1000)))

    def finish(self):
        self.file.close()

    @staticmethod
    def join_traces(traces, output):
        raise NotImplementedError()

class GraphCombiner(TaskCombiner):

    def __init__(self, args, tree):
        TaskCombiner.__init__(self, tree)
        self.args = args
        self.per_domain = {}
        self.relations = {}
        self.threads = set()

    def complete_task(self, type, begin, end):
        self.threads.add(begin['tid'])
        domain = self.per_domain.setdefault(begin['domain'], {'counters': {}, 'objects':{}, 'frames': {}, 'tasks': {}, 'markers': {}})
        if type == 'task':
            task = domain['tasks'].setdefault(get_name(begin), {'time': []})
            task['time'].append(end['time'] - begin['time'])
            if begin.has_key('__file__'):
                task['src'] = begin['__file__'] + ":" + begin['__line__']
            stack = self.domains[begin['domain']]['tasks'][begin['tid']]['stack']
            if len(stack):
                parent = stack[-1]
                self.add_relation({'label':'calls', 'from': self.make_id(parent['domain'], get_name(parent)), 'to': self.make_id(begin['domain'], get_name(begin))})
            else:
                self.add_relation({'label':'executes', 'from': self.make_id("threads", str(begin['tid'])), 'to': self.make_id(begin['domain'], get_name(begin)), 'color': 'gray'})
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

class DGML(GraphCombiner):
    def __init__(self, args, tree):
        GraphCombiner.__init__(self, args, tree)
        self.file = open(self.get_targets()[-1], "w+b")
        self.file.write("""<?xml version='1.0' encoding='utf-8'?>\n<DirectedGraph xmlns="http://schemas.microsoft.com/vs/2009/dgml">""")

    def get_targets(self):
        return [self.args.output + ".dgml"]

    def finish(self):
        self.file.write('<Nodes>\n')
        for domain, data in self.per_domain.iteritems():
            #counters
            for counter_name, counter_data in data['counters'].iteritems():
                id = self.make_id(domain, counter_name)
                self.file.write('<Node Id="%s" Label="%s" Min="%g" Max="%g" Avg="%g" Category="CodeSchema_Type"/>\n' % (id, cgi.escape(counter_name), min(counter_data), max(counter_data), sum(counter_data) / len(counter_data)))
            #tasks
            for task_name, task_data in data['tasks'].iteritems():
                id = self.make_id(domain, task_name)
                time = task_data['time']
                self.file.write('<Node Id="%s" Category="CodeSchema_Method" Label="%s" Min="%s" Max="%s" Avg="%s" Count="%d" Src="%s"/>\n' % (
                        id, cgi.escape(task_name),
                        format_time(min(time)), format_time(max(time)), format_time(sum(time) / len(time)), len(time),
                        task_data['src'].replace('\\','/') if task_data.has_key('src') else ""
                    )
                )
            self.file.write('<Node Id="%s" Label="%s" Category="CodeSchema_Namespace" Group="Expanded"/>\n' % (self.make_id("domain", domain), cgi.escape(domain)))
        #threads
        thread_names = self.tree['threads']
        for tid in self.threads:
            tid_str, tid_hex = str(tid), to_hex(tid)
            id = self.make_id("threads", tid_str)
            thread_name = thread_names[tid_str] if thread_names.has_key(tid_str) else ""
            self.file.write('<Node Id="%s" Label="%s(%s)"/>\n' % (id, cgi.escape(thread_name), tid_hex))

        self.file.write('</Nodes>\n')
        self.file.write('<Links>\n')

        #relations
        for relation in self.relations.itervalues():
            if not relation.has_key('color'):
                relation['color'] = 'black'
            self.file.write('<Link Source="{from}" Target="{to}" Category="CodeSchema_Calls"/>\n'.format(**relation))

        for domain, data in self.per_domain.iteritems():
            #counters
            for counter_name, counter_data in data['counters'].iteritems():
                self.file.write('<Link Source="%s" Target="%s" Category="Contains"/>\n' % (self.make_id("domain", domain), self.make_id(domain, counter_name)))
            #tasks
            for task_name, task_data in data['tasks'].iteritems():
                self.file.write('<Link Source="%s" Target="%s" Category="Contains"/>\n' % (self.make_id("domain", domain), self.make_id(domain, task_name)))

        self.file.write('</Links>\n')

        self.file.write("</DirectedGraph>\n")
        self.file.close()

    @staticmethod
    def join_traces(traces, output): #FIXME: implement real joiner
        sorting = []
        for trace in traces:
            sorting.append((os.path.getsize(trace), trace))
        sorting.sort(key=lambda (size, trace): size, reverse = True)
        shutil.copyfile(sorting[0][1], output+".dgml")
        return output+".dgml"

class GraphViz(GraphCombiner):
    def __init__(self, args, tree):
        GraphCombiner.__init__(self, args, tree)
        self.file = open(self.get_targets()[-1], "w+b")
        self.file.write("digraph G{\nedge [labeldistance=0];\nnode [shape=record];\n")

    def get_targets(self):
        return [self.args.output + ".gv"]

    def finish(self):
        cluster_index = 0
        clusters = {}
        for domain, data in self.per_domain.iteritems():
            cluster = clusters.setdefault(cluster_index, [])
            cluster.append('subgraph cluster_%d {\nlabel = "%s";' % (cluster_index, domain))
            #counters
            for counter_name, counter_data in data['counters'].iteritems():
                id = self.make_id(domain, counter_name)
                self.file.write('%s [label="{COUNTER: %s|min=%g|max=%g|avg=%g}"];\n' % (id, cgi.escape(counter_name), min(counter_data), max(counter_data), sum(counter_data) / len(counter_data)))
                cluster.append("%s;" % (id))
            #tasks
            for task_name, task_data in data['tasks'].iteritems():
                id = self.make_id(domain, task_name)
                time = task_data['time']
                self.file.write('%s [label="{TASK: %s|min=%s|max=%s|avg=%s|count=%d%s}"];\n' % (
                        id,
                        cgi.escape(task_name), format_time(min(time)), format_time(max(time)), format_time(sum(time) / len(time)), len(time),
                        (("|%s" % task_data['src'].replace('\\','/')) if task_data.has_key('src') else "")
                    )
                )
                cluster.append("%s;" % (id))
            #: {}, 'objects':{}, 'frames': {}, 'markers': {}
            cluster_index += 1
        #threads
        thread_names = self.tree['threads']
        for tid in self.threads:
            tid_str, tid_hex = str(tid), to_hex(tid)
            id = self.make_id("threads", tid_str)
            thread_name = thread_names[tid_str] if thread_names.has_key(tid_str) else ""
            self.file.write('%s [label="{THREAD: %s|%s}" color=gray fontcolor=gray];\n' % (id, tid_hex, cgi.escape(thread_name)))

        #clusters
        for _, cluster in clusters.iteritems():
            for line in cluster:
                self.file.write(line + "\n")
            self.file.write("}\n")
        #relations
        for relation in self.relations.itervalues():
            if not relation.has_key('color'):
                relation['color'] = 'black'
            self.file.write('edge [label="{label}" color={color} fontcolor={color}];\n{from}->{to};\n'.format(**relation))

        self.file.write("}\n")
        self.file.close()

    @staticmethod
    def join_traces(traces, output):
        with open(output + ".gv", 'wb') as outfile:
            outfile.write("digraph G{\n")
            index = 0
            for file in traces:
                index += 1
                with open(file, 'rb') as infile:
                    lines = infile.readlines()
                    del lines[0] #first line is digraph G{
                    del lines[-1] #last line is } #digraph G
                    for line in lines:
                        if line.startswith("subgraph cluster_"):
                            number = line.split('_')[1].split(' ')[0]
                            line = "subgraph cluster_%d%s {" % (index, number)
                        outfile.write(line)
            outfile.write("}\n")
        return output + ".gv"


###################################
# TODO: add OS events (sched/vsync)
class BestTraceFormat(TaskCombiner):
    """Writer for Best Trace Format.

    Specs for BTF v2.1.3: https://wiki.eclipse.org/images/e/e6/TA_BTF_Specification_2.1.3_Eclipse_Auto_IWG.pdf
    """
    def __init__(self, args, tree):
        """Open the .btf file and write its header."""
        TaskCombiner.__init__(self, tree)
        self.args = args
        self.file = open(self.get_targets()[-1], "w+b")
        self.file.write('#version 2.1.3\n')
        self.file.write('#creator GDP-SEA\n')
        self.file.write('#creationDate 2014-02-19T11:39:20Z\n')
        self.file.write('#timeScale ns\n')

    def get_targets(self):
        return [self.args.output + ".btf"]

    def complete_task(self, type, b, e):
        """
        type -- task type : {"task", "frame", "counter"}
        b -- { 'thread_name': '0x6296', 'domain': 'gles.trace.ergs', 'str': 'glPopMatrix', 'time': 1443097648250368731, 'tid': 25238, 'pid': 25238}
        e -- { 'tid': 25238, 'thread_name': '0x6296', 'domain': 'gles.trace.ergs', 'pid': 25238, 'time': 1443097648250548143}
        """
        # <Time>,<Source>,<SourceInstance >,<TargetType>,<Target>,<TargetInstance>,<Event>,<Note>
        if 'str' in b and type=="task":
            self.file.write("%d,%s,0,R,%s,-1,start\n" % (b['time'], b['str'],b['str']))
            self.file.write("%d,%s,0,R,%s,-1,terminate\n" % (e['time'], b['str'],b['str']))

    def finish(self):
        """ Close the .btf file"""
        self.file.close()

    @staticmethod
    def join_traces(traces, output):
        with open(output + ".btf", 'wb') as outfile:
            for file in traces:
                with open(file, 'rb') as infile:
                    for line in infile:
                        outfile.write(line)
        return output + ".btf"

class ETWXML:
    def __init__(self, callback, providers):
        self.callback = callback
        self.providers = providers

    def tag_name(self, tag):
        if tag[0] == '{':
            return tag.split('}')[1]
        return tag

    def iterate_events(self, file):
        try:
            import xml.etree.cElementTree as ET
        except:
            import xml.etree.ElementTree as ET
        level = 0
        for event, elem in ET.iterparse(file, events=('start','end')):
            if event == 'start':
                level += 1
            else:
                if level == 2:
                    yield elem
                    elem.clear()
                level -= 1

    def as_dict(self, elem):
        return dict((self.tag_name(child.tag), child) for child in elem.getchildren())

    def parse_system(self, system):
        res = {}
        system = self.as_dict(system)
        if not system:
            return res
        if system.has_key('TimeCreated'):
            time_created = system['TimeCreated']
            res['time'] = time_created.attrib['RawTime']
        if system.has_key('Task'):
            task = system['Task']
            res['Task'] = task.text
        if system.has_key('EventID'):
            EventID = system['EventID']
            res['EventID'] = EventID.text
        if system.has_key('Opcode'):
            Opcode = system['Opcode']
            res['Opcode'] = Opcode.text
        provider = system['Provider']
        execution = system['Execution'] if system.has_key('Execution') else None
        res['provider'] = provider.attrib['Name'] if provider.attrib.has_key('Name') else provider.attrib['Guid'] if provider.attrib.has_key('Guid') else None
        if execution != None:
            res['pid'] = execution.attrib['ProcessID']
            res['tid'] = execution.attrib['ThreadID']
            res['cpu'] = execution.attrib['ProcessorID']
        return res

    def parse_event_data(self, data):
        res = {}
        for child in data.getchildren():
            if 'ComplexData' == self.tag_name(child.tag):
                res[child.attrib['Name']] = self.parse_event_data(child)
            else:
                res[child.attrib['Name']] = child.text.strip() if child.text else ""
        return res

    def parse_rendering_info(self, info):
        res = {}
        info = self.as_dict(info)
        for key, data in info.iteritems():
            res[key] = data.text.strip() if data.text else ""
        return res

    def parse(self, file):
        unhandled_providers = set()
        for elem in self.iterate_events(file):
            children = self.as_dict(elem)
            if not children:
                continue
            system = self.parse_system(children['System'])
            if not system:
                continue
            if system['provider'] in self.providers:
                if children.has_key('BinaryEventData'):
                    self.callback(system, children['BinaryEventData'].text, self.as_dict(children['ExtendedTracingInfo'])['EventGuid'].text)
                else:
                    data = self.parse_event_data(children['EventData']) if children.has_key('EventData') else None
                    info = self.parse_rendering_info(children['RenderingInfo']) if children.has_key('RenderingInfo') else None
                    self.callback(system, data, info)
            else:
                if system['provider'] not in unhandled_providers:
                    unhandled_providers.add(system['provider'])
        return unhandled_providers

DMA_PACKET_TYPE = ["CLIENT_RENDER", "CLIENT_PAGING", "SYSTEM_PAGING", "SYSTEM_PREEMTION"]
QUEUE_PACKET_TYPE = ["RENDER", "DEFERRED", "SYSTEM", "MMIOFLIP", "WAIT", "SIGNAL", "DEVICE", "SOFTWARE", "PAGING"]
QUANTUM_STATUS = ["READY", "RUNNING", "EXPIRED", "PROCESSED_EXPIRE"]
FUN_NAMES = {0: 'DriverEntry', 1: 'DxgkCreateClose', 2: 'DxgkInternalDeviceIoctl', 2051: 'DxgkCreateKeyedMutex', 2052: 'DxgkOpenKeyedMutex', 2053: 'DxgkDestroyKeyedMutex', 2054: 'DxgkAcquireKeyedMutex', 2049: 'DxgkQueryStatistics', 2056: 'DxgkConfigureSharedResource', 2057: 'DxgkGetOverlayState', 2058: 'DxgkCheckVidPnExclusiveOwnership', 2059: 'DxgkCheckSharedResourceAccess', 2060: 'DxgkGetPresentHistory', 2050: 'DxgkOpenSynchronizationObject', 2062: 'DxgkDestroyOutputDupl', 2063: 'DxgkOutputDuplGetFrameInfo', 2064: 'DxgkOutputDuplGetMetaData', 2065: 'DxgkOutputDuplGetPointerShapeData', 2066: 'DxgkCreateKeyedMutex2', 2067: 'DxgkOpenKeyedMutex2', 2068: 'DxgkAcquireKeyedMutex2', 2069: 'DxgkReleaseKeyedMutex2', 2070: 'DxgkOfferAllocations', 2071: 'DxgkReclaimAllocations', 2072: 'DxgkOutputDuplReleaseFrame', 2073: 'DxgkQueryResourceInfoFromNtHandle', 2074: 'DxgkShareObjects', 2075: 'DxgkOpenNtHandleFromName', 2076: 'DxgkOpenResourceFromNtHandle', 2077: 'DxgkSetVidPnSourceOwner1', 2078: 'DxgkEnumAdapters', 2079: 'DxgkPinDirectFlipResources', 2080: 'DxgkUnpinDirectFlipResources', 2081: 'DxgkGetPathsModality', 2082: 'DxgkOpenAdapterFromLuid', 2083: 'DxgkWaitForVerticalBlankEvent2', 2084: 'DxgkSetContextInProcessSchedulingPriority', 2085: 'DxgkGetContextInProcessSchedulingPriority', 2086: 'DxgkOpenSyncObjectFromNtHandle', 2087: 'DxgkNotifyProcessFreezeCallout', 2088: 'DxgkGetSharedResourceAdapterLuid', 2089: 'DxgkSetStereoEnabled', 2090: 'DxgkGetCachedHybridQueryValue', 2055: 'DxgkReleaseKeyedMutex', 2092: 'DxgkPresentMultiPlaneOverlay', 2093: 'DxgkCheckMultiPlaneOverlaySupport', 2094: 'DxgkSetIndependentFlipMode', 2095: 'DxgkConfirmToken', 2096: 'DxgkNotifyProcessThawCallout', 2097: 'DxgkSetPresenterViewMode', 2098: 'DxgkReserveGpuVirtualAddress', 2099: 'DxgkFreeGpuVirtualAddress', 2100: 'DxgkMapGpuVirtualAddress', 2101: 'DxgkCreateContextVirtual', 2102: 'DxgkSubmitCommand', 2103: 'DxgkLock2', 2104: 'DxgkUnlock2', 2105: 'DxgkDestroyAllocation2', 2106: 'DxgkUpdateGpuVirtualAddress', 2107: 'DxgkCheckMultiPlaneOverlaySupport2', 2108: 'DxgkCreateSwapChain', 2109: 'DxgkOpenSwapChain', 2110: 'DxgkDestroySwapChain', 2111: 'DxgkAcquireSwapChain', 2112: 'DxgkReleaseSwapChain', 2113: 'DxgkAbandonSwapChain', 2114: 'DxgkSetDodIndirectSwapchain', 2115: 'DxgkMakeResident', 2116: 'DxgkEvict', 2117: 'DxgkCreatePagingQueue', 2048: 'DxgkSetDisplayPrivateDriverFormat', 2119: 'DxgkQueryVideoMemoryInfo', 2120: 'DxgkChangeVideoMemoryReservation', 2121: 'DxgkGetSwapChainMetadata', 2122: 'DxgkInvalidateCache', 2123: 'DxgkGetResourcePresentPrivateDriverData', 2124: 'DxgkSetStablePowerState', 2125: 'DxgkQueryClockCalibration', 2061: 'DxgkCreateOutputDupl', 2130: 'DxgkSetVidPnSourceHwProtection', 2131: 'DxgkMarkDeviceAsError', 2091: 'DxgkCacheHybridQueryValue', 7054: 'DmmMiniportInterfaceGetMonitorFrequencyRangeSet', 2118: 'DxgkDestroyPagingQueue', 2127: 'DxgkAdjustFullscreenGamma', 14001: 'VidMmRecalculateBudgets', 13000: 'DxgkDdiMiracastQueryCaps', 13001: 'DxgkDdiMiracastCreateContext', 13002: 'DxgkDdiMiracastIoControl', 13003: 'DxgkDdiMiracastDestroyContext', 13050: 'DxgkCbSendUserModeMessage', 13100: 'MiracastUmdDriverCreateMiracastContext', 13101: 'MiracastUmdDriverDestroyMiracastContext', 13102: 'MiracastUmdDriverStartMiracastSession', 13103: 'MiracastUmdDriverStopMiracastSession', 13104: 'MiracastUmdDriverHandleKernelModeMessage', 7000: 'DmmMiniportInterfaceGetNumSourceModes', 7001: 'DmmMiniportInterfaceAcquireFirstSourceMode', 7002: 'DmmMiniportInterfaceAcquireNextSourceMode', 7003: 'DmmMiniportInterfaceAcquirePinnedSourceMode', 7004: 'DmmMiniportInterfaceReleaseSourceMode', 7005: 'DmmMiniportInterfaceCreateNewSourceMode', 7006: 'DmmMiniportInterfaceAddSourceMode', 7007: 'DmmMiniportInterfacePinSourceMode', 7008: 'DmmMiniportInterfaceGetNumTargetModes', 7009: 'DmmMiniportInterfaceAcquireFirstTargetMode', 7010: 'DmmMiniportInterfaceAcquireNextTargetMode', 7011: 'DmmMiniportInterfaceAcquirePinnedTargetMode', 7012: 'DmmMiniportInterfaceReleaseTargetMode', 7013: 'DmmMiniportInterfaceCreateNewTargetMode', 7014: 'DmmMiniportInterfaceAddTargetMode', 7015: 'DmmMiniportInterfacePinTargetMode', 7016: 'DmmMiniportInterfaceGetNumMonitorSourceModes', 7017: 'DmmMiniportInterfaceAcquirePreferredMonitorSourceMode', 7018: 'DmmMiniportInterfaceAcquireFirstMonitorSourceMode', 7019: 'DmmMiniportInterfaceAcquireNextMonitorSourceMode', 7020: 'DmmMiniportInterfaceCreateNewMonitorSourceMode', 7021: 'DmmMiniportInterfaceAddMonitorSourceMode', 7022: 'DmmMiniportInterfaceReleaseMonitorSourceMode', 7023: 'DmmMiniportInterfaceGetNumMonitorFrequencyRanges', 7024: 'DmmMiniportInterfaceAcquireFirstMonitorFrequencyRange', 7025: 'DmmMiniportInterfaceAcquireNextMonitorFrequencyRange', 7026: 'DmmMiniportInterfaceReleaseMonitorFrequencyRange', 7027: 'DmmMiniportInterfaceGetNumMonitorDescriptors', 7028: 'DmmMiniportInterfaceAcquireFirstMonitorDescriptor', 7029: 'DmmMiniportInterfaceAcquireNextMonitorDescriptor', 7030: 'DmmMiniportInterfaceReleaseMonitorDescriptor', 7031: 'DmmMiniportInterfaceGetNumPaths', 7032: 'DmmMiniportInterfaceGetNumPathsFromSource', 7033: 'DmmMiniportInterfaceEnumPathTargetsFromSource', 7034: 'DmmMiniportInterfaceGetPathSourceFromTarget', 7035: 'DmmMiniportInterfaceAcquirePath', 7036: 'DmmMiniportInterfaceAcquireFirstPath', 7037: 'DmmMiniportInterfaceAcquireNextPath', 7038: 'DmmMiniportInterfaceUpdatePathSupport', 7039: 'DmmMiniportInterfaceReleasePath', 7040: 'DmmMiniportInterfaceCreateNewPath', 7041: 'DmmMiniportInterfaceAddPath', 7042: 'DmmMiniportInterfaceGetTopology', 7043: 'DmmMiniportInterfaceAcquireSourceModeSet', 7044: 'DmmMiniportInterfaceReleaseSourceModeSet', 7045: 'DmmMiniportInterfaceCreateNewSourceModeSet', 7046: 'DmmMiniportInterfaceAssignSourceModeSet', 7047: 'DmmMiniportInterfaceAssignMultisamplingSet', 5000: 'DdiQueryAdapterInfo', 5001: 'DdiCreateDevice', 5002: 'DdiCreateAllocation', 5003: 'DdiDescribeAllocation', 5004: 'DdiGetStandardAllocationDriverData', 5005: 'DdiDestroyAllocation', 5006: 'DdiAcquireSwizzlingRange', 5007: 'DdiReleaseSwizzlingRange', 5008: 'DdiPatch', 5009: 'DdiCommitVidPn', 5010: 'DdiSetVidPnSourceAddress', 5011: 'DdiSetVidPnSourceVisibility', 5012: 'DdiUpdateActiveVidPnPresentPath', 5013: 'DdiSubmitCommand', 5014: 'DdiPreemptCommand', 5015: 'DdiQueryCurrentFence', 5016: 'DdiBuildPagingBuffer', 5017: 'DdiSetPalette', 5018: 'DdiSetPointerShape', 5019: 'DdiSetPointerPosition', 5020: 'DdiResetFromTimeout', 5021: 'DdiRestartFromTimeout', 5022: 'DdiEscape', 5023: 'DdiCollectDbgInfo', 5024: 'DdiRecommendFunctionalVidPn', 5025: 'DdiIsSupportedVidPn', 5026: 'DdiEnumVidPnCofuncModality', 5027: 'DdiDestroyDevice', 5028: 'DdiOpenAllocation', 5029: 'DdiCloseAllocation', 5030: 'DdiRender', 5031: 'DdiPresent', 5032: 'DdiCreateOverlay', 5033: 'DdiUpdateOverlay', 5034: 'DdiFlipOverlay', 5035: 'DdiDestroyOverlay', 5036: 'DdiGetScanLine', 5037: 'DdiRecommendMonitorModes', 5038: 'DdiControlInterrupt', 5039: 'DdiStopCapture', 5040: 'DdiRecommendVidPnTopology', 5041: 'DdiCreateContext', 5042: 'DdiDestroyContext', 5043: 'DdiNotifyDpc', 5044: 'DdiSetDisplayPrivateDriverFormat', 5045: 'DdiRenderKm', 5046: 'DdiAddTargetMode', 5047: 'DdiQueryVidPnHWCapability', 5048: 'DdiPresentDisplayOnly', 5049: 'DdiQueryDependentEngineGroup', 5050: 'DdiQueryEngineStatus', 5051: 'DdiResetEngine', 5052: 'DdiCancelCommand', 5053: 'DdiGetNodeMetadata', 5054: 'DdiControlInterrupt2', 5055: 'DdiCheckMultiPlaneOverlaySupport', 3008: 'DxgkCddPresent', 3009: 'DxgkCddSetGammaRamp', 5058: 'DdiGetRootPageTableSize', 5059: 'DdiSetRootPageTable', 3012: 'DxgkCddSetPointerShape', 5061: 'DdiMapCpuHostAperture', 5062: 'DdiUnmapCpuHostAperture', 5063: 'DdiSubmitCommandVirtual', 5064: 'DdiCreateProcess', 5065: 'DdiDestroyProcess', 5066: 'DdiRenderGdi', 5067: 'DdiCheckMultiPlaneOverlaySupport2', 5068: 'DdiSetStablePowerState', 5069: 'DdiSetVideoProtectedRegion', 3022: 'DxgkCddDrvColorFill', 3023: 'DxgkCddDrvStrokePath', 3024: 'DxgkCddDrvAlphaBlend', 3025: 'DxgkCddDrvLineTo', 3026: 'DxgkCddDrvFillPath', 3027: 'DxgkCddDrvStrokeAndFillPath', 3028: 'DxgkCddDrvStretchBltROP', 3029: 'DxgkCddDrvPlgBlt', 3030: 'DxgkCddDrvStretchBlt', 3031: 'DxgkCddDrvTextOut', 3032: 'DxgkCddDrvGradientFill', 3033: 'DxgkCddDrvTransparentBlt', 3034: 'DxgkCddOpenResource', 3035: 'DxgkCddQueryResourceInfo', 3036: 'DxgkCddSubmitPresentHistory', 3037: 'DxgkCddCreateDeviceBitmap', 3038: 'DxgkCddUpdateGdiMem', 3039: 'DxgkCddAddCommand', 3040: 'DxgkCddEnableLite', 3041: 'DxgkCddAssertModeInternal', 3042: 'DxgkCddSetLiteModeChange', 3043: 'DxgkCddPresentDisplayOnly', 3044: 'DxgkCddSignalGdiContext', 3045: 'DxgkCddWaitGdiContext', 3046: 'DxgkCddSignalDxContext', 3047: 'DxgkCddWaitDxContext', 3048: 'DxgkCddStartDxInterop', 3049: 'DxgkCddEndDxInterop', 3050: 'DxgkCddAddD3DDirtyRect', 3051: 'DxgkCddDxGdiInteropFailed', 3052: 'DxgkCddSyncDxAccess', 3053: 'DxgkCddFlushCpuCache', 3054: 'DxgkCddLockMdlPages', 3055: 'DxgkCddOpenResourceFromNtHandle', 3056: 'DxgkCddQueryResourceInfoFromNtHandle', 3057: 'DxgkCddUnlockMdlPages', 3058: 'DxgkCddTrimStagingSize', 7059: 'DmmMiniportInterfaceGetAdditionalMonitorModesSet', 13150: 'MiracastUmdDriverCbReportSessionStatus', 13151: 'MiracastUmdDriverCbMiracastIoControl', 13152: 'MiracastUmdDriverCbReportStatistic', 13153: 'MiracastUmdDriverCbGetNextChunkData', 13154: 'MiracastUmdDriverCbRegisterForDataRateNotifications', 1004: 'DpiDispatchIoctl', 7048: 'DmmMiniportInterfaceAcquireTargetModeSet', 7049: 'DmmMiniportInterfaceReleaseTargetModeSet', 7050: 'DmmMiniportInterfaceCreateNewTargetModeSet', 7051: 'DmmMiniportInterfaceAssignTargetModeSet', 7052: 'DmmMiniportInterfaceAcquireMonitorSourceModeSet', 7053: 'DmmMiniportInterfaceReleaseMonitorSourceModeSet', 1000: 'DpiAddDevice', 7055: 'DmmMiniportInterfaceGetMonitorDescriptorSet', 7056: 'DmmMiniportInterfaceQueryVidPnInterface', 7057: 'DmmMiniportInterfaceQueryMonitorInterface', 7058: 'DmmMiniportInterfaceRemovePath', 1001: 'DpiDispatchClose', 7060: 'DmmMiniportInterfaceReleaseAdditionalMonitorModesSet', 1002: 'DpiDispatchCreate', 1003: 'DpiDispatchInternalIoctl', 4000: 'DpiDxgkDdiAddDevice', 4001: 'DpiDxgkDdiStartDevice', 4002: 'DpiDxgkDdiStopDevice', 4003: 'DpiDxgkDdiRemoveDevice', 6052: 'DmmInterfaceCreateVidPn', 6053: 'DmmInterfaceCreateVidPnFromActive', 6054: 'DmmInterfaceCreateVidPnCopy', 1005: 'DpiDispatchPnp', 6056: 'DmmInterfaceIsUsingDefaultMonitorProfile', 6057: 'DmmInterfaceIsMonitorConnected', 6058: 'DmmInterfaceRemoveCopyProtection', 6059: 'DmmInterfaceGetPathImportance', 1006: 'DpiDispatchPower', 6061: 'DmmInterfaceEnumPaths', 1007: 'DpiDispatchSystemControl', 1008: 'DpiDriverUnload', 3000: 'DxgkCddCreate', 6055: 'DmmInterfaceReleaseVidPn', 3001: 'DxgkCddDestroy', 3002: 'DxgkCddEnable', 3003: 'DxgkCddDisable', 3004: 'DxgkCddGetDisplayModeList', 3005: 'DxgkCddGetDriverCaps', 3006: 'DxgkCddLock', 3007: 'DxgkCddUnlock', 3010: 'DxgkCddSetPalette', 3011: 'DxgkCddSetPointerPosition', 3013: 'DxgkCddTerminateThread', 3014: 'DxgkCddSetOrigin', 3015: 'DxgkCddWaitForVerticalBlankEvent', 14000: 'VidMmProcessOperations', 3016: 'DxgkCddSyncGPUAccess', 3017: 'DxgkCddCreateAllocation', 3018: 'DxgkCddDestroyAllocation', 3019: 'DxgkCddBltToPrimary', 3020: 'DxgkCddGdiCommand', 3021: 'DxgkCddDrvBitBlt', 12000: 'BLTQUEUE_Present', 6060: 'DmmInterfaceGetNumPaths', 8000: 'ProbeAndLockPages', 8001: 'UnlockPages', 8002: 'MapViewOfAllocation', 8003: 'UnmapViewOfAllocation', 8004: 'ProcessHeapAllocate', 8005: 'ProcessHeapRotate', 8006: 'BootInt10ModeChange', 8007: 'ResumeInt10ModeChange', 8008: 'FlushAllocationCache', 8009: 'NotifyVSync', 8010: 'MakeProcessIdleToFlushTlb', 6000: 'DmmInterfaceAcquiredPreferredMonitorSourceMode', 6001: 'DmmInterfaceReleaseMonitorSourceMode', 6002: 'DmmInterfaceGetNumSourceModes', 6003: 'DmmInterfaceAcquireFirstSourceMode', 6004: 'DmmInterfaceAcquireNextSourceMode', 6005: 'DmmInterfaceAcquirePinnedSourceMode', 6006: 'DmmInterfaceReleaseSourceMode', 6007: 'DmmInterfacePinSourceMode', 6008: 'DmmInterfaceUnpinSourceMode', 6009: 'DmmInterfaceGetNumTargetModes', 6010: 'DmmInterfaceAcquireFirstTargetMode', 6011: 'DmmInterfaceAcquireNextTargetMode', 6012: 'DmmInterfaceAcquriePinnedTargetMode', 6013: 'DmmInterfaceReleaseTargetMode', 6014: 'DmmInterfaceCompareTargetMode', 6015: 'DmmInterfacePinTargetMode', 6016: 'DmmInterfaceUnpinTargetMode', 6017: 'DmmInterfaceIsTargetModeSupportedByMonitor', 6018: 'DmmInterfaceGetNumPathsFromSource', 6019: 'DmmInterfaceEnumPathTargetsFromSource', 6020: 'DmmInterfaceGetPathSourceFromTarget', 6021: 'DmmInterfaceAcquirePath', 6022: 'DmmInterfaceReleasePath', 6023: 'DmmInterfaceAddPath', 6024: 'DmmInterfaceRemovePath', 6025: 'DmmInterfaceRemoveAllPaths', 6026: 'DmmInterfacePinScaling', 6027: 'DmmInterfaceUnpinScaling', 6028: 'DmmInterfacePinRotation', 6029: 'DmmInterfaceUnpinRotation', 6030: 'DmmInterfaceRecommendVidPnTopology', 6031: 'DmmInterfaceFindFirstAvailableTarget', 6032: 'DmmInterfaceRestoreFromLkgForSource', 6033: 'DmmInterfaceGetTopology', 6034: 'DmmInterfaceAcquireSourceModeSet', 6035: 'DmmInterfaceReleaseSourceModeSet', 6036: 'DmmInterfaceAcquireTargetModeSet', 6037: 'DmmInterfaceReleaseTargetModeSet', 6038: 'DmmInterfaceAcquireMonitorSourceModeSet', 6039: 'DmmInterfaceReleaseMonitorSourceModeSet', 6040: 'DmmInterfaceGetNumSources', 6041: 'DmmInterfaceAcquireFirstSource', 6042: 'DmmInterfaceAcquireNextSource', 6043: 'DmmInterfaceReleaseSource', 6044: 'DmmInterfaceGetNumTargets', 6045: 'DmmInterfaceAcquireFirstTarget', 6046: 'DmmInterfaceAcquireNextTarget', 6047: 'DmmInterfaceReleaseTarget', 6048: 'DmmInterfaceAcquireSourceSet', 6049: 'DmmInterfaceReleaseSourceSet', 6050: 'DmmInterfaceAcquireTargetSet', 6051: 'DmmInterfaceReleaseTargetSet', 4004: 'DpiDxgkDdiDispatchIoRequest', 4005: 'DpiDxgkDdiQueryChildRelations', 4006: 'DpiDxgkDdiQueryChildStatus', 4007: 'DpiDxgkDdiQueryDeviceDescriptor', 4008: 'DpiDxgkDdiSetPowerState', 4009: 'DpiDxgkDdiNotifyAcpiEvent', 4010: 'DpiDxgkDdiUnload', 4011: 'DpiDxgkDdiControlEtwLogging', 4012: 'DpiDxgkDdiQueryInterface', 4013: 'DpiDpcForIsr', 4014: 'DpiFdoMessageInterruptRoutine', 4015: 'VidSchDdiNotifyInterrupt', 4016: 'VidSchiCallNotifyInterruptAtISR', 4017: 'DpiDxgkDdiStopDeviceAndReleasePostDisplayOwnership', 4018: 'DpiDxgkDdiGetChildContainerId', 4019: 'DpiDxgkDdiNotifySurpriseRemoval', 4020: 'DpiFdoThermalActiveCooling', 4021: 'DpiFdoThermalPassiveCooling', 4022: 'DxgkCbIndicateChildStatus', 2000: 'DxgkProcessCallout', 2001: 'DxgkOpenAdapter', 2002: 'DxgkCloseAdapter', 2003: 'DxgkCreateAllocation', 2004: 'DxgkQueryResourceInfo', 2005: 'DxgkOpenResource', 2006: 'DxgkDestroyAllocation', 2007: 'DxgkSetAllocationPriority', 2008: 'DxgkQueryAllocationResidency', 2009: 'DxgkCreateDevice', 2010: 'DxgkDestroyDevice', 2011: 'DxgkLock', 2012: 'DxgkUnlock', 2013: 'DxgkRender', 2014: 'DxgkGetRuntimeData', 2015: 'DxgkQueryAdapterInfo', 2016: 'DxgkEscape', 2017: 'DxgkGetDisplayModeList', 2018: 'DxgkSetDisplayMode', 2019: 'DxgkGetMultisampleMethodList', 2020: 'DxgkPresent', 2021: 'DxgkGetSharedPrimaryHandle', 2022: 'DxgkCreateOverlay', 2023: 'DxgkUpdateOverlay', 2024: 'DxgkFlipOverlay', 2025: 'DxgkDestroyOverlay', 2026: 'DxgkWaitForVerticalBlankEvent', 2027: 'DxgkSetVidPnSourceOwner', 2028: 'DxgkGetDeviceState', 2029: 'DxgkSetContextSchedulingPriority', 2030: 'DxgkGetContextSchedulingPriority', 2031: 'DxgkSetProcessSchedulingPriorityClass', 2032: 'DxgkGetProcessSchedulingPriorityClass', 2033: 'DxgkReleaseProcessVidPnSourceOwners', 2034: 'DxgkGetScanLine', 2035: 'DxgkSetQueuedLimit', 2036: 'DxgkPollDisplayChildren', 2037: 'DxgkInvalidateActiveVidPn', 2038: 'DxgkCheckOcclusion', 2039: 'DxgkCreateContext', 2040: 'DxgkDestroyContext', 2041: 'DxgkCreateSynchronizationObject', 2042: 'DxgkDestroySynchronizationObject', 2043: 'DxgkWaitForSynchronizationObject', 2044: 'DxgkSignalSynchronizationObject', 2045: 'DxgkWaitForIdle', 2046: 'DxgkCheckMonitorPowerState', 2047: 'DxgkCheckExclusiveOwnership'}
PAGING_QUEUE_TYPE = ['UMD', 'DEFAULT', 'EVICT', 'RECLAIM']
VIDMM_OPERATION = {0: 'None', 200: 'CloseAllocation', 202: 'ComplexLock', 203: 'PinAllocation', 204: 'FlushPendingGpuAccess', 205: 'UnpinAllocation', 206: 'MakeResident', 207: 'Evict', 208: 'LockInAperture', 209: 'InitContextAllocation', 210: 'ReclaimAllocation', 211: 'DiscardAllocation', 212: 'SetAllocationPriority', 1000: 'EvictSystemMemoryOfferList', 101: 'RestoreSegments', 102: 'PurgeSegments', 103: 'CleanupPrimary', 104: 'AllocatePagingBufferResources', 105: 'FreePagingBufferResources', 106: 'ReportVidMmState', 107: 'RunApertureCoherencyTest', 108: 'RunUnmapToDummyPageTest', 109: 'DeferredCommand', 110: 'SuspendMemorySegmentAccess', 111: 'ResumeMemorySegmentAccess', 112: 'EvictAndFlush', 113: 'CommitVirtualAddressRange', 114: 'UncommitVirtualAddressRange', 115: 'DestroyVirtualAddressAllocator', 116: 'PageInDevice', 117: 'MapContextAllocation', 118: 'InitPagingProcessVaSpace'}
SYNC_REASON = ['CREATE', 'DESTROY', 'OPEN', 'CLOSE', 'REPORT']
OPCODES = ['Info', 'Start', 'Stop', 'DCStart', 'DCEnd', 'Extension']

class ETWXMLHandler:
    def __init__(self, args, callbacks):
        self.args = args
        self.callbacks = callbacks
        self.count = 0
        self.process_names={}
        self.thread_pids={}
        self.ftrace = open(args.input + '.ftrace', 'w') if "gt" in args.format else None
        self.first_ftrace_record = True
        self.gui_packets = {}
        self.files = {}
        self.irps = {}
        self.context_to_node = {}

    def convert_time(self, time):
        return 1000000000 * (int(time, 16) if '0x' in str(time) else int(time)) / self.PerfFreq

    def MapReasonToState(self, state, wait_reason):
        if wait_reason in [5,12]: #Suspended, WrSuspended
            return 'D' #uninterruptible sleep (usually IO)
        elif wait_reason in [35, 34, 32, 23, 11, 4, 28]: # WrGuardedMutex, WrFastMutex, WrPreempted, WrProcessInSwap, WrDelayExecution, DelayExecution, WrPushLock
            return 'S' #interruptible sleep (waiting for an event to complete)
        elif wait_reason in [22,36]: #WrRundown, WrTerminated
            return 'X' #dead (should never be seen)
        elif wait_reason in [1,2,8,9]: #WrFreePage, WrPageIn, FreePage, PageIn
            return 'W' #paging
        else:
            if state == 3: #Standby
                return 'D' #uninterruptible sleep
            elif state == 4: #Terminated
                return 'X' #dead
            elif state == 5: #Waiting
                return 'S' #interruptible sleep (waiting for an event to complete)
            return 'R'
        """
        States:
        0	Initialized
        1	Ready
        2	Running
        3	Standby
        4	Terminated
        5	Waiting
        6	Transition
        7	DeferredReady

        Windows: https://msdn.microsoft.com/en-us/library/windows/desktop/aa964744(v=vs.85).aspx
        0	Executive           13	WrUserRequest       26	WrKernel
        1	FreePage            14	WrEventPair         27	WrResource
        2	PageIn              15	WrQueue             28	WrPushLock
        3	PoolAllocation      16	WrLpcReceive        29	WrMutex
        4	DelayExecution      17	WrLpcReply          30	WrQuantumEnd
        5	Suspended           18	WrVirtualMemory     31	WrDispatchInt
        6	UserRequest         19	WrPageOut           32	WrPreempted
        7	WrExecutive         20	WrRendezvous        33	WrYieldExecution
        8	WrFreePage          21	WrKeyedEvent        34	WrFastMutex
        9	WrPageIn            22	WrTerminated        35	WrGuardedMutex
        10	WrPoolAllocation    23	WrProcessInSwap     36	WrRundown
        11	WrDelayExecution    24	WrCpuRateControl
        12	WrSuspended         25	WrCalloutStack

        Linux:
        D    uninterruptible sleep (usually IO)
        R    running or runnable (on run queue)
        S    interruptible sleep (waiting for an event to complete)
        T    stopped, either by a job control signal or because it is being traced.
        W    paging (not valid since the 2.6.xx kernel)
        X    dead (should never be seen)
        Z    defunct ("zombie") process, terminated but not reaped by its parent.

        From google trace parser:
        'S' SLEEPING
        'R' || 'R+' RUNNABLE
        'D' UNINTR_SLEEP
        'T' STOPPED
        't' DEBUG
        'Z' ZOMBIE
        'X' EXIT_DEAD
        'x' TASK_DEAD
        'K' WAKE_KILL
        'W' WAKING
        'D|K' UNINTR_SLEEP_WAKE_KILL
        'D|W' UNINTR_SLEEP_WAKING
        """

    def get_process_name_by_tid(self, tid):
        if self.thread_pids.has_key(tid):
            pid = self.thread_pids[tid]
            if self.process_names.has_key(pid):
                name = self.process_names[pid]['name']
            else:
                name = "PID:%d" % int(pid, 16)
        else:
            name = "TID:%d" % tid
        return name

    def handle_file_name(self, file):
        file_name = file.encode('utf-8').replace('\\', '/').replace('"', r'\"')
        file_name = file_name.split('/')
        file_name.reverse()
        return file_name[0] + " " + "/".join(file_name[1:])

    def MSNT_SystemTrace(self, system, data, info):
        if info['EventName'] == 'EventTrace':
            if info['Opcode'] == 'Header':
                self.PerfFreq = int(data['PerfFreq'])
                for callback in self.callbacks.callbacks:
                    callback("metadata_add", {'domain':'GPU', 'str':'__process__', 'pid':-1, 'tid':-1, 'data':'GPU Engines', 'time': self.convert_time(system['time']), 'delta': -2})
        elif info['EventName'] == 'DiskIo':
            if info['Opcode'] in ['FileDelete', 'FileRundown']:
                if self.files.has_key(data['FileObject']):
                    file = self.files[data['FileObject']]
                    if file.has_key('pid'):
                        call_data = {'tid': file['tid'], 'pid': file['pid'], 'domain': 'MSNT_SystemTrace', 'time': self.convert_time(system['time']), 'str': file['name'], 'type':11, 'id': int(data['FileObject'], 16)}
                        self.callbacks.on_event("object_delete", call_data)
                    del self.files[data['FileObject']]
            elif info['Opcode'] in ['Read', 'Write', 'HardFault', 'FlushBuffers', 'WriteInit', 'ReadInit', 'FlushInit']:
                tid = int(data['IssuingThreadId']) if data.has_key('IssuingThreadId') else int(data['TThreadId'], 16) if data.has_key('TThreadId') else None
                if tid == None:
                    return
                if not data.has_key('FileObject'):
                    if self.irps.has_key(data['Irp']):
                        data['FileObject'] = self.irps[data['Irp']]
                    else:
                        return
                if self.files.has_key(data['FileObject']) and self.thread_pids.has_key(tid):
                    file = self.files[data['FileObject']]
                    pid = int(self.thread_pids[tid], 16)
                    call_data = {'tid': tid, 'pid': pid, 'domain': 'MSNT_SystemTrace', 'time': self.convert_time(system['time']), 'str': file['name'], 'type':10, 'id': int(data['FileObject'], 16)}
                    file['tid'] = tid
                    file['pid'] = pid
                    if file['creation'] != None: #write creation on first operation where tid is known
                        creation = call_data.copy()
                        creation['type'] = 9
                        creation['time'] = file['creation']
                        self.callbacks.on_event("object_new", creation)
                        file['creation'] = None
                    if data.has_key('Irp'):
                        self.irps[data['Irp']] = data['FileObject']
                    data['OPERATION'] = info['Opcode']
                    call_data['args'] = {'snapshot': data}
                    self.callbacks.on_event("object_snapshot", call_data)
            else:
                print info['Opcode']
        elif info['EventName'] == 'FileIo':
            if info['Opcode'] == 'FileCreate':
                file_name = self.handle_file_name(data['FileName'])
                if '.sea/' not in file_name: #ignore own files - they are toooo many in the view
                    self.files[data['FileObject']] = {'name': file_name, 'creation': self.convert_time(system['time'])}
            elif info['Opcode'] == 'Create':
                file_name = self.handle_file_name(data['OpenPath'])
                if '.sea/' not in file_name: #ignore own files - they are toooo many in the view
                    self.files[data['FileObject']] = {'name': file_name, 'creation': None}
                    call_data = {'tid': int(system['tid']), 'pid': int(system['pid']), 'domain': 'MSNT_SystemTrace', 'time': self.convert_time(system['time']), 'str': file_name, 'type':9, 'id': int(data['FileObject'], 16)}
                    self.callbacks.on_event("object_new", call_data)
            elif info['Opcode'] in ['Close', 'FileDelete', 'Delete']:
                if self.files.has_key(data['FileObject']):
                    file = self.files[data['FileObject']]
                    call_data = {'tid': int(system['tid']), 'pid': int(system['pid']), 'domain': 'MSNT_SystemTrace', 'time': self.convert_time(system['time']), 'str': file['name'], 'type':11, 'id': int(data['FileObject'], 16)}
                    self.callbacks.on_event("object_delete", call_data)
                    del self.files[data['FileObject']]
            elif info['Opcode'] not in ['OperationEnd', 'Cleanup', 'QueryInfo']:
                if self.files.has_key(data['FileObject']):
                    file = self.files[data['FileObject']]
                    tid = int(system['tid'])
                    pid = int(system['pid'])
                    call_data = {'tid': tid, 'pid': pid, 'domain': 'MSNT_SystemTrace', 'time': self.convert_time(system['time']), 'str': file['name'], 'type':10, 'id': int(data['FileObject'], 16)}
                    file['tid'] = tid
                    file['last_access'] = call_data['time']
                    file['pid'] = pid
                    if data.has_key('IrpPtr'):
                        self.irps[data['IrpPtr']] = data['FileObject']
                    data['OPERATION'] = info['Opcode']
                    call_data['args'] = {'snapshot': data}
                    self.callbacks.on_event("object_snapshot", call_data)
        else:
            if 'Start' in info['Opcode']:
                event = info['EventName']
                if event in ['Process', 'Defunct']:
                    self.process_names[data['ProcessId']] = {'name': data['ImageFileName'].split('.')[0], 'cmd': data['CommandLine']}
                elif event == 'Thread':
                    pid = data['ProcessId'] if '0x0' != data['ProcessId'] else hex(int(system['pid']))
                    self.thread_pids[int(data['TThreadId'], 16)] = pid
            elif info['Opcode'] == 'CSwitch':
                if self.ftrace == None and not self.first_ftrace_record:
                    return
                time = self.convert_time(system['time'])
                if not self.callbacks.check_time_in_limits(time):
                    return
                #mandatory: prevState, nextComm, nextPid, nextPrio
                prev_tid = int(data['OldThreadId'], 16)
                prev_name = self.get_process_name_by_tid(prev_tid)
                next_tid = int(data['NewThreadId'], 16)

                if self.first_ftrace_record:
                    self.ftrace = open(self.args.input + '.ftrace', 'w') if "gt" in self.args.format else None
                    self.first_ftrace_record = False
                    if not self.ftrace:
                        return
                    self.ftrace.write("# tracer: nop\n")
                    args = (prev_name, prev_tid, int(system['cpu']), time / 1000000000., time / 1000000000.)
                    ftrace = "%s-%d [%03d] .... %.6f: tracing_mark_write: trace_event_clock_sync: parent_ts=%.6f\n" % args
                    self.ftrace.write(ftrace)
                args = (
                    prev_name, prev_tid, int(system['cpu']), time / 1000000000.,
                    prev_name, prev_tid, int(data['OldThreadPriority']), self.MapReasonToState(int(data['OldThreadState']), int(data['OldThreadWaitReason'])),
                    self.get_process_name_by_tid(next_tid), next_tid, int(data['NewThreadPriority'])
                )
                ftrace = "%s-%d [%03d] .... %.6f: sched_switch: prev_comm=%s prev_pid=%d prev_prio=%d prev_state=%s ==> next_comm=%s next_pid=%d next_prio=%d\n" % args
                self.ftrace.write(ftrace)

    def auto_break_gui_packets(self, call_data, tid, begin):
        id = call_data['id']
        if begin:
            self.gui_packets.setdefault(tid, {})[id] = call_data
        else:
            if self.gui_packets.has_key(tid) and self.gui_packets[tid].has_key(id):
                del self.gui_packets[tid][id]
                for begin_data in self.gui_packets[tid].itervalues(): #finish all and start again to form melting task queue
                    begin_data['time'] = call_data['time']
                    end_data = begin_data.copy()
                    end_data['type'] = call_data['type']
                    self.callbacks.on_event('task_end_overlapped', end_data)
                    self.callbacks.on_event('task_begin_overlapped', begin_data)

    def on_event(self, system, data, info, static={'queue':{}, 'frames':{}, 'paging':{}, 'dmabuff':{}, 'tex2d':{}, 'resident':{}, 'fence':{}}):
        if self.count % ProgressConst == 0:
            self.progress.tick(self.file.tell())
        self.count += 1
        if not info or not data:
            return
        if not isinstance(data, dict):
            return self.on_binary(system, data, info)
        opcode = info['Opcode'] if info.has_key('Opcode') else ""
        if system['provider'] == '{9e814aad-3204-11d2-9a82-006008a86939}': #MSNT_SystemTrace
            return self.MSNT_SystemTrace(system, data, info)

        call_data = {
            'tid': int(system['tid']), 'pid': int(system['pid']), 'domain': system['provider'],
            'time': self.convert_time(data['SyncQPCTime'] if data.has_key('SyncQPCTime') else system['time']),
            'str': info['Task'] if info.has_key('Task') and info['Task'] else 'Unknown',
            'args': data,
        }

        if call_data['str'] == 'SelectContext': #Microsoft-Windows-DxgKrnl
            context = data['hContext']
            node = data['NodeOrdinal']
            self.context_to_node[context] = node
            return

        if data.has_key('QuantumStatus'):
            data['QuantumStatusStr'] = QUANTUM_STATUS[int(data['QuantumStatus'])]

        if 'Start' in opcode:
            call_data["type"] = 2
            type = "task_begin_overlapped"
        elif 'Stop' in opcode:
            call_data["type"] = 3
            type = "task_end_overlapped"
        else:
            call_data["type"] = 5
            type = "marker"
            call_data['data'] = 'track'
        relation = None

        if call_data['str'] == 'DmaPacket': #Microsoft-Windows-DxgKrnl
            context = data['hContext']
            if not self.context_to_node.has_key(context) or 'Info' in opcode:
                return #no node info at this moment, just skip it. Or may be keep until it is known?
            call_data['pid'] = -1 #GUI 'process'
            tid = int(self.context_to_node[context])
            call_data['tid'] = tid
            call_data['str'] = DMA_PACKET_TYPE[int(data['PacketType'])]
            id = int(data['uliSubmissionId'] if data.has_key('uliSubmissionId') else data['uliCompletionId'])
            call_data['id'] = id
            if 'Start' in opcode:
                if static['queue'].has_key(int(data['ulQueueSubmitSequence'])):
                    relation = (call_data.copy(), static['queue'][int(data['ulQueueSubmitSequence'])], call_data)
                    relation[0]['parent'] = id
                self.auto_break_gui_packets(call_data, 2**64 + tid, True)
            else:
                self.auto_break_gui_packets(call_data, 2**64 + tid, False)

        elif call_data['str'] == 'QueuePacket': #Microsoft-Windows-DxgKrnl
            if 'Info' in opcode:
                return
            call_data['tid'] = -call_data['tid']
            id = int(data['SubmitSequence'])
            if not data.has_key('PacketType'): #workaround, PacketType is not set for Waits
                call_data['str'] = 'WAIT'
                assert(data.has_key('FenceValue'))
            else:
                call_data['str'] = QUEUE_PACKET_TYPE[int(data['PacketType'])]
            call_data['id'] = id
            if 'Start' in opcode:
                if static['queue'].has_key(id): #forcefully closing the previous one
                    closing = call_data.copy()
                    closing['type'] = 3
                    closing['id'] = id
                    self.callbacks.on_event("task_end_overlapped", closing)
                static['queue'][id] = call_data
                self.auto_break_gui_packets(call_data, call_data['tid'], True)
                if data.has_key('FenceValue') and static['fence'].has_key(data['FenceValue']):
                    relation = (call_data.copy(), static['fence'][data['FenceValue']], call_data)
                    relation[0]['parent'] = data['FenceValue']
                    del static['fence'][data['FenceValue']]
            elif 'Stop' in opcode:
                if not static['queue'].has_key(id):
                    return
                call_data['pid'] = static['queue'][id]['pid']
                call_data['tid'] = static['queue'][id]['tid']
                del static['queue'][id]
                self.auto_break_gui_packets(call_data, call_data['tid'], False)

        elif call_data['str'] == 'SCHEDULE_FRAMEINFO': #Microsoft-Windows-Dwm-Core
            presented = int(data['qpcPresented'], 16)
            if presented:
                begin = int(data['qpcBegin'], 16)
                call_data['time'] = self.convert_time(begin)
                call_data['type'] = 7 #to make it frame
                call_data['pid'] = -1 #to make it GUI
                del call_data['tid'] #to be global for GUI
                end_data = {'time': self.convert_time(int(data['qpcFrame'], 16))}
                if self.callbacks.check_time_in_limits(call_data['time']):
                    for callback in self.callbacks.callbacks:
                        callback.complete_task('frame', call_data, end_data)
            return

        elif 'Profiler' in call_data['str']:#Microsoft-Windows-DxgKrnl
            func = int(data['Function'])
            name = FUN_NAMES[func] if FUN_NAMES.has_key(func) else 'Unknown'
            call_data['str'] = name
            call_data['id'] = func

        elif call_data['str'] == 'MakeResident':#Microsoft-Windows-DxgKrnl
            if 'Start' in opcode:
                static['resident'].setdefault(system['tid'], []).append(data)
            elif 'Stop' in opcode:
                resident = static['resident'][system['tid']]
                if len(resident):
                    saved = resident.pop()
                else:
                    return
                data.update(saved)
                static['fence'][data['PagingFenceValue']] = call_data
            call_data['id'] = int(data['pSyncObject'], 16)

        elif call_data['str'] == 'PagingQueuePacket':#Microsoft-Windows-DxgKrnl
            if 'Info' in opcode:
                return
            call_data['tid'] = -call_data['tid']
            id = int(data['PagingQueuePacket'], 16)
            call_data['id'] = id
            if data.has_key('PagingQueueType'):
                VidMmOpType = int(data['VidMmOpType'])
                call_data['str'] = PAGING_QUEUE_TYPE[int(data['PagingQueueType'])] + ":" + (VIDMM_OPERATION[VidMmOpType] if VIDMM_OPERATION.has_key(VidMmOpType) else "Unknown")
                static['paging'][id] = call_data
            elif static['paging'].has_key(id):
                start = static['paging'][id]
                call_data['str'] = start['str']
                call_data['pid'] = start['pid']
                call_data['tid'] = start['tid']
                del static['paging'][id]

        elif call_data['str'] == 'PagingPreparation': #Microsoft-Windows-DxgKrnl
            if 'Info' in opcode: return
            pDmaBuffer = data['pDmaBuffer']
            call_data['id'] = int(pDmaBuffer, 16)
            if 'Stop' in opcode and static['dmabuff'].has_key(pDmaBuffer):
                call_data['args'].update(static['dmabuff'][pDmaBuffer])
                del static['dmabuff'][pDmaBuffer]
        elif call_data['str'] == 'AddDmaBuffer': #Microsoft-Windows-DxgKrnl
            static['dmabuff'][data['pDmaBuffer']] = data #parse arguments for PagingPreparation from AddDmaBuffer
            return

        elif call_data['str'] == 'Present': #Microsoft-Windows-DxgKrnl
            if 'Start' in opcode:
                call_data["type"] = 0
                type = "task_begin"
            elif 'Stop' in opcode:
                call_data["type"] = 1
                type = "task_end"
            else:
                return
            """XXX gives nothing
            elif call_data['str'] == 'Texture2D':
                if not data.has_key('pID3D11Resource'):
                    return
                obj = data['pID3D11Resource']
                if static['tex2d'].has_key(obj):
                    obj = static['tex2d'][obj]
                    if 'Stop' in opcode:
                        del static['tex2d'][data['pID3D11Resource']]
                if info.has_key('Message'):
                    data['OPERATION'] = info['Message']
                else:
                    data['OPERATION'] = 'Texture2D'
                call_data['str'] = obj
                call_data['args'] = {'snapshot': data}
                call_data['id'] = int(data['pID3D11Resource'], 16)
                return self.callbacks.on_event("object_snapshot", call_data)
            elif call_data['str'] == 'Name': #names for Texture2D
                static['tex2d'][data['pObject']] = data['DebugObjectName']
                return
            elif call_data['str'] in ['Fence', 'MonitoredFence', 'SynchronizationMutex', 'ReportSyncObject']:
                if 'Info' in opcode:
                    del call_data['data']
                if data.has_key('pSyncObject'):
                    obj = data['pSyncObject']
                else:
                    obj = data['hSyncObject']
                call_data['id'] = int(obj, 16) #QueuePacket.ObjectArray refers to it
                data['OPERATION'] = call_data['str']
                if data.has_key('Reason'):
                    data['OPERATION'] += ":" + SYNC_REASON[int(data['Reason'])]
                call_data['str'] = "SyncObject:" + obj
                call_data['args'] = {'snapshot': data}
                return self.callbacks.on_event("object_snapshot", call_data)

            elif call_data['str'] == 'ProcessAllocationDetails':
                if 'Info' in opcode: return
                call_data['id'] = int(data['Handle'], 16)
            """
        else:
            return

        self.callbacks.on_event(type, call_data)
        assert(type == TaskTypes[call_data['type']])
        if relation:
            if self.callbacks.check_time_in_limits(relation[0]['time']):
                for callback in self.callbacks.callbacks:
                    callback.relation(*relation)

    def finish(self):
        for id, file in self.files.iteritems():
            if file.has_key('last_access'): #rest aren't rendered anyways
                call_data = {'tid': file['tid'], 'pid': file['pid'], 'domain': 'MSNT_SystemTrace', 'time': file['last_access'], 'str': file['name'], 'type':11, 'id': int(id, 16)}
                self.callbacks.on_event("object_delete", call_data)

    def on_binary(self, system, data, info):
        opcode = int(system['Opcode'])
        if opcode >= len(OPCODES):
            return
        if info == '{fdf76a97-330d-4993-997e-9b81979cbd40}': #DX - Create/Dest Context
            """
            struct context_t
            {
                uint64_t device;
                uint32_t nodeOrdinal;
                uint32_t engineAffinity;
                uint32_t dmaBufferSize;
                uint32_t dmaBufferSegmentSet;
                uint32_t dmaBufferPrivateDataSize;
                uint32_t allocationListSize;
                uint32_t patchLocationListSize;
                uint32_t contextType;
                uint64_t context;
            };
            """
            chunk = data.decode('hex')
            (device, nodeOrdinal, engineAffinity, dmaBufferSize, dmaBufferSegmentSet, dmaBufferPrivateDataSize, allocationListSize, patchLocationListSize, contextType, context) = struct.unpack('QLLLLLLLLQ', chunk)
            self.context_to_node[context] = nodeOrdinal
        elif info == '{4746dd2b-20d7-493f-bc1b-240397c85b25}': #DX - Dma Packet
            """
            struct dma_packet_t
            {
                uint64_t context;
                uint32_t unknown1;
                uint32_t submissionId;
                uint32_t unknown2;
                uint32_t submitSequence;
            };
            """
            chunk = data.decode('hex')
            (context, packetType, submissionId, unknown, submitSequence) = struct.unpack('QLLLL', chunk[:24])
            new_info = {'Task': 'DmaPacket', 'Opcode' : OPCODES[opcode]}
            system['provider'] = 'Microsoft-Windows-DxgKrnl'
            return self.on_event(system, {'hContext': context, 'PacketType': packetType, 'uliSubmissionId':submissionId, 'ulQueueSubmitSequence': submitSequence}, new_info)
        elif info == '{295e0d8e-51ec-43b8-9cc6-9f79331d27d6}': #DX - Queue Packet
            """
            struct queue_packet_t
            {
                uint64_t context;
                uint32_t unknown1;
                uint32_t submitSequence;
            };
            """
            chunk = data.decode('hex')
            (context, packetType, submitSequence) = struct.unpack('QLL', chunk[:16])
            new_info = {'Task': 'QueuePacket', 'Opcode' : OPCODES[opcode]}
            system['provider'] = 'Microsoft-Windows-DxgKrnl'
            return self.on_event(system, {'SubmitSequence': submitSequence, 'PacketType': packetType}, new_info)

    def parse(self):
        with open(self.args.input) as file:
            self.file = file
            with Progress(os.path.getsize(self.args.input), 50, "Parsing ETW XML: " + os.path.basename(self.args.input)) as progress:
                self.progress = progress
                etwxml = ETWXML(self.on_event, [
                    'Microsoft-Windows-DXGI',
                    #'Microsoft-Windows-Direct3D11',
                    #'Microsoft-Windows-D3D10Level9',
                    #'Microsoft-Windows-Win32k',
                    'Microsoft-Windows-DxgKrnl',
                    'Microsoft-Windows-Dwm-Core',
                    '{9e814aad-3204-11d2-9a82-006008a86939}', #MSNT_SystemTrace
                    #'Microsoft-Windows-Shell-Core'
                    None #Win7 events
                ])
                unhandled_providers = etwxml.parse(file)
                self.finish()
            print "Unhandled providers:", str(unhandled_providers)
        if self.ftrace != None:
            self.ftrace.close()
            for pid, data in self.process_names.iteritems():
                for callback in self.callbacks.callbacks:
                    proc_name = data['name']
                    if len(data['cmd']) > len(proc_name):
                        proc_name = data['cmd'].replace('\\"', '').replace('"', '')
                    callback("metadata_add", {'domain':'IntelSEAPI', 'str':'__process__', 'pid':int(pid, 16), 'tid':-1, 'data':proc_name})

def transform_etw_xml(args):
    tree = default_tree()
    tree['ring_buffer'] = True
    TaskCombiner.disable_handling_leftovers = True
    with Callbacks(args, tree) as callbacks:
        if callbacks.is_empty():
            return callbacks.get_result()
        handler = ETWXMLHandler(args, callbacks)
        handler.parse()
    TaskCombiner.disable_handling_leftovers = False
    res = callbacks.get_result()
    if handler.ftrace != None:
        res += [handler.ftrace.name]
    return res

if __name__ == "__main__":
    main()
