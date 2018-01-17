using System;
using System.Runtime.InteropServices;

namespace SEAPI
{
    public interface INative
    {
        IntPtr CreateDomain(string name);
    }
}