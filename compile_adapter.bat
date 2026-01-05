@echo off
set CSC="C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"

echo Compiling LegacyAdapter...
%CSC% /target:exe /out:src\legacy_adapter\bin\Debug\LegacyAdapter.exe ^
 /reference:src\legacy_adapter\bin\Debug\AnaliseCliente.dll ^
 /reference:src\legacy_adapter\bin\Debug\DadosColeta.dll ^
 /reference:src\legacy_adapter\bin\Debug\EntityFramework.dll ^
 /reference:src\legacy_adapter\bin\Debug\EntityFramework.SqlServer.dll ^
 /reference:src\legacy_adapter\bin\Debug\ManagerDB.dll ^
 /reference:System.dll ^
 /reference:System.Core.dll ^
 /reference:System.Data.dll ^
 /reference:System.Xml.dll ^
 /reference:System.Xml.Linq.dll ^
 /reference:Microsoft.CSharp.dll ^
 /reference:System.Net.Http.dll ^
 src\legacy_adapter\Program.cs

if %errorlevel% neq 0 (
    echo Compilation Failed!
    exit /b %errorlevel%
)

echo Compilation Success!
echo Copying config...
copy /Y "src\legacy_adapter\App.config" "src\legacy_adapter\bin\Debug\LegacyAdapter.exe.config"

echo Running Test...
src\legacy_adapter\bin\Debug\LegacyAdapter.exe 8945290 "captures/instagram_DS2gSufDT4i.png" content.txt 2025-12-29 54108 17847105 130374
