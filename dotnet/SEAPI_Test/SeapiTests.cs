using System;
using System.Threading;
using SEAPI;
using Xunit;

namespace SEAPI_Test
{
    public class SeapiTests
    {
        private readonly Random _random = new Random();

        private void StartTask(Domain domain)
        {
            using (domain.GetTask("dotnet_task"))
            {
                Thread.Sleep(10);
                if (_random.Next(2) != 0)
                {
                    StartTask(domain);
                }

                Thread.Sleep(10);
            }
        }

        [Fact]
        public void Test()
        {
            var domain = ITT.CreateDomain("dotnet");
            domain.Marker("Begin");
            var ts1 = ITT.GetTimeStamp();
            using (var task = domain.GetTask("Main"))
            {
                for (var i = 0; i < 100; i++)
                {
                    StartTask(domain);
                    domain.SetCounter("dotnet_counter", i);
                }
            }

            var ts2 = ITT.GetTimeStamp();
            domain.Marker("End");
            using (ITT.GetTrack("group", "track"))
            {
                var dur = (ts2 - ts1) / 100 + 1;
                for (var i = ts1; i <= ts2; i += dur)
                {
                    domain.SubmitTask("submitted", dur, dur / 2);
                }
            }
        }
    }
}