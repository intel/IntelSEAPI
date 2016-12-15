import os
from sea_runtool import default_tree, Callbacks, Progress, TaskCombiner, ProgressConst, TaskTypes, format_bytes


class Parser:
    def __init__(self, args, callbacks):
        self.args = args
        self.callbacks = callbacks
        self.section = None
        self.header = {}
        self.current = {}
        self.line_break = False
        self.time_start = 0
        self.proc_map = {}
        self.per_cpu = {}
        self.category = {
            'CONTROL': self.on_control,
            'THREAD': self.on_thread,
            'KER_CALL': self.on_ker_call,
            'KER_EXIT': self.on_ker_exit,
            'COMM': self.on_comm,
            'SYSTEM': self.on_system,
            'INT_CALL': self.on_int_call,
            'INT_ENTR': self.on_int_entr,
            'INT_EXIT': self.on_int_exit,
            'INT_HANDLER_ENTR': self.on_int_handler_entr,
            'INT_HANDLER_EXIT': self.on_int_handler_exit,
            'PROCESS': self.on_process
        }

    def on_line(self, line, num):
        if self.section != 'KERNEL EVENTS':
            if line.startswith('--'):
                self.section = line.strip('- ')
                return
            if self.section == 'HEADER FILE INFORMATION':
                parts = line.split('::')
                self.header[parts[0].strip()] = parts[1].strip()
            else:
                parts = line.split('version')
                self.header[parts[0].strip()] = parts[1].strip()
        else:
            def add_arg(part):
                if ':' in part:
                    (name, value) = part.split(':', 1)
                    if 'rmsg' == name:
                        name = 'msg'
                    self.current['args'][name] = value
                    if name == 'msg':
                        self.line_break = value.count('"') % 2
                else:
                    idx = len(self.current['args'])
                    self.current['args'][idx] = part.strip()
            if line.startswith('t:'):
                self.handle_event()
                self.line_break = False
                self.current = {}
                parts = line.split(':')
                leading = ':'.join(parts[:3])
                trailing = line[len(leading) + 1:].strip().replace(',', '').replace(' = ', ':')
                parts = leading.split()
                self.current['time'] = int(parts[0].split(':')[1], 16)
                self.current['CPU'] = int(parts[1].split(':')[1])
                self.current['op'] = parts[2]
                parts = trailing.split()
                self.current['name'] = parts[0]
                self.current['args'] = {}
                for index, part in enumerate(parts[1:]):
                    if ':' in part:
                        add_arg(part)
                    else:
                        (name, value) = (index, part)
                        self.current['args'][name] = value
            else:
                if self.line_break:
                    self.current['args']['msg'] += line
                    self.line_break = not line.count('"') % 2
                else:
                    add_arg(line.replace('=', ':'))

    def handle_event(self):
        if not self.current:
            return
        op = self.current['op']
        assert(op in self.category)
        self.category[op]()

    def on_control(self):
        if self.current['name'] == 'TIME':
            msb = int(self.current['args']['msb'], 16)
            lsb = int(self.current['args']['lsb(offset)'], 16)
            self.time_start = msb * 2**32 + lsb
            pass
        elif self.current['name'] == 'BUFFER':
            pass  # num_events can be used here for sanity checks
        else:
            assert False

    def on_process(self):
        args = self.current['args']
        if self.current['name'] == 'PROCCREATE_NAME':
            assert(args['pid'] not in self.proc_map)
            args.update({'threads': {}})
            self.proc_map[args['pid']] = args
        elif self.current['name'] == 'PROCTHREAD_NAME':
            if args['pid'] not in self.proc_map:
                 self.proc_map[args['pid']] = {}
            threads = self.proc_map[args['pid']]['threads']
            threads.setdefault(args['tid'], {'name': args['name']})
        else:
            assert False

    def on_thread(self):
        args = self.current['args']
        if self.current['name'] == 'THCREATE':
            pass
        elif self.current['name'] == 'THRUNNING':
            self.per_cpu[self.current['CPU']] = (int(args['pid']), int(args['tid']))
        elif self.current['name'] == 'THREADY':
            pass  # TODO: for context switches
        elif self.current['name'] == 'THSIGWAITINFO':
            pass  # TODO: for context switches
        elif self.current['name'] == 'THNANOSLEEP':
            pass  # TODO: for context switches
        elif self.current['name'] == 'THSTOPPED':
            pass  # TODO: for context switches
        elif self.current['name'] == 'THWAITPAGE':
            pass  # TODO: for context switches
        elif self.current['name'] == 'THMUTEX':
            pass  # TODO: for context switches
        elif self.current['name'] == 'THRECEIVE':
            pass
        elif self.current['name'] == 'THREPLY':
            pass
        elif self.current['name'] == 'THCONDVAR':
            pass
        elif self.current['name'] == 'THSEND':
            pass
        else:
            print self.current['name']
            assert False

    def on_ker_call(self):
        (pid, tid) = self.per_cpu[self.current['CPU']]
        self.callbacks.on_event("task_begin", {'tid': tid, 'pid': pid, 'domain': 'qnx', 'time': self.time_start + self.current['time'], 'str': self.current['name'], 'type': 0})

    def on_ker_exit(self):
        (pid, tid) = self.per_cpu[self.current['CPU']]
        self.callbacks.on_event("task_end", {'tid': tid, 'pid': pid, 'domain': 'qnx', 'time': self.time_start + self.current['time'], 'type': 1})

    def on_comm(self):
        pass

    def on_system(self):
        pass

    def on_int_entr(self):
        pass

    def on_int_call(self):
        pass

    def on_int_exit(self):
        pass

    def on_int_handler_entr(self):
        pass

    def on_int_handler_exit(self):
        pass

    def finish(self):
        self.handle_event()
        self.current = {}
        for callback in self.callbacks.callbacks:
            for pid, proc_data in self.proc_map.iteritems():
                proc_name = proc_data['name'].replace('\\"', '').replace('"', '')
                callback("metadata_add", {'domain': 'IntelSEAPI', 'str': '__process__', 'pid': pid, 'tid': -1, 'data': proc_name})
                for tid, thread_data in proc_data['threads'].iteritems():
                    thread_name = thread_data['name'].replace('\\"', '').replace('"', '')
                    callback("metadata_add", {'domain': 'IntelSEAPI', 'str': '__thread__', 'pid': pid, 'tid': tid, 'data': '%s (tid %d)' % (thread_name, tid)})


def transform_qnx(args):
    tree = default_tree(args)
    tree['ring_buffer'] = True
    args.no_left_overs = True
    with Callbacks(args, tree) as callbacks:
        if callbacks.is_empty():
            return callbacks.get_result()
        parser = Parser(args, callbacks)
        count = 0
        with Progress(os.path.getsize(args.input), 50, "Parsing: " + os.path.basename(args.input)) as progress:
            with open(args.input) as file:
                for line in file:
                    parser.on_line(line.strip(), count)
                    count += 1
                    if not count % 1000:
                        progress.tick(file.tell())
                parser.finish()
    return callbacks.get_result()


IMPORTER_DESCRIPTORS = [{
    'format': 'qnx',
    'available': True,
    'importer': transform_qnx
}]
