@echo off
set CSC="C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"
if exist obj rmdir /s /q obj
%CSC% /target:exe /out:LegacyAdapter.exe /reference:bin\Debug\EntityFramework.dll /reference:bin\Debug\EntityFramework.SqlServer.dll /reference:bin\Debug\ManagerDB.dll /reference:bin\Debug\DadosColeta.dll /reference:System.Data.dll /reference:System.Runtime.Serialization.dll /reference:System.Xml.Linq.dll /reference:System.Drawing.dll /reference:Microsoft.CSharp.dll Program.cs
if %errorlevel% neq 0 exit /b %errorlevel%
echo Compilation Successful.
copy LegacyAdapter.exe bin\Debug\LegacyAdapter.exe /Y
pause
