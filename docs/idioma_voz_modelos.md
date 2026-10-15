# Idioma pt-BR, Ollama pelo painel, voz e múltiplos modelos

Tudo é opcional: sem configurar nada, o Jarvis se comporta como o original (francês,
um modelo por provedor, sem fallback, sem ajustes de voz).

## 1. Idioma (`assistant.langue: fr | pt`)

- Seletor **FR / PT-BR** no topo do painel, ou por voz: « fale em português » /
  « repasse en français » (ferramenta `changer_langue`).
- Em `pt`: o LLM responde em português do Brasil, o Whisper transcreve em `pt`, a voz
  (ElevenLabs, Piper `pt_BR`, Kokoro `pf_dora`, Windows) fala português e as
  confirmações entendem « sim / não / sempre ».
- Frases fixas do sistema (avisos de espera, anúncios de confirmação N2/N3, erros,
  orçamento) são traduzidas em `core/langue.py`.
- O painel é traduzido na tela (`web/pwa/i18n.js`), sem alterar o HTML original.
- Limitação: o texto bruto devolvido por uma ferramenta e lido **sem passar pelo
  LLM** (rotas diretas e resultado após confirmação) continua em francês quando não
  está no dicionário.

## 2. Ollama pelo painel (aba « Provedores IA »)

- **Detecção automática** ao abrir a aba: endereço configurado e, se não responder,
  `localhost` / `127.0.0.1` (o endereço é corrigido sozinho).
- **Instalar Ollama**: instalador oficial em segundo plano (winget no Windows,
  `ollama.com/install.sh` no Linux como root, Homebrew no macOS).
- **Iniciar Ollama** se estiver instalado mas parado.
- Seletor de modelos: instalados (✓), catálogo (⬇) ou qualquer nome digitado.
  Ao salvar/usar um modelo que não está instalado, o painel **pergunta se deseja
  instalar** e mostra o progresso do download.

## 3. Vários modelos por provedor + fallback

- **Favoritos** por provedor (`<provedor>.favoris`), com « usar » em um clique.
- Por voz: « troca para o Claude » / « usa o modelo local » (ferramenta
  `changer_modele_ia`, só entre favoritos).
- **Fallback** (`llm.repli_actif`, `llm.repli`): se o modelo principal falhar
  (erro, sem crédito, fora do ar), o Jarvis tenta os próximos, em ordem.
  No modo local, só entradas Ollama são usadas.

## 4. Voz

- **ElevenLabs**: estabilidade, similaridade, estilo/calor, velocidade e speaker
  boost (enviados apenas se definidos) e **clonagem da sua voz** por upload de
  amostras (até 25 MB), opcionalmente ativando-a como voz do Jarvis.
- **Voz local (Piper)**: baixar vozes do catálogo oficial (pt_BR e fr_FR), importar
  `.onnx` + `.onnx.json`, escolher, remover e ajustar velocidade e entonação.
  Kokoro: velocidade.
