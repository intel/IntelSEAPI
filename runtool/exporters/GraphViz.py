import cgi
from sea_runtool import GraphCombiner, to_hex, format_time


class GraphViz(GraphCombiner):
    def __init__(self, args, tree):
        GraphCombiner.__init__(self, args, tree)
        self.file = open(self.get_targets()[-1], "w+b")
        self.file.write("digraph G{\nedge [labeldistance=0];\nnode [shape=record];\n")

    def get_targets(self):
        return [self.args.output + ".gv"]

    def finish(self):
        GraphCombiner.finish(self)
        cluster_index = 0
        clusters = {}
        for domain, data in self.per_domain.iteritems():
            cluster = clusters.setdefault(cluster_index, [])
            cluster.append('subgraph cluster_%d {\nlabel = "%s";' % (cluster_index, domain))
            # counters
            for counter_name, counter_data in data['counters'].iteritems():
                id = self.make_id(domain, counter_name)
                self.file.write(
                    '%s [label="{COUNTER: %s|min=%s|max=%s|avg=%s}"];\n' % (
                    id, cgi.escape(counter_name),
                    format_time(min(counter_data)), format_time(max(counter_data)),
                    format_time(sum(counter_data) / len(counter_data)))
                )
                cluster.append("%s;" % (id))
            # tasks
            for task_name, task_data in data['tasks'].iteritems():
                id = self.make_id(domain, task_name)
                time = task_data['time']
                self.file.write(
                    '%s [label="{TASK: %s|min=%s|max=%s|avg=%s|count=%d%s}"];\n' % (
                        id,
                        cgi.escape(task_name), format_time(min(time)), format_time(max(time)), format_time(sum(time) / len(time)), len(time),
                        (("|%s" % task_data['src'].replace('\\', '/')) if task_data.has_key('src') else "")
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
            thread_name = thread_names[tid_str] if thread_names.has_key(tid_str) else ""
            self.file.write('%s [label="{THREAD: %s|%s}" color=gray fontcolor=gray];\n' % (id, tid_hex, cgi.escape(thread_name)))

        # clusters
        for _, cluster in clusters.iteritems():
            for line in cluster:
                self.file.write(line + "\n")
            self.file.write("}\n")
        # relations
        for relation in self.relations.itervalues():
            if not relation.has_key('color'):
                relation['color'] = 'black'
            self.file.write('edge [label="{label}" color={color} fontcolor={color}];\n{from}->{to};\n'.format(**relation))

        self.file.write("}\n")
        self.file.close()

    @staticmethod
    def join_traces(traces, output, args):
        with open(output + ".gv", 'wb') as outfile:
            outfile.write("digraph G{\n")
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
                        outfile.write(line)
            outfile.write("}\n")
        return output + ".gv"

EXPORTER_DESCRIPTORS = [{
    'format': 'gv',
    'available': True,
    'exporter': GraphViz
}]
