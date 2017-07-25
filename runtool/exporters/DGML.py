import cgi

from sea_runtool import GraphCombiner, to_hex, format_time


class DGML(GraphCombiner):
    def __init__(self, args, tree):
        GraphCombiner.__init__(self, args, tree)
        self.file = open(self.get_targets()[-1], "w+b")
        self.file.write("""<?xml version='1.0' encoding='utf-8'?>\n<DirectedGraph xmlns="http://schemas.microsoft.com/vs/2009/dgml">""")

    def get_targets(self):
        return [self.args.output + ".dgml"]

    def finish(self):
        GraphCombiner.finish(self)
        self.file.write('<Nodes>\n')
        for domain, data in self.per_domain.iteritems():
            # counters
            for counter_name, counter_data in data['counters'].iteritems():
                id = self.make_id(domain, counter_name)
                self.file.write('<Node Id="%s" Label="%s" Min="%g" Max="%g" Avg="%g" Category="CodeSchema_Type"/>\n' % (id, cgi.escape(counter_name), min(counter_data), max(counter_data), sum(counter_data) / len(counter_data)))
            # tasks
            for task_name, task_data in data['tasks'].iteritems():
                id = self.make_id(domain, task_name)
                time = task_data['time']
                self.file.write('<Node Id="%s" Category="CodeSchema_Method" Label="%s" Min="%s" Max="%s" Avg="%s" Count="%d" Src="%s"/>\n' % (
                        id, cgi.escape(task_name),
                        format_time(min(time)), format_time(max(time)), format_time(sum(time) / len(time)), len(time),
                        task_data['src'].replace('\\', '/') if task_data.has_key('src') else ""
                    )
                )
            self.file.write('<Node Id="%s" Label="%s" Category="CodeSchema_Namespace" Group="Expanded"/>\n' % (self.make_id("domain", domain), cgi.escape(domain)))
        # threads
        thread_names = self.tree['threads']
        for tid in self.threads:
            tid_str, tid_hex = str(tid), (to_hex(tid) if tid is not None else "None")
            id = self.make_id("threads", tid_str)
            thread_name = thread_names[tid_str] if thread_names.has_key(tid_str) else ""
            self.file.write('<Node Id="%s" Label="%s(%s)"/>\n' % (id, cgi.escape(thread_name), tid_hex))

        self.file.write('</Nodes>\n')
        self.file.write('<Links>\n')

        # relations
        for relation in self.relations.itervalues():
            if not relation.has_key('color'):
                relation['color'] = 'black'
            self.file.write('<Link Source="{from}" Target="{to}" Category="CodeSchema_Calls"/>\n'.format(**relation))

        for domain, data in self.per_domain.iteritems():
            # counters
            for counter_name, counter_data in data['counters'].iteritems():
                self.file.write('<Link Source="%s" Target="%s" Category="Contains"/>\n' % (self.make_id("domain", domain), self.make_id(domain, counter_name)))
            # tasks
            for task_name, task_data in data['tasks'].iteritems():
                self.file.write('<Link Source="%s" Target="%s" Category="Contains"/>\n' % (self.make_id("domain", domain), self.make_id(domain, task_name)))

        self.file.write('</Links>\n')

        self.file.write("</DirectedGraph>\n")
        self.file.close()

    @staticmethod
    def join_traces(traces, output, args):
        with open(output + ".dgml", 'wb') as outfile:
            outfile.write("""<?xml version='1.0' encoding='utf-8'?>\n<DirectedGraph xmlns="http://schemas.microsoft.com/vs/2009/dgml">""")
            outfile.write('<Nodes>\n')
            for file in traces:
                with open(file, 'rb') as infile:
                    for line in infile:
                        if line.startswith("<Node "):
                            outfile.write(line)
            outfile.write('</Nodes>\n')
            outfile.write('<Links>\n')
            for file in traces:
                with open(file, 'rb') as infile:
                    for line in infile:
                        if line.startswith("<Link "):
                            outfile.write(line)
            outfile.write('</Links>\n')
            outfile.write("</DirectedGraph>\n")
        return output + ".dgml"


EXPORTER_DESCRIPTORS = [{
    'format': 'dgml',
    'available': True,
    'exporter': DGML
}]
