from __future__ import absolute_import, print_function
import os
import re
import sys
import json
import codecs
import subprocess

from sea_runtool import default_tree, Callbacks, Progress, TaskCombiner, get_exporters, get_decoders, get_importers, format_bytes, message
sys.path.append(os.path.realpath(os.path.dirname(__file__)))  # weird CentOS behaviour workaround
from etw import GPUQueue
sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), '..', 'exporters')))
from SQLite import SQLiteWrapper, sortby


def demangle(name, static={}):
    if not name.startswith('_Z'):
        return name
    if name not in static:
        demangled, err = subprocess.Popen('c++filt -n ' + name, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
        static[name] = demangled.strip().decode('utf-8')
    return static[name]


SYNC_PRIM = ['MUTEX', 'RWLOCK', 'CV', 'SEMA', 'USER', 'USER_PI', 'SHUTTLE']


class DTrace(GPUQueue):
    def __init__(self, args, gt, callbacks):
        GPUQueue.__init__(self, args, callbacks)
        self.cs = None
        self.ignore_gpu = True  # workaround for incomplete dtrace ring
        self.cpu_packets = {}
        self.gpu_packets = {}
        self.thread_names = {}
        self.gpu_transition = {}
        self.prepares = {}
        self.pid_names = {}
        self.tid_map = {}
        self.event_tracker = {}  # key is ring+channel => key is tracking stamp => [events]
        self.contexts = {u'0': 'System'}  # id to type map
        callbacks.set_process_name(-1, 'GPU Contexts')
        self.stat = {}

        self.decoders = []
        decoders = get_decoders()
        if 'dtrace' in decoders:
            for decoder in decoders['dtrace']:
                self.decoders.append(decoder(args, callbacks))

        importers = get_importers()
        self.read_system_info()
        self.collected_domains = set()

    def read_system_info(self):
        path = os.path.join(self.args.user_input, 'sysinfo.txt')
        if not os.path.exists(path):
            return
        sys_info = {}
        with open(path) as file:
            for line in file:
                if not line.strip():
                    continue
                key, value = line.split(":", 1)
                subkeys = key.split(".")
                current = sys_info
                for subkey in subkeys:
                    prev = current
                    current = current.setdefault(subkey, {})
                value = value.strip()
                try:
                    value = eval(value)
                except:
                    pass
                prev[subkey] = value
        self.callbacks.add_metadata('SysInfo', sys_info)

    def add_tid_name(self, tid, name):
        if name == 'kernel_task':
            return

        # one of the tids is equal to pid, and all threads have the same name as process (if not renamed)
        pid = self.tid_map[tid] if tid in self.tid_map else tid
        if abs(pid) < 4:
            return

        if pid not in self.pid_names:
            self.pid_names[pid] = [name]
        elif name not in self.pid_names[pid]:
            assert abs(pid) > 100
            self.pid_names[pid].append(name)
            full_name = '->'.join(self.pid_names[pid])
            message('warning', 'Pid %d name changed: %s' % (pid, full_name))

    @sortby("time", step=0, table='first')
    def handle_record(self, time, cmd, args):
        if not self.callbacks.check_time_in_limits(time, cmd == 'off'):
            return
        if cmd == 'off':
            cpu, prev_tid, prev_prio, prev_name, next_tid, next_prio, next_name = args

            # setting kernel activities of 0 priority as Idle:
            if prev_prio == '0' and prev_name == 'kernel_task':
                prev_tid = '0'
            if next_prio == '0' and next_name == 'kernel_task':
                next_tid = '0'
            prev_tid = int(prev_tid, 16)
            next_tid = int(next_tid, 16)

            self.callbacks.context_switch(time, int(cpu, 16),
                prev_tid=prev_tid, prev_state='S', next_tid=next_tid,
                prev_prio=int(prev_prio, 16), next_prio=int(next_prio, 16),
                prev_name=prev_name.replace(' ', '_'), next_name=next_name.replace(' ', '_'))
            self.add_tid_name(prev_tid, prev_name)
            self.add_tid_name(next_tid, next_name)
        elif cmd == 'wkp':
            prev_pid, prev_tid, prev_name, cpu, next_name, next_pid, next_tid, prim_type, prim_addr = args
            self.callbacks.wakeup(time, int(cpu, 16),
                prev_pid=int(prev_pid, 16), prev_tid=int(prev_tid, 16),
                next_pid=int(next_pid, 16), next_tid=int(next_tid, 16),
                prev_name=prev_name.replace(' ', '_'),
                next_name=next_name.replace(' ', '_'),
                sync_prim=SYNC_PRIM[int(prim_type, 16)], sync_prim_addr=int(prim_addr, 16)
            )
        elif cmd.startswith('dtHook'):
            if not self.ignore_gpu:
                pid, tid = args[0:2]
                self.gpu_call(time, cmd[6:], int(pid, 16), int(tid, 16), args[2:])
            elif cmd == 'dtHookCompleteExecute':
                self.ignore_gpu = False
        elif cmd in ['e', 'r']:
            pid, tid = args[0:2]
            self.task(time, int(pid, 16), int(tid, 16), cmd == 'e', args[2], args[3], args[4:])
        elif cmd == 'm':
            pid, tid = args[0:2]
            self.marker(time, int(pid, 16), int(tid, 16), args[2], args[3], args[4:])
        elif cmd == 'arg':
            pid, tid = args[0:2]
            self.arg(time, int(pid, 16), int(tid, 16), args[2], '\t'.join(args[3:]))
        elif cmd == 'args':
            pid, tid = args[0:2]
            self.arguments(time, int(pid, 16), int(tid, 16), args[2:])
        elif cmd in ['ie', 'ir']:
            pid, tid = args[0:2]
            self.interrupt(time, int(pid, 16), int(tid, 16), cmd == 'ie', args[2], int(args[3], 16), args[4:])
        elif cmd == 'io':
            pid, tid = args[0:2]
            self.io(time, int(pid, 16), int(tid, 16), args[2], args[3])
        else:
            handled = False
            if self.decoders:
                pid, tid = args[0:2]
                pid, tid = int(pid, 16), int(tid, 16)
                for decoder in self.decoders:
                    res = decoder.handle_record(time, pid, tid, cmd, args[2:])
                handled |= True if res else False
            if not handled:
                message('warning', "unsupported cmd '%s': %s" % (str(cmd), str(args)))

    def io(self, time, pid, tid, op, path):
        path = path.replace('??/','')
        thread = self.callbacks.process(pid).thread(tid)
        if op == 'open':
            thread.task_pool[path] = thread.object(time, path).create(time)
            thread.task_pool[path].snapshot(time, {'op': op, 'tid': tid})
        elif path in thread.task_pool:
            assert op == 'close'
            thread.task_pool[path].snapshot(time, {'op': op, 'tid': tid})
            thread.task_pool[path].destroy(time)

    @sortby("time", step=0, table='first')
    def handle_stack(self, time, kind, pid, tid, stack):
        pid = int(pid, 16)
        tid = int(tid, 16)
        self.tid_map[tid] = pid
        if not self.callbacks.check_time_in_limits(time) or not self.callbacks.check_pid_allowed(pid):
            return
        parsed = []
        for frame in stack:
            if '`' in frame:
                module, name = frame.split('`', 1)
                parsed.append({'ptr': hash(name), 'module': module.strip(), 'str': name.strip()})
            else:
                parsed.append({'ptr': int(frame, 16), 'module': '', 'str': ''})
        self.callbacks.handle_stack(pid, tid, time, parsed, kind)

    def interrupt(self, time, pid, tid, starts, execname, cpu, args):
        self.task(time, pid, tid, starts, args[0], args[1], {'proc': execname, 'cpu': cpu})

    def task(self, time, pid, tid, starts, domain, name, args):
        name = demangle(name)
        self.collected_domains.add(domain)
        if 'mach_kernel' == domain:
            tid = -tid
        self.tid_map[tid] = pid
        thread = self.callbacks.process(pid).thread(tid)
        if not starts and name in ['-[MTLIGAccelCommandBuffer presentDrawable:]', 'IGAccelGLContext::BlitFramebuffer', 'eglSwapBuffers', 'CGLFlushDrawable', 'glutSwapBuffers', 'CGLSetCurrentContext', 'glEnd_Exec', '-[MTLIOAccelCommandBuffer commit]']:
            self.process_frame_boundary(time, thread, domain, name, args)

        # task_stack = thread.task_pool.setdefault(domain + (str(name, 'utf-8') if isinstance(name, bytes) else name), [])
        task_stack = thread.task_pool.setdefault(domain + name, [])
        if starts:
            item = thread.task(name, domain)
            task_stack.append(item.begin(time))
            if args:
                if isinstance(args, list):
                    assert args[0] != '0'  # if not args or args[0] == '0' else thread.frame(name, domain)
                    task_stack[-1].add_args(dict(enumerate(args)))
                else:
                    task_stack[-1].add_args(args)
            thread.task_stack.append(task_stack[-1])  # for arguments, see 'def arg' below
        elif task_stack:  # it's fine, circular buffer can eat some begins
            task = task_stack.pop()
            task.end(time)
            thread.task_stack.pop()

    def marker(self, time, pid, tid, domain, name, args):
        self.tid_map[tid] = pid
        thread = self.callbacks.process(pid).thread(tid)
        thread.marker('thread', '%s:%s' % (domain, name), 'objc').set(time, dict(enumerate(args)))

    def process_frame_boundary(self, time, thread, domain, name, args):
        auto_frame = thread.task_pool.setdefault('__sea_auto_frame__', {})

        if name in auto_frame:
            dur = time - auto_frame[name]
            thread.frame('FRAME').complete(auto_frame[name], time - auto_frame[name], args={
                'FPS': int(1e9 / dur),
                'AbsTime': auto_frame[name],
                'base': name
            })
        auto_frame[name] = time

    def arg(self, time, pid, tid, name, value):
        thread = self.callbacks.process(pid).thread(tid)
        if thread.task_stack:
            thread.task_stack[-1].add_args({name: value})
        else:
            message('warning', "Orphan arg: %s %s" % (name, value))

    def arguments(self,time, pid, tid, args):
        thread = self.callbacks.process(pid).thread(tid)
        if thread.task_stack:
            for n, value in enumerate(args):
                thread.task_stack[-1].add_args({n: int(value)})
        else:
            message('warning', "Orphan args: " + str(args))

    def submit_prepare(self, time, id, pid, tid, args):
        if id not in self.prepares:
            return
        end_data = self.prepares[id].copy()
        end_data.update({'time': time})
        self.callbacks.complete_task('frame', self.prepares[id], end_data)

    def report_relation(self, id, begin_data):
        if id in self.cpu_packets:
            relation = (begin_data.copy(), self.cpu_packets[id].copy(), begin_data)
            if 'realtime' in relation[1]:
                relation[1]['time'] = relation[1]['realtime']
            relation[0]['parent'] = begin_data['id']
            if self.callbacks.check_time_in_limits(relation[0]['time']):
                for callback in self.callbacks.callbacks:
                    callback.relation(*relation)
            return True

    @staticmethod
    def map_context_type(ctx_type):
        ctx_types = ['UNKNOWN', 'GL', 'CL', 'Media', 'Metal']
        if int(ctx_type) > len(ctx_types) - 1:
            ctx_type = 0
        return ctx_types[int(ctx_type)]

    @staticmethod
    def map_ring_type(ring_type):
        ring_types = ['Render', 'Media', 'Blit', 'VEBox']
        if int(ring_type) > len(ring_types) - 1:
            return 'UNKNOWN'
        return ring_types[int(ring_type)]

    @sortby("stamp", step=2, table='second')
    def append_stage(self, ring_type, channel, stamp, data):
        self.event_tracker.setdefault((ring_type, channel), {}).setdefault(stamp, []).append(data)

    @sortby("latest_stamp", step=2, table='second')
    def complete_stage(self, ring_type, channel, latest_stamp, data):
        stamps = self.event_tracker.setdefault((ring_type, channel), {})
        to_del = set(stamp for stamp in stamps.keys() if stamp <= latest_stamp)
        if len(to_del) < 100:  # in old driver with GuC the CompleteExecute might be called so rare that it is not reliable at all
            for stamp, stages in stamps.items():
                if stamp <= latest_stamp:
                    verbose = ['%s(%s) %d:' % (ring_type, channel, stamp)]
                    ctx_type = None
                    old_ctx_id = None
                    changed_context = False
                    for stage in stages:
                        verbose.append(stage['cmd'])
                        if 'ctx_id' in stage:
                            changed_context = old_ctx_id and old_ctx_id != stage['ctx_id']
                            verbose.append('(%s)' % (('!' if changed_context else '') + stage['ctx_id']))
                            old_ctx_id = stage['ctx_id']
                        if 'ctx_type' in stage:
                            assert ctx_type == stage['ctx_type'] or not ctx_type or changed_context
                            ctx_type = stage['ctx_type']
                    if not ctx_type and old_ctx_id:
                        ctx_type = self.contexts[old_ctx_id] if old_ctx_id in self.contexts else None
                    if ctx_type:
                        verbose.append('%s - %s' % (data['cmd'], ctx_type))
                    else:
                        verbose.append(data['cmd'])
                    message('info', 'verbose: ' + ' '.join(verbose))
                    if not changed_context:  # not sure what TODO with it yet
                        gpu_task = self.complete_gpu(stages[-1], data, ctx_type, old_ctx_id)
                        found_submit = False
                        cpu_task = None
                        for stage in stages:
                            if stage['cmd'] in ['SubmitQueueKMD', 'WriteStamp']:
                                found_submit = True
                                cpu_task = self.complete_cpu(stage, data, ctx_type, old_ctx_id, gpu_task)
                                break
                        for stage in stages:
                            if stage['cmd'] == 'PrepareQueueKMD':
                                self.complete_prepare(stages[0], stages[-1], ctx_type, old_ctx_id, cpu_task)
                                break
                        if not found_submit:
                            self.complete_cpu(stages[-1], data, ctx_type, old_ctx_id, gpu_task)
                    else:
                        message('warning', 'context has changed, not handled yet')
                else:
                    message('warning', 'timestamp order is bad, not handled yet')
        else:
            message('error', 'Unreliable CompleteExecutes: expect no GPU activity :(')

        for stamp in to_del:
            del stamps[stamp]

    def complete_gpu(self, submit, complete, ctx_type, ctx_id):
        task = self.callbacks.process(-1).thread(int(ctx_id, 16))\
            .task('%s-%s: %s' % (self.map_ring_type(submit['ring_type']), int(submit['channel'], 16), submit['stamp']), 'dth')\
            .begin(submit['time'])
        task.end_overlap(complete['time'])
        return task

    def complete_cpu(self, submit, complete, ctx_type, ctx_id, gpu_task):
        task = self.callbacks.process(submit['pid']).thread(-int(submit['channel'], 16), '%s ring' % self.map_ring_type(submit['ring_type']))\
            .task('%s-%s: %s' % (ctx_type, int(ctx_id, 16), submit['stamp']), 'dth')\
            .begin(submit['time'])
        task.relate(gpu_task)
        task.end_overlap(complete['time'])
        return task

    def complete_prepare(self, prepare, submit, ctx_type, ctx_id, cpu_task=None):
        task = self.callbacks.process(submit['pid']).thread(prepare['tid'])\
            .frame('Prepare %s-%s' % (self.map_ring_type(submit['ring_type']), int(submit['channel'], 16)))\
            .complete(prepare['time'], submit['time'] - prepare['time'], args={'ctx_type': ctx_type, 'ctx_id': int(ctx_id, 16)})
        return task

    def gpu_call(self, time, cmd, pid, tid, args):
        if 'PrepareQueueKMD' == cmd:
            if len(args) == 3:
                ctx_id, stamp, ctx_type = args
                ring_type, channel = '0', '0'
            else:
                ctx_id, ctx_type, ring_type, channel, stamp = args
            ctx_type = self.map_context_type(ctx_type)
            self.contexts[ctx_id] = ctx_type
            self.append_stage(ring_type, channel, int(stamp, 16), locals())
        elif 'SubmitQueueKMD' == cmd:
            if len(args) == 7:
                ctx_id, ctx_type, ring_type, channel, stamp, umd_submission_id, umd_call_count = args
            else:
                ctx_id, stamp, ctx_type, umd_submission_id, umd_call_count = args
                ring_type, channel = '0', '0'
            ctx_type = self.map_context_type(ctx_type)
            self.contexts[ctx_id] = ctx_type
            self.append_stage(ring_type, channel, int(stamp, 16), locals())
        elif 'SubmitToRing' == cmd:
            if len(args) == 4:
                ctx_id, ring_type, channel, stamp = args
            else:
                ctx_id, stamp, ring_type = args
                channel = '0'
            self.append_stage(ring_type, channel, int(stamp, 16), locals())
        elif 'SubmitBatchBuffer' == cmd:
            if len(args) == 4:
                ctx_id, ring_type, channel, stamp = args
            else:
                ctx_id, stamp, ring_type = args
                channel = '0'
            self.append_stage(ring_type, channel, int(stamp, 16), locals())
        elif 'SubmitExecList' == cmd:
            ctx_id, ring_type, channel, stamp = args
            self.append_stage(ring_type, channel, int(stamp, 16), locals())
        elif 'CompleteExecute' == cmd:
            if len(args) == 2:
                ring_type, latest_stamp = args
                channel = '0'
            else:
                ring_type, channel, latest_stamp = args
            self.complete_stage(ring_type, channel, int(latest_stamp, 16), locals())
        elif 'CompleteExecList' == cmd:
            ctx_id, ring_type, channel, latest_stamp, ctx_run_time = args
            self.complete_stage(ring_type, channel, int(latest_stamp, 16), locals())
        elif 'WriteStamp' == cmd:
            ctx_id, ring_type, channel, stamp = args
            self.append_stage(ring_type, channel, int(stamp, 16), locals())
        elif 'RemoveQueueKMD' == cmd:
            if len(args) == 2:
                ring_type, latest_stamp = args
                channel = '0'
            else:
                ring_type, channel, latest_stamp = args
            self.complete_stage(ring_type, channel, int(latest_stamp, 16), locals())
        elif 'SwCtxCreation' == cmd:
            ctx_id, ctx_type = args
            ctx_type = self.map_context_type(ctx_type)
            self.contexts[ctx_id] = ctx_type
        elif 'SwCtxDestroy' == cmd:
            ctx_id, ctx_type = args
            ctx_type = self.map_context_type(ctx_type)
            self.contexts[ctx_id] = ctx_type
        elif 'DidFlip' == cmd:
            self.callbacks.vsync(time)
        elif 'BeginExecOnGPU' == cmd:
            cpu_time, ctx_id, ring_type, channel, stamp = args
            if cpu_time[0] == 'f':
                message('error', "BeginExecOnGPU has wrong timestamp: " + str(args))
                return
            cpu_time = int(cpu_time, 16)
            if not cpu_time:
                if self.args.debug:
                    print("Warning: zero timestamp: ", cmd, args)
                return
            thread = self.callbacks.process(-1).thread(int(ctx_id, 16))
            ring = self.map_ring_type(ring_type)
            """ FIXME: fix lanes
            thread.lane('GPU:Render', 'dth').frame_begin(cpu_time, ring,args={
                'ring': ring, 'stamp': stamp, 'channel': int(channel, 16), 'ctx_id': int(ctx_id, 16)
            })
            """

            thread.task_pool[(ring_type, channel, stamp)] = thread.frame("GPU (%d)" % thread.tid, 'dth').begin(cpu_time, args={
                'ring': ring, 'stamp': stamp, 'channel': int(channel, 16), 'ctx_id': int(ctx_id, 16)
            })

            """
            thread.task_pool[(ring_type, channel, stamp)] = thread.task("GPU:" + ring, 'dth').begin(cpu_time, args={
                'ring': ring, 'stamp': stamp, 'channel': int(channel, 16), 'ctx_id': int(ctx_id, 16)
            })
            """
        elif 'EndExecOnGPU' == cmd:
            cpu_time, ctx_id, ring_type, channel, stamp = args
            if cpu_time[0] == 'f':
                message('error', "EndExecOnGPU has wrong timestamp: " + str(args))
                return
            cpu_time = int(cpu_time, 16)
            if not cpu_time:
                if self.args.debug:
                    print("Warning: zero timestamp: ", cmd, args)
                return
            thread = self.callbacks.process(-1).thread(int(ctx_id, 16))
            if (ring_type, channel, stamp) in thread.task_pool:
                thread.task_pool[(ring_type, channel, stamp)].end(cpu_time)
                del thread.task_pool[(ring_type, channel, stamp)]
        else:
            print("Unhandled gpu_call:", cmd)

    def on_gpu_frame(self, time, pid, tid):
        self.callbacks.on_event("marker", {'pid': pid, 'tid': tid, 'domain': 'gits', 'time': time, 'str': "GPU Frame", 'type': 5, 'data': 'task'})

    def handle_stat(self, mod, fun, dur):
        by_mod = self.stat.setdefault(mod, {None:0})
        assert fun not in by_mod
        by_mod[fun] = int(dur)

    def finalize(self):
        sortby.finalize(self)
        self.callbacks.get_globals()['dtrace']['finished'] = True

        for tid, (name, pid) in self.thread_names.items():
            for callback in self.callbacks.callbacks:
                thread_name = name.replace('\\"', '').replace('"', '')
                callback("metadata_add", {'domain': 'IntelSEAPI', 'str': '__thread__', 'pid': pid, 'tid': tid, 'data': '%s (%d)' % (thread_name, tid)})
        for pid, names in self.pid_names.items():
            for name in names:
                self.callbacks.set_process_name(pid, name)
                self.callbacks.set_process_name(-pid, 'Sampling: ' + name)

        for context, name in self.contexts.items():
            self.callbacks.set_thread_name(-1, int(context, 16), name)

        for pid, proc in self.callbacks.processes.items():
            if not self.callbacks.get_process_name(pid) and abs(pid) > 100:
                names = []
                for tid, thread in proc.threads.items():
                    if tid in self.pid_names:
                        assert tid != pid
                        names += self.pid_names[tid]

                for name in names:
                    self.callbacks.set_process_name(pid, name)
                    if pid > 0:
                        self.callbacks.set_process_name(-pid, 'Sampling: ' + name)

        if self.args.hook or self.args.hook_kmd:
            print('\nTo limit HOTSPOTS use:\t--hook ' + ' '.join(self.collected_domains))

        function_stat = []
        for mod, functions in self.stat.items():
            for fn, val in functions.items():
                function_stat.append((val, fn, mod))
        function_stat.sort(key=lambda val_fn_mod: val_fn_mod[0], reverse=True)

        for val, fn, mod in function_stat:
            if val:
                print('%d\t%s\t%s' % (val, fn, mod))


def transform_dtrace(args):
    if not os.path.exists(args.input):
        message('error', 'File not found: ' + args.input)
        return []
    tree = default_tree(args)
    tree['ring_buffer'] = True
    args.no_left_overs = True
    gt = get_exporters()['gt']
    with Callbacks(args, tree) as callbacks:
        if callbacks.is_empty():
            return callbacks.get_result()
        dtrace = DTrace(args, gt, callbacks)
        size = os.path.getsize(args.input)
        with Progress(size, 50, "Parsing: %s (%s)" % (os.path.basename(args.input), format_bytes(size))) as progress:
            count = 0
            with codecs.open(args.input, 'r', 'utf-8', errors='ignore') as file:
                reading_stack = None
                stack = []
                stat = None
                for line in file:
                    count += 1
                    ends_with_vt = (11 == ord(line[-1])) if len(line) else False
                    #old_line = line
                    line = line.strip('\r\n')
                    #print("%d\t%s" % (count, line))
                    if not line:
                        if reading_stack:
                            dtrace.handle_stack(*(reading_stack + [stack]))
                            reading_stack = None
                            stack = []
                        continue
                    if stat is not None:
                        parts = line.split()
                        dtrace.handle_stat(parts[0], ' '.join(parts[1:-1]), parts[-1])
                        continue
                    if reading_stack:
                        if ends_with_vt:  # Vertical Tab signifies too long stack frame description
                            line += '...'
                            end_of_line = file.readline()  # it is also treated as line end by codecs.open
                            line += end_of_line.strip()
                        stack.append(line.replace('\t', ' '))
                        continue
                    parts = line.split('\t')
                    if len(parts) < 4:
                        if '-=STATS=-' in parts:
                            stat = {}
                        else:
                            message('warning', "weird line:" + line)
                        continue
                    if parts[1] in ['ustack', 'kstack', 'jstack']:
                        reading_stack = [int(parts[0], 16), parts[1], parts[2], parts[3].rstrip(':')]
                        continue
                    dtrace.handle_record(int(parts[0], 16), parts[1], parts[2:])
                    if not count % 1000:
                        progress.tick(file.tell())
            dtrace.finalize()
    return callbacks.get_result()

IMPORTER_DESCRIPTORS = [{
    'format': 'dtrace',
    'available': True,
    'importer': transform_dtrace
}]
