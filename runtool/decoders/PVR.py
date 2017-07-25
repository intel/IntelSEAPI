from etw import GPUQueue

TRACK_INDEX, TRACK_NAME = -1, 'GPU'


class PVRFtrace(GPUQueue):

    def __init__(self, args, callbacks):
        GPUQueue.__init__(self, args, callbacks)
        self.gpu = self.callbacks.process(TRACK_INDEX, TRACK_NAME)

    @staticmethod
    def parse_args(args):
        return dict(pair.split('=') for pair in args.split())

    @staticmethod
    def get_gpu_lane(idx):
        if idx == 1:
            return 'Tile Accelerator'
        if idx == 2:
            return '3D'
        return 'Unknown'

    def handle_record(self, proc, pid, tid, cpu, flags, timestamp, name, args):
        if name not in ['PVR_start', 'PVR_end']:
            return
        args = self.parse_args(args)
        tid = int(args['node'])
        thread = self.gpu.thread(tid, self.get_gpu_lane(tid))
        if name == 'PVR_start':
            task = thread.task('GPU', 'PVR')
            task.begin(timestamp)
            thread.task_stack.append(task)
        elif name == 'PVR_end':
            if thread.task_stack:
                task = thread.task_stack.pop()
                task.end(timestamp)

    def finalize(self):
        pass


class PVRCSV(GPUQueue):
    def __init__(self, args, callbacks):
        GPUQueue.__init__(self, args, callbacks)
        self.gpu = self.callbacks.process(TRACK_INDEX, TRACK_NAME).thread(-1)

    def handle_record(self, data):
        for item in ['name', 'start_tsc.CLOCK_MONOTONIC_RAW', 'end_tsc']:
            if item not in data:
                return
        frame = self.gpu.frame(data['name'])
        start = int(data['start_tsc.CLOCK_MONOTONIC_RAW'])
        end = int(data['end_tsc'])
        frame.complete(start, end-start)

    def finalize(self):
        pass


DECODER_DESCRIPTORS = [{
    'format': 'ftrace',
    'available': True,
    'decoder': PVRFtrace
},
{
    'format': 'csv',
    'available': True,
    'decoder': PVRCSV
}
]
