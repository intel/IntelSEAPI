using System;
using System.Runtime.InteropServices;

namespace SEAPI
{
	internal class IntelSEAPI32Native : NativeBase
    {
		private const string NativeLibraryName = "IntelSEAPI32";
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_create_domain")]
		private static extern IntPtr NativeCreateDomain(string name);

		public override IntPtr CreateDomain(string name)
        {
            return NativeCreateDomain(name);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_create_string")]
		private static extern IntPtr NativeCreateString(string name);

		protected override IntPtr CreateString(string name)
        {
            return NativeCreateString(name);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_marker")]
		private static extern void NativeMarker(IntPtr domain, ulong id, IntPtr name, int scope, ulong timestamp);

		protected override void Marker(IntPtr domain, ulong id, IntPtr name, int scope, ulong timestamp)
        {
            NativeMarker(domain, id, name, scope, timestamp);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_task_begin")]
		private static extern void NativeBeginTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp);

		protected override void BeginTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp)
        {
            NativeBeginTask(domain, id, parent, name, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_task_begin_overlapped")]
		private static extern void NativeBeginOverlappedTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp);

		protected override void BeginOverlappedTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp)
        {
            NativeBeginOverlappedTask(domain, id, parent, name, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_metadata_add")]
		private static extern void NativeAddMetadata(IntPtr domain, ulong id, IntPtr name, double value);

		protected override void AddMetadata(IntPtr domain, ulong id, IntPtr name, double value)
        {
            NativeAddMetadata(domain, id, name, value);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_metadata_add_str")]
		private static extern void NativeAddStringMetadata(IntPtr domain, ulong id, IntPtr name, string value);

		protected override void AddStringMetadata(IntPtr domain, ulong id, IntPtr name, string value)
        {
            NativeAddStringMetadata(domain, id, name, value);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_metadata_add_blob")]
		private static extern void NativeAddBlobMetadata(IntPtr domain, ulong id, IntPtr name, IntPtr value, uint size);

		protected override void AddBlobMetadata(IntPtr domain, ulong id, IntPtr name, IntPtr value, uint size)
        {
            NativeAddBlobMetadata(domain, id, name, value, size);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_task_end")]
		private static extern void NativeEndTask(IntPtr domain, ulong timestamp);

		public override void EndTask(IntPtr domain, ulong timestamp)
        {
            NativeEndTask(domain, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_task_end_overlapped")]
		private static extern void NativeEndOverlappedTask(IntPtr domain, ulong timestamp, ulong taskId);

		public override void EndOverlappedTask(IntPtr domain, ulong timestamp, ulong taskId)
        {
            NativeEndOverlappedTask(domain, timestamp, taskId);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_counter_create")]
		private static extern IntPtr NativeCreateCounter(IntPtr domain, IntPtr name);

		protected override IntPtr CreateCounter(IntPtr domain, IntPtr name)
        {
            return NativeCreateCounter(domain, name);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_set_counter")]
		private static extern void NativeSetCounter(IntPtr id, double value, ulong timestamp);

		public override void SetCounter(IntPtr id, double value, ulong timestamp)
        {
            NativeSetCounter(id, value, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_create_track")]
		private static extern IntPtr NativeCreateTrack(string group, string track);

		public override IntPtr CreateTrack(string group, string track)
        {
            return NativeCreateTrack(group, track);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_set_track")]
		private static extern void NativeSetTrack(IntPtr track);

		public override void SetTrack(IntPtr track)
        {
            NativeSetTrack(track);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_get_timestamp")]
		private static extern ulong NativeGetTimeStamp();

		public override ulong GetTimeStamp()
        {
            return NativeGetTimeStamp();
        }
	}

	internal class IntelSEAPI64Native : NativeBase
    {
		private const string NativeLibraryName = "IntelSEAPI64";
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_create_domain")]
		private static extern IntPtr NativeCreateDomain(string name);

		public override IntPtr CreateDomain(string name)
        {
            return NativeCreateDomain(name);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_create_string")]
		private static extern IntPtr NativeCreateString(string name);

		protected override IntPtr CreateString(string name)
        {
            return NativeCreateString(name);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_marker")]
		private static extern void NativeMarker(IntPtr domain, ulong id, IntPtr name, int scope, ulong timestamp);

		protected override void Marker(IntPtr domain, ulong id, IntPtr name, int scope, ulong timestamp)
        {
            NativeMarker(domain, id, name, scope, timestamp);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_task_begin")]
		private static extern void NativeBeginTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp);

		protected override void BeginTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp)
        {
            NativeBeginTask(domain, id, parent, name, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_task_begin_overlapped")]
		private static extern void NativeBeginOverlappedTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp);

		protected override void BeginOverlappedTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp)
        {
            NativeBeginOverlappedTask(domain, id, parent, name, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_metadata_add")]
		private static extern void NativeAddMetadata(IntPtr domain, ulong id, IntPtr name, double value);

		protected override void AddMetadata(IntPtr domain, ulong id, IntPtr name, double value)
        {
            NativeAddMetadata(domain, id, name, value);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_metadata_add_str")]
		private static extern void NativeAddStringMetadata(IntPtr domain, ulong id, IntPtr name, string value);

		protected override void AddStringMetadata(IntPtr domain, ulong id, IntPtr name, string value)
        {
            NativeAddStringMetadata(domain, id, name, value);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_metadata_add_blob")]
		private static extern void NativeAddBlobMetadata(IntPtr domain, ulong id, IntPtr name, IntPtr value, uint size);

		protected override void AddBlobMetadata(IntPtr domain, ulong id, IntPtr name, IntPtr value, uint size)
        {
            NativeAddBlobMetadata(domain, id, name, value, size);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_task_end")]
		private static extern void NativeEndTask(IntPtr domain, ulong timestamp);

		public override void EndTask(IntPtr domain, ulong timestamp)
        {
            NativeEndTask(domain, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_task_end_overlapped")]
		private static extern void NativeEndOverlappedTask(IntPtr domain, ulong timestamp, ulong taskId);

		public override void EndOverlappedTask(IntPtr domain, ulong timestamp, ulong taskId)
        {
            NativeEndOverlappedTask(domain, timestamp, taskId);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_counter_create")]
		private static extern IntPtr NativeCreateCounter(IntPtr domain, IntPtr name);

		protected override IntPtr CreateCounter(IntPtr domain, IntPtr name)
        {
            return NativeCreateCounter(domain, name);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_set_counter")]
		private static extern void NativeSetCounter(IntPtr id, double value, ulong timestamp);

		public override void SetCounter(IntPtr id, double value, ulong timestamp)
        {
            NativeSetCounter(id, value, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_create_track")]
		private static extern IntPtr NativeCreateTrack(string group, string track);

		public override IntPtr CreateTrack(string group, string track)
        {
            return NativeCreateTrack(group, track);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_set_track")]
		private static extern void NativeSetTrack(IntPtr track);

		public override void SetTrack(IntPtr track)
        {
            NativeSetTrack(track);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_get_timestamp")]
		private static extern ulong NativeGetTimeStamp();

		public override ulong GetTimeStamp()
        {
            return NativeGetTimeStamp();
        }
	}

	internal class libIntelSEAPI32Native : NativeBase
    {
		private const string NativeLibraryName = "libIntelSEAPI32";
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_create_domain")]
		private static extern IntPtr NativeCreateDomain(string name);

		public override IntPtr CreateDomain(string name)
        {
            return NativeCreateDomain(name);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_create_string")]
		private static extern IntPtr NativeCreateString(string name);

		protected override IntPtr CreateString(string name)
        {
            return NativeCreateString(name);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_marker")]
		private static extern void NativeMarker(IntPtr domain, ulong id, IntPtr name, int scope, ulong timestamp);

		protected override void Marker(IntPtr domain, ulong id, IntPtr name, int scope, ulong timestamp)
        {
            NativeMarker(domain, id, name, scope, timestamp);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_task_begin")]
		private static extern void NativeBeginTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp);

		protected override void BeginTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp)
        {
            NativeBeginTask(domain, id, parent, name, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_task_begin_overlapped")]
		private static extern void NativeBeginOverlappedTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp);

		protected override void BeginOverlappedTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp)
        {
            NativeBeginOverlappedTask(domain, id, parent, name, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_metadata_add")]
		private static extern void NativeAddMetadata(IntPtr domain, ulong id, IntPtr name, double value);

		protected override void AddMetadata(IntPtr domain, ulong id, IntPtr name, double value)
        {
            NativeAddMetadata(domain, id, name, value);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_metadata_add_str")]
		private static extern void NativeAddStringMetadata(IntPtr domain, ulong id, IntPtr name, string value);

		protected override void AddStringMetadata(IntPtr domain, ulong id, IntPtr name, string value)
        {
            NativeAddStringMetadata(domain, id, name, value);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_metadata_add_blob")]
		private static extern void NativeAddBlobMetadata(IntPtr domain, ulong id, IntPtr name, IntPtr value, uint size);

		protected override void AddBlobMetadata(IntPtr domain, ulong id, IntPtr name, IntPtr value, uint size)
        {
            NativeAddBlobMetadata(domain, id, name, value, size);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_task_end")]
		private static extern void NativeEndTask(IntPtr domain, ulong timestamp);

		public override void EndTask(IntPtr domain, ulong timestamp)
        {
            NativeEndTask(domain, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_task_end_overlapped")]
		private static extern void NativeEndOverlappedTask(IntPtr domain, ulong timestamp, ulong taskId);

		public override void EndOverlappedTask(IntPtr domain, ulong timestamp, ulong taskId)
        {
            NativeEndOverlappedTask(domain, timestamp, taskId);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_counter_create")]
		private static extern IntPtr NativeCreateCounter(IntPtr domain, IntPtr name);

		protected override IntPtr CreateCounter(IntPtr domain, IntPtr name)
        {
            return NativeCreateCounter(domain, name);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_set_counter")]
		private static extern void NativeSetCounter(IntPtr id, double value, ulong timestamp);

		public override void SetCounter(IntPtr id, double value, ulong timestamp)
        {
            NativeSetCounter(id, value, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_create_track")]
		private static extern IntPtr NativeCreateTrack(string group, string track);

		public override IntPtr CreateTrack(string group, string track)
        {
            return NativeCreateTrack(group, track);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_set_track")]
		private static extern void NativeSetTrack(IntPtr track);

		public override void SetTrack(IntPtr track)
        {
            NativeSetTrack(track);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_get_timestamp")]
		private static extern ulong NativeGetTimeStamp();

		public override ulong GetTimeStamp()
        {
            return NativeGetTimeStamp();
        }
	}

	internal class libIntelSEAPI64Native : NativeBase
    {
		private const string NativeLibraryName = "libIntelSEAPI64";
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_create_domain")]
		private static extern IntPtr NativeCreateDomain(string name);

		public override IntPtr CreateDomain(string name)
        {
            return NativeCreateDomain(name);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_create_string")]
		private static extern IntPtr NativeCreateString(string name);

		protected override IntPtr CreateString(string name)
        {
            return NativeCreateString(name);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_marker")]
		private static extern void NativeMarker(IntPtr domain, ulong id, IntPtr name, int scope, ulong timestamp);

		protected override void Marker(IntPtr domain, ulong id, IntPtr name, int scope, ulong timestamp)
        {
            NativeMarker(domain, id, name, scope, timestamp);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_task_begin")]
		private static extern void NativeBeginTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp);

		protected override void BeginTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp)
        {
            NativeBeginTask(domain, id, parent, name, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_task_begin_overlapped")]
		private static extern void NativeBeginOverlappedTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp);

		protected override void BeginOverlappedTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp)
        {
            NativeBeginOverlappedTask(domain, id, parent, name, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_metadata_add")]
		private static extern void NativeAddMetadata(IntPtr domain, ulong id, IntPtr name, double value);

		protected override void AddMetadata(IntPtr domain, ulong id, IntPtr name, double value)
        {
            NativeAddMetadata(domain, id, name, value);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_metadata_add_str")]
		private static extern void NativeAddStringMetadata(IntPtr domain, ulong id, IntPtr name, string value);

		protected override void AddStringMetadata(IntPtr domain, ulong id, IntPtr name, string value)
        {
            NativeAddStringMetadata(domain, id, name, value);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_metadata_add_blob")]
		private static extern void NativeAddBlobMetadata(IntPtr domain, ulong id, IntPtr name, IntPtr value, uint size);

		protected override void AddBlobMetadata(IntPtr domain, ulong id, IntPtr name, IntPtr value, uint size)
        {
            NativeAddBlobMetadata(domain, id, name, value, size);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_task_end")]
		private static extern void NativeEndTask(IntPtr domain, ulong timestamp);

		public override void EndTask(IntPtr domain, ulong timestamp)
        {
            NativeEndTask(domain, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_task_end_overlapped")]
		private static extern void NativeEndOverlappedTask(IntPtr domain, ulong timestamp, ulong taskId);

		public override void EndOverlappedTask(IntPtr domain, ulong timestamp, ulong taskId)
        {
            NativeEndOverlappedTask(domain, timestamp, taskId);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_counter_create")]
		private static extern IntPtr NativeCreateCounter(IntPtr domain, IntPtr name);

		protected override IntPtr CreateCounter(IntPtr domain, IntPtr name)
        {
            return NativeCreateCounter(domain, name);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_set_counter")]
		private static extern void NativeSetCounter(IntPtr id, double value, ulong timestamp);

		public override void SetCounter(IntPtr id, double value, ulong timestamp)
        {
            NativeSetCounter(id, value, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_create_track")]
		private static extern IntPtr NativeCreateTrack(string group, string track);

		public override IntPtr CreateTrack(string group, string track)
        {
            return NativeCreateTrack(group, track);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_set_track")]
		private static extern void NativeSetTrack(IntPtr track);

		public override void SetTrack(IntPtr track)
        {
            NativeSetTrack(track);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_get_timestamp")]
		private static extern ulong NativeGetTimeStamp();

		public override ulong GetTimeStamp()
        {
            return NativeGetTimeStamp();
        }
	}

	internal class libIntelSEAPINative : NativeBase
    {
		private const string NativeLibraryName = "libIntelSEAPI";
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_create_domain")]
		private static extern IntPtr NativeCreateDomain(string name);

		public override IntPtr CreateDomain(string name)
        {
            return NativeCreateDomain(name);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_create_string")]
		private static extern IntPtr NativeCreateString(string name);

		protected override IntPtr CreateString(string name)
        {
            return NativeCreateString(name);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_marker")]
		private static extern void NativeMarker(IntPtr domain, ulong id, IntPtr name, int scope, ulong timestamp);

		protected override void Marker(IntPtr domain, ulong id, IntPtr name, int scope, ulong timestamp)
        {
            NativeMarker(domain, id, name, scope, timestamp);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_task_begin")]
		private static extern void NativeBeginTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp);

		protected override void BeginTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp)
        {
            NativeBeginTask(domain, id, parent, name, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_task_begin_overlapped")]
		private static extern void NativeBeginOverlappedTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp);

		protected override void BeginOverlappedTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp)
        {
            NativeBeginOverlappedTask(domain, id, parent, name, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_metadata_add")]
		private static extern void NativeAddMetadata(IntPtr domain, ulong id, IntPtr name, double value);

		protected override void AddMetadata(IntPtr domain, ulong id, IntPtr name, double value)
        {
            NativeAddMetadata(domain, id, name, value);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_metadata_add_str")]
		private static extern void NativeAddStringMetadata(IntPtr domain, ulong id, IntPtr name, string value);

		protected override void AddStringMetadata(IntPtr domain, ulong id, IntPtr name, string value)
        {
            NativeAddStringMetadata(domain, id, name, value);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_metadata_add_blob")]
		private static extern void NativeAddBlobMetadata(IntPtr domain, ulong id, IntPtr name, IntPtr value, uint size);

		protected override void AddBlobMetadata(IntPtr domain, ulong id, IntPtr name, IntPtr value, uint size)
        {
            NativeAddBlobMetadata(domain, id, name, value, size);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_task_end")]
		private static extern void NativeEndTask(IntPtr domain, ulong timestamp);

		public override void EndTask(IntPtr domain, ulong timestamp)
        {
            NativeEndTask(domain, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_task_end_overlapped")]
		private static extern void NativeEndOverlappedTask(IntPtr domain, ulong timestamp, ulong taskId);

		public override void EndOverlappedTask(IntPtr domain, ulong timestamp, ulong taskId)
        {
            NativeEndOverlappedTask(domain, timestamp, taskId);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_counter_create")]
		private static extern IntPtr NativeCreateCounter(IntPtr domain, IntPtr name);

		protected override IntPtr CreateCounter(IntPtr domain, IntPtr name)
        {
            return NativeCreateCounter(domain, name);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_set_counter")]
		private static extern void NativeSetCounter(IntPtr id, double value, ulong timestamp);

		public override void SetCounter(IntPtr id, double value, ulong timestamp)
        {
            NativeSetCounter(id, value, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_create_track")]
		private static extern IntPtr NativeCreateTrack(string group, string track);

		public override IntPtr CreateTrack(string group, string track)
        {
            return NativeCreateTrack(group, track);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_set_track")]
		private static extern void NativeSetTrack(IntPtr track);

		public override void SetTrack(IntPtr track)
        {
            NativeSetTrack(track);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_get_timestamp")]
		private static extern ulong NativeGetTimeStamp();

		public override ulong GetTimeStamp()
        {
            return NativeGetTimeStamp();
        }
	}

}