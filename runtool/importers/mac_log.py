import os
from sea_runtool import default_tree, Callbacks, Progress, get_decoders


class Log:
    def __init__(self, args, callbacks):
        self.args, self.callbacks = args, callbacks
        self.decoders = []
        decoders = get_decoders()
        if 'log' in decoders:
            for decoder in decoders['log']:
                self.decoders.append(decoder(args, callbacks))

    def handle_record(self, time, pid, tid, type, activity, msg):
        thread = self.callbacks.process(pid).thread(tid)
        thread.marker('thread', 'Log').set(time, args={'type': type, 'activity': activity, 'msg': ' '.join(msg)})
        for decoder in self.decoders:
            decoder.handle_record(time, pid, tid, type, activity, msg)


def transform_log(args):
    from dateutil import parser
    tree = default_tree(args)
    tree['ring_buffer'] = True
    with Callbacks(args, tree) as callbacks:
        if callbacks.is_empty():
            return callbacks.get_result()
        log = Log(args, callbacks)
        with open(args.input) as file:
            with Progress(os.path.getsize(args.input), 50, "Parsing: " + os.path.basename(args.input)) as progress:
                count = 0
                header = None
                first_stamp = None
                for line in file:
                    if not count % 1000:
                        progress.tick(file.tell())
                    parts = line.split()
                    if not header:
                        if len(parts) != 5:
                            continue
                        if not parts[0].startswith('Timestamp'):
                            print "Error: this log format is not supported. Expected log from OSX's 'log stream'"
                        header = parts
                        continue
                    else:
                        time = parser.parse(' '.join(parts[0:2]))
                        if first_stamp:
                            time = int((time - first_stamp).total_seconds() * 10e9)
                        else:
                            first_stamp = time
                            time = 0
                        tid = int(parts[2], 16)
                        type = parts[3]
                        activity = int(parts[4], 16)
                        pid = int(parts[5], 16)
                        msg = parts[6:]
                        log.handle_record(time, pid, tid, type, activity, msg)
    return callbacks.get_result()

IMPORTER_DESCRIPTORS = [{
    'format': 'log',
    'available': True,
    'importer': transform_log
}]