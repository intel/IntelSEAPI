using System;

namespace SEAPI
{
    public class Task : IDisposable
    {
        private readonly IntPtr _domain;
        private readonly INative _native;
        internal readonly ulong Id;

        internal Task(INative native, IntPtr domain, string name, ulong id, Task parent)
        {
            _native = native;
            _domain = domain;
            Id = id;
            _native.BeginTask(domain, id, parent?.Id ?? 0, name, 0);
        }


        public void Dispose()
        {
            _native.EndTask(_domain, 0);
        }

        public Task AddArgument(string name, double value)
        {
            _native.AddMetadata(_domain, Id, name, value);
            return this;
        }

        public Task AddArgument(string name, string value)
        {
            _native.AddStringMetadata(_domain, Id, name, value);
            return this;
        }

        public Task AddData(string name, byte[] value)
        {
            unsafe
            {
                fixed (byte* p = value)
                {
                    _native.AddBlobMetadata(_domain, Id, name, (IntPtr)p, (uint)value.Length);
                }
            }

            return this;
        }
    }
}