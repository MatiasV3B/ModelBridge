Set WshShell = CreateObject("WScript.Shell")
strCurrentDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strCurrentDir
' Entorno aislado creado por install.ps1 (uv); sin ventana de consola
WshShell.Run """" & strCurrentDir & "\.venv\Scripts\pythonw.exe"" main.py", 0, False
