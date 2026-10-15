"""Outil pour basculer a la voix entre les modeles d'IA favoris (panneau)."""
from core.registre import outil


@outil(
    nom="changer_modele_ia",
    description="Change le modele d'IA (cerveau) de l'assistant parmi les modeles FAVORIS "
                "enregistres dans le panneau. A utiliser quand l'utilisateur dit 'passe sur "
                "Claude', 'utilise le modele local', 'troca para o GPT', 'usa o modelo "
                "rapido'. Sans modele precis, renvoie la liste des favoris.",
    parametres={
        "type": "object",
        "properties": {
            "fournisseur": {"type": "string", "enum": ["openai", "anthropic", "ollama"],
                            "description": "Fournisseur vise."},
            "modele": {"type": "string",
                       "description": "Nom (ou partie du nom) d'un modele favori ; vide = lister."},
        },
        "required": ["fournisseur"],
    },
)
def changer_modele_ia(fournisseur: str, modele: str = "") -> str:
    from core import provedores
    fournisseur = str(fournisseur or "").strip().lower()
    favoris = provedores.favoris(fournisseur)
    if not favoris:
        return (f"Aucun modele favori pour {fournisseur}. Ajoute-les dans le panneau, "
                "onglet Provedores IA.")
    cible = str(modele or "").strip().lower()
    choix = [m for m in favoris if cible and cible in m.lower()]
    if not cible or not choix:
        return f"Favoris {fournisseur} : {', '.join(favoris)}. Lequel veux-tu ?"
    res = provedores.activer(fournisseur, choix[0])
    return res.get("message", "") if isinstance(res, dict) else str(res)
