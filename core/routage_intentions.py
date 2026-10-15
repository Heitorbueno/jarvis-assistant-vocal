"""Décision commune des routes prioritaires et des domaines d'outils.

Ce module ne réalise aucune action : il choisit seulement le chemin. Le micro
principal et les satellites consomment ainsi exactement la même décision, sans
dupliquer les heuristiques Alexa/média/Astra/Hermes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re

from core.util import sans_accents

LOG = logging.getLogger("jarvis.routage_intentions")


@dataclass(frozen=True)
class Decision:
    """Route prioritaire à exécuter avant le LLM général."""

    type: str                         # "outil" | "vision" | "astra" | "hermes"
    outil: str = ""
    arguments: dict = field(default_factory=dict)
    tache: str = ""


def decider_prioritaire(phrase: str, piece: str = "") -> Decision | None:
    """Renvoie une route déterministe commune au PC et aux satellites."""
    phrase = str(phrase or "").strip()
    if not phrase:
        return None

    # Caméra/gestes : commandes locales explicites, avant toute interprétation
    # domotique ou média.
    try:
        from tools.gestes import (demande_calibration_gestes,
                                  demande_demo_gestes,
                                  demande_mode_regard,
                                  demande_mode_visio)
        regard = demande_mode_regard(phrase)
        visio = demande_mode_visio(phrase)
        if regard is True:
            return Decision("outil", "lancer_mode_regard")
        if regard is False:
            return Decision("outil", "quitter_mode_regard")
        if visio is True:
            return Decision("outil", "lancer_demo_gestes")
        if visio is False:
            return Decision("outil", "controler_gestes", {"actif": False})
        if demande_demo_gestes(phrase):
            return Decision("outil", "lancer_demo_gestes")
        if demande_calibration_gestes(phrase):
            return Decision("outil", "lancer_calibration_gestes")
    except Exception:
        LOG.exception("routage caméra et gestes")

    # Une invocation Astra explicite choisit l'outil sans passer par le LLM ;
    # elle ne vaut PAS autorisation : controle_pc_astra (N3) reste confirmé au
    # PC, et il est refusé depuis un satellite.
    try:
        from tools.astra_pc import extraire_commande_explicite
        tache = extraire_commande_explicite(phrase)
        if tache is not None:
            return Decision("astra", tache=tache)
    except Exception:
        LOG.exception("routage Astra explicite")

    if est_demande_vision_ecran(phrase):
        return Decision("vision", tache=phrase)

    for module, fonction in (
        ("tools.alexa", "router_commande"),
        ("tools.media", "router_commande_media"),
        ("tools.apps", "router_ouverture_simple"),
        ("tools.colis", "router_suivi"),
    ):
        try:
            mod = __import__(module, fromlist=[fonction])
            route = getattr(mod, fonction)(phrase, piece=piece)
            if route:
                nom, arguments = route
                return Decision("outil", nom, arguments or {})
        except Exception:
            LOG.exception("routage prioritaire %s", module)

    try:
        from tools.deleguer_a_hermes import extraire_tache_contenu
        tache = extraire_tache_contenu(phrase)
        if tache is not None:
            return Decision("hermes", tache=tache)
    except Exception:
        LOG.exception("routage Hermes contenu")

    return None


_REFERENCES_ECRAN = (
    "ecran", "affiche", "cette erreur", "ce message", "cette fenetre",
    "cette page", "ce texte", "ce qui est ouvert", "ce que tu vois",
)
_INTENTIONS_VISION = (
    "lis", "lire", "regarde", "voir", "decris", "decrire", "explique",
    "expliquer", "traduis", "traduire", "c est quoi", "qu est ce que",
    "que vois tu", "qu est ce qui",
)
_ACTIONS_ECRAN = (
    "clique", "double clique", "tape ", "saisis", "ouvre", "ferme", "deplace",
    "active", "desactive", "selectionne", "configure", "installe", "supprime",
)


def est_demande_vision_ecran(phrase: str) -> bool:
    """Vrai pour une lecture visuelle sans action sur l'interface."""
    p = " ".join(re.sub(
        r"[^a-z0-9]+", " ", sans_accents(str(phrase or "").lower())
    ).split())
    if any(action in p for action in _ACTIONS_ECRAN):
        return False
    return (any(ref in p for ref in _REFERENCES_ECRAN)
            and any(intent in p for intent in _INTENTIONS_VISION))


