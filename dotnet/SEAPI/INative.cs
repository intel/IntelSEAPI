using System;

namespace SEAPI
{
    internal interface INative
    {
        IntPtr CreateDomain(string name);
        void Marker(IntPtr domain, ulong id, string name, int scope, ulong timestamp);
        void BeginTask(IntPtr domain, ulong id, ulong parent, string name, ulong timestamp);
        void BeginOverlappedTask(IntPtr domain, ulong id, ulong parent, string name, ulong timestamp);
        void AddMetadata(IntPtr domain, ulong id, string name, double value);
        void AddStringMetadata(IntPtr domain, ulong id, string name, string value);
        void AddBlobMetadata(IntPtr domain, ulong id, string name, IntPtr value, uint size);
        void EndTask(IntPtr domain, ulong timestamp);
        void EndOverlappedTask(IntPtr domain, ulong timestamp, ulong taskId);
        IntPtr CreateCounter(IntPtr domain, string name);
        void SetCounter(IntPtr id, double value, ulong timestamp);
        IntPtr CreateTrack(string group, string track);
        void SetTrack(IntPtr track);
        ulong GetTimeStamp();
    }
}