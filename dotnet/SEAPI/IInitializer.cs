namespace SEAPI
{
    internal interface IInitializer
    {
        void Init();
        INative CreateNative();
    }
}