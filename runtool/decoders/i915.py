
class I915:
    def __init__(self, callbacks):
        self.counters = {}
        self.callbacks = callbacks

    def handle_record(self, proc, pid, tid, cpu, flags, timestamp, name, args):
        if name.startswith('i915_gem_request_wait'):
            counter = self.counters.setdefault(tid, {})
            counter.setdefault('i915_wait_request', 0)
            if name.endswith('_end'):
                if counter['i915_wait_request'] <= 0:
                    return
                counter['i915_wait_request'] -= 1
                self.callbacks.on_event("task_end", {'tid': tid, 'pid': (pid if pid is not None else 0), 'domain': 'ftrace', 'time': timestamp, 'type': 1})
            elif name.endswith('_begin'):
                counter['i915_wait_request'] += 1
                self.callbacks.on_event("task_begin", {'tid': tid, 'pid': (pid if pid is not None else 0), 'domain': 'ftrace', 'time': timestamp, 'str': '__i915_wait_request', 'type': 0})
            else:
                assert(not "Unhandled")
        elif name.startswith('libdrm'):
            parts = args.strip().split()
            args = {}
            for part in parts:
                key, val = tuple(part.split('='))
                args[key] = val
            counter = self.counters.setdefault(tid, {})
            fn = args['name']
            counter.setdefault(fn, 0)
            if name.endswith('_end'):
                if counter[fn] <= 0:
                    return
                counter[fn] -= 1
                self.callbacks.on_event("task_end", {'tid': tid, 'pid': (pid if pid is not None else 0), 'domain': 'ftrace', 'time': timestamp, 'type': 1})
            elif name.endswith('_begin'):
                counter[fn] += 1
                self.callbacks.on_event("task_begin", {'tid': tid, 'pid': (pid if pid is not None else 0), 'domain': 'ftrace', 'time': timestamp, 'str': fn, 'type': 0})

DECODER_DESCRIPTORS = [{
    'format': 'ftrace',
    'available': True,
    'decoder': I915
}]
