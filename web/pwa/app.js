"use strict";
const indicator = document.getElementById("status-bullet");
const label = document.getElementById("api-status");
async function checkJarvis() {
  label.textContent = "Verificando conexão com o Jarvis…";
  indicator.className = "status-bullet";
  try {
    const response = await fetch("/api/ping", { cache: "no-store", credentials: "omit" });
    const data = response.ok ? await response.json() : null;
    if (!data || data.ok !== true || data.service !== "jarvis") {
      throw new Error("Resposta inesperada");
    }
    label.textContent = "Jarvis conectado · API disponível";
    indicator.className = "status-bullet online";
  } catch (_) {
    label.textContent = "Servidor indisponível. Verifique a conexão com o Tailscale.";
    indicator.className = "status-bullet offline";
  }
}
document.getElementById("refresh").addEventListener("click", checkJarvis);
checkJarvis();
window.setInterval(checkJarvis, 30000);
if ("serviceWorker" in navigator && window.isSecureContext) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}
