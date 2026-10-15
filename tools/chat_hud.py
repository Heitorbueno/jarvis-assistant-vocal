"""Outil pour afficher ou masquer le chat du HUD (masque par defaut, ouvert a la voix)."""
from core.registre import outil


@outil(
    nom="afficher_chat",
    description="Affiche ou masque le chat ecrit du HUD (historique de la conversation et "
                "champ pour taper une commande). A utiliser quand l'utilisateur dit 'ouvre le "
                "chat', 'affiche la conversation', 'abre o chat', 'mostra o chat', 'quero "
                "digitar', 'fecha o chat', 'esconde o chat'.",
    parametres={
        "type": "object",
        "properties": {
            "visible": {"type": "boolean", "description": "true = ouvrir, false = fermer."}
        },
        "required": ["visible"],
    },
)
def afficher_chat(visible: bool = True) -> str:
    try:
        import hud
        hud.chat(bool(visible))
    except Exception:
        return "Le HUD n'est pas disponible."
    from core import langue
    if langue.est_pt():
        return "Chat aberto." if visible else "Chat fechado."
    return "Chat ouvert." if visible else "Chat ferme."
