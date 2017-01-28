import os
from sea_runtool import default_tree, Callbacks, Progress, get_decoders


class PerfHandler:
    def __init__(self, args, callbacks):
        self.callbacks = callbacks
        self.args = args
        self.last_record = None
        self.decoders = []
        decoders = get_decoders()
        if 'perf' in decoders:
            for decoder in decoders['perf']:
                self.decoders.append(decoder(args, callbacks))

    def handle_record(self, name, pid, tid, time):
        time = int(time * 1000000000)
        self.last_record = locals()

    def handle_stack(self, stack):
        unwound = []
        for frame in stack:
            parts = frame.split()
            ptr = parts[0]
            fn = ' '.join(parts[1:-1])
            mdl = parts[-1]
            if fn.lower() == '[unknown]':
                fn = None
            unwound.append({'ptr': int(ptr, 16), 'str': fn, 'module': mdl[1:-1]})
        self.callbacks.handle_stack(self.last_record['pid'], self.last_record['tid'], self.last_record['time'], unwound)

    def finalize(self):
        for decoder in self.decoders:
            decoder.finalize()


def parse_event(line, statics={}):
    if not statics:
        import re
        expressions = [
            r'(?P<name>.*)\s+',  # thread name
            r'(?P<pid>\d+)/(?P<tid>\d+)\s+',  # pid/tid
            r'(?P<time>\d+\.\d+):',  # time
        ]
        statics['regexp'] = re.compile(''.join(expressions), re.IGNORECASE | re.DOTALL)
    res = statics['regexp'].search(line.strip())
    if not res:
        return {}
    return res.groupdict()


def transform_perf(args, preprocess=None):
    tree = default_tree(args)
    tree['ring_buffer'] = True
    args.no_left_overs = True
    with Callbacks(args, tree) as callbacks:
        if callbacks.is_empty():
            return callbacks.get_result()
        with Progress(os.path.getsize(args.input), 50, "Parsing: " + os.path.basename(args.input)) as progress:
            count = 0
            with open(args.input) as file:
                handler = PerfHandler(args, callbacks)
                read_stack = None
                for line in file:
                    count += 1
                    if not count % 1000:
                        progress.tick(file.tell())
                    line = line.strip()
                    if read_stack is not None:
                        if not line:
                            handler.handle_stack(read_stack)
                            read_stack = None
                        else:
                            read_stack.append(line)
                    else:
                        fields = parse_event(line)
                        handler.handle_record(fields['name'], int(fields['pid']), int(fields['tid']), float(fields['time']))
                        if line.endswith(':'):
                            read_stack = []
                handler.finalize()
    return callbacks.get_result()

IMPORTER_DESCRIPTORS = [{
    'format': 'perf',
    'available': True,
    'importer': transform_perf
}]
