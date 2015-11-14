start README.txt
wevtutil.exe um "%CD%\ETW\IntelSEAPI.man"
wevtutil.exe im "%CD%\ETW\IntelSEAPI.man" /rf:"%CD%\bin\IntelSEAPI32.dll" /mf:"%CD%\bin\IntelSEAPI32.dll"