# Groupes utilisés uniquement pour réduire le catalogue d'outils transmis au
# LLM. Une action inconnue conserve le catalogue complet : le filtrage améliore
# les cas clairs sans rendre les formulations nouvelles impossibles.
_DOMAINES = (
    (("heure", "date", "minuteur", "chronometre", "alarme", "rappel"),
     {"temps", "notes"}),
    (("meteo", "temperature", "pleut", "pluie", "temps fait"), {"meteo"}),
    (("mail", "mails", "email", "emails", "courriel", "gmail"),
     {"mail", "factures", "brief"}),
    (("colis", "paquet", "livraison", "livraisons", "mes commandes", "ma commande"),
     {"colis", "mail"}),
    (("agenda", "calendrier", "rendez vous", "evenement", "deadline"),
     {"agenda", "loopstr", "suivi"}),
    (("spotify", "playlist", "musique", "chanson", "morceau", "netflix",
      "volume", "pause", "lecture", "piste", "sortie audio"),
     {"spotify", "media", "musique", "audio", "systeme"}),
    (("lumiere", "lampe", "hue", "amaran", "clim", "climatisation",
      "ventilateur", "prise", "alexa", "echo", "domotique"),
     {"lumieres", "amaran", "alexa", "google_home", "modes", "scenes"}),
    (("mode visio", "mode vision", "controle gestuel", "controle par gestes",
      "gestes visibles", "regarde mes mains", "webcam"), {"gestes"}),
    (("ecran", "fenetre", "souris", "clique", "clic", "ordinateur", " pc ",
      "application", "logiciel", "dossier", "telechargements", "parametre"),
     {"ecran", "souris", "apps", "systeme", "astra_pc", "gestes", "stats"}),
    (("chrome", "navigateur", "onglet", "site", "page web", "internet",
      "cherche sur le web", "recherche web", "reserve", "reservation"),
     {"navigateur", "web", "reservation"}),
    (("script", "hook", "accroche", "storyboard", "contenu", "video",
      "youtube", "tiktok", "reel", "publication", "inspiration"),
     {"contenu", "suivi", "deleguer_a_hermes"}),
    (("hermes", "recherche de fond", "analyse approfondie", "compare",
      "comparaison", "synthese", "veille"), {"deleguer_a_hermes", "web"}),
    (("discord", "mention", "salon discord"), {"discord_bot"}),
    (("instagram", "abonne", "followers", "vues"), {"instagram"}),
    (("appel", "appelle", "telephone", "raccroche"), {"appels", "appel_direct"}),
    (("obs", "stream", "direct", "replay", "scene"), {"obs", "scenes"}),
    (("memoire", "souviens", "rappelle toi", "oublie"), {"memoire"}),
    (("note", "notes", "idee", "pense bete"), {"notes"}),
    (("mode hybride", "mode qualite", "mode local", "mode cloud"),
     {"budget", "modes"}),
    (("budget", "cout", "depense", "consommation api"), {"budget"}),
    (("abonnement", "transaction", "releve", "finance"), {"finances", "factures"}),
    (("gpu", "cpu", "ram", "memoire vive", "statistiques pc"), {"stats"}),
    (("personnalite", "mode neutre", "mode concis", "sarcastique"),
     {"personnalite", "modes"}),
    (("presence", "je suis rentre", "je pars", "retour maison"),
     {"presence", "scenes"}),
)

# Equivalents portugais (assistant.langue = pt), fusionnes avec _DOMAINES : un
# domaine reconnu dans l'une ou l'autre langue donne les memes modules.
_DOMAINES_PT = (
    (("hora", "horas", "data", "cronometro", "alarme", "despertador", "lembrete", "timer"),
     {"temps", "notes"}),
    (("clima", "tempo vai", "previsao", "temperatura", "chuva", "chover"), {"meteo"}),
    (("email", "emails", "e mail", "e mails", "gmail", "caixa de entrada"),
     {"mail", "factures", "brief"}),
    (("encomenda", "pacote", "entrega", "rastreio", "meu pedido"), {"colis", "mail"}),
    (("agenda", "calendario", "compromisso", "reuniao", "evento", "prazo"),
     {"agenda", "loopstr", "suivi"}),
    (("spotify", "playlist", "musica", "cancao", "netflix", "volume", "pausa",
      "pausar", "proxima", "anterior", "toca", "tocar"),
     {"spotify", "media", "musique", "audio", "systeme"}),
    (("luz", "luzes", "lampada", "ar condicionado", "ventilador", "tomada", "alexa",
      "automacao"), {"lumieres", "amaran", "alexa", "google_home", "modes", "scenes"}),
    (("tela", "janela", "mouse", "clica", "clique", "computador", " pc ",
      "aplicativo", "programa", "pasta", "downloads", "configuracao do windows"),
     {"ecran", "souris", "apps", "systeme", "astra_pc", "gestes", "stats"}),
    (("chrome", "navegador", "aba", "site", "pagina", "internet", "pesquisa",
      "pesquise", "procura na web", "reserva"), {"navigateur", "web", "reservation"}),
    (("roteiro", "gancho", "conteudo", "video", "youtube", "tiktok", "reels",
      "publicacao", "inspiracao"), {"contenu", "suivi", "deleguer_a_hermes"}),
    (("hermes", "pesquisa profunda", "analise", "compare", "comparacao", "sintese"),
     {"deleguer_a_hermes", "web"}),
    (("ligacao", "liga para", "ligue", "telefone", "telefonar"), {"appels", "appel_direct"}),
    (("memoria", "lembra", "lembre", "esquece", "esqueca"), {"memoire"}),
    (("anota", "anote", "nota", "notas", "ideia"), {"notes"}),
    (("modo hibrido", "modo qualidade", "modo local", "modo nuvem", "idioma",
      "portugues", "frances", "modelo", "troca para"),
     {"budget", "modes", "langue", "modeles_ia"}),
    (("orcamento", "custo", "gasto", "consumo da api"), {"budget"}),
    (("assinatura", "transacao", "extrato", "financas", "financeiro"),
     {"finances", "factures"}),
    (("personalidade", "modo neutro", "modo conciso", "sarcastico"),
     {"personnalite", "modes"}),
    (("chat", "conversa escrita", "digitar"), {"chat_hud"}),
    (("cheguei", "estou saindo", "voltei para casa"), {"presence", "scenes"}),
)
_DOMAINES_COMMUNS = (
    (("github", "repositorio", "repository", "issue", "pull request", " pr ", "commit",
      "branch", "git", "notion", "integracao", "integration", "mcp"), {"integrations_mcp"}),
    (("langue", "parle en", "francais", "chat"), {"langue", "chat_hud"}),
)

