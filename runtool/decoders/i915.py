
class I915:
    def __init__(self, callbacks):
        self.counters = {}
        self.callbacks = callbacks

    def handle_record(self, proc, pid, tid, cpu, flags, timestamp, name, args):
        if name.startswith('i915_manual'):
            counter = self.counters.setdefault(tid, [0])
            if name.endswith('_end'):
                counter[0] -= 1
                if counter[0] < 0:
                    return
                self.callbacks.on_event("task_end", {'tid': tid, 'pid': (pid if pid is not None else 0), 'domain': 'ftrace', 'time': timestamp, 'type': 1})
            elif name.endswith('_begin'):
                counter[0] += 1
                self.callbacks.on_event("task_begin", {'tid': tid, 'pid': (pid if pid is not None else 0), 'domain': 'ftrace', 'time': timestamp, 'str': args.split('=')[1], 'type': 0})
            else:
                assert(not "Unhandled")

DECODER_DESCRIPTORS = [{
    'format': 'ftrace',
    'available': True,
    'decoder': I915
}]