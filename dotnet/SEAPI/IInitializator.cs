namespace SEAPI
{
    internal interface IInitializator
    {
        void Init();
        INative CreateNative();
    }
}