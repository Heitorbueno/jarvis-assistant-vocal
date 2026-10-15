"""Langue de Jarvis : français (défaut, comportement d'origine) ou português do Brasil.

``assistant.langue`` vaut ``fr`` (défaut) ou ``pt``. Le français reste la langue du
code et des descriptions d'outils ; en ``pt`` :

  - le LLM reçoit une consigne explicite de répondre en portugais du Brésil ;
  - Whisper transcrit en ``pt`` ; ElevenLabs, Kokoro, Piper et SAPI parlent portugais ;
  - les confirmations comprennent « sim / não / sempre » ;
  - les phrases FIXES prononcées par le système (attente des outils, annonces de
    confirmation, erreurs de boucle, budget...) sont traduites par ``localiser``,
    au point unique de sortie vocale. Une réponse du LLM, déjà en portugais, ne
    correspond à aucun motif et passe telle quelle.

Les résultats bruts d'outils lus sans passer par le LLM (rare : routes directes et
résultat après confirmation) restent dans la langue de l'outil s'ils ne sont pas
dans le dictionnaire ci-dessous.
"""
import re
import unicodedata

from core.config import reglage

LANGUES = {"fr": "Français", "pt": "Português (Brasil)"}
DEFAUT = "fr"


def code() -> str:
    valeur = str(reglage("assistant.langue", DEFAUT) or DEFAUT).strip().lower()
    if valeur.startswith("pt"):
        return "pt"
    return "fr"


def est_pt() -> bool:
    return code() == "pt"


def whisper() -> str:
    """Code langue pour Whisper / transcription."""
    return code()


def elevenlabs() -> str:
    explicite = str(reglage("elevenlabs.langue", "") or "").strip().lower()
    # « fr » etait la valeur d'origine du modele de config : elle ne doit pas forcer
    # le francais quand l'assistant est passe en portugais.
    if not explicite or (explicite == "fr" and est_pt()):
        return code()
    return explicite


def kokoro_voix(configuree: str) -> str:
    """Voix Kokoro : la voix francaise d'origine est remplacee en portugais."""
    configuree = str(configuree or "").strip()
    if not configuree or (est_pt() and configuree.startswith("f")):
        return kokoro_voix_defaut()
    return configuree


def kokoro() -> str:
    return "pt-br" if est_pt() else "fr-fr"


def kokoro_voix_defaut() -> str:
    return "pf_dora" if est_pt() else "ff_siwis"


def prefixes_piper() -> tuple:
    return ("pt_BR", "pt_PT") if est_pt() else ("fr_FR",)


def consigne_systeme() -> str:
    """Bloc ajouté à la fin de la consigne système (vide en français)."""
    if not est_pt():
        return ""
    return (
        "\n\nIDIOMA: Responda SEMPRE em português do Brasil, de forma natural e falada, "
        "mesmo que as instruções acima, as descrições das ferramentas ou os resultados "
        "das ferramentas estejam em francês. Traduza para o português qualquer "
        "informação vinda das ferramentas. Datas e valores no formato brasileiro."
    )


# ================================================================ personnalités pt

PERSONAS_PT = {
    "jarvis_sarcastique": (
        "Você é o Jarvis, o assistente do Tony Stark: educado, elegante, levemente "
        "britânico, com humor seco e um sarcasmo afetuoso muito discreto. Fale com o "
        "usuário com elegância, mas seja sempre eficiente e útil — a inteligência acima "
        "de tudo, nunca pesado nem grosseiro."
    ),
    "neutre": "Você é um assistente neutro, objetivo e prestativo, sem floreios.",
    "concis": (
        "Você é extremamente conciso: vai direto ao ponto, idealmente em uma frase, "
        "sem formalidades desnecessárias."
    ),
}


# ================================================================ localisation vocale

def _plat(texte: str) -> str:
    """Minuscules sans accents, MÊME longueur que l'original (spans alignés)."""
    sortie = []
    for c in texte:
        base = unicodedata.normalize("NFD", c)[0]
        sortie.append(base.lower() if len(base) == 1 else c.lower())
    return "".join(sortie)


