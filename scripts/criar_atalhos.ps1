# Cria atalhos "Jarvis" e "Jarvis Painel" na Area de Trabalho e no Menu Iniciar,
# abrindo como aplicativo (janela propria, sem barra de endereco) via Edge ou Chrome.
# Uso: powershell -ExecutionPolicy Bypass -File scripts\criar_atalhos.ps1
$navs = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
          "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
          "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
          "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe")
$nav = $navs | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $nav) { Write-Host "Edge/Chrome nao encontrado." -ForegroundColor Red; exit 1 }
$raiz = Split-Path $PSScriptRoot -Parent
$shell = New-Object -ComObject WScript.Shell
$destinos = @([Environment]::GetFolderPath('Desktop'), (Join-Path ([Environment]::GetFolderPath('Programs')) ""))
$apps = @(@{Nome="Jarvis"; Url="http://127.0.0.1:8770/"}, @{Nome="Jarvis Painel"; Url="http://127.0.0.1:8790/panneau"})
foreach ($d in $destinos) {
  foreach ($a in $apps) {
    $lnk = $shell.CreateShortcut((Join-Path $d ($a.Nome + ".lnk")))
    $lnk.TargetPath = $nav
    $lnk.Arguments = "--app=" + $a.Url
    $lnk.WorkingDirectory = $raiz
    $lnk.Save()
  }
}
Write-Host "OK: atalhos criados na Area de Trabalho e no Menu Iniciar." -ForegroundColor Green
