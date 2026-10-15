' Abre o Jarvis sem nenhuma janela de prompt (atalhos, link jarvis://, inicio automatico).
Dim alvo, pasta
alvo = "hud"
If WScript.Arguments.Count > 0 Then alvo = WScript.Arguments(0)
pasta = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
If LCase(alvo) = "completo" Then
  ' Inicio com o Windows : Jarvis + (se configurado) MCP/Hermes, tudo oculto.
  CreateObject("WScript.Shell").Run "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & _
    pasta & "\demarrer_jarvis_complet.ps1""", 0, False
Else
  CreateObject("WScript.Shell").Run "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & _
    pasta & "\abrir_jarvis.ps1"" -Alvo """ & alvo & """", 0, False
End If
