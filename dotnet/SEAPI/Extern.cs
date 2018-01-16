using System;
using System.Runtime.InteropServices;

namespace SEAPI
{
    public static class Extern
    {
        private const string DllName =
#if BUILD64
                "IntelSEAPI64";
        //"INTEL_LIBITTNOTIFY64";
#else
                "IntelSEAPI32";
                //"INTEL_LIBITTNOTIFY32";
#endif

        [DllImport(DllName, EntryPoint = "itt_create_domain")]
        public static extern IntPtr CreateDomain(string name);
    }
}