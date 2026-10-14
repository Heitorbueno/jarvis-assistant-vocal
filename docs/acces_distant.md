# Acesso remoto, provedores de IA e PWA

Por padrão o painel (`/panneau`) e o cockpit (`/cockpit`) continuam **somente
locais**. O acesso remoto só existe se você o ativar no próprio PC.

## Por que aparecia `{"detail":"Not Found"}` e HTTP 403

- `/` não tinha rota: agora redireciona para `/panneau` (local ou sessão válida)
  ou para `/acesso` (host remoto declarado).
- `core/http_local.requete_locale` recusa qualquer requisição com
  `X-Forwarded-For` ou com `Host` diferente de localhost. Tailscale Serve e
  cloudflared adicionam esses cabeçalhos: a proteção funciona como previsto.
  Ela **não foi enfraquecida**; foi adicionado um segundo caminho autenticado.

## Ativar (no PC, em `http://127.0.0.1:8790/panneau` → aba « Acesso remoto »)

1. Exponha a porta (escolha uma opção):
   - **Tailscale Serve** (privado, HTTPS automático): `tailscale serve --bg 8790`
     (`tailscale funnel --bg 8790` para internet pública).
   - **Cloudflare Tunnel**: `cloudflared tunnel --url http://127.0.0.1:8790`
     ou um túnel nomeado apontando o hostname para `http://127.0.0.1:8790`.
   - **IP público**: proxy HTTPS local (ex. Caddy `reverse_proxy 127.0.0.1:8790`)
     com domínio. Nunca exponha a porta 8790 sem TLS.
2. Em « Hosts autorizados », informe o nome HTTPS (ex. `jarvis-pc.tailXXXX.ts.net`).
3. Clique em « Gerar novo código » e anote-o (exibido uma única vez).
4. « Salvar e ATIVAR ».
5. No celular/desktop, abra `https://<host>/` → código → painel.

`serveur.actif: true` continua necessário para o servidor web iniciar.

## Segurança

- Requisição remota aceita somente se: acesso ativo + socket vinda do proxy local
  (ou de `acces_distant.reseaux`) + `Host` na lista + cookie de sessão HMAC
  (`HttpOnly`, `Secure`, `SameSite=Strict`).
- Escritas remotas exigem `Origin` HTTPS do mesmo host autorizado,
  `Content-Type: application/json` e `X-Jarvis-Panneau: 1`.
- Código salvo apenas como hash PBKDF2-SHA256; 5 erros/10 min por IP → bloqueio.
- Gerar novo código encerra todas as sessões.
- A configuração do acesso remoto só pode ser alterada **localmente**.
- `/cockpit` (finanças) remoto é opt-in separado (`acces_distant.cockpit`).
- HUD, gestos/câmera e regras N1/N2/N3 continuam locais e inalterados.
- O servidor roda com `proxy_headers=False` para que o endereço real da socket
  seja sempre verificado.

## Provedores de IA (aba « Provedores IA »)

OpenAI, Anthropic, Google Gemini, OpenRouter, Groq, DeepSeek, Mistral, xAI e
Ollama: salvar chave (nunca devolvida ao navegador), **Testar conexão** (lista os
modelos da conta, sem custo), buscar e salvar o modelo por provedor.
OpenAI, Anthropic e Ollama podem virar o cérebro do Jarvis (« Usar como
cérebro »); os outros ficam salvos em `<provedor>.cle` / `<provedor>.modele`
para conectores.

## ElevenLabs (aba « ElevenLabs »)

Chave, teste de conexão, busca/seleção de voz e modelo, botão para ativar o
motor ElevenLabs e teste de voz tocado no PC.

## PWA

Manifesto `/manifest.webmanifest`, service worker `/sw.js` (cacheia só ícones e
página offline; nunca `/api/*` nem páginas) e ícones em `web/pwa/`.
Instalação: Chrome/Edge/Android « Instalar app »; iPhone/iPad: Safari →
Compartilhar → « Adicionar à Tela de Início » (exige HTTPS: Tailscale/Cloudflare).

## Instalador

`INSTALLER_JARVIS.bat` não pede mais chave de API. Modo local instala o Ollama
nativamente (winget `Ollama.Ollama`) e baixa o modelo; chaves, modelos e voz são
configurados depois no painel.
