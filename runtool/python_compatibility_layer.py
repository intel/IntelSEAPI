import sys

if sys.version_info[0] > 2:
    def itervalues(dictionary):
        return dictionary.values()

    def iteritems(dictionary):
        return dictionary.items()

    xrange = range
    basestring = (str, bytes)
    unicode = str
else:
    def itervalues(dictionary):
        return dictionary.itervalues()

    def iteritems(dictionary):
        return dictionary.iteritems()

    xrange = xrange
    basestring = basestring
    unicode = unicode
