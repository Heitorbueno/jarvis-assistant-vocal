"""Outils vocaux lies aux widgets : cotations, bourse, actualites, affichage."""
from core import registre
from core.registre import outil


def _pt():
    from core import langue
    return langue.est_pt()


def _brl(v, d=2):
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


@outil(
    nom="cotacoes",
    description="Donne le cours des devises (dollar, euro, bitcoin en reais) et de la bourse "
                "(Ibovespa, actions configurees). A utiliser pour 'quanto esta o dolar', "
                "'cotacao do euro', 'como esta a bolsa', 'Ibovespa hoje', 'preco da PETR4'.",
    parametres={"type": "object", "properties": {
        "quoi": {"type": "string", "enum": ["moedas", "bolsa", "tudo"],
                 "description": "moedas = devises, bolsa = Ibovespa/actions, tudo = les deux."}}},
    lent=True, phrase_attente="Je regarde les cotations.", affichage="toujours",
)
def cotacoes(quoi: str = "tudo") -> str:
    from core import widgets
    partes = []
    if quoi in ("moedas", "tudo"):
        c = widgets.cambio()
        if c.get("ok"):
            partes.append("; ".join(f"{x['par'].split('-')[0]} R$ {_brl(x['valor'])} "
                                    f"({x['variacao']:+.2f}%)" for x in c["cotacoes"]))
        else:
            partes.append("cambio indisponivel")
    if quoi in ("bolsa", "tudo"):
        b = widgets.bolsa()
        if b.get("ok"):
            partes.append("; ".join(f"{a['nome']} {_brl(a['valor'], 0 if a['simbolo'] == '^BVSP' else 2)} "
                                    f"({a['variacao']:+.2f}%)" for a in b["ativos"]))
        else:
            partes.append("bolsa indisponivel")
    return ". ".join(partes)


@outil(
    nom="noticias",
    description="Lit les derniers titres d'actualite des flux RSS configures (widget Noticias). "
                "A utiliser pour 'quais as noticias', 'manchetes de hoje', 'o que esta acontecendo'.",
    parametres={"type": "object", "properties": {
        "quantidade": {"type": "integer", "description": "Nombre de titres (1 a 8).", "default": 5}}},
    lent=True, phrase_attente="Je regarde les actualites.", affichage="toujours",
)
def noticias(quantidade: int = 5) -> str:
    from core import widgets
    n = widgets.noticias()
    if not n.get("ok"):
        return n.get("erro", "Actualites indisponibles.")
    q = max(1, min(int(quantidade or 5), 8))
    return "\n".join(f"- {m['titulo']} ({m.get('fonte', '')})" for m in n["manchetes"][:q])


@outil(
    nom="afficher_widgets",
    description="Affiche ou masque les widgets du HUD (meteo, cotations, bourse, actualites, "
                "lecteurs). A utiliser pour 'mostra os widgets', 'esconde os widgets', "
                "'limpa a tela', 'affiche les widgets'.",
    parametres={"type": "object", "properties": {"visible": {"type": "boolean"}},
                "required": ["visible"]},
    affichage="jamais",
)
def afficher_widgets(visible: bool = True) -> str:
    from core import widgets
    widgets.definir_parametros({"visivel": bool(visible)})
    try:
        import hud
        hud.recharger_widgets()
    except Exception:
        pass
    if _pt():
        return "Widgets visíveis." if visible else "Widgets ocultos."
    return "Widgets affiches." if visible else "Widgets masques."


# Les titres d'actualite sont ecrits par des tiers : contenu externe non fiable.
registre.SOURCES_EXTERNES_DYNAMIQUES.add("noticias")