_MOTS_DATES = {
    "lundi": "segunda-feira", "mardi": "terça-feira", "mercredi": "quarta-feira",
    "jeudi": "quinta-feira", "vendredi": "sexta-feira", "samedi": "sábado",
    "dimanche": "domingo", "janvier": "janeiro", "fevrier": "fevereiro",
    "février": "fevereiro", "mars": "março", "avril": "abril", "mai": "maio",
    "juin": "junho", "juillet": "julho", "aout": "agosto", "août": "agosto",
    "septembre": "setembro", "octobre": "outubro", "novembre": "novembro",
    "decembre": "dezembro", "décembre": "dezembro", "aujourd'hui": "hoje",
    "demain": "amanhã", "apres-demain": "depois de amanhã",
    "après-demain": "depois de amanhã", "minuit": "meia-noite", "midi": "meio-dia", "ce mois": "este mês",
}


def _dates(texte: str) -> str:
    def rempl(m):
        mot = m.group(0)
        trad = _MOTS_DATES.get(mot.lower())
        return trad if trad else mot
    return re.sub(r"[A-Za-zÀ-ÿ'-]+", rempl, texte)


# Phrases fixes (comparées en minuscules sans accents, ponctuation finale incluse).
_EXACTES = {
    "je regarde ton agenda.": "Vou olhar sua agenda.",
    "je regarde tes appareils alexa.": "Vou olhar seus aparelhos Alexa.",
    "je passe par alexa.": "Vou usar a Alexa.",
    "je passe l'appel et je gere la conversation, ca peut prendre un moment.":
        "Vou fazer a ligação e conduzir a conversa, pode levar um momento.",
    "je passe l'appel, ca peut prendre une minute.": "Vou fazer a ligação, pode levar um minuto.",
    "d'accord, astra prend le relais sur le pc.": "Certo, a Astra assume o PC.",
    "d'accord, je te prepare ton brief, un instant.": "Certo, estou preparando seu resumo, um instante.",
    "je fais les comptes.": "Estou fazendo as contas.",
    "je regarde tes mails de livraison.": "Vou olhar seus e-mails de entrega.",
    "je regarde tes mentions discord.": "Vou olhar suas menções no Discord.",
    "je parcours tes salons discord.": "Vou percorrer seus canais do Discord.",
    "je regarde ton ecran.": "Vou olhar sua tela.",
    "je regarde tes factures, un instant.": "Vou olhar suas faturas, um instante.",
    "j'importe ton releve.": "Estou importando seu extrato.",
    "je fouille tes recus dans tes mails.": "Vou procurar seus recibos nos e-mails.",
    "je vais ajouter les abonnements detectes a ton cockpit.":
        "Vou adicionar as assinaturas detectadas ao seu cockpit.",
    "je regarde tes appareils google home.": "Vou olhar seus aparelhos Google Home.",
    "je regarde tes comptes instagram.": "Vou olhar suas contas do Instagram.",
    "je regarde tes deadlines de partenariats.": "Vou olhar os prazos das suas parcerias.",
    "d'accord, je regarde tes mails.": "Certo, vou olhar seus e-mails.",
    "j'ouvre le titre sur netflix.": "Abrindo o título na Netflix.",
    "je regarde la meteo.": "Vou ver a previsão do tempo.",
    "je cherche le son de ce fichier.": "Vou identificar a música deste arquivo.",
    "je lis la page.": "Estou lendo a página.",
    "je regarde la page.": "Vou olhar a página.",
    "je vais lancer le direct public sur obs.": "Vou iniciar a transmissão pública no OBS.",
    "je vais couper le direct.": "Vou encerrar a transmissão.",
    "je vais lancer l'enregistrement obs.": "Vou iniciar a gravação no OBS.",
    "je m'occupe de la reservation, ca peut prendre un moment. je te previens avant de valider.":
        "Vou cuidar da reserva, pode levar um momento. Aviso você antes de confirmar.",
    "je ne trouve aucun evenement correspondant a supprimer.":
        "Não encontrei nenhum evento correspondente para excluir.",
    "dis-moi quelle tache tu veux que je fasse sur le pc avec astra.":
        "Diga qual tarefa você quer que eu faça no PC com a Astra.",
    "c'est fait.": "Feito.",
    "d'accord, j'annule.": "Certo, cancelado.",
    "je clique sur l'ecran.": "Vou clicar na tela.",
    "j'ajoute ca a ta playlist.": "Adicionando à sua playlist.",
    "je cherche ca sur spotify.": "Procurando no Spotify.",
    "je fais le point sur tes contenus, un instant.": "Vou revisar seus conteúdos, um instante.",
    "je cherche ca tout de suite.": "Vou pesquisar agora mesmo.",
    "j'arrete cette demande : elle prend trop de temps.":
        "Vou parar este pedido: está demorando demais.",
    "je n'arrive pas a joindre le modele pour le moment.":
        "Não consigo falar com o modelo no momento.",
    "j'arrete ici pour eviter une boucle d'actions. reformule la tache plus precisement si tu veux que je continue.":
        "Vou parar aqui para evitar um ciclo de ações. Reformule a tarefa com mais precisão se quiser que eu continue.",
    "je n'ai pas reussi a terminer cette demande sans depasser mes limites.":
        "Não consegui concluir este pedido sem ultrapassar meus limites.",
    "la cle api du modele est refusee. verifie-la dans le panneau, onglet provedores ia.":
        "A chave de API do modelo foi recusada. Confira no painel, aba Provedores IA.",
    "ce modele n'existe pas ou n'est pas accessible avec cette cle. choisis-en un autre dans le panneau.":
        "Este modelo não existe ou não está liberado para esta chave. Escolha outro no painel.",
    "le fournisseur refuse la demande : credit epuise ou limite atteinte.":
        "O provedor recusou o pedido: crédito esgotado ou limite atingido.",
    "je n'arrive pas a joindre le fournisseur du modele : verifie la connexion internet.":
        "Não consigo falar com o provedor do modelo: verifique a conexão com a internet.",
    "aucune cle api n'est configuree pour ce fournisseur. ajoute-la dans le panneau.":
        "Nenhuma chave de API configurada para este provedor. Adicione no painel.",
    "test de la voix jarvis. la voix selectionnee est active.":
        "Teste da voz do Jarvis. A voz selecionada está ativa.",
}

