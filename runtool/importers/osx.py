import os
import sys
from sea_runtool import default_tree, Callbacks, Progress, TaskCombiner, get_exporters
sys.path.append(os.path.realpath(os.path.dirname(__file__)))  # weird CentOS behaviour workaround
from etw import GPUQueue


class DTrace(GPUQueue):
    def __init__(self, args, gt, callbacks):
        GPUQueue.__init__(self, args, callbacks)
        self.res = [args.input + '.ftrace']
        self.cs = gt.ContextSwitch(self.res[0])
        self.ignore_gpu = True  # workaround for incomplete dtrace ring
        self.cpu_packets = {}
        self.gpu_packets = {}
        self.thread_names = {}
        self.gpu_transition = {}
        self.gpu_frame = {'catch': [0, 0], 'task': None}
        self.prepares = {}
        for callback in self.callbacks.callbacks:
            callback("metadata_add", {'domain': 'GPU', 'str': '__process__', 'pid': -1, 'tid': -1, 'data': 'GPU Engines', 'time': 0, 'delta': -2})

    def handle_record(self, time, cmd, args):
        if cmd == 'off':
            if not self.callbacks.check_time_in_limits(time):
                return
            cpu, prev_tid, prev_prio, prev_name, next_tid, next_prio, next_name = args

            # setting kernel activities of 0 priority as Idle:
            if prev_prio == '0' and prev_name == 'kernel_task':
                prev_tid = '0'
            if next_prio == '0' and next_name == 'kernel_task':
                next_tid = '0'

            self.cs.write(
                time=time, cpu=int(cpu, 16),
                prev_tid=int(prev_tid, 16), prev_state='S', next_tid=int(next_tid, 16),
                prev_prio=int(prev_prio, 16), next_prio=int(next_prio, 16),
                prev_name=prev_name.replace(' ', '_'), next_name=next_name.replace(' ', '_')
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
        else:
            print "unsupported cmd:", cmd, args

    def task(self, time, pid, tid, starts, domain, name, args):
        if name in ['IGAccelGLContext::BlitFramebuffer', 'CGLFlushDrawable']:
            self.gpu_frame['catch'][0 if starts else 1] = time
            if name == 'CGLFlushDrawable':
                return
        data = {
            'domain': domain, 'type': 0 if starts else 1,
            'time': time, 'tid': tid, 'pid': pid, 'str': name,
            'args': dict((idx, val) for idx, val in enumerate(args))
        }
        self.callbacks.on_event('task_begin' if starts else 'task_end', data)

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

    def gpu_call(self, time, cmd, pid, tid, args):
        if 'PrepareQueueKMD' == cmd:  # first argument seems to be 'context', see SwCtxDestroy
            id = args[-2] if len(args) == 3 else args[-1]
            self.prepares[id] = {
                'domain': 'AppleIntelGraphics', 'type': 7,
                'time': time, 'tid': tid, 'pid': pid, 'str': 'PrepareQueueKMD', 'id': int(id, 16),
                'args': dict((idx, val) for idx, val in enumerate(args))
            }
        elif 'SwCtxCreation' == cmd:
            pass
        elif 'SubmitExecList' == cmd:
            pass
        elif 'SubmitQueueKMD' == cmd:
            id = args[-3] if len(args) == 7 else args[-4]
            self.submit_prepare(time, id, pid, tid, args)
            if id in self.gpu_packets:
                return
            self.gpu_packets[id] = begin_data = {
                'domain': 'AppleIntelGraphics', 'type': 2,
                'time': time, 'tid': int(args[3], 16), 'pid': -1, 'str': id, 'id': int(id, 16),
                'args': dict((idx, val) for idx, val in enumerate(args))
            }
            self.report_relation(id, begin_data)

            self.auto_break_gui_packets(begin_data, 2 ** 64 + begin_data['tid'], True)
            self.callbacks.on_event("task_begin_overlapped", begin_data)
        elif 'SubmitToRing' == cmd:
            id = args[-3] if len(args) == 4 else args[-2]
            if id.endswith('00000000'):
                id = id[:-8]
                if args[0][0] == 'f' and args[-1] != id and id in self.gpu_packets:  # change of id when sending to GPU
                    self.gpu_transition[args[-1]] = id
            if int(id, 16) == 0:
                id = args[-1]
            if id in self.cpu_packets:
                return
            self.cpu_packets[id] = begin_data = {
                'domain': 'AppleIntelGraphics', 'type': 2,
                'time': time, 'tid': -tid, 'pid': pid, 'str': id, 'id': int(id, 16),
                'args': dict((idx, val) for idx, val in enumerate(args))
            }
            self.auto_break_gui_packets(begin_data, begin_data['tid'], True)
            self.callbacks.on_event("task_begin_overlapped", begin_data)
            if begin_data['tid'] not in self.thread_names:
                self.thread_names[begin_data['tid']] = ("CPU Queue", begin_data['pid'])
        elif 'SubmitBatchBuffer' == cmd:
            id = args[1]
            if id in self.cpu_packets:
                self.cpu_packets[id]['name'] = 'BatchBuffer:' + id
        elif '2DBlt' == cmd:
            id = args[1]
            if id in self.cpu_packets:
                self.cpu_packets[id]['name'] = '2DBlt:' + id
        elif '3DBlt' == cmd:
            id = args[1]
            if id in self.cpu_packets:
                self.cpu_packets[id]['name'] = '3DBlt:' + id
        elif 'CompleteExecList' == cmd:
            pass
        elif 'CompleteExecute' == cmd:
            id = args[-1]
            gpu_task_id = id
            if gpu_task_id not in self.gpu_packets and gpu_task_id in self.gpu_transition:
                gpu_task_id = self.gpu_transition[id]
                del self.gpu_transition[id]
                if gpu_task_id in self.gpu_packets:
                    self.report_relation(id, self.gpu_packets[gpu_task_id])
            if id in self.cpu_packets:
                end_data = self.cpu_packets[id]
                end_data.update({'time': time, 'type': 3})
                self.auto_break_gui_packets(end_data, end_data['tid'], False)
                self.callbacks.on_event("task_end_overlapped", end_data)
                del self.cpu_packets[id]
            if gpu_task_id in self.gpu_packets:
                end_data = self.gpu_packets[gpu_task_id]
                end_data.update({'time': time, 'type': 3})
                self.auto_break_gui_packets(end_data, 2 ** 64 + end_data['tid'], False)
                self.callbacks.on_event("task_end_overlapped", end_data)
                if id == self.gpu_frame['task']:
                    self.on_gpu_frame(time, end_data['pid'], end_data['tid'])
                del self.gpu_packets[gpu_task_id]
        elif 'RemoveQueueKMD' == cmd:
            pass
        elif 'SwCtxDestroy' == cmd:
            pass
        elif 'WriteStamp' == cmd:
            pass
        else:
            print cmd

    def on_gpu_frame(self, time, pid, tid):
        self.callbacks.on_event("marker", {'pid': pid, 'tid': tid, 'domain': 'gits', 'time': time, 'str': "GPU Frame", 'type': 5, 'data': 'task'})

    def finalize(self):
        for tid, (name, pid) in self.thread_names.iteritems():
            for callback in self.callbacks.callbacks:
                thread_name = name.replace('\\"', '').replace('"', '')
                callback("metadata_add", {'domain': 'IntelSEAPI', 'str': '__thread__', 'pid': pid, 'tid': tid, 'data': '%s (%d)' % (thread_name, tid)})

    def get_result(self):
        return [path for path in self.res if os.path.exists(path)]


def transform_dtrace(args):
    tree = default_tree(args)
    tree['ring_buffer'] = True
    args.no_left_overs = True
    gt = get_exporters()['gt']
    with Callbacks(args, tree) as callbacks:
        if callbacks.is_empty():
            return callbacks.get_result()
        dtrace = DTrace(args, gt, callbacks)
        with Progress(os.path.getsize(args.input), 50, "Parsing: " + os.path.basename(args.input)) as progress:
            count = 0
            with open(args.input) as file:
                for line in file:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split('\t')
                    dtrace.handle_record(int(parts[0], 16), parts[1], parts[2:])
                    if not count % 1000:
                        progress.tick(file.tell())
                    count += 1
            dtrace.finalize()
    return callbacks.get_result() + dtrace.get_result()

IMPORTER_DESCRIPTORS = [{
    'format': 'dtrace',
    'available': True,
    'importer': transform_dtrace
}]
