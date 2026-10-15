# Changelog

Toutes les évolutions notables de Jarvis. Format inspiré de
[Keep a Changelog](https://keepachangelog.com/fr/) ; versionnage
[SemVer](https://semver.org/lang/fr/).

## [Unreleased] — 2026-10-14

### Corrigé (retours terrain Windows)
- pt-BR : prompt système de base entièrement en portugais (`SYSTEME_BASE_PT`),
  reconstruit au changement de langue, filet de traduction si la réponse sort en français.
- « Oi Jarvis » seul : Jarvis répond « Pois não? » et réécoute au lieu de se taire.
- ElevenLabs : clé ID (64 hex) détectée et expliquée ; repli Piper puis SAPI signalé
  dans le panneau ; erreurs de clonage traduites (plan, permissions, limite).
- Instance unique (verrou socket) : un second lancement ramène la fenêtre.
- Lancement sans invite : `scripts/abrir_jarvis.vbs/.ps1`, raccourcis Bureau/Menu,
  protocole `jarvis://`, démarrage auto via raccourci caché ; page hors-ligne PWA
  avec bouton « Iniciar Jarvis ».
- Panneau : bouton « Voltar ao Jarvis » et « Criar atalhos ».

### Ajouté
- Accès distant authentifié au panneau (Tailscale Serve, Cloudflare Tunnel,
  proxy HTTPS) : hôtes déclarés, code d'accès PBKDF2, session HMAC, opt-in
  cockpit ; configuration modifiable en local uniquement (`core/acces_distant.py`).
- Route `/` (redirection panneau / connexion) et page `/acesso`.
- Onglets « Provedores IA » (clés en écriture seule, test de connexion, recherche
  et choix du modèle par fournisseur) et « ElevenLabs » (`core/provedores.py`).
- PWA (manifeste, service worker, icônes) pour desktop, Android et iOS (`core/pwa.py`).
- Docs `docs/acces_distant.md`, tests `tests/test_acces_distant.py`.

- Langue pt-BR sélectionnable (`assistant.langue`, `core/langue.py`) : réponses,
  Whisper, voix, confirmations « sim/não », phrases système, panneau traduit
  (`web/pwa/i18n.js`), outil vocal `changer_langue`.
- Ollama depuis le panneau (`core/ollama_gestion.py`) : détection automatique,
  installation officielle, démarrage, proposition d'installer un modèle absent.
- Favoris par fournisseur, outil vocal `changer_modele_ia` et repli (fallback)
  optionnel entre modèles (`core/llm.py`, `llm.repli`).
- Voix (`core/voix_gestion.py`) : réglages fins ElevenLabs, clonage par upload,
  voix Piper (catalogue, import, choix) et vitesse Piper/Kokoro.
- Docs `docs/idioma_voz_modelos.md`, tests `tests/test_langue_voix_modeles.py`.
- Démarrage automatique (Windows/systemd), chat HUD ouvert à la voix, prompt
  comportemental, diagnostic des erreurs du modèle, fenêtre HUD unique.
- Intégrations MCP (client) : GitHub, Git, Notion… avec confirmation N2 par défaut.
- Widgets du HUD (météo, change, bourse, actualités, YouTube, Spotify, Netflix, Prime).
- Module financier (`/financeiro`) : banques, contas a pagar/receber, récurrence,
  parcelles, flux de trésorerie projeté, import OFX + rapprochement, Open Finance
  (Pluggy, lecture seule), outils vocaux N2 (`docs/financeiro.md`).

### Modifié
- Serveur unifié : `proxy_headers=False` (adresse de socket réelle vérifiée).
- Installateur : plus aucune clé demandée ; Ollama installé nativement en mode local.

## [1.0.0] — 2026-08-07

Première version publique. Assistant vocal local en français, architecture
modulaire, deux modes (cloud / local hors ligne).

### Cœur
- Chaîne vocale : openWakeWord (« Hey Jarvis ») → faster-whisper (STT local) →
  LLM → synthèse vocale, avec fenêtre de suivi pour enchaîner sans redire le mot-clé.
- Architecture modulaire : chaque outil est un fichier de `tools/` auto-découvert
  (décorateur `@outil`), registre central, `config.yaml` unique non versionné.
- Confirmation vocale des actions irréversibles ; interruption « attends/stop »
  (barge-in anti-écho) ; accusé de réception immédiat pour les outils lents.
- Abstraction des providers (mode `cloud` | `local`) :
  - LLM : **Claude** (Anthropic) ou **Ollama** (`qwen3.5:4b`…), même interface.
  - TTS : **ElevenLabs** ou, en local, **Piper** / **Kokoro** (repli voix Windows).
  - STT : faster-whisper (local dans les deux modes, GPU si dispo).

### Outils
- Domotique : Philips Hue (allumer, luminosité, couleur), ambiances/scènes.
- PC & streaming : OBS (direct, enregistrement, scènes, replay), stats système,
  lancement d'apps, média/volume, capture d'écran (vision).
- Productivité : Google Agenda (tous les agendas, y compris iCal abonnés),
  Gmail, brief du matin, mémoire long terme, minuteurs, météo, personnalités.
- Présence : détection par ping du téléphone, modes automatiques.
- Web : recherche, réservation pilotée par LLM (Playwright), assistance sur le
  vrai Chrome (CDP) avec domaines protégés en lecture seule.
- Communication : Discord (mentions + messages du jour), Instagram (abonnés &
  vues vs la veille, multi-comptes, refresh auto des tokens), appels Twilio
  (message simple V1, conversation temps réel V2).
- Serveur MCP : expose les outils domotique/PC à tout client MCP (Claude Desktop,
  Hermes), liste blanche par outil.

### Confidentialité & sécurité
- Secrets et données perso jamais versionnés (config, mémoire, logs, transcriptions
  d'appels, tokens OAuth, profils navigateur).
- Appels téléphoniques : présentation honnête comme assistant automatisé ; jamais
  de données bancaires ni de mots de passe ; blocage des numéros surtaxés.

### Installation
- Installateur interactif `scripts/setup.py` et diagnostic `scripts/doctor.py`.
- `INSTALL_WITH_AI.md` (FR/EN) : guide agnostique pour installer via n'importe
  quelle IA gratuite.
- Documentation par intégration dans `docs/`, README FR (défaut) + EN.

[1.0.0]: https://github.com/sosoj92/jarvis-assistant-vocal/releases/tag/v1.0.0
