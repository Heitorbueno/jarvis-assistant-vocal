/* Traduction de l'interface du panneau/cockpit selon assistant.langue (fr | pt).
   Non invasif : le HTML d'origine reste en français ; en pt, les textes connus sont
   remplacés à l'affichage (y compris ceux générés ensuite par le JS, via un
   MutationObserver). Les onglets ajoutés en portugais repassent en français en fr. */
(function () {
  const langue = (document.documentElement.dataset.langue || 'fr').toLowerCase();

  // Français -> Português (expressions les plus longues d'abord à l'application).
  const FR_PT = {
    "Jarvis — Panneau de configuration": "Jarvis — Painel de configuração",
    "Modèles": "Modelos", "Réglages": "Ajustes", "État": "Status", "Permissions": "Permissões",
    "Matériel": "Hardware", "Modèle actif par backend": "Modelo ativo por backend",
    "Modèles cloud OpenAI": "Modelos de nuvem OpenAI",
    "Modèle": "Modelo", "Capacités": "Recursos", "Prix API / 1M tokens": "Preço API / 1M tokens",
    "Activer": "Ativar", "Activé": "Ativado", "Actif": "Ativo", "actif": "ativo",
    "L'abonnement ChatGPT et la facturation API sont séparés. La clé reste uniquement dans":
      "A assinatura ChatGPT e a cobrança da API são separadas. A chave fica somente em",
    "Modèles LLM locaux (Ollama)": "Modelos LLM locais (Ollama)",
    "Badges": "Selos", "Taille": "Tamanho",
    "Modèles Whisper (transcription)": "Modelos Whisper (transcrição)",
    "Les tests du panneau utilisent le CPU pour rester portables ; l'exécution réelle dépend de la configuration.":
      "Os testes do painel usam a CPU para serem portáveis; a execução real depende da configuração.",
    "Mode de routage": "Modo de roteamento", "Où réfléchit Jarvis": "Onde o Jarvis pensa",
    "Local = hors ligne. Hybride = modèle quotidien économique du fournisseur choisi + Hermes pour le fond. Qualité = modèle puissant séparé.":
      "Local = offline. Híbrido = modelo diário econômico do provedor escolhido + Hermes para tarefas longas. Qualidade = modelo potente separado.",
    "Hybride": "Híbrido", "Qualité": "Qualidade",
    "Le profil hybride mémorise le fournisseur et son modèle quotidien : Luna chez OpenAI et Haiku chez Claude par défaut. Un choix manuel reste prioritaire.":
      "O perfil híbrido memoriza o provedor e seu modelo diário: Luna na OpenAI e Haiku na Claude por padrão. Uma escolha manual tem prioridade.",
    "Microphone": "Microfone", "Entrée utilisée pour t'écouter.": "Entrada usada para te ouvir.",
    "Haut-parleur": "Alto-falante", "Sortie pour la voix de Jarvis.": "Saída para a voz do Jarvis.",
    "Voix de Jarvis": "Voz do Jarvis", "Moteur vocal": "Motor de voz",
    "Auto choisit ElevenLabs en cloud et Piper en local. Le mode local reste intégralement local.":
      "Auto escolhe ElevenLabs na nuvem e Piper no local. O modo local continua 100% local.",
    "Voix ElevenLabs": "Voz ElevenLabs", "Vérification du compte…": "Verificando a conta…",
    "Modèle ElevenLabs": "Modelo ElevenLabs",
    "Flash = faible latence pour la conversation.": "Flash = baixa latência para conversa.",
    "Tester la voix": "Testar a voz", "Voix & écoute": "Voz e escuta",
    "Personnalité": "Personalidade", "Le ton des réponses.": "O tom das respostas.",
    "Durée d'écoute enchaînée": "Tempo de escuta contínua",
    "Secondes où Jarvis continue d'écouter après une réponse (sans redire le mot d'activation).":
      "Segundos em que o Jarvis continua ouvindo após uma resposta (sem repetir a palavra de ativação).",
    "Mot d'activation": "Palavra de ativação", "Phrase": "Frase",
    "Modèle openWakeWord embarqué.": "Modelo openWakeWord embutido.",
    "Sensibilité": "Sensibilidade",
    "Bas = se déclenche facilement (plus de faux positifs). Haut = strict.":
      "Baixo = dispara facilmente (mais falsos positivos). Alto = rigoroso.",
    "Ces réglages s'écrivent dans": "Estes ajustes são gravados em",
    "redémarre Jarvis": "reinicie o Jarvis", "pour les appliquer.": "para aplicá-los.",
    "Chaîne Jarvis ↔ Hermes": "Cadeia Jarvis ↔ Hermes", "Rafraîchir": "Atualizar",
    "Reconnecter MCP (remède parking)": "Reconectar MCP",
    "Budget par fournisseur": "Orçamento por provedor",
    "File de tâches Hermes": "Fila de tarefas do Hermes", "Chargement…": "Carregando…",
    "Activité Hermes": "Atividade do Hermes",
    "Périmètre en un coup d'œil": "Perímetro em um relance",
    "Accès fichiers d'Hermes (Docker, montages)": "Acesso a arquivos do Hermes (Docker, montagens)",
    "Outils & garde-fous": "Ferramentas e proteções", "Outil": "Ferramenta", "Niveau": "Nível",
    "Exposé MCP": "Exposto no MCP", "Confirmation": "Confirmação", "Rôle": "Função",
    "N1 sûr": "N1 seguro", "N2 sensible": "N2 sensível", "N3 critique": "N3 crítico",
    "local + iPhone": "local + iPhone", "confirmation, mémorisable": "confirmação, memorizável",
    "jamais mémorisable, jamais à distance": "nunca memorizável, nunca remoto",
    "Aucune voix disponible": "Nenhuma voz disponível",
    "Sortie par défaut de Windows": "Saída padrão do Windows",
    "Voix actuellement configurée": "Voz configurada atualmente",
    "CPU seulement": "Somente CPU", "aucun GPU NVIDIA": "nenhuma GPU NVIDIA",
    "VRAM totale": "VRAM total", "exploitable (LLM)": "utilizável (LLM)",
    "tient en VRAM": "cabe na VRAM", "VRAM juste": "VRAM no limite",
    "français fiable": "francês confiável", "français faible": "francês fraco",
    "API OpenAI connectée.": "API OpenAI conectada.",
    "Clé absente dans config.yaml.": "Chave ausente no config.yaml.",
    "Clé API absente : ajoute": "Chave de API ausente: adicione", "dans config.yaml.": "no config.yaml.",
    "Aucun cron.": "Nenhum cron.", "Aucun montage détecté.": "Nenhuma montagem detectada.",
    "Aucune délégation.": "Nenhuma delegação.", "Crons planifiés": "Crons agendados",
    "Derniers runs de cron": "Últimas execuções de cron",
    "Tâches (kanban) en cours": "Tarefas (kanban) em andamento",
    "outils au total": "ferramentas no total", "exposés à Hermes (MCP)": "expostas ao Hermes (MCP)",
    "Les changements LLM et de mode prennent effet au prochain tour, sans redémarrage.":
      "Mudanças de LLM e de modo valem na próxima interação, sem reiniciar.",
    "Règle N3 (verrouillée dans le code)": "Regra N3 (travada no código)",
    "Installer": "Instalar", "Supprimer": "Remover", "Tester": "Testar", "installé": "instalado",
    "Révoquer": "Revogar", "lecture seule": "somente leitura", "accès refusé": "acesso negado",
    "non autorisé": "não autorizado", "Voix": "Voz",
    "Enregistre. Redemarre Jarvis pour l'appliquer.": "Salvo. Reinicie o Jarvis para aplicar.",
    "Voix activee pour la prochaine reponse.": "Voz ativada para a próxima resposta.",
    "Test vocal lance.": "Teste de voz iniciado.",
    "Abonnements": "Assinaturas", "Finances": "Finanças", "Cockpit": "Cockpit",
    // HUD (reacteur)
    "Systeme": "Sistema", "Modele": "Modelo", "Ecoute": "Escuta", "Niveau": "Nível",
    "Routage": "Roteamento", "Budget": "Orçamento", "Hors ligne": "Offline", "En ligne": "Online",
    "VEILLE": "EM ESPERA", "ECOUTE": "OUVINDO", "REFLEXION": "PENSANDO", "PAROLE": "FALANDO",
    "MUET": "MUDO", "Vous": "Você", "au repos": "em repouso",
    "⏳ En attente de confirmation…": "⏳ Aguardando confirmação…",
    "🔇 Micro coupé": "🔇 Microfone mudo", "DÉMO — rien n'est réel": "DEMO — nada é real",
    "Commandes rapides": "Comandos rápidos",
    "Chargement de la configuration…": "Carregando configuração…",
    "Profil cloud & modèle": "Perfil de nuvem e modelo", "Fournisseur": "Provedor",
    "Activer hybride": "Ativar híbrido", "Activer qualité": "Ativar qualidade",
    "Hybride privilégie Luna chez OpenAI et Haiku chez Claude, sauf choix manuel.":
      "O híbrido prefere Luna na OpenAI e Haiku na Claude, salvo escolha manual.",
    "Modèle local": "Modelo local", "Moteur TTS": "Motor de voz",
    "Ouvrir le panneau complet →": "Abrir o painel completo →",
    "Écrire à Jarvis…": "Escreva para o Jarvis…", "Envoyer": "Enviar", "Chargement…": "Carregando…",
    "Ollama est hors ligne": "Ollama está offline", "Aucune voix chargée": "Nenhuma voz carregada",
    "Clé ElevenLabs absente": "Chave ElevenLabs ausente",
  };

  // Onglets ajoutés en portugais -> français quand la langue est fr.
  const PT_FR = {
    "Provedores IA": "Fournisseurs IA", "ElevenLabs": "ElevenLabs", "Acesso remoto": "Accès distant",
    "Provedores de IA": "Fournisseurs d'IA", "Testar conexão": "Tester la connexion",
    "Salvar": "Enregistrer", "Remover": "Supprimer", "Salvar modelo": "Enregistrer le modèle",
    "Usar como cérebro": "Utiliser comme cerveau", "Buscar modelo…": "Chercher un modèle…",
    "Buscar voz…": "Chercher une voix…", "Salvar voz/modelo": "Enregistrer voix/modèle",
    "Salvar e usar ElevenLabs": "Enregistrer et utiliser ElevenLabs",
    "Ouvir teste no PC": "Écouter un test sur le PC", "Gerar novo código": "Générer un nouveau code",
    "Salvar e ATIVAR": "Enregistrer et ACTIVER", "Desativar": "Désactiver", "Sair": "Déconnexion",
    "Hosts autorizados": "Hôtes autorisés", "Código de acesso": "Code d'accès",
    "Como expor (escolha um)": "Comment exposer (au choix)", "Idioma": "Langue",
    "obter chave ↗": "obtenir une clé ↗", "sem chave": "sans clé", "pode ser cérebro": "peut être cerveau",
    "conector": "connecteur", "ATIVO": "ACTIF", "Cole a chave de API": "Colle la clé API",
    "Modelos favoritos": "Modèles favoris", "Adicionar aos favoritos": "Ajouter aux favoris",
    "Ordem de fallback": "Ordre de repli", "Instalar Ollama": "Installer Ollama",
    "Iniciar Ollama": "Démarrer Ollama", "Ajustes da voz": "Réglages de la voix",
    "Clonar voz": "Cloner une voix", "Vozes locais (Piper)": "Voix locales (Piper)",
  };

  const dict = langue === 'pt' ? FR_PT : PT_FR;
  const chaves = Object.keys(dict).sort((a, b) => b.length - a.length);
  if (!chaves.length) return;
  if (langue === 'pt') document.title = document.title.replace('Panneau', 'Painel').replace('Accès', 'Acesso');

  function traduzir(txt) {
    if (!txt || !/[A-Za-zÀ-ÿ]/.test(txt)) return txt;
    const limpo = txt.trim();
    if (dict[limpo]) return txt.replace(limpo, dict[limpo]);
    let saida = txt;
    for (const k of chaves) {
      if (!saida.includes(k)) continue;
      if (k.length >= 12) { saida = saida.split(k).join(dict[k]); continue; }
      if (saida.length < 48) {   // mots courts : seulement en mot entier, dans un texte court
        const esc = k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        saida = saida.replace(new RegExp('(^|[^A-Za-zÀ-ÿ])' + esc + '(?=$|[^A-Za-zÀ-ÿ])', 'g'),
          (m, p) => p + dict[k]);
      }
    }
    return saida;
  }
  function percorrer(raiz) {
    const w = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT, {
      acceptNode: n => (n.parentElement && /^(SCRIPT|STYLE|TEXTAREA|CODE|PRE)$/.test(n.parentElement.tagName))
        ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT });
    const nos = []; while (w.nextNode()) nos.push(w.currentNode);
    for (const n of nos) { const t = traduzir(n.nodeValue); if (t !== n.nodeValue) n.nodeValue = t; }
    if (raiz.querySelectorAll) raiz.querySelectorAll('[placeholder],[title]').forEach(el => {
      for (const a of ['placeholder', 'title']) {
        const v = el.getAttribute(a); if (v) { const t = traduzir(v); if (t !== v) el.setAttribute(a, t); }
      }
    });
  }
  function iniciar() {
    percorrer(document.body);
    new MutationObserver(ms => {
      for (const m of ms) for (const n of m.addedNodes) {
        if (n.nodeType === 3) { const t = traduzir(n.nodeValue); if (t !== n.nodeValue) n.nodeValue = t; }
        else if (n.nodeType === 1) percorrer(n);
      }
    }).observe(document.body, { childList: true, subtree: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
  window.JARVIS_I18N = { langue, traduzir };
})();
