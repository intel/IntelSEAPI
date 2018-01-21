using System;
using System.Collections.Concurrent;

namespace SEAPI
{
    internal abstract class NativeBase : INative
    {
        private static readonly ConcurrentDictionary<string, IntPtr> Pointers =
                new ConcurrentDictionary<string, IntPtr>();

        public void Marker(IntPtr domain, ulong id, string name, int scope, ulong timestamp)
        {
            Marker(domain, id, GetStringPointer(name), scope, timestamp);
        }

        public void BeginTask(IntPtr domain, ulong id, ulong parent, string name, ulong timestamp)
        {
            BeginTask(domain, id, parent, GetStringPointer(name), timestamp);
        }

        public void BeginOverlappedTask(IntPtr domain, ulong id, ulong parent, string name, ulong timestamp)
        {
            BeginOverlappedTask(domain, id, parent, GetStringPointer(name), timestamp);
        }

        public void AddMetadata(IntPtr domain, ulong id, string name, double value)
        {
            AddMetadata(domain, id, GetStringPointer(name), value);
        }

        public void AddStringMetadata(IntPtr domain, ulong id, string name, string value)
        {
            AddStringMetadata(domain, id, GetStringPointer(name), value);
        }

        public void AddBlobMetadata(IntPtr domain, ulong id, string name, IntPtr value, uint size)
        {
            AddBlobMetadata(domain, id, GetStringPointer(name), value, size);
        }

        public IntPtr CreateCounter(IntPtr domain, string name)
        {
            return CreateCounter(domain, GetStringPointer(name));
        }

        public abstract IntPtr CreateDomain(string name);
        public abstract void EndTask(IntPtr domain, ulong timestamp);
        public abstract void EndOverlappedTask(IntPtr domain, ulong timestamp, ulong taskId);
        public abstract void SetCounter(IntPtr id, double value, ulong timestamp);
        public abstract IntPtr CreateTrack(string group, string track);
        public abstract void SetTrack(IntPtr track);
        public abstract ulong GetTimeStamp();
        protected abstract IntPtr CreateString(string name);
        protected abstract void Marker(IntPtr domain, ulong id, IntPtr name, int scope, ulong timestamp);
        protected abstract void BeginTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp);
        protected abstract void BeginOverlappedTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp);
        protected abstract void AddMetadata(IntPtr domain, ulong id, IntPtr name, double value);
        protected abstract void AddStringMetadata(IntPtr domain, ulong id, IntPtr name, string value);
        protected abstract void AddBlobMetadata(IntPtr domain, ulong id, IntPtr name, IntPtr value, uint size);
        protected abstract IntPtr CreateCounter(IntPtr domain, IntPtr name);

        private IntPtr GetStringPointer(string str)
        {
            return Pointers.GetOrAdd(str, CreateString);
        }
    }
}