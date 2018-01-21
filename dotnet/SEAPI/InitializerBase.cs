using System;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Runtime.Loader;

namespace SEAPI
{
    internal abstract class InitializerBase : AssemblyLoadContext, IInitializer
    {
        protected static readonly string Bitness = GetBitness();

        public abstract void Init();
        public abstract INative CreateNative();

        protected override Assembly Load(AssemblyName assemblyName)
        {
            return null;
        }

        private static string GetBitness()
        {
            switch (RuntimeInformation.OSArchitecture)
            {
                case Architecture.Arm:
                case Architecture.X86:
                    return "32";
                case Architecture.Arm64:
                case Architecture.X64:
                    return "64";
                default:
                    throw new ArgumentOutOfRangeException();
            }
        }
    }
}