import os
import sys
import glob
import codecs
from sea_runtool import default_tree, Callbacks, Progress, TaskCombiner, get_exporters, get_decoders, get_importers, format_bytes
sys.path.append(os.path.realpath(os.path.dirname(__file__)))  # weird CentOS behaviour workaround
from etw import GPUQueue


class DTrace(GPUQueue):
    def __init__(self, args, gt, callbacks):
        GPUQueue.__init__(self, args, callbacks)
        self.cs = None
        self.ignore_gpu = True  # workaround for incomplete dtrace ring
        self.cpu_packets = {}
        self.gpu_packets = {}
        self.thread_names = {}
        self.gpu_transition = {}
        self.gpu_frame = {'catch': [0, 0], 'task': None}
        self.prepares = {}
        self.pid_names = {}
        self.tid_map = {}
        self.event_tracker = {}  # key is ring+channel => key is tracking stamp => [events]
        self.contexts = {u'0': 'System'}  # id to type map
        for callback in self.callbacks.callbacks:
            if 'ContextSwitch' in dir(callback):
                self.cs = callback.ContextSwitch(callback, args.input + '.ftrace')
        self.callbacks("metadata_add", {'domain': 'GPU', 'str': '__process__', 'pid': -1, 'tid': -1, 'data': 'GPU Contexts', 'time': 0, 'delta': -2})

        self.decoders = []
        decoders = get_decoders()
        if 'dtrace' in decoders:
            for decoder in decoders['dtrace']:
                self.decoders.append(decoder(args, callbacks))

        self.read_system_info()

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
        if tid == 0:
            return
        if name == 'kernel_task':
            return
        if tid in self.tid_map:
            self.pid_names[self.tid_map[tid]] = name
        else:
            self.pid_names[tid] = name

    def handle_record(self, time, cmd, args):
        if not self.callbacks.check_time_in_limits(time):
            return
        if cmd == 'off':
            if not self.cs:
                return
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
        elif cmd.startswith('dtHook'):
            if not self.ignore_gpu:
                pid, tid = args[0:2]
                self.gpu_call(time, cmd[6:], int(pid, 16), int(tid, 16), args[2:])
            elif cmd == 'dtHookCompleteExecute':
                self.ignore_gpu = False
        elif cmd in ['e', 'r']:
            pid, tid = args[0:2]
            self.task(time, int(pid, 16), int(tid, 16), cmd == 'e', args[2], args[3], args[4:])
        elif cmd == 'arg':
            pid, tid = args[0:2]
            self.arg(time, int(pid, 16), int(tid, 16), args[2], '\t'.join(args[3:]))
        else:
            if self.decoders:
                pid, tid = args[0:2]
                pid, tid = int(pid, 16), int(tid, 16)
                for decoder in self.decoders:
                    decoder.handle_record(time, pid, tid, cmd, args[2:])
            else:
                print "unsupported cmd:", cmd, args

    def handle_stack(self, kind, time, pid, tid, stack):
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

    def task(self, time, pid, tid, starts, domain, name, args):
        self.tid_map[tid] = pid
        if name in ['IGAccelGLContext::BlitFramebuffer', 'CGLFlushDrawable']:
            self.gpu_frame['catch'][0 if starts else 1] = time
            if name == 'CGLFlushDrawable':
                return
        """ OLD WAY
        data = {
            'domain': domain, 'type': 0 if starts else 1,
            'time': time, 'tid': tid, 'pid': pid, 'str': name,
            'args': dict((idx, val) for idx, val in enumerate(args))
        }
        self.callbacks.on_event('task_begin' if starts else 'task_end', data)
        """
        thread = self.callbacks.process(pid).thread(tid)
        if starts:
            item = thread.task(name, domain) if not args or args[0] == '0' else thread.frame(name, domain)
            thread.task_stack.append(item.begin(time))
        elif thread.task_stack:  # it's fine, circular buffer can eat some begins
            task = thread.task_stack.pop()
            task.end(time)

    def arg(self, time, pid, tid, name, value):
        thread = self.callbacks.process(pid).thread(tid)
        if thread.task_stack:
            thread.task_stack[-1].add_args({name: value})
        else:
            print "Orphan arg:", name, value

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
                if self.gpu_frame['catch'][0] <= relation[1]['time'] <= self.gpu_frame['catch'][1]:
                    self.gpu_frame['task'] = id
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

    def append_stage(self, ring_type, channel, stamp, data):
        self.event_tracker.setdefault((ring_type, channel), {}).setdefault(int(stamp, 16), []).append(data)

    def complete_stage(self, ring_type, channel, latest_stamp, data):
        stamps = self.event_tracker.setdefault((ring_type, channel), {})
        latest_stamp = int(latest_stamp, 16)
        to_del = set(stamp for stamp in stamps.iterkeys() if stamp <= latest_stamp)
        if len(to_del) < 100:  # in old driver the CompleteExecute might be called so rare that it is not reliable at all
            for stamp, stages in stamps.iteritems():
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
                    if self.args.verbose:
                        print 'verbose:', ' '.join(verbose)
                    if not changed_context:  # not sure what TODO with it yet
                        task = self.complete_gpu(stages[-1], data, ctx_type, old_ctx_id)
                        found_submit = False
                        for stage in stages:
                            if stage['cmd'] in ['SubmitQueueKMD', 'WriteStamp']:
                                found_submit = True
                                task = self.complete_cpu(stage, data, ctx_type, old_ctx_id, task)
                                if stages[0]['cmd'] == 'PrepareQueueKMD':
                                    self.complete_prepare(stages[0], stage, ctx_type, old_ctx_id, task)
                                break
                        if not found_submit:
                            self.complete_cpu(stages[0], data, ctx_type, old_ctx_id, task)
        for stamp in to_del:
            del stamps[stamp]

    def complete_gpu(self, submit, complete, ctx_type, ctx_id):
        task = self.callbacks.process(-1).thread(int(ctx_id, 16))\
            .task('%s-%s: %s' % (self.map_ring_type(submit['ring_type']), int(submit['channel'], 16), submit['stamp']), 'dth')\
            .begin(submit['time'])
        task.end_overlap(complete['time'])
        return task

    def complete_cpu(self, submit, complete, ctx_type, ctx_id, gpu):
        task = self.callbacks.process(submit['pid']).thread(-int(submit['channel'], 16), '%s ring' % self.map_ring_type(submit['ring_type']))\
            .task('%s-%s: %s' % (ctx_type, int(ctx_id, 16), submit['stamp']), 'dth')\
            .begin(submit['time'])
        task.relate(gpu)
        task.end_overlap(complete['time'])
        return task

    def complete_prepare(self, prepare, submit, ctx_type, ctx_id, cpu):
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
            self.append_stage(ring_type, channel, stamp, locals())
        elif 'SubmitQueueKMD' == cmd:
            if len(args) == 7:
                ctx_id, ctx_type, ring_type, channel, stamp, umd_submission_id, umd_call_count = args
            else:
                ctx_id, stamp, ctx_type, umd_submission_id, umd_call_count = args
                ring_type, channel = '0', '0'
            ctx_type = self.map_context_type(ctx_type)
            self.contexts[ctx_id] = ctx_type
            self.append_stage(ring_type, channel, stamp, locals())
        elif 'SubmitToRing' == cmd:
            if len(args) == 4:
                ctx_id, ring_type, channel, stamp = args
            else:
                ctx_id, stamp, ring_type = args
                channel = '0'
            self.append_stage(ring_type, channel, stamp, locals())
        elif 'SubmitBatchBuffer' == cmd:
            if len(args) == 4:
                ctx_id, ring_type, channel, stamp = args
            else:
                ctx_id, stamp, ring_type = args
                channel = '0'
            self.append_stage(ring_type, channel, stamp, locals())
        elif 'SubmitExecList' == cmd:
            ctx_id, ring_type, channel, stamp = args
            self.append_stage(ring_type, channel, stamp, locals())
        elif 'CompleteExecute' == cmd:
            if len(args) == 2:
                ring_type, latest_stamp = args
                channel = '0'
            else:
                ring_type, channel, latest_stamp = args
            self.complete_stage(ring_type, channel, latest_stamp, locals())
        elif 'CompleteExecList' == cmd:
            ctx_id, ring_type, channel, latest_stamp, ctx_run_time = args
            self.complete_stage(ring_type, channel, latest_stamp, locals())
        elif 'WriteStamp' == cmd:
            ctx_id, ring_type, channel, stamp = args
            self.append_stage(ring_type, channel, stamp, locals())
        elif 'RemoveQueueKMD' == cmd:
            if len(args) == 2:
                ring_type, latest_stamp = args
                channel = '0'
            else:
                ring_type, channel, latest_stamp = args
            self.complete_stage(ring_type, channel, latest_stamp, locals())
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
            cpu_time = int(cpu_time, 16)
            if not cpu_time:
                if self.args.debug:
                    print "Warning: zero timestamp: ", cmd, args
                return
            thread = self.callbacks.process(-1).thread(int(ctx_id, 16))
            ring = self.map_ring_type(ring_type)
            thread.task_pool[(ring_type, channel, stamp)] = thread.task("GPU:" + ring, 'dth').begin(cpu_time, args={
                'ring': ring, 'stamp': stamp, 'channel': int(channel, 16), 'ctx_id': int(ctx_id, 16)
            })
        elif 'EndExecOnGPU' == cmd:
            cpu_time, ctx_id, ring_type, channel, stamp = args
            cpu_time = int(cpu_time, 16)
            if not cpu_time:
                if self.args.debug:
                    print "Warning: zero timestamp: ", cmd, args
                return
            thread = self.callbacks.process(-1).thread(int(ctx_id, 16))
            if (ring_type, channel, stamp) in thread.task_pool:
                thread.task_pool[(ring_type, channel, stamp)].end(cpu_time)
                del thread.task_pool[(ring_type, channel, stamp)]
        else:
            print "Unhandled gpu_call:", cmd

    def on_gpu_frame(self, time, pid, tid):
        self.callbacks.on_event("marker", {'pid': pid, 'tid': tid, 'domain': 'gits', 'time': time, 'str': "GPU Frame", 'type': 5, 'data': 'task'})

    def finalize(self):
        for tid, (name, pid) in self.thread_names.iteritems():
            for callback in self.callbacks.callbacks:
                thread_name = name.replace('\\"', '').replace('"', '')
                callback("metadata_add", {'domain': 'IntelSEAPI', 'str': '__thread__', 'pid': pid, 'tid': tid, 'data': '%s (%d)' % (thread_name, tid)})
        for pid, name in self.pid_names.iteritems():
            self.callbacks.set_process_name(pid, name)
            self.callbacks.set_process_name(-pid, 'Sampling: ' + name)

        for context, name in self.contexts.iteritems():
            self.callbacks.set_thread_name(-1, int(context, 16), name)

        for pid, proc in self.callbacks.processes.iteritems():
            name = None
            for tid, thread in proc.threads.iteritems():
                if tid in self.pid_names:
                    name = self.pid_names[tid]
                    break
            if name:
                self.callbacks.set_process_name(pid, name)
                self.callbacks.set_process_name(-pid, 'Sampling: ' + name)


def transform_dtrace(args):
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
                for line in file:
                    count += 1
                    ends_with_vt = (11 == ord(line[-1])) if len(line) else False
                    #old_line = line
                    line = line.strip('\r\n')
                    #print "%d\t%s" % (count, line)
                    if not line:
                        if reading_stack:
                            dtrace.handle_stack(*(reading_stack + [stack]))
                            reading_stack = None
                            stack = []
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
                        print "Warning: weird line:", line
                        continue
                    if parts[1] in ['ustack', 'kstack', 'jstack']:
                        reading_stack = [parts[1], int(parts[0], 16), parts[2], parts[3].rstrip(':')]
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
