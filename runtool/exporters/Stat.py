import cgi
from sea_runtool import GraphCombiner

import os
import sys
sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))
from python_compatibility_layer import iteritems

class Stat(GraphCombiner):
    def __init__(self, args, tree):
        GraphCombiner.__init__(self, args, tree)
        self.file = open(self.get_targets()[-1], "w+b")
        self.file.write("domain,name,min,max,avg,count\n")

    def get_targets(self):
        return [self.args.output + ".csv"]

    def finish(self):
        GraphCombiner.finish(self)
        for (domain, data) in iteritems(self.per_domain):
            for (task_name, task_data) in iteritems(data['tasks']):
                time = task_data['time']
                self.file.write('%s,%s,%s,%s,%s,%d\n' % (
                        cgi.escape(domain), cgi.escape(task_name),
                        min(time), max(time), sum(time) / len(time), len(time)
                    )
                )
        self.file.close()

    @staticmethod
    def join_traces(traces, output, args):  # FIXME: implement real joiner
        sorting = []
        for trace in traces:
            sorting.append((os.path.getsize(trace), trace))
        sorting.sort(key=lambda size_trace: size_trace[0], reverse=True)
        shutil.copyfile(sorting[0][1], output + ".csv")
        return output + ".csv"

EXPORTER_DESCRIPTORS = [{
    'format': 'stat',
    'available': True,
    'exporter': Stat
}]
