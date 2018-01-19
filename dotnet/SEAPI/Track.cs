using System;

namespace SEAPI
{
    public class Track : IDisposable
    {
        private readonly INative _native;

        internal Track(INative native, IntPtr pointer)
        {
            _native = native;
            _native.SetTrack(pointer);
        }

        public void Dispose()
        {
            _native.SetTrack(IntPtr.Zero);
        }
    }
}