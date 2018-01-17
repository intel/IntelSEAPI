using System;

namespace SEAPI
{
    public class Profiler
    {
        private readonly INative _native;

        public Profiler(INative native)
        {
            _native = native;
        }

        public void CreateDomain(string name)
        {
            var res = _native.CreateDomain(name);
            if (res == IntPtr.Zero)
            {
                throw new InvalidOperationException();
            }
        }
    }
}