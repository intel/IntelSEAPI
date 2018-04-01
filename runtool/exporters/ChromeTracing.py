import os
import sys
#sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))  # uncomment for debugging single file

import sea
import json
import codecs
import strings
import tempfile
import subprocess
from datetime import datetime
from sea_runtool import TaskCombiner, Progress, resolve_stack, to_hex, ProgressConst, get_importers

MAX_GT_SIZE = 50 * 1024 * 1024
GT_FLOAT_TIME = True


class GoogleTrace(TaskCombiner):

    class ContextSwitch:
        def __init__(self, parent, file):
            self.parent = parent
            self.file = file + '.ftrace'
            self.ftrace = None

        def write(self, time, cpu, prev_tid, prev_state, next_tid, prev_prio=0, next_prio=0, prev_name=None, next_name=None):
            if not prev_name:
                prev_name = '%d' % prev_tid
            if not next_name:
                next_name = '%d' % next_tid
            if not self.ftrace:
                self.ftrace = open(self.file, 'w')
                self.ftrace.write("# tracer: nop\n")
                args = (prev_name, prev_tid, cpu, self.parent.convert_time(time) / 1000000., self.parent.convert_time(time) / 1000000.)
                ftrace = "%s-%d [%03d] .... %.6f: tracing_mark_write: trace_event_clock_sync: parent_ts=%.6f\n" % args
                self.ftrace.write(ftrace)
                self.parent.targets.append(self.file)
            args = (
                prev_name, prev_tid, cpu, self.parent.convert_time(time) / 1000000.,
                prev_name, prev_tid, prev_prio, prev_state,
                next_name, next_tid, next_prio
            )
            ftrace = "%s-%d [%03d] .... %.6f: sched_switch: prev_comm=%s prev_pid=%d prev_prio=%d prev_state=%s ==> next_comm=%s next_pid=%d next_prio=%d\n" % args
            self.ftrace.write(ftrace)

    def context_switch(self, time, cpu, prev, next):
        if not self.cs:
            self.cs = GoogleTrace.ContextSwitch(self, self.args.input)
        self.cs.write(time, cpu, prev['tid'], prev['state'], next['tid'], prev['prio'], next['prio'], prev['name'], next['name'])

    def __init__(self, args, tree):
        TaskCombiner.__init__(self, args, tree)
        self.size_keeper = None
        self.targets = []
        self.trace_number = 0
        self.counters = {}
        self.frames = {}
        self.samples = []
        self.last_task = None
        self.metadata = {}
        self.last_relation_id = 0
        self.cs = None
        if self.args.trace:
            handled = []
            for trace in self.args.trace:
                if not os.path.exists(trace):
                    print "Error: File not found:", trace
                    continue
                if trace.endswith(".etl"):
                    self.handle_etw_trace(trace)
                    handled.append(trace)
                elif trace.endswith(".ftrace"):
                    self.handle_ftrace(trace)
                    handled.append(trace)
                elif trace.endswith(".dtrace"):
                    self.handle_dtrace(trace)
                    handled.append(trace)
                elif trace.endswith(".perf"):
                    self.handle_perf(trace)
                    handled.append(trace)
                else:
                    print "Error: unsupported extension:", trace
                args.trace = [trace for trace in args.trace if trace not in handled]
        self.start_new_trace()

    def start_new_trace(self):
        self.targets.append("%s-%d.json" % (self.args.output, self.trace_number))
        self.trace_number += 1
        self.file = codecs.open(self.targets[-1], "wb+", 'utf-8')
        self.file.write('{\n"traceEvents": [\n\n')  # second \n is for the rare case when there are no events, and finish cuts last two symbols

        for key, value in self.tree["threads"].iteritems():
            pid_tid = key.split(',')
            self.file.write(
                '{"name": "thread_name", "ph":"M", "pid":%s, "tid":%s, "args": {"name":"%s(%s)"}},\n' % (pid_tid[0], pid_tid[1], value, pid_tid[1])
            )

    def get_targets(self):
        return self.targets

    @staticmethod
    def read_ftrace_lines(trace, time_sync):
        write_chrome_time_sync = True
        with open(trace) as file:
            count = 0
            with Progress(os.path.getsize(trace), 50, "Loading ftrace") as progress:
                for line in file:
                    if 'IntelSEAPI_Time_Sync' in line:
                        parts = line.split()
                        time_sync.append((float(parts[-4].strip(":")), int(parts[-1])))  # target (ftrace), source (nanosecs)
                        if write_chrome_time_sync:  # chrome time sync, pure zero doesn't work, so we shift on very little value
                            yield "%strace_event_clock_sync: parent_ts=%s\n" % (line.split("IntelSEAPI_Time_Sync")[0], line.split(":")[-4].split()[-1])
                            write_chrome_time_sync = False  # one per trace is enough
                    else:
                        yield line
                    if count % ProgressConst == 0:
                        progress.tick(file.tell())
                    count += 1

    def handle_ftrace(self, trace):
        time_sync = []
        self.targets.append(self.args.output + '.cut.ftrace')
        with open(self.targets[-1], 'w') as file:
            for line in GoogleTrace.read_ftrace_lines(trace, time_sync):
                file.write(line)
        sync = self.apply_time_sync(time_sync)

        save = (self.args.input, self.args.output, self.args.trace)
        (self.args.input, self.args.output, self.args.trace) = (trace, trace, None)
        self.args.sync = [0, 0, 1. / 1000]  # since ftrace is already set as time sync the events coming from it shall have source time
        res = get_importers()['ftrace'](self.args)
        self.args.sync = sync
        (self.args.input, self.args.output, self.args.trace) = save

        self.set_sync(*sync)
        self.targets += res

    def handle_etw_trace(self, etw_file):
        sea.prepare_environ(self.args)
        sea_itf = sea.ITT('tools')
        if sea_itf.can_parse_standard_source():
            save = (self.args.input, self.args.output, self.args.trace)
            (self.args.input, self.args.output, self.args.trace) = (etw_file, etw_file, None)
            res = get_importers()['etl'](self.args)
            (self.args.input, self.args.output, self.args.trace) = save
        else:
            etw_xml = etw_file + ".xml"
            proc = subprocess.Popen('tracerpt "%s" -of XML -rts -lr -o "%s" -y' % (etw_file, etw_xml), shell=True, stderr=subprocess.PIPE)
            (out, err) = proc.communicate()
            if err:
                return None

            save = (self.args.input, self.args.output, self.args.trace)
            (self.args.input, self.args.output, self.args.trace) = (etw_xml, etw_xml, None)
            res = get_importers()['xml'](self.args)
            (self.args.input, self.args.output, self.args.trace) = save

        self.targets += res
        return res

    def handle_dtrace(self, trace):
        save = (self.args.input, self.args.output, self.args.trace)
        (self.args.input, self.args.output, self.args.trace) = (trace, trace, None)
        res = get_importers()['dtrace'](self.args)
        (self.args.input, self.args.output, self.args.trace) = save
        self.targets += res
        return res

    def handle_perf(self, trace):
        save = (self.args.input, self.args.output, self.args.trace)
        (self.args.input, self.args.output, self.args.trace) = (trace, trace, None)
        self.args.sync = [0, 0, 1. / 1000]  # perf ticks in ftrace time units
        res = get_importers()['perf'](self.args)
        (self.args.input, self.args.output, self.args.trace) = save
        self.targets += res
        return res

    def apply_time_sync(self, time_sync):
        self.source_scale_start, self.target_scale_start, self.ratio = GoogleTrace.calc_time_sync(time_sync)
        return self.source_scale_start, self.target_scale_start, self.ratio

    @staticmethod
    def calc_time_sync(time_sync, series=True):
        if len(time_sync) < 2:  # too few markers to sync
            return None
        Target = 0  # ftrace (it's Target because we better convert ITT time to ftrace for Chrome to understand)
        Source = 1  # ITT time, nanoseconds
        if series:
            # looking for closest time points to calculate start points
            diffs = []
            for i in range(1, len(time_sync)):
                diff = (time_sync[i][Target] - time_sync[i - 1][Target], time_sync[i][Source] - time_sync[i - 1][Source])
                diffs.append((diff, i))
            diffs.sort()
            (diff, index) = diffs[0]  # it's the width between two closest measurements

            # source measurement is the fisrt, target is second
            # Target time is always after the source, due to workflow
            # one measurement is begin -> begin and another is end -> end
            # if nothing interferes begin -> begin measurement should take same time as end -> end

            # run 1: most ballanced case - everything is even
            # S   /b  |  |  I  /e
            # T          /b  I  |  |  /e

            # run 2: takes more time after Target measurement
            # S   /b  |  |  I  /e
            # T      /b  I  |  |  /e

            # run 3: takes more time before Target measurement
            # S   /b  |  |  I  /e
            # T              /b  I  |  |  /e

            # From these runs obvious that in all cases the closest points (I) of global timeline are:
            # Quarter to end of Source and Quarter after begin of Target
            source_scale_start = time_sync[index - 1][Source] + int(diff[Source] * 0.75)  # to keep the precision
            target_scale_start = (time_sync[index - 1][Target] + (diff[Target] * 0.25)) * 1000000.  # multiplying by 1000000. to have time is microseconds (ftrace/target time was in seconds)

            print "Timelines correlation precision is +- %f us" % (diff[Target] / 2. * 1000000.)
        else:
            source_scale_start = time_sync[0][Source]
            target_scale_start = time_sync[0][Target] * 1000000.  # multiplying by 1000000. to have time in microseconds (ftrace/target time was in seconds)

        # taking farest time points to calculate frequencies
        diff = (time_sync[-1][Target] - time_sync[0][Target], time_sync[-1][Source] - time_sync[0][Source])
        ratio = 1000000. * diff[Target] / diff[Source]  # when you multiply Source value with this ratio you get Target units. Multiplying by 1000000. to have time is microseconds (ftrace/target time was in seconds)
        return source_scale_start, target_scale_start, ratio

    def global_metadata(self, data):
        if data['str'] == "__process__":  # this is the very first record in the trace
            if 'data' in data:
                self.file.write(
                    '{"name": "process_name", "ph":"M", "pid":%d, "tid":%d, "args": {"name":"%s"}},\n' % (int(data['pid']), int(data['tid']), data['data'].replace("\\", "\\\\").encode('utf-8'))
                )
            if 'delta' in data:
                self.file.write(
                    '{"name": "process_sort_index", "ph":"M", "pid":%d, "tid":%s, "args": {"sort_index":%d}},\n' % (data['pid'], data['tid'], abs(data['delta']) if abs(data['delta']) > 100 else data['delta'])
                )
            if 'labels' in data and data['labels']:
                self.file.write(
                    '{"name": "process_labels", "ph":"M", "pid":%d, "tid":%s, "args": {"labels":"%s"}},\n' % (data['pid'], data['tid'], ','.join(data['labels']))
                )
            if data['tid'] >= 0 and not self.tree['threads'].has_key('%d,%d' % (data['pid'], data['tid'])):  # marking the main thread
                self.file.write(
                    '{"name": "thread_name", "ph":"M", "pid":%d, "tid":%s, "args": {"name":"%s"}},\n' % (data['pid'], data['tid'], "<main>")
                )
        elif data['str'] == "__thread__":
            self.file.write(
                '{"name": "thread_name", "ph":"M", "pid":%d, "tid":%d, "args": {"name":"%s"}},\n' % (int(data['pid']), int(data['tid']), data['data'].replace("\\", "\\\\").encode('utf-8'))
            )
            if 'delta' in data:
                self.file.write(
                    '{"name": "thread_sort_index", "ph":"M", "pid":%d, "tid":%s, "args": {"sort_index":%d}},\n' % (data['pid'], data['tid'], abs(data['delta']) if abs(data['delta']) > 100 else data['delta'])
                )
        else:
            self.metadata.setdefault(data['str'], []).append(data['data'])

    def generate_relation_id(self):
        self.last_relation_id = self.last_relation_id + 1
        return self.last_relation_id

    def relation(self, data, head, tail):
        if not head or not tail:
            return
        items = sorted([head, tail], key=lambda item: item['time'])  # we can't draw lines in backward direction, so we sort them by time
        relation_id = self.generate_relation_id()
        if GT_FLOAT_TIME:
            template = '{"ph":"%s", "name": "relation", "pid":%d, "tid":%s, "ts":%.3f, "id":%s, "args":{"name": "%s"}, "cat":"%s"},\n'
        else:
            template = '{"ph":"%s", "name": "relation", "pid":%d, "tid":%s, "ts":%d, "id":%s, "args":{"name": "%s"}, "cat":"%s"},\n'
        if not data.has_key('str'):
            data['str'] = "unknown"
        self.file.write(template % ("s", items[0]['pid'], items[0]['tid'], self.convert_time(items[0]['time']), relation_id, data['str'], data['domain']))
        self.file.write(template % ("f", items[1]['pid'], items[1]['tid'], self.convert_time(items[1]['time'] - 1), relation_id, data['str'], data['domain']))

    def format_value(self, arg):  # this function must add quotes if value is string, and not number/float, do this recursively for dictionary
        if type(arg) == type({}):
            return "{" + ", ".join(['"%s":%s' % (key, self.format_value(value)) for key, value in arg.iteritems()]) + "}"
        try:
            val = float(arg)
            if float('inf') != val:
                if val.is_integer():
                    return int(val)
                else:
                    return val
        except:
            pass
        return '"%s"' % unicode(arg).encode('ascii', 'ignore').strip().replace("\\", "\\\\").replace('"', '\\"').replace('\n', '\\n')

    def format_args(self, arg):  # this function must add quotes if value is string, and not number/float, do this recursively for dictionary
        if type(arg) == type({}):
            return dict([(key, self.format_args(value)) for key, value in arg.iteritems()])
        try:
            val = float(arg)
            if float('inf') != val:
                if val.is_integer():
                    return int(val)
                else:
                    return val
        except:
            pass
        return arg.strip()


    Phase = {'task': 'X', 'counter': 'C', 'marker': 'i', 'object_new': 'N', 'object_snapshot': 'O', 'object_delete': 'D', 'frame': 'X'}

    def complete_task(self, type, begin, end):
        if self.args.distinct:
            if self.last_task == (type, begin, end):
                return
            self.last_task = (type, begin, end)
        assert (GoogleTrace.Phase.has_key(type))
        if begin['type'] == 7:  # frame_begin
            if 'id' not in begin:
                begin['id'] = id(begin)  # Async events are groupped by cat & id
            res = self.format_task('b', 'frame', begin, {})
            if end:
                res += [',\n']
                end_begin = begin.copy()
                end_begin['time'] = end['time'] - 1000
                if 'args' in end:
                    end_begin['args'] = end['args']
                res += self.format_task('e', 'frame', end_begin, {})
        else:
            res = self.format_task(GoogleTrace.Phase[type], type, begin, end)

        if not res:
            return
        if type in ['task', 'counter'] and 'data' in begin and 'str' in begin:  # FIXME: move closer to the place where stack is demanded
            self.handle_stack(begin, resolve_stack(self.args, self.tree, begin['data']), '%s:%s' % (begin['domain'], type))
        if self.args.debug and begin['type'] != 7:
            res = "".join(res)
            try:
                json.loads(res)
            except Exception as exc:
                import traceback
                print "\n" + exc.message + ":\n" + res + "\n"
                traceback.print_stack()
                self.format_task(GoogleTrace.Phase[type], type, begin, end)
            res += ',\n'
        else:
            res = "".join(res + [',\n'])
        self.file.write(res)
        if self.file.tell() > MAX_GT_SIZE:
            self.finish(intermediate=True)
            self.start_new_trace()

    def handle_stack(self, task, stack, name='stack'):
        if not stack:
            return
        parent = None
        for frame in reversed(stack):  # going from parents to children
            if parent is None:
                frame_id = '%d' % frame['ptr']
            else:
                frame_id = '%d:%s' % (frame['ptr'], parent)
            if frame_id not in self.frames:
                data = {'category': os.path.basename(frame['module']), 'name': frame['str'].replace(' ', '\t')}
                if '__file__' in frame and frame['__file__']:
                    line = str(frame['__line__']) if '__line__' in frame else '0'
                    data['name'] += ' %s(%s)' % (frame['__file__'].replace(' ', '\t'), line)
                if parent is not None:
                    data['parent'] = parent
                self.frames[frame_id] = data
            parent = frame_id
        time = self.convert_time(task['time'])
        self.samples.append({
            'tid': task['tid'],
            'ts': round(time, 3) if GT_FLOAT_TIME else int(time),
            'sf': frame_id, 'name': name
        })

    Markers = {
        "unknown": "t",
        "global": "g",
        "track_group": "p",
        "track": "t",
        "task": "t",
        "marker": "t"
    }

    def format_task(self, phase, type, begin, end):
        res = []
        res.append('{"ph":"%s"' % phase)
        res.append(', "pid":%(pid)d' % begin)
        if begin.has_key('tid'):
            res.append(', "tid":%(tid)d' % begin)
        if GT_FLOAT_TIME:
            res.append(', "ts":%.3f' % (self.convert_time(begin['time'])))
        else:
            res.append(', "ts":%d' % (self.convert_time(begin['time'])))
        if "counter" == type:  # workaround of chrome issue with forgetting the last counter value
            self.counters.setdefault(begin['domain'], {})[begin['str']] = begin  # remember the last counter value
        if "marker" == type:
            name = begin['str']
            res.append(', "s":"%s"' % (GoogleTrace.Markers[begin['data']]))
        elif "object_" in type:
            if 'str' in begin:
                name = begin['str']
            else:
                name = ""
        elif "frame" == type:
            if 'str' in begin:
                name = begin['str']
            else:
                name = begin['domain']
        else:
            if type not in ["counter", "task", "overlapped"]:
                name = type + ":"
            else:
                name = ""

            if 'parent' in begin:
                name += to_hex(begin['parent']) + "->"
            if 'str' in begin:
                name += begin['str'] + ":"
            if 'pointer' in begin:
                name += "func<" + to_hex(begin['pointer']) + ">:"
            else:
                name = name.rstrip(":")

        assert (name or "object_" in type)
        res.append(', "name":"%s"' % name)
        res.append(', "cat":"%s"' % (begin['domain']))

        if 'id' in begin:
            res.append(', "id":"%s"' % str(begin['id']))
        if type in ['task']:
            dur = self.convert_time(end['time']) - self.convert_time(begin['time'])
            if dur < self.args.min_dur:
                return []
            if GT_FLOAT_TIME:
                res.append(', "dur":%.3f' % dur)
            else:
                res.append(', "dur":%d' % dur)
        args = {}
        if 'args' in begin:
            args = begin['args'].copy()
        if 'args' in end:
            args.update(end['args'])
        if '__file__' in begin:
            args["__file__"] = begin["__file__"]
            args["__line__"] = begin["__line__"]
        if 'counter' == type:
            if 'delta' in begin:  # multi-counter is passed as named sub-counters dict
                args[name] = begin['delta']
        if 'memory' in begin:
            total = 0
            breakdown = {}
            children = 0
            for size, values in begin['memory'].iteritems():
                if size is None:  # special case for children attribution
                    children = values
                else:
                    all = sum(values)
                    total += size * all
                    if all:
                        breakdown[size] = all
            breakdown['TOTAL'] = total
            breakdown['CHILDREN'] = children
            args['CRT:Memory(size,count)'] = breakdown
        if args:
            res.append(', "args":')
            res.append(json.dumps(self.format_args(args), ensure_ascii=False))
        res.append('}')
        return res

    def handle_leftovers(self):
        TaskCombiner.handle_leftovers(self)
        for counters in self.counters.itervalues():  # workaround: google trace forgets counter last value
            for counter in counters.itervalues():
                counter['time'] += 1  # so, we repeat it on the end of the trace
                self.complete_task("counter", counter, counter)

    def remove_last(self, count):
        self.file.seek(-count, os.SEEK_END)
        self.file.truncate()

    def finish(self, intermediate=False):
        self.remove_last(2)  # remove trailing ,\n
        if not intermediate:
            if self.samples:
                self.file.write('], "stackFrames": {\n')
                for id, frame in self.frames.iteritems():
                    self.file.write('"%s": %s,\n' % (id, json.dumps(frame)))
                if self.frames:  # deleting last two symbols from the file as we can't leave comma at the end due to json restrictions
                    self.remove_last(2)
                self.file.write('\n}, "samples": [\n')
                for sample in self.samples:
                    self.file.write(json.dumps(sample) + ',\n')
                if self.samples:   # deleting last two symbols from the file as we can't leave comma at the end due to json restrictions
                    self.remove_last(2)
                self.samples = []
                self.frames = {}
            if self.metadata:
                self.file.write('\n],\n')
                for key, value in self.metadata.iteritems():
                    self.file.write('"%s": %s,\n' % (key, json.dumps(value[0] if len(value) == 1 else value)))
                self.remove_last(2)  # remove trailing ,\n
                self.file.write('\n}')
                self.file.close()
                return

        self.file.write('\n]}')
        self.file.close()

    @staticmethod
    def get_catapult_path(args):
        if args.no_catapult:
            return None
        if 'INTEL_SEA_CATAPULT' in os.environ and os.path.exists(os.environ['INTEL_SEA_CATAPULT']):
            return os.environ['INTEL_SEA_CATAPULT']
        else:
            path = os.path.join(args.bindir, 'catapult', 'tracing')
            if os.path.exists(path):
                return path
            zip_path = os.path.join(args.bindir, 'catapult.zip')
            if os.path.exists(zip_path):
                print "Extracting catapult..."
                from zipfile import PyZipFile
                pzf = PyZipFile(zip_path)
                pzf.extractall(args.bindir)
                return path
            return None

    @staticmethod
    def join_traces(traces, output, args):
        ftrace = []  # ftrace files have to be joint by time: chrome reads them in unpredictable order and complains about time
        for file in traces:
            if file.endswith('.ftrace') and 'merged.ftrace' != os.path.basename(file):
                ftrace.append(file)
        if len(ftrace) > 1:  # just concatenate all files in order of creation
            ftrace.sort()  # name defines sorting
            merged = os.path.join(os.path.dirname(ftrace[0]), 'merged.ftrace')
            trace_event_clock_sync = False
            with open(merged, 'w') as output_file:
                for file_name in ftrace:
                    with open(file_name) as input_file:
                        for line in input_file:
                            if 'trace_event_clock_sync' in line:
                                if trace_event_clock_sync:
                                    continue
                                trace_event_clock_sync = True
                            output_file.write(line)
            traces = [file for file in traces if not file.endswith('.ftrace')]
            traces.append(merged)

        catapult_path = GoogleTrace.get_catapult_path(args)
        if catapult_path:
            import threading
            proc = threading.Thread(target=GoogleTrace.catapult, args=(catapult_path, output, traces))
            proc.start()
            with Progress(0, 0, strings.catapulting) as progress:
                count = 0
                while proc.is_alive():
                    progress.tick(count)
                    count += 1
                    proc.join(0.5)
            return output + '.html'
        else:
            return GoogleTrace.zip_traces(traces, output)

    @staticmethod
    def catapult(catapult_path, output, traces):
        sys.path.append(catapult_path)
        from tracing_build import trace2html
        import codecs
        with codecs.open(output + '.html', 'w', 'utf-8') as new_file:
            def WriteHTMLForTracesToFile(trace_filenames, output_file, config_name=None):
                trace_data_list = []
                for filename in trace_filenames:
                    with open(filename, 'r') as f:
                        trace_data = f.read()
                        try:
                            trace_data = json.loads(trace_data)
                        except ValueError:
                            pass
                        trace_data_list.append(trace_data)
                project_title = getattr(__builtins__, 'sea_project_title', 'Intel(R) Single Event API')
                title = os.path.basename(output).split('_')[0] + ": " + project_title
                trace2html.WriteHTMLForTraceDataToFile(trace_data_list, title, output_file, config_name)

            WriteHTMLForTracesToFile(traces, new_file)
        return output + '.html'

    @staticmethod
    def zip_traces(traces, output):
        import zipfile
        with zipfile.ZipFile(output + ".zip", 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zip:
            count = 0
            with Progress(len(traces), 50, "Merging traces") as progress:
                for file in traces:
                    progress.tick(count)
                    zip.write(file, os.path.basename(file))
                    count += 1
        return output + ".zip"


EXPORTER_DESCRIPTORS = [{
    'format': 'gt',
    'available': True,
    'exporter': GoogleTrace
}]


def support_no_console(log):
    if sys.executable.lower().endswith("w.exe"):
        sys.stdout = open(os.devnull, "w")
        sys.stderr = open(log, "w")
        sys.stdin = open(os.devnull, "r")

if __name__ != "__main__":
    support_no_console(os.path.join(tempfile.gettempdir(), datetime.now().strftime('sea_%H_%M_%S__%d_%m_%Y.log')))

