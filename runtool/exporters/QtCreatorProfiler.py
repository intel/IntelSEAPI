import cgi
from sea_runtool import TaskCombiner, get_name, to_hex

#https://github.com/danimo/qt-creator/blob/master/src/plugins/qmlprofiler/qmlprofilertracefile.cpp
#https://github.com/danimo/qt-creator/blob/master/src/plugins/qmlprofiler/qv8profilerdatamodel.cpp

class QTProfiler(TaskCombiner):
    def __init__(self, args, tree):
        TaskCombiner.__init__(self, args, tree)
        self.file_name = self.args.output + ".qtd"
        self.file = open(self.file_name, "w")
        self.notes = []
        self.start_time = None
        self.end_time = None

    def get_targets(self):
        return [self.file_name] if self.file_name else []

    def set_times(self, start, end):
        if self.start_time is None:
            self.start_time = start
        else:
            self.start_time = min(start, self.start_time)
        if self.end_time is None:
            self.end_time = end
        else:
            self.end_time = max(end, self.end_time)

    def complete_task(self, type, begin, end):
        if 'tid' not in begin:
            return

        start_time = round(begin['time'] / 1000)  # sad but it's limiter to milliseconds only
        end_time = round(end['time'] / 1000)
        dur = end_time - start_time
        if dur < self.args.min_dur:
            return

        name = get_name(begin)

        details = (type + ":") if type != 'task' else ""
        if begin.has_key('parent'):
            details += to_hex(begin['parent']) + "->"
        details += name

        if type == 'counter' or type == 'marker':
            kind = 'Painting'
        elif type == 'frame' or 'object_' in type:
            kind = 'Creating'
        else:
            kind = 'Javascript'

        record = (
            begin['__file__'].replace("\\", "/") if begin.has_key('__file__') else "",
            begin['__line__'] if begin.has_key('__line__') else "0",
            kind,
            "%s | %s" % (details, begin['domain']),
            name
        )
        record = tuple([cgi.escape(item) for item in record])

        if self.event_map.has_key(record):
            index = self.event_map[record]
        else:
            index = len(self.events)
            self.events.append(record)
            self.event_map[record] = index

        tag = '<range startTime="%d" duration="%d" eventIndex="%d"/>\n' % (start_time, dur, index)

        args = {}
        if type == "counter":
            if 'delta' in begin:
                args['value'] = begin['delta']
            else:  # TODO: add multi-value support
                return
        if begin.has_key('args'):
            args = begin['args']
            if end.has_key('args'):
                args.update(end['args'])
        if args:
            self.notes.append((start_time, dur, index, args))

        self.set_times(start_time, end_time)
        self.file.write(tag)

    def write_header(self):
        # at this moment print is redirected to output file
        print '<?xml version="1.0" encoding="UTF-8"?>'
        print '<trace version="1.02" traceStart="%d" traceEnd="%d">' % (self.start_time, self.end_time)
        print '<eventData totalTime="%d">' % (self.end_time - self.start_time)
        counter = 0
        for event in self.events:
            print '<event index="%d"><filename>%s</filename><line>%s</line><type>%s</type><details>%s</details><displayname>%s</displayname></event>' \
                  % (counter, event[0], event[1], event[2], event[3], event[4])
            counter += 1
        print '</eventData><profilerDataModel>'

    def write_footer(self, file):
        file.write('</profilerDataModel><noteData>\n')
        for note in self.notes:
            args = "\n".join([str(key) + " = " + str(val).replace("{","").replace("}","") for key, val in note[3].iteritems()])
            file.write('<note startTime="%d" duration="%d" eventIndex="%d">%s</note>\n' % (note[0], note[1], note[2], cgi.escape(args)))
        file.write('</noteData><v8profile totalTime="0"/></trace>\n')

    def finish(self):
        import fileinput
        self.file.close()
        fi = fileinput.input(self.file_name, inplace=1)
        wrote_header = False
        for line in fi:
            if fi.isfirstline():
                self.write_header()
                wrote_header = True
            print line,
        if wrote_header:
            with open(self.file_name, "a") as file:
                self.write_footer(file)
        else:
            self.file_name = None

    @staticmethod
    def join_traces(traces, output, args):  # TODO: implement progress
        import xml.dom.minidom as minidom
        output += ".qtd"
        with open(output, "w") as file:  # FIXME: doesn't work on huge traces, consider using "iterparse" approach
            print >> file, '<?xml version="1.0" encoding="UTF-8"?>'
            traces = [minidom.parse(trace) for trace in traces]  # parse all traces right away
            traceStarts = sorted([int(dom.documentElement.attributes['traceStart'].nodeValue) for dom in traces]) #earliest start time
            traceEnds = sorted([int(dom.documentElement.attributes['traceEnd'].nodeValue) for dom in traces], reverse=True)#latest end time
            print >> file, '<trace version="1.02" traceStart="%d" traceEnd="%d">' % (traceStarts[0], traceEnds[0])
            print >> file, '<eventData totalTime="%d">' % (traceEnds[0] - traceStarts[0])
            event_count = []  # accumulate event count to map indices
            for dom in traces:  # first we go by events
                events = dom.getElementsByTagName('eventData')[0].getElementsByTagName('event')
                for event in events:  # and correct each event index, adding count of events in previous files
                    index = int(event.attributes['index'].nodeValue) + sum(event_count)
                    event.setAttribute('index', str(index))
                    print >> file, event.toxml()
                event_count.append(len(events))  # for next traces to adjust index start
            print >> file, '</eventData><profilerDataModel>'
            index = 0
            for dom in traces:
                ranges = dom.getElementsByTagName('profilerDataModel')[0].getElementsByTagName('range')
                for range in ranges:
                    eventIndex = int(range.attributes['eventIndex'].nodeValue) + sum(event_count[:index])
                    range.setAttribute('eventIndex', str(eventIndex))
                    print >> file, range.toxml()
                index += 1
            print >> file, '</profilerDataModel><noteData>'
            index = 0
            for dom in traces:
                notes = dom.getElementsByTagName('noteData')[0].getElementsByTagName('note')
                for note in notes:
                    eventIndex = int(note.attributes['eventIndex'].nodeValue) + sum(event_count[:index])
                    note.setAttribute('eventIndex', str(eventIndex))
                    print >> file, note.toxml()
                index += 1
            print >> file, '</noteData><v8profile totalTime="0"/></trace>'
        return output

EXPORTER_DESCRIPTORS = [{
    'format': 'qt',
    'available': True,
    'exporter': QTProfiler
}]
