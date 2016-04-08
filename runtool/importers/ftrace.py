import os
import glob
from sea_runtool import default_tree, Callbacks, Progress, TaskCombiner, get_decoders


class FTrace:
    def __init__(self, args, callbacks):
        self.callbacks = callbacks
        self.args = args
        self.tid_map = {}
        self.decoders = []
        if hasattr(self.args, 'user_input') and os.path.isdir(self.args.user_input):
            self.build_tid_map(self.args.user_input)
        decoders = get_decoders()
        if 'ftrace' in decoders:
            for decoder in decoders['ftrace']:
                self.decoders.append(decoder(callbacks))

    def build_tid_map(self, src):
        if self.args.multiproc:
            for folder in glob.glob(os.path.join(src, 'pid-*')):
                self.parse_process(folder)
        else:
            self.parse_process(src)

    def parse_process(self, src):
        pid = int(src.rsplit('-', 1)[1])
        for folder in glob.glob(os.path.join(src, '*', '*.sea')):
            tid = int(os.path.basename(folder).split('.')[0])
            self.tid_map[tid] = pid

    def handle_record(self, proc, tid, cpu, flags, timestamp, name, args):
        pid = self.tid_map[tid] if tid in self.tid_map else None
        timestamp *= 1000000000.  # seconds to nanoseconds
        for decoder in self.decoders:
            decoder.handle_record(proc, pid, tid, cpu, flags, timestamp, name, args)


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
                    regular = line[:46]
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

    return callbacks.get_result()

IMPORTER_DESCRIPTORS = [{
    'format': 'ftrace',
    'available': True,
    'importer': transform_ftrace
}]