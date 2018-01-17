namespace SEAPI
{
    public interface IInitializator
    {
        void Init();
        INative CreateNative();
    }
}