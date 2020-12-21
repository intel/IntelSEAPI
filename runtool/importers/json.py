from __future__ import absolute_import, print_function
import os
import json as the_json
import codecs
from sea_runtool import default_tree, Callbacks, Progress, get_decoders


class OwnDecoder:
    def __init__(self, args, callbacks):
        self.args, self.callbacks = args, callbacks
        self.handlers = {}
        self.per_pid = {}
        self.latest_time = 0
        self.id_counter = 0

    def convert_time(self, tics):
        return tics * 10e8

    def handle_record(self, key, data):
        if 'type' not in data:
            return
        handler = getattr(self, data['type'], None)
        if not handler:
            print('No handler for:', data['type'])
            return
        handler(**data)

    def process_name(self, pid, name, **kwargs):
        self.callbacks.set_process_name(pid, name)

    def thread_name(self, pid, tid, name, **kwargs):
        self.callbacks.set_thread_name(pid, tid, name)

    def event(self, time, pid, tid, name, data, **kwargs):
        timestamp = self.convert_time(time)
        obj = self.callbacks.process(pid).thread(tid).object(self.id_counter, name)
        obj.snapshot(timestamp, args={'description': data})
        self.id_counter += 1

    def task(self, begin, end, pid, tid, name, **kwargs):
        begin = self.convert_time(begin)
        end = self.convert_time(end)
        self.callbacks.process(pid).thread(tid).task(name).complete(begin, end - begin)

    def finalize(self):
        pass


class JsonHandler:
    def __init__(self, args, callbacks):
        self.callbacks = callbacks
        self.args = args
        self.decoders = []
        decoders = get_decoders()
        if 'json' in decoders:
            for decoder in decoders['json'] + [OwnDecoder]:
                self.decoders.append(decoder(args, callbacks))

    def handle_record(self, key, value):
        for decoder in self.decoders:
            decoder.handle_record(key, value)

    def finalize(self):
        for decoder in self.decoders:
            decoder.finalize()


def transform_json(args, preprocess=None):
    file_size = os.path.getsize(args.input)
    if not file_size:
        return []
    tree = default_tree(args)
    tree['ring_buffer'] = True
    args.no_left_overs = True
    with Callbacks(args, tree) as callbacks:
        if callbacks.is_empty():
            return callbacks.get_result()
        with Progress(file_size, 50, "Parsing: " + os.path.basename(args.input)) as progress:
            count = 0
            with codecs.open(args.input, 'r', 'utf-8', errors='ignore') as file:
                data = the_json.load(file)
                handler = JsonHandler(args, callbacks)
                for key, val in (enumerate(data) if isinstance(data, list) else data.items()):
                    count += 1
                    if not count % 1000:
                        progress.tick(file.tell())
                    handler.handle_record(key, val)
                handler.finalize()
    return callbacks.get_result()


IMPORTER_DESCRIPTORS = [{
    'format': 'json',
    'available': True,
    'importer': transform_json
}]
