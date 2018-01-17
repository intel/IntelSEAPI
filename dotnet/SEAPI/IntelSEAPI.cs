using System;

namespace SEAPI
{
    public static class IntelSEAPI
    {
        public static readonly Profiler Profiler;

        static IntelSEAPI()
        {
            var initializator = CreateInitializator();
            initializator.Init();
            Profiler = new Profiler(initializator.CreateNative());
        }

        private static IInitializator CreateInitializator()
        {
            switch (Environment.OSVersion.Platform)
            {
                case PlatformID.MacOSX:
                    throw new NotImplementedException("MacOS is not implemented");
                case PlatformID.Unix:
                    throw new NotImplementedException("Unix is not implemented");
                case PlatformID.Win32NT:
                    return new WindowsInitializator();
                case PlatformID.Win32S:
                    throw new NotImplementedException("Win32S is not implemented");
                case PlatformID.Win32Windows:
                    throw new NotImplementedException("Windows 95/98 is not implemented");
                case PlatformID.WinCE:
                    throw new NotImplementedException("Windows CE is not implemented");
                case PlatformID.Xbox:
                    throw new NotImplementedException("Xbox is not implemented");
                default:
                    throw new ArgumentOutOfRangeException();
            }
        }
    }
}