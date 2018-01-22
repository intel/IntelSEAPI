using System;
using System.IO;

namespace SEAPI
{
    internal class WindowsInitializer : InitializerBase
    {
        private static readonly string LibraryName = $"IntelSEAPI{Bitness}.dll";

        public override void Init()
        {
            if (TryGetFromEnvironment(out var path) ||
                TryGetFromCurrentFolder(out path) ||
                TryGetFromBuildFolder(out path))
            {
                LoadUnmanagedDllFromPath(path);
            }
        }

        public override INative CreateNative()
        {
            if (Bitness == "32")
            {
                return new IntelSEAPI32Native();
            }

            return new IntelSEAPI64Native();
        }

        private static bool TryGetFromEnvironment(out string path)
        {
            path = Environment.GetEnvironmentVariable($"INTEL_LIBITTNOTIFY{Bitness}");
            return !string.IsNullOrWhiteSpace(path) && path.EndsWith(LibraryName) && File.Exists(path);
        }

        private static bool TryGetFromCurrentFolder(out string path)
        {
            path = Path.Combine(Directory.GetCurrentDirectory(), LibraryName);
            return File.Exists(path);
        }

        private static bool TryGetFromBuildFolder(out string path)
        {
            var dir = new DirectoryInfo(Directory.GetCurrentDirectory());
            while (dir != null && dir.Name != "dotnet")
            {
                dir = dir.Parent;
            }

            if (dir == null)
            {
                path = null;
                return false;
            }

            path = Path.Combine(dir.Parent.FullName, "bin", LibraryName);
            return File.Exists(path);
        }
    }
}