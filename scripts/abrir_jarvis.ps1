# Abre o Jarvis sem prompt : inicia o assistente em segundo plano (se ainda nao
# estiver rodando) e abre a interface pedida. Usado pelos atalhos, pelo link
# jarvis:// (botao do PWA quando o Jarvis esta desligado) e pelo inicio automatico.
#   -Alvo hud      : janela do reator (padrao)
#   -Alvo painel   : painel de configuracao
#   -Alvo iniciar  : so garante que o Jarvis esta rodando (inicio automatico)
param([string]$Alvo = "hud")
$ErrorActionPreference = "SilentlyContinue"
$raiz = Split-Path $PSScriptRoot -Parent
New-Item -ItemType Directory -Force "$raiz\logs" | Out-Null
function Log($m) { "$("{0:yyyy-MM-dd HH:mm:ss}" -f (Get-Date)) $m" | Add-Content "$raiz\logs\abrir_jarvis.log" }
function Escutando($porta) { [bool](Get-NetTCPConnection -State Listen -LocalPort $porta -ErrorAction SilentlyContinue) }

$Alvo = ($Alvo -replace '^jarvis:(//)?', '').Trim('/').ToLower()
if ($Alvo -notin @("hud", "painel", "iniciar")) { $Alvo = "hud" }

$rodando = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
           Where-Object { $_.CommandLine -match 'jarvis14\.py' }
$acabouDeIniciar = $false
if (-not $rodando) {
  $uv = "$env:USERPROFILE\.local\bin\uv.exe"
  if (-not (Test-Path $uv)) { $uv = (Get-Command uv -ErrorAction SilentlyContinue).Source }
  if (-not $uv) { Log "uv nao encontrado"; exit 1 }
  # Sem console : a saida vai para logs\jarvis-console.log (UTF-8, sem quebrar em acentos/emoji).
  $env:PYTHONIOENCODING = "utf-8"; $env:PYTHONUTF8 = "1"
  Start-Process $uv -ArgumentList "run", "python", "jarvis14.py" -WorkingDirectory $raiz -WindowStyle Hidden `
    -RedirectStandardOutput "$raiz\logs\jarvis-console.log" -RedirectStandardError "$raiz\logs\jarvis-console.err.log"
  Log "Jarvis iniciado (alvo $Alvo)"
  $acabouDeIniciar = $true
}
if ($Alvo -eq "iniciar") { exit 0 }

$porta = if ($Alvo -eq "painel") { 8790 } else { 8770 }
for ($i = 0; $i -lt 90 -and -not (Escutando $porta); $i++) { Start-Sleep -Milliseconds 700 }
# Ao iniciar, o proprio Jarvis abre a janela do reator : nao abrir uma segunda.
if ($acabouDeIniciar -and $Alvo -eq "hud") { exit 0 }

# Jarvis ja rodando + alvo hud : pede ao proprio Jarvis para trazer a janela existente
# (ou abrir uma, se foi fechada). Evita uma segunda janela do reator.
if ($Alvo -eq "hud") {
  try {
    Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8790/api/panneau/abrir-hud" -Body "{}" `
      -ContentType "application/json" -Headers @{ "X-Jarvis-Panneau" = "1" } -TimeoutSec 5 | Out-Null
    exit 0
  } catch { Log "abrir-hud indisponivel, abrindo janela diretamente" }
}
$url = if ($Alvo -eq "painel") { "http://127.0.0.1:8790/panneau" } else { "http://127.0.0.1:8770/" }
$navs = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
          "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
          "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
          "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe")
$nav = $navs | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($nav) { Start-Process $nav "--app=$url" } else { Start-Process $url }
