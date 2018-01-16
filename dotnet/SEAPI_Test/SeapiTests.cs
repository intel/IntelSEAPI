using System;
using SEAPI;
using Xunit;

namespace SEAPI_Test
{
    public class SeapiTests
    {
        public SeapiTests()
        {
            new InitializatorFactory().Create().Init();
        }
        [Fact]
        public void Test()
        {
            var domain = Extern.CreateDomain("asd");
        }
    }
}
