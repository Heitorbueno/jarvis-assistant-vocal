# Installe le démarrage automatique de Jarvis à l'ouverture de session.
# Essaie d'abord une tâche planifiée (délai 30 s "propre", nécessite l'admin) ;
# sinon REPLI automatique sur le dossier Démarrage de Windows (sans admin).
#
# Usage :  powershell -ExecutionPolicy Bypass -File scripts\autostart_install.ps1
# Retrait : scripts\autostart_uninstall.ps1

$script = Join-Path $PSScriptRoot "demarrer_jarvis_complet.ps1"
$nom = "JarvisAutostart"
if (-not (Test-Path $script)) { Write-Host "Introuvable : $script" -ForegroundColor Red; exit 1 }

# --- 1) Tâche planifiée (login + 30 s). Nécessite des droits admin. ---
$tacheOk = $false
try {
  $action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
  $trigger = New-ScheduledTaskTrigger -AtLogOn
  $trigger.Delay = "PT10S"
  $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)
  Register-ScheduledTask -TaskName $nom -Action $action -Trigger $trigger `
    -Settings $settings -Description "Démarre la chaîne Hermes + le Jarvis vocal au login." `
    -Force -RunLevel Limited -ErrorAction Stop | Out-Null
  $tacheOk = $true
} catch {
  $tacheOk = $false
}

# Atalhos + link jarvis:// (o PWA consegue iniciar o Jarvis quando ele estiver desligado).
try { & (Join-Path $PSScriptRoot "criar_atalhos.ps1") | Out-Null } catch {}

if ($tacheOk) {
  Write-Host "OK : tâche planifiée « $nom » installée (login + 30 s)." -ForegroundColor Green
  Write-Host "Tester : Start-ScheduledTask -TaskName $nom"
  exit 0
}

# --- 2) Repli SANS admin : atalho OCULTO na pasta Inicializar (sem janela de prompt) ---
Write-Host "Tâche planifiée refusée (pas d'admin) -> atalho na pasta Inicializar." -ForegroundColor Yellow
$startup = [Environment]::GetFolderPath('Startup')
$antigo = Join-Path $startup "JarvisAutostart.cmd"
if (Test-Path $antigo) { Remove-Item $antigo -Force }      # versao antiga abria um prompt visivel
$lnkPath = Join-Path $startup "JarvisAutostart.lnk"
$sh = New-Object -ComObject WScript.Shell
$lnk = $sh.CreateShortcut($lnkPath)
$lnk.TargetPath = Join-Path $env:WINDIR "System32\wscript.exe"
$lnk.Arguments = "`"$(Join-Path $PSScriptRoot 'abrir_jarvis.vbs')`" completo"
$lnk.WorkingDirectory = Split-Path $PSScriptRoot -Parent
$ico = Join-Path (Split-Path $PSScriptRoot -Parent) "web\pwa\favicon.ico"
if (Test-Path $ico) { $lnk.IconLocation = $ico }
$lnk.Save()
if (Test-Path $lnkPath) {
  Write-Host "OK : início automático instalado (pasta Inicializar, sem admin, sem janela)." -ForegroundColor Green
  Write-Host "  -> $lnkPath"
} else {
  Write-Host "ECHEC : impossible d'écrire dans le dossier Démarrage." -ForegroundColor Red
  exit 1
}
