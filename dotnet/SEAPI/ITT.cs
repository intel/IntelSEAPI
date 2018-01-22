using System;
using System.Collections.Concurrent;

namespace SEAPI
{
    public class ITT
    {
        private static readonly INative Native;
        private static readonly ConcurrentDictionary<Tuple<string, string>, IntPtr> Tracks =
                new ConcurrentDictionary<Tuple<string, string>, IntPtr>();

        private readonly ConcurrentDictionary<string, IntPtr> _counters = new ConcurrentDictionary<string, IntPtr>();
        private readonly IntPtr _domainPointer;

        static ITT()
        {
            var initializator = CreateInitializator();
            initializator.Init();
            Native = initializator.CreateNative();
        }

        private ITT(IntPtr domainPointer)
        {
            _domainPointer = domainPointer;
        }

        public static ITT CreateDomain(string name)
        {
            var domainPointer = Native.CreateDomain(name);
            if (domainPointer == IntPtr.Zero)
            {
                throw new InvalidOperationException();
            }

            return new ITT(domainPointer);
        }

        public static ulong GetTimeStamp()
        {
            return Native.GetTimeStamp();
        }

        public static Track GetTrack(string group, string name)
        {
            var pointer = Tracks.GetOrAdd(Tuple.Create(group, name), x => Native.CreateTrack(x.Item1, x.Item2));
            return new Track(Native, pointer);
        }

        public void Marker(string name, Scope scope = Scope.Process, ulong timeStamp = 0, ulong id = 0)
        {
            Native.Marker(_domainPointer, id, name, (int)scope, timeStamp);
        }

        public Task GetTask(string name, ulong id = 0, Task parent = null)
        {
            return new Task(Native, _domainPointer, name, id, parent);
        }

        public void SubmitTask(string name, ulong timeStamp, ulong dur, ulong id = 0, Task parent = null)
        {
            Native.BeginTask(_domainPointer, id, parent?.Id ?? 0, name, timeStamp);
            Native.EndTask(_domainPointer, timeStamp + dur);
        }

        public void SetCounter(string name, double value, ulong timestamp = 0)
        {
            var pointer = _counters.GetOrAdd(name, x => Native.CreateCounter(_domainPointer, x));
            Native.SetCounter(pointer, value, timestamp);
        }

        private static IInitializer CreateInitializator()
        {
            switch (Environment.OSVersion.Platform)
            {
                case PlatformID.Win32Windows:
                case PlatformID.Win32NT:
                case PlatformID.Win32S:
                case PlatformID.WinCE:
                    return new WindowsInitializer();

                case PlatformID.Unix:
                    return new LinuxInitializer();

                case PlatformID.MacOSX:
                    return new OSXInitializer();

                default:
                    throw new PlatformNotSupportedException();
            }
        }
    }
}