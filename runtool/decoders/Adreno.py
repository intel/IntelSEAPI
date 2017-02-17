
TRACK_INDEX, TRACK_NAME = -1, 'GPU'


class Adreno:
    def __init__(self, args, callbacks):
        self.callbacks = callbacks
        self.gpu = self.callbacks.process(TRACK_INDEX, TRACK_NAME)
        self.ctx = {}
        self.gpu_tasks = []
        self.cpu_tasks = []
        self.task_counter = 0
        self.memory = {}
        self.switches = {}

    @staticmethod
    def parse_args(args):
        res = {None:[]}
        no_pair = []
        for chunk in args.split():
            if '=' in chunk:
                key, val = chunk.split('=')
                res[key] = val
            else:
                res[None].append(chunk)
        return res

    def gpu_queue(self, ctx, inflight, timestamp):
        state = self.ctx.setdefault(ctx, {'inflight': inflight, 'queued': None})
        delta = (inflight - state['inflight']) if state['inflight'] is not None else 0
        state['inflight'] = inflight
        if not delta:
            return
        thread = self.gpu.thread(ctx, 'GPU %d' % ctx)
        for i in xrange(abs(delta)):
            if delta > 0:
                task = thread.task(str(self.task_counter), 'Adreno', overlapped=True).begin(timestamp + len(self.gpu_tasks) * 1000, self.task_counter)
                self.gpu_tasks.append(task)
                self.task_counter += 1
                for cpu_task in self.cpu_tasks:
                    if cpu_task.get_args()['ctx'] == ctx and not cpu_task.relation and cpu_task.get_data()['realtime'] < task.get_data()['realtime']:
                        task.relate(cpu_task)
                        break
            elif self.gpu_tasks:
                self.gpu_tasks[0].end(timestamp - (len(self.gpu_tasks) - 1) * 1000)
                del self.gpu_tasks[0]

    def cpu_queue(self, pid, tid, ctx, queued, timestamp):
        state = self.ctx.setdefault(ctx, {'inflight': None, 'queued': queued})
        delta = (queued - state['queued']) if state['queued'] is not None else 0
        state['queued'] = queued
        if not delta:
            return
        for i in xrange(abs(delta)):
            if delta > 0:
                self.cpu_tasks.append(
                    self.callbacks.process(pid).thread(tid)
                        .task(str(self.task_counter), 'Adreno', overlapped=True)
                        .begin(timestamp + len(self.cpu_tasks) * 1000, self.task_counter, args={'ctx': ctx})
                )
                self.task_counter += 1
            elif self.cpu_tasks:
                self.cpu_tasks[0].end(timestamp - (len(self.cpu_tasks) - 1) * 1000)
                del self.cpu_tasks[0]

    def gpu_memory(self, timestamp, delta, args):
        args = self.parse_args(args)
        usage = args['usage']
        amount = self.memory.setdefault(usage, {'amount': 0})
        size = delta * int(args['size'])
        amount['amount'] = max(amount['amount'] + size, 0)
        thread = self.gpu.thread(-1)
        thread.counter('MEMORY: ' + usage).set_value(timestamp, amount['amount'])

    def switch(self, time, gpu, on):
        gpu_state = self.switches.setdefault(gpu, {'frame': None})
        if on:
            gpu_state['frame'] = self.gpu.thread(gpu, ('GPU %d' % gpu) if gpu else 'GPU IDLE').frame('WORKS' if gpu else 'GPU IDLE').begin(time)
        elif gpu_state['frame']:
            gpu_state['frame'].end(time)
            gpu_state['frame'] = None

    def handle_record(self, proc, pid, tid, cpu, flags, timestamp, name, args):
        adreno = name.startswith('adreno_') or name.startswith('kgsl_') or name in ['dispatch_queue_context']
        if not adreno:
            return
        if name == 'adreno_cmdbatch_queued':
            args = self.parse_args(args)
            self.cpu_queue(pid, tid, int(args['ctx']), int(args['queued']), timestamp)
        elif name == 'dispatch_queue_context':
            pass
        elif name == 'adreno_cmdbatch_submitted':
            args = self.parse_args(args)
            self.gpu_queue(int(args['ctx']), int(args['inflight']), timestamp)
            # print 'submitted', args
        elif name == 'adreno_cmdbatch_retired':
            args = self.parse_args(args)
            self.gpu_queue(int(args['ctx']), int(args['inflight']), timestamp)
            # print 'retired', args
        elif name == 'kgsl_waittimestamp_entry':  # ctx here is important, but absent in _exit, and adreno_drawctxt_wait does the same
            """
            thread = self.callbacks.process(pid).thread(tid)
            thread.task_stack.append(thread.task('waittimestamp', 'Adreno').begin(timestamp))
            """
        elif name == 'kgsl_waittimestamp_exit':
            """
            thread = self.callbacks.process(pid).thread(tid)
            if thread.task_stack:
                task = thread.task_stack.pop()
                task.end(timestamp)
            """
        elif name == 'adreno_drawctxt_switch':
            args = self.parse_args(args)
            self.switch(timestamp, int(args['oldctx']), False)
            self.switch(timestamp, int(args['newctx']), True)
        elif name == 'adreno_drawctxt_wait_start':
            args = self.parse_args(args)
            thread = self.callbacks.process(pid).thread(tid)
            thread.task_stack.append(thread.task('wait', 'Adreno').begin(timestamp, args=args))
        elif name == 'adreno_drawctxt_wait_done':
            args = self.parse_args(args)
            thread = self.callbacks.process(pid).thread(tid)
            if thread.task_stack:
                task = thread.task_stack.pop()
                task.end(timestamp)
        elif name == 'kgsl_pwrlevel':
            args = self.parse_args(args)
            thread = self.gpu.thread(-1)
            thread.counter('POWER_LEVEL').set_value(timestamp, int(args['pwrlevel']))
            thread.counter('FREQUENCY').set_value(timestamp, int(args['freq']))
        elif name in ['kgsl_pwr_set_state', 'kgsl_pwr_request_state']:
            args = self.parse_args(args)
            thread = self.gpu.thread(-1)
            if 'state' in args:
                state = 0 if args['state'] == 'NAP' else 1
            else:
                state = 0 if 'NAP' in args[None] else 1
            thread.counter('POWER_STATE').set_value(timestamp, state)
        elif name == 'kgsl_gpubusy':
            args = self.parse_args(args)
            thread = self.gpu.thread(-1)
            thread.counter('busy').set_value(timestamp, int(args['busy']))
            thread.counter('elapsed').set_value(timestamp, int(args['elapsed']))
        elif name == 'kgsl_tz_params':
            args = self.parse_args(args)
            thread = self.gpu.thread(-1)
            thread.counter('total_time').set_value(timestamp, int(args['total_time']))
            thread.counter('busy_time').set_value(timestamp, int(args['busy_time']))
            thread.counter('idle_time').set_value(timestamp, int(args['idle_time']))
        elif name == 'kgsl_a3xx_irq_status':
            args = self.parse_args(args)
            thread = self.gpu.thread(-1)
            thread.object(0, args['d_name'], 'Adreno').snapshot(timestamp, args)
        elif name in ['kgsl_bus', 'kgsl_rail', 'kgsl_irq', 'kgsl_clk']:
            args = self.parse_args(args)
            thread = self.gpu.thread(-1)
            if 'flag' in args:
                state = 1 if args['flag'] == 'on' else 0
            else:
                state = 1 if 'on' in args[None] else 0
            thread.counter(name.split('_')[1].upper()).set_value(timestamp, state)
        elif name in ['kgsl_register_event', 'kgsl_fire_event', 'kgsl_regwrite', 'kgsl_issueibcmds', 'kgsl_active_count']:
            args = self.parse_args(args)
            self.callbacks.process(pid).thread(tid).marker('thread', name, 'Adreno').set(timestamp, args=args)
        elif name == 'kgsl_mem_alloc':
            self.gpu_memory(timestamp, +1, args)
        elif name in ['kgsl_mem_mmap', 'kgsl_mem_map']:
            self.callbacks.process(pid).thread(tid).object(0, 'mem_map', 'Adreno').snapshot(timestamp, args)
        elif name == 'kgsl_mem_free':
            self.gpu_memory(timestamp, -1, args)
        elif name in ['kgsl_context_create', 'kgsl_context_detach', 'kgsl_context_destroy']:
            pass
        elif name in ['kgsl_mem_timestamp_queue', 'kgsl_mem_timestamp_free']:
            pass
        else:
            print name

    def finalize(self):
        pass


DECODER_DESCRIPTORS = [{
    'format': 'ftrace',
    'available': True,
    'decoder': Adreno
},
]
