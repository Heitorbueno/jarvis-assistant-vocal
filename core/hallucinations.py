"""Phrases que Whisper invente sur du silence ou du bruit de fond.

Partage par toutes les voies vocales (micro du PC, satellites, agent Windows) : une
telle « phrase » ne doit jamais etre traitee comme une demande.
"""
from core.util import sans_accents

HALLUCINATIONS = (
    "amara.org", "sous-titres", "sous titres", "merci d'avoir regarde",
    "abonnez-vous", "abonnez vous", "a la prochaine video",
    "n'oubliez pas de vous abonner", "sous-titrage",
    # Equivalents portugais (assistant.langue = pt)
    "legendas pela comunidade", "obrigado por assistir", "obrigada por assistir",
    "inscreva-se no canal", "inscreva se no canal", "legendado por", "ate o proximo video",
)


def est_hallucination(texte):
    """Vrai si la transcription ressemble a une hallucination connue de Whisper."""
    plat = sans_accents(str(texte or ""))
    return any(h in plat for h in HALLUCINATIONS)
