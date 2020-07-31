import csv
from sea_runtool import GraphCombiner


class Stat(GraphCombiner):
    def __init__(self, args, tree):
        GraphCombiner.__init__(self, args, tree)

    def get_targets(self):
        return [self.args.output + ".csv"]

    def finish(self):
        GraphCombiner.finish(self)
        with open(self.get_targets()[-1], 'w+b') as f:
            writer = csv.writer(f)
            writer.writerow(["domain", "name", "min", "max", "avg", "total", "count"])
            for domain, data in self.per_domain.iteritems():
                for task_name, task_data in data['tasks'].iteritems():
                    time = task_data['time']
                    writer.writerow([domain, task_name, min(time), max(time), sum(time) / len(time), sum(time), len(time)])

    @staticmethod
    def join_traces(traces, output, args):  # FIXME: implement real joiner
        sorting = []
        for trace in traces:
            sorting.append((os.path.getsize(trace), trace))
        sorting.sort(key=lambda (size, trace): size, reverse=True)
        shutil.copyfile(sorting[0][1], output + ".csv")
        return output + ".csv"

EXPORTER_DESCRIPTORS = [{
    'format': 'stat',
    'available': True,
    'exporter': Stat
}]
