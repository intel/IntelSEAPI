import os
import codecs

# use vulcanized_traceviewer to create trace_viewer_full.html


def read_file(filename):
    with codecs.open(filename, 'r', 'utf-8') as fh:
        return fh.read()


result = read_file('prefix.html')

viewer = read_file('trace_viewer_full.html')
result = result.replace('{{TRACE_VIEWER_HTML}}', viewer)

license = read_file('LICENSE')
result = result.replace('{{ISEA_CATAPULT_LICENSE}}', license)

with codecs.open(os.path.join('../isea.htm'), 'w', 'utf-8') as fh:
    fh.writelines(result)

