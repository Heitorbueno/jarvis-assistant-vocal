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

## 5. Iniciar com o computador, chat e prompt

- **Início automático** (painel › Ajustes, ou `uv run python scripts/autostart.py`):
  Windows usa o método original (`autostart_install.ps1`: tarefa agendada ou pasta
  Inicializar → `demarrer_jarvis_complet.ps1`, que não abre duas instâncias).
  Linux usa systemd: modo **completo** (serviço do usuário, com som) ou **servidor**
  (`--modo servidor`, root; LXC/servidor sem som: painel, acesso remoto e PWA via
  `scripts/jarvis_servidor.py`).
- **Janela duplicada ao dizer "Jarvis"**: a tradução automática do navegador renomeava
  a janela do HUD e ela não era encontrada. A página agora é `translate="no"`, o HUD
  é traduzido pelo próprio Jarvis e nenhuma janela nova abre enquanto uma página HUD
  estiver conectada.
- **Chat de texto**: oculto sempre; abre só por voz (« abre o chat ») e fecha pelo ×
  ou « fecha o chat ». A transcrição fica dentro dele, sem cobrir o reator.
- **Prompt comportamental** (painel › Ajustes): tom, como te chamar, contexto.
  Não altera confirmações N2/N3.
- **Instalar como app**: botão « Instalar app » no painel (Chrome/Edge); o HUD em
  `http://127.0.0.1:8770/` também é instalável. O instalador cria os atalhos
  « Jarvis » e « Jarvis Painel » (`scripts/criar_atalhos.ps1`).
- **Configuração**: continua só o `config.yaml` (não versionado, sem `.env`). Cada
  chave nova tem padrão no código, então atualizar nunca exige editar o arquivo.
  Gravação atômica com cópia em `config.yaml.bak`; `JARVIS_CONFIG=/caminho` permite
  outro local (LXC/serviço).
- **"Não consigo falar com o modelo"**: agora o Jarvis diz a causa (chave recusada,
  modelo inexistente, sem crédito, sem rede, chave ausente) e o painel mostra o
  último erro em Provedores IA.

## 6. Integrações MCP (GitHub, Git, Notion…)

Painel › **Integrações**: escolha um modelo pronto (GitHub oficial, Git local, Notion,
Arquivos) ou informe URL HTTP + cabeçalho de autenticação, ou um comando stdio
(`uvx`, `npx`). « Salvar e testar » lista as ferramentas do servidor.

- Cada ferramenta vira uma ferramenta do Jarvis (`mcp_<integração>__<ferramenta>`),
  usável por voz e pelo chat.
- **Segurança**: por padrão toda ferramenta pede confirmação de voz (N2). Marque
  apenas leituras como « sem confirmação » (N1). O resultado é tratado como conteúdo
  externo não confiável; nada é reexposto pelo MCP do Jarvis nem oferecido ao modelo
  local; adicionar/editar só no próprio PC; tokens nunca voltam ao navegador.
- O filtro de ferramentas por assunto agora entende português (antes, em pt, muitas
  frases ficavam sem ferramentas).

## 7. Widgets do HUD

Painel › **Widgets** funciona como loja: instalar/remover, coluna (esquerda/direita),
ordem e configuração. Os widgets ficam em colunas laterais calculadas a partir do
tamanho do reator: **nunca o cobrem**; em janela estreita somem sozinhos. Com o chat
aberto, a coluna esquerda dá lugar ao chat.

| Widget | Fonte | Atualização |
|---|---|---|
| Clima (agora + 3 dias) | Open-Meteo (gratuito, sem chave) | 10 min |
| Câmbio (USD, EUR, BTC…) | AwesomeAPI (gratuito, sem chave) | 2 min |
| Bolsa (Ibovespa, ações) | Yahoo Finance (não oficial) ou brapi.dev com token | 5 min |
| Notícias | RSS configurável (padrão g1) | 15 min |
| YouTube / Spotify | players oficiais incorporados | — |
| Netflix / Prime Video | atalho (os serviços bloqueiam player incorporado/DRM) | — |

