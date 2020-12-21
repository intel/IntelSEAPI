import html

from sea_runtool import GraphCombiner, to_hex, format_time


class DGML(GraphCombiner):
    def __init__(self, args, tree):
        GraphCombiner.__init__(self, args, tree)
        self.file = open(self.get_targets()[-1], "w+b")
        self._write("""<?xml version='1.0' encoding='utf-8'?>\n<DirectedGraph xmlns="http://schemas.microsoft.com/vs/2009/dgml">""")

    def _write(self, data):
        self.file.write(data.encode())

    def get_targets(self):
        return [self.args.output + ".dgml"]

    def finish(self):
        GraphCombiner.finish(self)
        self._write('<Nodes>\n')
        for domain, data in self.per_domain.items():
            # counters
            for counter_name, counter_data in data['counters'].items():
                id = self.make_id(domain, counter_name)
                self._write('<Node Id="%s" Label="%s" Min="%g" Max="%g" Avg="%g" Category="CodeSchema_Type"/>\n' % (id, html.escape(counter_name), min(counter_data), max(counter_data), sum(counter_data) / len(counter_data)))
            # tasks
            for task_name, task_data in data['tasks'].items():
                id = self.make_id(domain, task_name)
                time = task_data['time']
                self._write('<Node Id="%s" Category="CodeSchema_Method" Label="%s" Min="%s" Max="%s" Avg="%s" Count="%d" Src="%s"/>\n' % (
                        id, html.escape(task_name),
                        format_time(min(time)), format_time(max(time)), format_time(sum(time) / len(time)), len(time),
                        task_data['src'].replace('\\', '/') if 'src' in task_data else ""
                    )
                )
            self._write('<Node Id="%s" Label="%s" Category="CodeSchema_Namespace" Group="Expanded"/>\n' % (self.make_id("domain", domain), html.escape(domain)))
        # threads
        thread_names = self.tree['threads']
        for tid in self.threads:
            tid_str, tid_hex = str(tid), (to_hex(tid) if tid is not None else "None")
            id = self.make_id("threads", tid_str)
            thread_name = thread_names[tid_str] if tid_str in thread_names else ""
            self._write('<Node Id="%s" Label="%s(%s)"/>\n' % (id, html.escape(thread_name), tid_hex))

        self._write('</Nodes>\n')
        self._write('<Links>\n')

        # relations
        for relation in self.relations.values():
            if 'color' not in relation:
                relation['color'] = 'black'
            self._write('<Link Source="{from}" Target="{to}" Category="CodeSchema_Calls"/>\n'.format(**relation))

        for domain, data in self.per_domain.items():
            # counters
            for counter_name, counter_data in data['counters'].items():
                self._write('<Link Source="%s" Target="%s" Category="Contains"/>\n' % (self.make_id("domain", domain), self.make_id(domain, counter_name)))
            # tasks
            for task_name, task_data in data['tasks'].items():
                self._write('<Link Source="%s" Target="%s" Category="Contains"/>\n' % (self.make_id("domain", domain), self.make_id(domain, task_name)))

        self._write('</Links>\n')

        self._write("</DirectedGraph>\n")
        self.file.close()

    @staticmethod
    def join_traces(traces, output, args):
        with open(output + ".dgml", 'wb') as outfile:
            outfile.write(b"""<?xml version='1.0' encoding='utf-8'?>\n<DirectedGraph xmlns="http://schemas.microsoft.com/vs/2009/dgml">""")
            outfile.write(b'<Nodes>\n')
            for file in traces:
                with open(file, 'rb') as infile:
                    for line in infile:
                        if line.startswith(b"<Node "):
                            outfile.write(line)
            outfile.write(b'</Nodes>\n')
            outfile.write(b'<Links>\n')
            for file in traces:
                with open(file, 'rb') as infile:
                    for line in infile:
                        if line.startswith(b"<Link "):
                            outfile.write(line)
            outfile.write(b'</Links>\n')
            outfile.write(b"</DirectedGraph>\n")
        return output + ".dgml"


EXPORTER_DESCRIPTORS = [{
    'format': 'dgml',
    'available': True,
    'exporter': DGML
}]
