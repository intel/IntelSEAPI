'''
Module to handle pprof trace:
profile https://github.com/google/pprof/blob/master/doc/developer/profile.proto.md
sympolized with protobuf https://github.com/golang/protobuf and compressed.
'''
import os
import sys
import gzip
import imp

from sea_runtool import default_tree, Callbacks, Progress, get_decoders

IS_AVAILABLE = True
profile = None


def import_profile():
    try:
        global profile
        profile = imp.load_source('profile', os.path.join(os.path.dirname(os.path.realpath(__file__)), 'pprof_importer', 'profile.py'))
    except (ImportError, AttributeError):
        global IS_AVAILABLE
        IS_AVAILABLE = False
        #pylint: disable=superfluous-parens
        print("Warning! Pprof importer is unavailable. Google protobuf library should be installed.")
        print("To get protobuf follow the link: https://github.com/google/protobuf/tree/master/python")
        print('\n')


class PprofHandler(object):
    '''
    Class to process pprof trace.
    '''
    def __init__(self, args, callbacks):
        self.callbacks = callbacks
        self.args = args
        self.decoders = []
        self.last_record = None
        self.period = 1
        decoders = get_decoders()
        if 'pprof' in decoders:
            for decoder in decoders['pprof']:
                self.decoders.append(decoder(args, callbacks))

    #pylint: disable=too-many-arguments
    def handle_record(self, name, pid, tid, time, duration):
        '''
        Updates variable last_record.
        :param name: string
        :param pid: int
        :param tid: int
        :param time: long
        :return: -
        '''
        #pylint: disable=unused-argument
        self.last_record = locals()
        the_thread = self.callbacks.process(pid).thread(tid)
        counter = the_thread.counter(domain='cpu', name='cpu tid:%d' % tid)
        counter.set_value(time_stamp=time, value=(float(duration / self.period) * 100))


    def handle_sample(self, sample):
        '''
        Appends stack from sample to callbacks.
        :param sample: pprof_profile.Sample object
        :return: -
        '''
        unwound = []
        for location in sample.Location:
            ptr = location.Address or location.ID
            function = ""
            module = ""
            line = -1
            if len(location.Line) != 0:
                function = location.Line[0].Function.Name
                module = location.Line[0].Function.Filename
                line = location.Line[0].Line
            unwound.append({'ptr': ptr, 'str': function, 'module': module,
                            '__file__': module, '__line__': str(line)})
        self.callbacks.handle_stack(-self.last_record['pid'], -self.last_record['tid'],
                                    self.last_record['time'], unwound)

    def finalize(self):
        '''
        Calls finalization from all decoders.
        :return: -
        '''
        for decoder in self.decoders:
            decoder.finalize()

    #pylint: disable=no-self-use
    def get_string(self, strings, index):
        '''
        Returns string by index from strings and sets index to 0
        :param strings: list of strings
        :param index: int
        :return: string
        '''
        if index < 0 or index >= len(strings):
            return ""
        ret_value = strings[index]
        index = 0
        return ret_value

    #pylint: disable=too-many-locals, too-many-branches, too-many-statements
    def preprocess(self, profile):
        '''
        postDecode takes the unexported fields populated by decode (with
        suffix X) and populates the corresponding exported fields.
        The unexported fields are cleared up to facilitate testing.
        :param profile: protobuf generated pprof_profile.Profile
        :return:
        '''
        self.period = profile.Period
        mappings = {}
        for maping in profile.Mapping:
            maping.File = self.get_string(profile.stringTable, maping.fileX)
            maping.BuildID = self.get_string(profile.stringTable, maping.buildIDX)
            mappings[maping.ID] = maping

        functions = {}
        for function in profile.Function:
            function.Name = self.get_string(profile.stringTable, function.nameX)
            function.SystemName = self.get_string(profile.stringTable, function.systemNameX)
            function.Filename = self.get_string(profile.stringTable, function.filenameX)
            functions[function.ID] = function

        locations = {}
        for location in profile.Location:
            if mappings.get(location.mappingIDX) is not None:
                location.Mapping.CopyFrom(mappings.get(location.mappingIDX))
            location.mappingIDX = 0
            for i in range(0, len(location.Line)):
                line = location.Line[i]
                uid = line.functionIDX
                if uid != 0:
                    if functions.get(uid) is not None:
                        location.Line[i].Function.CopyFrom(functions.get(uid))
                    if location.Line[i].Function is None:
                        raise Exception("Function ID %d not found", uid)
                    location.Line[i].functionIDX = 0
            locations[location.ID] = location

        for sample_type in profile.SampleType:
            sample_type.Type = self.get_string(profile.stringTable, sample_type.typeX)
            sample_type.Unit = self.get_string(profile.stringTable, sample_type.unitX)

        for sample in profile.Sample:
            labels = {}
            num_labels = {}
            for label in sample.labelX:
                key = self.get_string(profile.stringTable, label.keyX)
                if label.strX != 0:
                    value = self.get_string(profile.stringTable, label.strX)
                    if key not in labels:
                        labels[key] = []
                    labels[key].append(value)
                else:
                    if key not in num_labels:
                        num_labels[key] = []
                    num_labels[key].append(label.numX)

            if len(labels) > 0:
                for key, value in labels.iteritems():
                    label = sample.Label.add()
                    label.key = key
                    for val in value:
                        label.value.append(val)

            if len(num_labels) > 0:
                for key, value in num_labels.iteritems():
                    label = sample.NumLabel.add()
                    label.key = key
                    for val in value:
                        label.value.append(val)

            for location_id in sample.locationIDX:
                if locations.get(location_id) is not None:
                    location = sample.Location.add()
                    location.CopyFrom(locations.get(location_id))

        period_type = profile.PeriodType
        if period_type is None:
            profile.PeriodType = profile.ValueType()
        else:
            period_type.Type = self.get_string(profile.stringTable, period_type.typeX)
            period_type.Unit = self.get_string(profile.stringTable, period_type.unitX)


def transform_pprof(args):
    '''
    Transforms pprof trace to chosen export format.
    :param args: args
    :return: list of callbacks
    '''
    import_profile()
    if not IS_AVAILABLE:
        return []
    tree = default_tree(args)
    tree['ring_buffer'] = True
    args.no_left_overs = True
    prof = profile.Profile()
    with Callbacks(args, tree) as callbacks:
        if callbacks.is_empty():
            return callbacks.get_result()
        with Progress(os.path.getsize(args.input), 50, "Parsing: " +
                      os.path.basename(args.input)) as progress:
            count = 0
            with gzip.open(args.input) as input_file:
                handler = PprofHandler(args, callbacks)
                prof.ParseFromString(input_file.read())
                handler.preprocess(prof)
                time = prof.TimeNanos
                pid = 0
                tid = 0
                for sample in prof.Sample:
                    duration = sample.Value[1]
                    if len(sample.NumLabel) != 0:
                        for label in sample.NumLabel:
                            if label.key == "pid":
                                pid = label.value[0]
                            elif label.key == "tid":
                                tid = label.value[0]
                            elif label.key == "timestamp":
                                time = label.value[0]
                    handler.handle_record("name", pid, tid, time, duration)
                    time += prof.Period
                    count += 1
                    if not count % 1000:
                        progress.tick(input_file.tell())
                    handler.handle_sample(sample)
                handler.finalize()

    return callbacks.get_result()

IMPORTER_DESCRIPTORS = [{
    'format': 'pprof',
    'available': IS_AVAILABLE,
    'importer': transform_pprof
}]