_VERBES_ACTION_GENERIQUES_PT = {
    "abre", "abrir", "ativa", "ativar", "acende", "acender", "apaga", "apagar",
    "adiciona", "adicionar", "cria", "criar", "desliga", "desligar", "liga", "ligar",
    "envia", "enviar", "manda", "mandar", "fecha", "fechar", "faz", "fazer", "faca",
    "inicia", "iniciar", "le", "ler", "leia", "mostra", "mostrar", "mude", "muda",
    "mudar", "coloca", "colocar", "poe", "programa", "agenda", "agendar", "procura",
    "procurar", "busca", "buscar", "remove", "remover", "exclui", "excluir", "apague",
    "verifica", "verificar", "confere", "conferir", "toca", "tocar", "para", "pare",
    "aumenta", "diminui", "abaixa", "sobe", "baixa", "encontra", "encontrar", "lista",
    "listar", "qual", "quais", "quanto", "quantos", "como", "onde", "quando",
}
_MARQUES_DEMANDE_PT = (
    "eu quero", "quero", "eu queria", "gostaria", "voce pode", "pode", "consegue",
    "por favor", "preciso",
)

_VERBES_ACTION_GENERIQUES = {
    "active", "activer", "affiche", "afficher", "ajoute", "ajouter",
    "baisse", "baisser", "change",
    "changer", "controle", "controler", "corrige", "corriger", "cree", "creer",
    "demarre", "demarrer", "envoie", "envoyer", "eteins", "eteindre", "ferme",
    "fermer", "fais", "faire", "lance", "lancer", "lis", "lire", "mets",
    "mettre", "modifie", "modifier", "montre", "montrer", "note", "noter",
    "ouvre", "ouvrir", "planifie", "planifier", "prepare", "preparer",
    "programme", "programmer", "cherche", "chercher", "supprime", "supprimer",
    "suivre", "verifie", "verifier", "trouve", "trouver",
}
_MARQUES_DEMANDE = (
    "je veux", "je voudrais", "j aimerais", "tu peux", "peux tu", "tu pourrais",
    "pourrais tu", "est ce que tu peux",
)


def modules_pour_phrase(phrase: str) -> set[str] | None:
    """Modules utiles au LLM, ensemble vide pour une réponse sans outil.

    ``None`` signifie « catalogue complet » : repli conservateur lorsqu'une action
    est demandée mais que son domaine n'est pas reconnu.
    """
    normalise = " ".join(re.sub(
        r"[^a-z0-9]+", " ", sans_accents(str(phrase or "").lower())
    ).split())
    enveloppe = f" {normalise} "
    modules = set()
    for expressions, candidats in _DOMAINES + _DOMAINES_PT + _DOMAINES_COMMUNS + _domaines_mcp():
        if any(expr in enveloppe for expr in expressions):
            modules.update(candidats)
    if modules:
        # Ces outils transverses sont petits et fréquemment nécessaires après une
        # action spécialisée (réponse, changement de mode, état des tâches).
        modules.update({"reponses"})
        return modules

    mots = set(normalise.split())
    if mots & (_VERBES_ACTION_GENERIQUES | _VERBES_ACTION_GENERIQUES_PT):
        return None
    # « je veux… », « tu peux… » annoncent une demande : mieux vaut tout le catalogue
    # qu'une reponse sans outil qui improvise.
    if any(f" {marque} " in enveloppe for marque in _MARQUES_DEMANDE + _MARQUES_DEMANDE_PT):
        return None
    return set()


def _domaines_mcp():
    """Le nom de chaque integration MCP configuree active son domaine."""
    try:
        from core.mcp_cliente import serveurs
        noms = tuple(f" {s['nom'].replace('-', ' ')} " for s in serveurs())
    except Exception:
        noms = ()
    return ((noms, {"integrations_mcp"}),) if noms else ()
