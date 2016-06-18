import os
from sea_runtool import default_tree, Callbacks, Progress, TaskCombiner, get_decoders, build_tid_map


class FTrace:
    def __init__(self, args, callbacks):
        self.callbacks = callbacks
        self.args = args
        self.tid_map = {}
        self.decoders = []
        if hasattr(self.args, 'user_input') and os.path.isdir(self.args.user_input):
            self.tid_map = build_tid_map(self.args, self.args.user_input)
        decoders = get_decoders()
        if 'ftrace' in decoders:
            for decoder in decoders['ftrace']:
                self.decoders.append(decoder(args, callbacks))

    def handle_record(self, proc, tid, cpu, flags, timestamp, name, args):
        pid = self.tid_map[tid] if tid in self.tid_map else None
        timestamp = int(timestamp * 1000000000)  # seconds to nanoseconds
        for decoder in self.decoders:
            if name == 'tracing_mark_write' or name == '0':
                parts = args.split(':', 1)
                if len(parts) == 2:
                    name, args = tuple(parts)
            decoder.handle_record(proc, pid, tid, cpu, flags, timestamp, name, args)

    def finalize(self):
        for decoder in self.decoders:
            decoder.finalize()

def transform_ftrace(args):
    tree = default_tree()
    tree['ring_buffer'] = True
    TaskCombiner.disable_handling_leftovers = True
    with Callbacks(args, tree) as callbacks:
        if callbacks.is_empty():
            return callbacks.get_result()
        with Progress(os.path.getsize(args.input), 50, "Parsing: " + os.path.basename(args.input)) as progress:
            count = 0
            with open(args.input) as file:
                handler = FTrace(args, callbacks)
                for line in file:
                    count += 1
                    if line.startswith('#'):
                        continue
                    regular = line[:48].rstrip(' :')
                    payload = line[48:]
                    parts = regular.split()
                    if len(parts) != 4:
                        right = parts[-3:]
                        left = parts[:-3]
                        parts = [' '.join(left)] + right
                    (proc, tid) = parts[0].rsplit('-', 1)
                    cpu = int(parts[1][1:4])
                    flags = parts[2]
                    timestamp = float(parts[3])
                    (name, args) = payload.split(':', 1)
                    handler.handle_record(proc, int(tid), cpu, flags, timestamp, name.strip(), args.strip())
                    if not count % 1000:
                        progress.tick(file.tell())
                handler.finalize()

    return callbacks.get_result()

IMPORTER_DESCRIPTORS = [{
    'format': 'ftrace',
    'available': True,
    'importer': transform_ftrace
}]