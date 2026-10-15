# Cria os atalhos « Jarvis » e « Jarvis Painel » (Area de Trabalho e Menu Iniciar) e
# registra o link jarvis:// (sem admin). Os atalhos INICIAM o Jarvis se ele estiver
# desligado — nada de abrir prompt e digitar « uv run python jarvis14.py ».
# Uso: powershell -ExecutionPolicy Bypass -File scripts\criar_atalhos.ps1
$raiz = Split-Path $PSScriptRoot -Parent
$vbs = Join-Path $PSScriptRoot "abrir_jarvis.vbs"
$wscript = Join-Path $env:WINDIR "System32\wscript.exe"
$icone = Join-Path $raiz "web\pwa\favicon.ico"
$shell = New-Object -ComObject WScript.Shell
$destinos = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))
$apps = @(@{Nome = "Jarvis"; Alvo = "hud"}, @{Nome = "Jarvis Painel"; Alvo = "painel"})
foreach ($d in $destinos) {
  foreach ($a in $apps) {
    $lnk = $shell.CreateShortcut((Join-Path $d ($a.Nome + ".lnk")))
    $lnk.TargetPath = $wscript
    $lnk.Arguments = "`"$vbs`" $($a.Alvo)"
    $lnk.WorkingDirectory = $raiz
    if (Test-Path $icone) { $lnk.IconLocation = $icone }
    $lnk.Save()
  }
}
# Link jarvis:// : o botao « Iniciar Jarvis » do PWA (quando o Jarvis esta desligado)
# chama este link, que inicia o Jarvis. Registro so do usuario atual (HKCU, sem admin).
$base = "HKCU:\Software\Classes\jarvis"
New-Item -Path $base -Force | Out-Null
Set-ItemProperty -Path $base -Name "(Default)" -Value "URL:Jarvis"
Set-ItemProperty -Path $base -Name "URL Protocol" -Value ""
New-Item -Path "$base\shell\open\command" -Force | Out-Null
Set-ItemProperty -Path "$base\shell\open\command" -Name "(Default)" -Value "`"$wscript`" `"$vbs`" `"%1`""
Write-Host "OK: atalhos criados e link jarvis:// registrado." -ForegroundColor Green
