import os
import struct
from sea_runtool import TaskCombiner, get_exporters, resolve_pointer


class Memory(TaskCombiner):
    def __init__(self, args, tree):
        TaskCombiner.__init__(self, args, tree)
        self.mem = {}
        stat_mem = os.path.join(self.args.input, 'stat.mem')
        self.mem_stat = self.read_mem_stat(stat_mem) if os.path.exists(stat_mem) else None
        self.targets = [self.args.output + ".csv"]

    def read_mem_stat(self, path):
        strings = self.tree['strings']
        if self.tree['process']['bits'] == 64:
            def read_pointer(file):
                return struct.unpack('Q', file.read(8))[0]
        else:
            def read_pointer(file):
                return struct.unpack('I', file.read(4))[0]
        with open(path, 'rb') as file:
            def read_node():
                mem = {}
                mem_block_count = struct.unpack('I', file.read(4))[0]
                total_max = 0
                for i in range(mem_block_count):
                    block_size, block_current, block_max = struct.unpack('IiI', file.read(4*3))
                    mem[block_size] = (block_current, block_max)
                    total_max += block_max * block_size
                child_count = struct.unpack('I', file.read(4))[0]
                children = {}
                for i in range(child_count):
                    domain = read_pointer(file)
                    name = read_pointer(file)
                    if name in strings:
                        name = strings[name]
                    else:
                        call = {}
                        if resolve_pointer(self.args, self.tree, name, call):
                            name = call['str']
                        else:
                            name = 'unresolved'
                    child_node = read_node()
                    children[(domain, name)] = child_node
                    total_max += child_node['total_max']
                return {'mem': mem, 'children': children, 'total_max': total_max}
            return read_node()

    def export_mem_stat(self):
        gt = get_exporters()['gt'](self.args, self.tree)
        total = self.mem_stat['total_max']

        def export_node(name, node, offset):
            length = 1000000. * node['total_max'] / total

            call_data = {'tid': 0, 'pid': 0, 'domain': 'memory', 'time': offset, 'str': name, 'type': 0}
            end_data = call_data.copy()
            end_data['time'] = offset + length
            end_data['type'] = 1
            gt.complete_task('task', call_data, end_data)
            for pair, child in node['children'].iteritems():
                offset += export_node(pair[1], child, offset)
            return length
        export_node('global scope', self.mem_stat, 0)
        gt.finish()
        self.targets.append(gt.get_targets()[0])

    def get_targets(self):
        return self.targets

    def complete_task(self, type, begin, e):
        if type != 'task' or 'memory' not in begin:
            return
        score = self.mem.setdefault(begin['str'], {'self': 0, 'children': 0})
        for size, values in begin['memory'].iteritems():
            if size is None:  # special case for children attribution
                score['children'] += values
            else:
                score['self'] += size * sum(values)

    def finish(self):
        with open(self.get_targets()[0], "w+b") as file:
            file.write('name,self,children\n')
            for key, value in self.mem.iteritems():
                file.write('%s,%f,%f\n' % (key, value['self'], value['children']))
        if self.mem_stat:
            self.export_mem_stat()

    @staticmethod
    def join_traces(traces, output, args):
        return traces[0]

EXPORTER_DESCRIPTORS = [{
    'format': 'mem',
    'available': True,
    'exporter': Memory
}]
