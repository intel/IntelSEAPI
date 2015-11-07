package IntelSEA;
public final class IntelSEA
{
    static {
        System.loadLibrary("IntelSEA"); //sort out with bitness here
    }
    
    private native static uint64 createDomain(String name);
    private native static uint64 createString(String name); //for names
	private native static void beginTask(uint64 domain, uint64 name, uint64 id, uint64 parent);
	private native static void endTask(uint64 domain);
	private native static void counter(uint64 domain, uint64 name, double value);
    private native static void marker(uint64 domain, uint64 name, uint64 scope);
};

//domain and string ids
//returning task as object
//having counter as object

//see for example: /Users/aaraud/Perforce/gpa/mainline/SystemAnalyzer/PackageInfo/src/com/intel/gpa/packageinfo/SystemView.java