Cada fonte tem cache e falha isolada (mostra o último valor como « offline »).
Por voz: « quanto está o dólar », « como está a bolsa », « quais as notícias »,
« esconde/mostra os widgets ». Ferramenta de clima corrigida: aceita a cidade pedida,
responde em português e não cai mais em Paris quando a localização falha.

**ElevenLabs**: o painel recusa o *ID* da chave (erro `api_key_id_used_as_api_key`);
use a chave que começa com `sk_`, exibida só ao criar/rotacionar.

## 8. Manutenção, primeiros passos e conversa

- **Primeiros passos** (topo do painel): checklist do que falta configurar (idioma,
  cérebro, voz, início automático, prompt, widgets, financeiro, acesso remoto), com
  botão que leva à aba certa. Some quando tudo estiver feito (ou em « ocultar »).
- **Manutenção** (somente no PC):
  - *Atualizar*: verifica novidades no GitHub e roda `git pull --ff-only` + `uv sync`
    (nunca força nem descarta alterações locais); depois, reinicie o Jarvis.
  - *Backup*: ZIP com config.yaml (chaves), memória, finanças, notas e calibrações.
    *Restaurar* só aceita ZIP gerado pelo Jarvis e só esses caminhos; o estado atual
    é salvo antes em `logs/antes-da-restauracao-*.zip`.
  - *Diagnóstico*: roda `scripts/doctor.py` e mostra o resultado.
  - *Logs*: últimas linhas de `logs/*.log`, com chaves e tokens mascarados.
- **Conversa**: últimas falas entre você e o Jarvis (também no acesso remoto
  autenticado); nada é gravado em disco.

## 9. Falar com o Jarvis pelo celular (PWA) — chat oculto

- Botão 🎤 no canto do painel/PWA: toque, fale, toque de novo (máx. 15 s). O áudio
  é transcrito pelo Whisper do PC e a resposta volta em texto e **em voz no próprio
  aparelho** (se houver voz configurada).
- O **chat de texto fica oculto**: só abre quando você diz « abre o chat » (e fecha
  com « fecha o chat » ou ×).
- Regra de acesso a distância (inalterada): executa só ferramentas seguras (N1
  expostas e a domótica liberada em `pont_iphone.domotique_distante`). Ações N2/N3
  (lançar conta, e-mail, ligação, desligar…) são recusadas: « faça pela voz em casa ».
- Gravar áudio exige contexto seguro: `http://127.0.0.1` no PC ou HTTPS (Tailscale,
  Cloudflare). Limite de 20 comandos por minuto.
- Corrigido: no celular o painel ficava mais largo que a tela (tabelas das abas
  Modelos e Permissões); agora elas rolam dentro do card.

## 10. Configurações (todas as integrações pelo painel)

Painel › **Configurações**: tudo o que antes era editado à mão no `config.yaml`, em
14 grupos (Assistente, Áudio, Casa inteligente, E-mail e agenda, Telefonia, Redes,
Música e transmissão, Hermes, Servidor/iPhone, Navegador, HUD/overlay, Orçamento,
Resumo da manhã, Gestos), com validação e botão **Testar** (Hue, Gmail, Twilio,
Discord, Spotify, OBS, Hermes — chamadas só de leitura).

- Senhas e tokens nunca voltam à tela (`••••1234`); deixe o campo como está para
  manter, « Remover » para apagar.
- Campos vazios ou iguais ao padrão não são gravados (o `config.yaml` fica limpo).
- Caminhos de executáveis/porta do painel só mudam no próprio PC.
- Credenciais do Google Agenda: envie o JSON OAuth pelo painel.
- « Ponte iPhone » tem botão **Gerar** token forte.
- Itens marcados « reinício » valem depois de reiniciar o Jarvis.

**ElevenLabs**: ao colar a chave (`sk_…`) ela é salva e as vozes da sua conta
aparecem na hora: primeiro **Minhas vozes** (clonadas, geradas, salvas da biblioteca),
depois as padrão, com descrição e botão ▶ Prévia. O ID da chave é recusado com
explicação.
