import os
from sea_runtool import default_tree, Callbacks, Progress, get_decoders

class CSVHandler:
    def __init__(self, args, callbacks):
        self.callbacks = callbacks
        self.args = args
        self.decoders = []
        decoders = get_decoders()
        if 'csv' in decoders:
            for decoder in decoders['csv']:
                self.decoders.append(decoder(args, callbacks))

    def handle_record(self, data):
        for decoder in self.decoders:
            decoder.handle_record(data)

    def finalize(self):
        for decoder in self.decoders:
            decoder.finalize()


def transform_csv(args, preprocess=None):
    tree = default_tree(args)
    tree['ring_buffer'] = True
    args.no_left_overs = True
    with Callbacks(args, tree) as callbacks:
        if callbacks.is_empty():
            return callbacks.get_result()
        with Progress(os.path.getsize(args.input), 50, "Parsing: " + os.path.basename(args.input)) as progress:
            count = 0
            with open(args.input) as file:
                handler = CSVHandler(args, callbacks)
                header = None
                for line in file:
                    count += 1
                    if not count % 1000:
                        progress.tick(file.tell())
                    if line.startswith('//'):
                        continue
                    parts = [item.strip() for item in line.strip().split(',')]
                    if header:
                        fields = dict(zip(header, parts))
                        if preprocess:
                            fields = preprocess(fields)
                            if not fields:
                                continue
                        handler.handle_record(fields)
                    else:
                        header = parts
                handler.finalize()
    return callbacks.get_result()


IMPORTER_DESCRIPTORS = [{
    'format': 'csv',
    'available': True,
    'importer': transform_csv
}]