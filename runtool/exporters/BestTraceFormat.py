from sea_runtool import TaskCombiner

###################################
# TODO: add OS events (sched/vsync)
class BestTraceFormat(TaskCombiner):
    """Writer for Best Trace Format.

    Specs for BTF v2.1.3: https://wiki.eclipse.org/images/e/e6/TA_BTF_Specification_2.1.3_Eclipse_Auto_IWG.pdf
    """

    def __init__(self, args, tree):
        """Open the .btf file and write its header."""
        TaskCombiner.__init__(self, args, tree)
        self.file = open(self.get_targets()[-1], "w+b")
        self.file.write('#version 2.1.3\n')
        self.file.write('#creator GDP-SEA\n')
        self.file.write('#creationDate 2014-02-19T11:39:20Z\n')
        self.file.write('#timeScale ns\n')

    def get_targets(self):
        return [self.args.output + ".btf"]

    def complete_task(self, type, b, e):
        """
        type -- task type : {"task", "frame", "counter"}
        b -- { 'thread_name': '0x6296', 'domain': 'gles.trace.ergs', 'str': 'glPopMatrix', 'time': 1443097648250368731, 'tid': 25238, 'pid': 25238}
        e -- { 'tid': 25238, 'thread_name': '0x6296', 'domain': 'gles.trace.ergs', 'pid': 25238, 'time': 1443097648250548143}
        """
        # <Time>,<Source>,<SourceInstance >,<TargetType>,<Target>,<TargetInstance>,<Event>,<Note>
        if 'str' in b and type == "task":
            self.file.write("%d,%s,0,R,%s,-1,start\n" % (b['time'], b['str'], b['str']))
            self.file.write("%d,%s,0,R,%s,-1,terminate\n" % (e['time'], b['str'], b['str']))

    def finish(self):
        """ Close the .btf file"""
        self.file.close()

    @staticmethod
    def join_traces(traces, output, args):
        with open(output + ".btf", 'wb') as outfile:
            for file in traces:
                with open(file, 'rb') as infile:
                    for line in infile:
                        outfile.write(line)
        return output + ".btf"

EXPORTER_DESCRIPTORS = [{
    'format': 'btf',
    'available': True,
    'exporter': BestTraceFormat
}]
