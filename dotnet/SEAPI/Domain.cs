using System;
using System.Collections.Concurrent;

namespace SEAPI
{
    public class Domain
    {
        private readonly IntPtr _domainPointer;
        private readonly INative _native;
        private readonly ConcurrentDictionary<string, IntPtr> _counters = new ConcurrentDictionary<string, IntPtr>();

        internal Domain(INative native, IntPtr domainPointer)
        {
            _domainPointer = domainPointer;
            _native = native;
        }

        public void Marker(string name, Scope scope = Scope.Process, ulong timeStamp = 0, ulong id = 0)
        {
            _native.Marker(_domainPointer, id, name, (int)scope, timeStamp);
        }

        public Task GetTask(string name, ulong id = 0, Task parent = null)
        {
            return new Task(_native, _domainPointer, name, id, parent);
        }

        public void SubmitTask(string name, ulong timeStamp, ulong dur, ulong id =0, Task parent = null  )
        {
            _native.BeginTask(_domainPointer, id, parent?.Id??0, name, timeStamp);
            _native.EndTask(_domainPointer, timeStamp + dur);
        }

        public void SetCounter(string name, double value, ulong timestamp = 0)
        {
            var pointer = _counters.GetOrAdd(name, x => _native.CreateCounter(_domainPointer, x));
            _native.SetCounter(pointer, value, timestamp);
        }
    }
}