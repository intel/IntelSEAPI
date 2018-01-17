using System;
using System.Runtime.InteropServices;

namespace SEAPI
{
	public class IntelSEAPI32Native : INative
    {
		private const string NativeLibraryName = "IntelSEAPI32";
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_create_domain")]
		private static extern IntPtr NativeCreateDomain(string name);

		public IntPtr CreateDomain(string name)
        {
            return NativeCreateDomain(name);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_create_string")]
		private static extern IntPtr NativeCreateString(string name);

		public IntPtr CreateString(string name)
        {
            return NativeCreateString(name);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_marker")]
		private static extern void NativeMarker(IntPtr domain, ulong id, IntPtr name, int scope, ulong timestamp);

		public void Marker(IntPtr domain, ulong id, IntPtr name, int scope, ulong timestamp)
        {
            NativeMarker(domain, id, name, scope, timestamp);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_task_begin")]
		private static extern void NativeBeginTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp);

		public void BeginTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp)
        {
            NativeBeginTask(domain, id, parent, name, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_task_begin_overlapped")]
		private static extern void NativeBeginOverlappedTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp);

		public void BeginOverlappedTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp)
        {
            NativeBeginOverlappedTask(domain, id, parent, name, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_metadata_add")]
		private static extern void NativeAddMetadata(IntPtr domain, ulong id, IntPtr name, double value);

		public void AddMetadata(IntPtr domain, ulong id, IntPtr name, double value)
        {
            NativeAddMetadata(domain, id, name, value);
        }
	}

	public class IntelSEAPI64Native : INative
    {
		private const string NativeLibraryName = "IntelSEAPI64";
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_create_domain")]
		private static extern IntPtr NativeCreateDomain(string name);

		public IntPtr CreateDomain(string name)
        {
            return NativeCreateDomain(name);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_create_string")]
		private static extern IntPtr NativeCreateString(string name);

		public IntPtr CreateString(string name)
        {
            return NativeCreateString(name);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_marker")]
		private static extern void NativeMarker(IntPtr domain, ulong id, IntPtr name, int scope, ulong timestamp);

		public void Marker(IntPtr domain, ulong id, IntPtr name, int scope, ulong timestamp)
        {
            NativeMarker(domain, id, name, scope, timestamp);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_task_begin")]
		private static extern void NativeBeginTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp);

		public void BeginTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp)
        {
            NativeBeginTask(domain, id, parent, name, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_task_begin_overlapped")]
		private static extern void NativeBeginOverlappedTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp);

		public void BeginOverlappedTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp)
        {
            NativeBeginOverlappedTask(domain, id, parent, name, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_metadata_add")]
		private static extern void NativeAddMetadata(IntPtr domain, ulong id, IntPtr name, double value);

		public void AddMetadata(IntPtr domain, ulong id, IntPtr name, double value)
        {
            NativeAddMetadata(domain, id, name, value);
        }
	}

	public class libIntelSEAPI32Native : INative
    {
		private const string NativeLibraryName = "libIntelSEAPI32";
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_create_domain")]
		private static extern IntPtr NativeCreateDomain(string name);

		public IntPtr CreateDomain(string name)
        {
            return NativeCreateDomain(name);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_create_string")]
		private static extern IntPtr NativeCreateString(string name);

		public IntPtr CreateString(string name)
        {
            return NativeCreateString(name);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_marker")]
		private static extern void NativeMarker(IntPtr domain, ulong id, IntPtr name, int scope, ulong timestamp);

		public void Marker(IntPtr domain, ulong id, IntPtr name, int scope, ulong timestamp)
        {
            NativeMarker(domain, id, name, scope, timestamp);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_task_begin")]
		private static extern void NativeBeginTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp);

		public void BeginTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp)
        {
            NativeBeginTask(domain, id, parent, name, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_task_begin_overlapped")]
		private static extern void NativeBeginOverlappedTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp);

		public void BeginOverlappedTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp)
        {
            NativeBeginOverlappedTask(domain, id, parent, name, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_metadata_add")]
		private static extern void NativeAddMetadata(IntPtr domain, ulong id, IntPtr name, double value);

		public void AddMetadata(IntPtr domain, ulong id, IntPtr name, double value)
        {
            NativeAddMetadata(domain, id, name, value);
        }
	}

	public class libIntelSEAPI64Native : INative
    {
		private const string NativeLibraryName = "libIntelSEAPI64";
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_create_domain")]
		private static extern IntPtr NativeCreateDomain(string name);

		public IntPtr CreateDomain(string name)
        {
            return NativeCreateDomain(name);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_create_string")]
		private static extern IntPtr NativeCreateString(string name);

		public IntPtr CreateString(string name)
        {
            return NativeCreateString(name);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_marker")]
		private static extern void NativeMarker(IntPtr domain, ulong id, IntPtr name, int scope, ulong timestamp);

		public void Marker(IntPtr domain, ulong id, IntPtr name, int scope, ulong timestamp)
        {
            NativeMarker(domain, id, name, scope, timestamp);
        }
		
		[DllImport(NativeLibraryName, EntryPoint = "itt_task_begin")]
		private static extern void NativeBeginTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp);

		public void BeginTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp)
        {
            NativeBeginTask(domain, id, parent, name, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_task_begin_overlapped")]
		private static extern void NativeBeginOverlappedTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp);

		public void BeginOverlappedTask(IntPtr domain, ulong id, ulong parent, IntPtr name, ulong timestamp)
        {
            NativeBeginOverlappedTask(domain, id, parent, name, timestamp);
        }

		[DllImport(NativeLibraryName, EntryPoint = "itt_metadata_add")]
		private static extern void NativeAddMetadata(IntPtr domain, ulong id, IntPtr name, double value);

		public void AddMetadata(IntPtr domain, ulong id, IntPtr name, double value)
        {
            NativeAddMetadata(domain, id, name, value);
        }
	}

}