No matter what operating system you are using, test that the executable file runs properly when using it for the first time.
Test method:
For Linux and Mac systems, execute ./psacd_linux or ./psacd_mac in the current directory. If it prompts that the libc++.so library is missing, it means that you need to configure the libc++ library environment variable.
In Windows systems, directly double-click psacd_win10. If there is an error pop-up window, it means that relevant library dependencies need to be added. You can add the provided libc++.dll and libunwind.dll to the path C:/Windows/System32