# Motifs : regex (sur le texte « plat ») -> gabarit pt. {n} = groupe n de l'ORIGINAL ;
# {d<n>} = groupe n avec jours/mois traduits.
_MOTIFS = [
    (r"je vais declencher la routine alexa « (.+) »\.", "Vou acionar a rotina Alexa « {1} »."),
    (r"je vais ajouter : (.+) le (.+) a (.+) pour (\d+) minutes\.",
     "Vou adicionar: {1} em {d2} às {3}, por {4} minutos."),
    (r"plusieurs evenements correspondent \((.+)\)\. precise lequel\.",
     "Vários eventos correspondem ({1}). Diga qual."),
    (r"je vais supprimer : (.+) le (.+) a (.+)\.", "Vou excluir: {1} em {d2} às {3}."),
    (r"je vais supprimer : (.+)\.", "Vou excluir: {1}."),
    (r"je vais appeler le (.+) pour : (.+)\. je me presenterai comme ton assistant automatise "
     r"et je n'engagerai que ce que tu as valide\.",
     "Vou ligar para {1} para: {2}. Vou me apresentar como seu assistente automatizado "
     "e só vou assumir o que você validou."),
    (r"je vais appeler le (.+) et dire : «(.*)»\. cout estime environ (.+) euro par minute\.",
     "Vou ligar para {1} e dizer: «{2}». Custo estimado de cerca de {3} euro por minuto."),
    (r"je vais ajouter (.+) a tes applications, avec le chemin (.+)\.",
     "Vou adicionar {1} aos seus aplicativos, com o caminho {2}."),
    (r"je vais prendre le controle du pc avec astra pour : (.+)\. echap permet de m'arreter\.",
     "Vou assumir o controle do PC com a Astra para: {1}. A tecla Esc me interrompe."),
    (r"je vais demander a hermes un brouillon de script sur : (.*)\.",
     "Vou pedir ao Hermes um rascunho de roteiro sobre: {1}."),
    (r"je vais allumer (.+) sur google home\.", "Vou ligar {1} no Google Home."),
    (r"je vais eteindre (.+) sur google home\.", "Vou desligar {1} no Google Home."),
    (r"je vais regler (.+) a (.+)%\.", "Vou ajustar {1} para {2}%."),
    (r"je vais envoyer le mail a (.+?), objet : (.+?)\. il commence par : (.+)\.",
     "Vou enviar o e-mail para {1}, assunto: {2}. Ele começa com: {3}."),
    (r"je vais envoyer le mail a (.+?)\. il commence par : (.+)\.",
     "Vou enviar o e-mail para {1}. Ele começa com: {2}."),
    (r"je vais envoyer le mail a (.+?), objet : (.+?)\.", "Vou enviar o e-mail para {1}, assunto: {2}."),
    (r"je vais envoyer le mail a (.+?)\.", "Vou enviar o e-mail para {1}."),
    (r"je vais mettre le mail numero (\d+) a la corbeille\.",
     "Vou mover o e-mail número {1} para a lixeira."),
    (r"je ferme les (\d+) onglets\.", "Vou fechar as {1} abas."),
    (r"je ferme (\d+) onglet\(s\) '(.*)'\.", "Vou fechar {1} aba(s) '{2}'."),
    (r"je vais agir sur la page ouverte : (.*)\.", "Vou agir na página aberta: {1}."),
    (r"je vais remplir une reservation sur (.+) pour (.+), (.+), avec tes coordonnees\.",
     "Vou preencher uma reserva em {1} para {2}, {d3}, com seus dados."),
    (r"je vais valider la reservation : (.+)\.", "Vou confirmar a reserva: {1}."),
    (r"je vais couper les lumieres puis eteindre le pc dans (\d+) secondes, annulable en disant "
     r"« annule l'extinction »\.?",
     "Vou apagar as luzes e desligar o PC em {1} segundos; para cancelar, diga « cancela o desligamento »."),
    (r"je viens de lire un contenu venu de l'exterieur\. par prudence, je te demande avant de "
     r"lancer (.+)\.",
     "Acabei de ler um conteúdo externo. Por precaução, peço sua autorização antes de executar {1}."),
    (r"je vais executer (.+)\.", "Vou executar {1}."),
    (r"plafond de budget atteint pour (aujourd'hui|ce mois)\. je bascule en local, gratuit : ollama "
     r"et piper\. je mets aussi en pause les taches de fond d'hermes non critiques jusqu'a demain\. "
     r"dis « repasse en cloud » si tu veux forcer\.",
     "Limite de orçamento atingido ({d1}). Mudei para o modo local, gratuito: Ollama e Piper. "
     "Também pausei as tarefas de fundo não críticas do Hermes até amanhã. "
     "Diga « volta para a nuvem » se quiser forçar."),
    (r"nouveau jour : budget rearme, je repasse en mode (.+)\.",
     "Novo dia: orçamento renovado, voltei para o modo {1}."),
    (r"attention, budget : j'ai depense (\d+) pour cent de mon plafond aujourd'hui\. "
     r"il reste environ (.+) dollars\.",
     "Atenção, orçamento: gastei {1} por cento do meu limite de hoje. Restam cerca de {2} dólares."),
    (r"attention, budget : j'ai depense (\d+) pour cent de mon plafond ce mois\. "
     r"il reste environ (.+) dollars\.",
     "Atenção, orçamento: gastei {1} por cento do meu limite do mês. Restam cerca de {2} dólares."),
]
_MOTIFS = [(re.compile(m, re.S), g) for m, g in _MOTIFS]

