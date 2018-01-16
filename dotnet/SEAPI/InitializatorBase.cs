using System;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Runtime.Loader;

namespace SEAPI
{
    internal abstract class InitializatorBase : AssemblyLoadContext, IInitializator
    {
        public string ArhitecturePostfix { get; } = GetArhitecturePostfix();

        public abstract void Init();

        protected override Assembly Load(AssemblyName assemblyName)
        {
            return null;
        }

        private static string GetArhitecturePostfix()
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