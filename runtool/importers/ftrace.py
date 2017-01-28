import os
import sys
import codecs

sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))
import strings
from sea_runtool import default_tree, Callbacks, Progress, get_decoders, build_tid_map, format_bytes


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

    def handle_record(self, proc, pid, tid, cpu, flags, timestamp, name, args):
        if pid is None:
            pid = self.tid_map[tid] if tid in self.tid_map else tid
        elif tid not in self.tid_map:
            self.tid_map[tid] = pid
        timestamp = int(timestamp * 1000000000)  # seconds to nanoseconds
        if name in ['tracing_mark_write', '0']:
            parts = args.split(':', 1)
            if len(parts) == 2:
                name, args = tuple(parts)
        for decoder in self.decoders:
            decoder.handle_record(proc, pid, tid, cpu, flags, timestamp, name, args)

    def finalize(self):
        for decoder in self.decoders:
            decoder.finalize()


def transform_ftrace(args, preprocess=None):
    tree = default_tree(args)
    tree['ring_buffer'] = True
    args.no_left_overs = True
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
                    res = FTraceImporter.parse(line)
                    if preprocess:
                        res = preprocess(res)
                        if not res:
                            continue
                    handler.handle_record(res['name'], res['tgid'], res['pid'], res['cpu'], res['flags'], res['time'], res['event'], res['args'])
                    if not count % 1000:
                        progress.tick(file.tell())
                handler.finalize()

    return callbacks.get_result()


class FTraceImporter:
    FTraceDecoders = FTrace

    def __call__(self, *args):
        return transform_ftrace(*args)

    @staticmethod
    def parse(line, statics={}):
        if not statics:
            import re
            expressions = [
                r'(?P<name>.*)-',           # process Name
                r'(?P<pid>\d+)\s+'          # pid
                r'(?P<tgid>.*\s+)?',        # tgid, if present
                r'\[(?P<cpu>.*)\]\s+',      # cpu
                r'((?P<flags>.*)\s+)?',     # flags, if present
                r'(?P<time>\d+\.\d+):\s+',  # time
                r'(?P<event>[^:]+):\s+',    # event name
                r'(?P<args>.*)',            # event arguments
            ]
            statics['regexp'] = re.compile(''.join(expressions), re.IGNORECASE | re.DOTALL)
        res = statics['regexp'].search(line.strip())
        if not res:
            return {}
        parsed = res.groupdict().copy()
        if parsed['tgid']:
            parsed['tgid'] = parsed['tgid'].strip().lstrip('(').rstrip(')').strip()
            if parsed['tgid'].isdigit():
                parsed['tgid'] = int(parsed['tgid'])
            else:
                parsed['tgid'] = None
        parsed.update({
            'pid': int(parsed['pid']),
            'cpu': int(parsed['cpu']),
            'time': float(parsed['time']),
        })
        if parsed['event'].strip() == '0':
            parsed['event'] = 'tracing_mark_write'
        return parsed

    @staticmethod
    def preprocess(input, output, fltr=None):
        header = []
        header_complete = False
        with codecs.open(input, 'r', 'utf-8', 'ignore') as input_file, codecs.open(output, 'wb+', 'utf-8') as output_file:
            size = os.path.getsize(input)
            count = 0
            with Progress(size, 50, strings.converting % (os.path.basename(input), format_bytes(size))) as progress:
                for line in input_file:
                    if fltr:
                        line = fltr(line)
                        if not line:
                            continue
                    if line.startswith('#'):
                        if not header_complete:
                            header.append(line)
                        else:
                            if line.startswith('##### CPU'):  # cleanup
                                output_file.seek(0)
                                output_file.writelines(header)
                                fltr(None)  # notify about cleanup
                    else:
                        if not header_complete:
                            output_file.writelines(header)
                            header_complete = True
                        output_file.write(line)
                    if not count % 1000:
                        progress.tick(input_file.tell())
                    count += 1


IMPORTER_DESCRIPTORS = [{
    'format': 'ftrace',
    'available': True,
    'importer': FTraceImporter()
}]
