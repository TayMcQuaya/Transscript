' Silent launcher for Transscript — zero cmd/console flash.
' Tries `pythonw` on PATH first, falls back to a common install path.

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
appPath = scriptDir & "\transscript.py"

fallback = "C:\Python312\pythonw.exe"

On Error Resume Next
shell.Run """pythonw.exe"" """ & appPath & """", 0, False
If Err.Number <> 0 Then
    Err.Clear
    If fso.FileExists(fallback) Then
        shell.Run """" & fallback & """ """ & appPath & """", 0, False
    Else
        MsgBox "Could not find pythonw.exe on PATH or at " & fallback & _
               vbCrLf & "Install Python 3.10+ from python.org, then reinstall requirements.", _
               vbCritical, "Transscript launcher"
    End If
End If
