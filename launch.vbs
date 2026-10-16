Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strCurrentDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strCurrentDir
' Entorno aislado (.venv, modo seguro) o el Python del sistema que guardo install.ps1 (modo normal); sin ventana de consola
strPython = strCurrentDir & "\.venv\Scripts\pythonw.exe"
strSaved = strCurrentDir & "\.python-path"
If fso.FileExists(strSaved) Then
    Set f = fso.OpenTextFile(strSaved, 1)
    If Not f.AtEndOfStream Then strPython = Trim(f.ReadLine)
    f.Close
End If
WshShell.Run """" & strPython & """ main.py", 0, False
