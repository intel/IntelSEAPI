using System;
using System.IO;

namespace SEAPI
{
    internal class LinuxInitializer : InitializerBase
    {
        private static string _libraryName;
        private static readonly string LibraryName1 = $"IntelSEAPI{Bitness}.so";
        private static readonly string LibraryName2 = $"libIntelSEAPI{Bitness}.so";

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
                if (_libraryName == LibraryName1)
                {
                    return new IntelSEAPI32Native();
                }

                if (_libraryName == LibraryName2)
                {
                    return new libIntelSEAPI32Native();
                }

                throw new InvalidOperationException();
            }

            if (_libraryName == LibraryName1)
            {
                return new IntelSEAPI64Native();
            }

            if (_libraryName == LibraryName2)
            {
                return new libIntelSEAPI64Native();
            }

            throw new FileNotFoundException();
        }

        private static bool TryGetFromEnvironment(out string path)
        {
            path = Environment.GetEnvironmentVariable($"INTEL_LIBITTNOTIFY{Bitness}");
            if (string.IsNullOrWhiteSpace(path))
            {
                return false;
            }

            if (path.EndsWith(LibraryName1))
            {
                _libraryName = LibraryName1;
                return File.Exists(path);
            }

            if (path.EndsWith(LibraryName2))
            {
                _libraryName = LibraryName2;
                return File.Exists(path);
            }

            return false;
        }

        private static bool TryGetFromCurrentFolder(out string path)
        {
            var currentDirectory = Directory.GetCurrentDirectory();
            path = Path.Combine(currentDirectory, LibraryName1);
            if (File.Exists(path))
            {
                _libraryName = LibraryName1;
                return true;
            }

            path = Path.Combine(currentDirectory, LibraryName2);
            if (File.Exists(path))
            {
                _libraryName = LibraryName2;
                return true;
            }

            return false;
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

            path = Path.Combine(dir.Parent.FullName, "bin", LibraryName1);
            if (File.Exists(path))
            {
                _libraryName = LibraryName1;
                return true;
            }

            path = Path.Combine(dir.Parent.FullName, "bin", LibraryName2);
            if (File.Exists(path))
            {
                _libraryName = LibraryName2;
                return true;
            }

            return false;
        }
    }
}