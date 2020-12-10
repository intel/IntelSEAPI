import html
from sea_runtool import GraphCombiner, to_hex, format_time


class GraphViz(GraphCombiner):
    def __init__(self, args, tree):
        GraphCombiner.__init__(self, args, tree)
        self.file = open(self.get_targets()[-1], "w+b")
        self._write("digraph G{\nedge [labeldistance=0];\nnode [shape=record];\n")

    def _write(self, data):
        self.file.write(data.encode())

    def get_targets(self):
        return [self.args.output + ".gv"]

    def finish(self):
        GraphCombiner.finish(self)
        cluster_index = 0
        clusters = {}
        for domain, data in self.per_domain.items():
            cluster = clusters.setdefault(cluster_index, [])
            cluster.append('subgraph cluster_%d {\nlabel = "%s";' % (cluster_index, domain))
            # counters
            for counter_name, counter_data in data['counters'].items():
                id = self.make_id(domain, counter_name)
                self._write(
                    '%s [label="{COUNTER: %s|min=%s|max=%s|avg=%s}"];\n' % (
                    id, html.escape(counter_name),
                    format_time(min(counter_data)), format_time(max(counter_data)),
                    format_time(sum(counter_data) / len(counter_data)))
                )
                cluster.append("%s;" % (id))
            # tasks
            for task_name, task_data in data['tasks'].items():
                id = self.make_id(domain, task_name)
                time = task_data['time']
                self._write(
                    '%s [label="{TASK: %s|min=%s|max=%s|avg=%s|count=%d%s}"];\n' % (
                        id,
                        html.escape(task_name), format_time(min(time)), format_time(max(time)), format_time(sum(time) / len(time)), len(time),
                        (("|%s" % task_data['src'].replace('\\', '/')) if 'src' in task_data else "")
                    )
                )
                cluster.append("%s;" % id)
            #: {}, 'objects':{}, 'frames': {}, 'markers': {}
            cluster_index += 1
        # threads
        thread_names = self.tree['threads']
        for tid in self.threads:
            tid_str, tid_hex = str(tid), (to_hex(tid) if tid is not None else "None")
            id = self.make_id("threads", tid_str)
            thread_name = thread_names[tid_str] if tid_str in thread_names else ""
            self._write('%s [label="{THREAD: %s|%s}" color=gray fontcolor=gray];\n' % (id, tid_hex, html.escape(thread_name)))

        # clusters
        for _, cluster in clusters.items():
            for line in cluster:
                self._write(line + "\n")
            self._write("}\n")
        # relations
        for relation in self.relations.values():
            if 'color' not in relation:
                relation['color'] = 'black'
            self._write('edge [label="{label}" color={color} fontcolor={color}];\n{from}->{to};\n'.format(**relation))

        self._write("}\n")
        self.file.close()

    @staticmethod
    def join_traces(traces, output, args):
        with open(output + ".gv", 'wb') as outfile:
            outfile.write(b"digraph G{\n")
            index = 0
            for file in traces:
                if not file.endswith('.gv'):
                    continue
                index += 1
                with open(file, 'rb') as infile:
                    lines = infile.readlines()
                    del lines[0]  # first line is digraph G{
                    del lines[-1]  # last line is } #digraph G
                    for line in lines:
                        if line.startswith("subgraph cluster_"):
                            number = line.split('_')[1].split(' ')[0]
                            line = "subgraph cluster_%d%s {" % (index, number)
                        outfile.write(line.encode())
            outfile.write(b"}\n")
        return output + ".gv"

EXPORTER_DESCRIPTORS = [{
    'format': 'gv',
    'available': True,
    'exporter': GraphViz
}]
