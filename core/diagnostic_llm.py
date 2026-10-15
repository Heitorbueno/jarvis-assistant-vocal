"""Diagnostic des erreurs d'appel au modele : message vocal precis + dernier echec.

Au lieu d'un « je n'arrive pas a joindre le modele » muet sur la cause, on dit
POURQUOI (cle refusee, modele inexistant, credit epuise, reseau) et le panneau
affiche le detail technique (sans jamais la cle).
"""
import re
import time

DERNIER = {}

_MESSAGES = {
    "auth": "La cle API du modele est refusee. Verifie-la dans le panneau, onglet Provedores IA.",
    "modele": "Ce modele n'existe pas ou n'est pas accessible avec cette cle. Choisis-en un autre dans le panneau.",
    "quota": "Le fournisseur refuse la demande : credit epuise ou limite atteinte.",
    "reseau": "Je n'arrive pas a joindre le fournisseur du modele : verifie la connexion Internet.",
    "cle_absente": "Aucune cle API n'est configuree pour ce fournisseur. Ajoute-la dans le panneau.",
    "inconnu": "Je n'arrive pas a joindre le modele pour le moment.",
}


def classer(erreur) -> str:
    texte = f"{type(erreur).__name__} {erreur}".lower()
    statut = getattr(erreur, "status_code", None) or getattr(
        getattr(erreur, "response", None), "status_code", None)
    if "cle openai absente" in texte or "cle anthropic absente" in texte or "api_key" in texte and "must be set" in texte:
        return "cle_absente"
    if statut in (401, 403) or "authentication" in texte or "invalid x-api-key" in texte \
            or "incorrect api key" in texte or "permission" in texte:
        return "auth"
    if statut == 404 or "model_not_found" in texte or "does not exist" in texte \
            or ("model" in texte and "not found" in texte):
        return "modele"
    if statut == 429 or "insufficient_quota" in texte or "rate limit" in texte \
            or "credit" in texte or "quota" in texte:
        return "quota"
    if "connection" in texte or "timeout" in texte or "timed out" in texte \
            or "name resolution" in texte or "getaddrinfo" in texte:
        return "reseau"
    return "inconnu"


def _sans_secret(texte: str) -> str:
    return re.sub(r"(sk|sk-ant|sk-proj|gsk|xai|AIza)[-_A-Za-z0-9]{6,}", "[cle masquee]", texte)


def enregistrer(erreur, fournisseur="", modele="") -> str:
    """Memorise l'echec et renvoie la phrase a prononcer (francais ; traduite en pt)."""
    code = classer(erreur)
    DERNIER.clear()
    DERNIER.update({"ts": time.time(), "fournisseur": fournisseur, "modele": modele,
                    "code": code, "detail": _sans_secret(f"{type(erreur).__name__}: {erreur}")[:300]})
    return _MESSAGES[code]


def dernier():
    return dict(DERNIER)
