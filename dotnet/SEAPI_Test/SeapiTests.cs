using System;
using SEAPI;
using Xunit;

namespace SEAPI_Test
{
    public class SeapiTests
    {
        [Fact]
        public void Test()
        {
            IntelSEAPI.Profiler.CreateDomain("a");
        }
    }
}
