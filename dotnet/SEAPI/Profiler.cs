using System;
using System.Collections.Concurrent;

namespace SEAPI
{
    internal class Profiler
    {
        private readonly INative _native;

        private readonly ConcurrentDictionary<Tuple<string, string>, IntPtr> _tracks =
                new ConcurrentDictionary<Tuple<string, string>, IntPtr>();

        internal Profiler(INative native)
        {
            _native = native;
        }

        public Domain CreateDomain(string name)
        {
            var domainPointer = _native.CreateDomain(name);
            if (domainPointer == IntPtr.Zero)
            {
                throw new InvalidOperationException();
            }

            return new Domain(_native, domainPointer);
        }

        public ulong GetTimeStamp()
        {
            return _native.GetTimeStamp();
        }

        public Track GetTrack(string group, string name)
        {
            var pointer = _tracks.GetOrAdd(Tuple.Create(group, name), x => _native.CreateTrack(x.Item1, x.Item2));
            return new Track(_native, pointer);
        }
    }
}