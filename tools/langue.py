"""Outil pour changer la langue de Jarvis a la voix (francais / portugais du Bresil)."""
from core import config
from core.registre import outil


@outil(
    nom="changer_langue",
    description="Change la langue parlee par l'assistant (reponses, voix, transcription). "
                "A utiliser quand l'utilisateur dit 'parle en portugais', 'fale em "
                "portugues', 'mude o idioma para portugues', 'repasse en francais', "
                "'volte para o frances'.",
    parametres={
        "type": "object",
        "properties": {
            "langue": {
                "type": "string",
                "enum": ["fr", "pt"],
                "description": "fr = francais, pt = portugais du Bresil.",
            }
        },
        "required": ["langue"],
    },
)
def changer_langue(langue: str) -> str:
    """Change assistant.langue, persiste dans config.yaml et recharge la voix."""
    code = "pt" if str(langue or "").lower().startswith("pt") else "fr"
    config.definir("assistant.langue", code)
    try:
        from core import tts
        tts.reinitialiser()
    except Exception:
        pass
    if code == "pt":
        return "Idioma alterado para português do Brasil."
    return "Langue changee : francais."