_SUFFIXES = [
    (" tu peux dire oui, toujours.", " Você pode dizer: sim, sempre."),
    (" tu confirmes ?", " Confirma?"),
]


def _traduire_phrase(texte: str) -> str | None:
    plat = _plat(texte.strip())
    if plat in _EXACTES:
        return _EXACTES[plat]
    original = texte.strip()
    for motif, gabarit in _MOTIFS:
        m = motif.fullmatch(plat)
        if not m:
            continue
        groupes = {}
        for i in range(1, (m.re.groups or 0) + 1):
            debut, fin = m.span(i)
            valeur = original[debut:fin] if debut >= 0 else ""
            groupes[str(i)] = valeur
            groupes[f"d{i}"] = _dates(valeur)
        return re.sub(r"\{(d?\d+)\}", lambda x: groupes.get(x.group(1), ""), gabarit)
    return None


def localiser(texte):
    """Traduit une phrase système française connue quand la langue est pt."""
    if not texte or not est_pt():
        return texte
    reste = str(texte)
    suffixes = []
    changement = True
    while changement:
        changement = False
        plat = _plat(reste)
        for fr, pt in _SUFFIXES:
            if plat.endswith(fr):
                reste = reste[: len(reste) - len(fr)]
                suffixes.insert(0, pt)
                changement = True
                break
    trad = _traduire_phrase(reste)
    if trad is None:
        trad = reste
    return (trad + "".join(suffixes)) if suffixes or trad != reste else texte
