"""Outils vocaux du module financier (contas a pagar/receber, bancos, fluxo de caixa).

Donnees 100 % locales (core/financeiro). Jamais exposes au MCP. Creer, baixar ou
annuler un titre demande une confirmation vocale (N2, memorisable « sempre »).
Aucun paiement n'est execute : Jarvis ENREGISTRE seulement.
"""
from core import financeiro as fin
from core.registre import outil


def _pt():
    from core import langue
    return langue.est_pt()


def _brl(v):
    return fin._brl(v)


def _d(iso):
    return f"{iso[8:10]}/{iso[5:7]}" if iso else "?"


def _annonce_lancar(a):
    tipo = "a pagar" if a.get("tipo") == "pagar" else "a receber"
    try:
        valor = _brl(fin.valor_br(a.get("valor")))
    except ValueError:
        valor = str(a.get("valor"))
    try:
        venc = fin.data_br(a.get("vencimento") or "hoje").strftime("%d/%m/%Y")
    except ValueError:
        venc = str(a.get("vencimento"))
    parc = int(a.get("parcelas") or 1)
    extra = f" em {parc} parcelas" if parc > 1 else ""
    rec = a.get("recorrencia") or "nenhuma"
    extra += f", recorrência {rec}" if rec != "nenhuma" else ""
    conta = f", conta {a['conta']}" if a.get("conta") else ""
    if _pt():
        return f"Vou lançar {tipo}: {a.get('descricao', '')}, R$ {valor}, vencimento {venc}{extra}{conta}."
    return (f"Je vais enregistrer {('a payer' if a.get('tipo') == 'pagar' else 'a recevoir')} : "
            f"{a.get('descricao', '')}, {valor} R$, echeance {venc}{extra}{conta}.")


@outil(
    nom="lancar_conta",
    description="Enregistre une conta a PAGAR ou a RECEBER (titre financier) dans le module "
                "financier local. A utiliser pour 'lanca conta de luz 230 reais dia 10 no Itau', "
                "'registra que vou receber 1500 do cliente X sexta', 'aluguel 2000 todo mes dia 5', "
                "'compra de 1200 em 3 vezes'. vencimento : AAAA-MM-JJ, dd/mm, 'dia 10', 'amanha'.",
    parametres={"type": "object", "properties": {
        "tipo": {"type": "string", "enum": ["pagar", "receber"]},
        "descricao": {"type": "string", "description": "Ex. 'Conta de luz', 'Cliente Acme'."},
        "valor": {"type": "string", "description": "Valeur en reais, ex. '230', '1.234,56'."},
        "vencimento": {"type": "string", "description": "Date d'echeance."},
        "conta": {"type": "string", "description": "Banque/compte cadastre (ex. 'Itau'). Optionnel."},
        "categoria": {"type": "string", "description": "Ex. Energia, Vendas, Impostos. Optionnel."},
        "recorrencia": {"type": "string", "enum": ["nenhuma", "semanal", "mensal", "anual"]},
        "parcelas": {"type": "integer", "description": "Nombre de parcelles (1 = a vista)."},
        "contraparte": {"type": "string", "description": "Fournisseur ou client. Optionnel."},
    }, "required": ["tipo", "descricao", "valor", "vencimento"]},
    confirmation=True, annonce=_annonce_lancar, affichage="toujours",
)
def lancar_conta(tipo, descricao, valor, vencimento, conta="", categoria="",
                 recorrencia="nenhuma", parcelas=1, contraparte=""):
    return fin.lancar(tipo, descricao, valor, vencimento, conta or None, categoria,
                      recorrencia, parcelas, contraparte, origem="voz")["message"]


@outil(
    nom="contas_financeiro",
    description="Liste les titres financiers (contas a pagar/receber) avec leur NUMERO (id). "
                "A utiliser pour 'o que tenho para pagar essa semana', 'contas atrasadas', "
                "'quanto vou receber este mes', ou pour trouver l'id avant baixar/cancelar.",
    parametres={"type": "object", "properties": {
        "tipo": {"type": "string", "enum": ["pagar", "receber", "todos"]},
        "periodo": {"type": "string", "enum": ["atrasadas", "hoje", "semana", "mes", "todas"]},
        "busca": {"type": "string", "description": "Filtre texte (description/fournisseur)."},
    }},
    affichage="toujours",
)
def contas_financeiro(tipo="todos", periodo="semana", busca=""):
    import datetime as dt
    hoje = dt.date.today()
    de = ate = None
    status = "aberto"
    if periodo == "atrasadas":
        status = "atrasado"
    elif periodo == "hoje":
        de = ate = hoje.isoformat()
    elif periodo == "semana":
        ate = (hoje + dt.timedelta(days=7)).isoformat()
    elif periodo == "mes":
        ate = (hoje + dt.timedelta(days=31)).isoformat()
    itens = fin.listar(tipo=None if tipo == "todos" else tipo, status=status, de=de, ate=ate,
                       busca=busca or "", limite=30)
    if not itens:
        return "Nenhum lançamento encontrado." if _pt() else "Aucun titre trouve."
    total = sum(float(i["valor"]) for i in itens)
    linhas = [f"#{i['id']} {'pagar' if i['tipo'] == 'pagar' else 'receber'} {i['descricao']} "
              f"R$ {_brl(i['valor'])} vence {_d(i['vencimento'])}"
              + (f" ({i['conta']})" if i.get("conta") else "") for i in itens]
    return "\n".join(linhas) + f"\nTotal: R$ {_brl(total)} em {len(itens)} lançamento(s)."


def _annonce_baixar(a):
    l = fin.lancamento(a.get("id", 0)) if str(a.get("id", "")).isdigit() else None
    if not l:
        return "Não encontrei esse lançamento." if _pt() else "Je ne trouve pas ce titre."
    verbo = "pago" if l["tipo"] == "pagar" else "recebido"
    valor = a.get("valor") or l["valor"]
    try:
        valor = _brl(fin.valor_br(valor))
    except ValueError:
        pass
    if _pt():
        return f"Vou marcar como {verbo}: #{l['id']} {l['descricao']}, R$ {valor}."
    return f"Je vais marquer comme {('paye' if l['tipo'] == 'pagar' else 'recu')} : #{l['id']} {l['descricao']}, {valor} R$."


@outil(
    nom="baixar_conta",
    description="Marque un titre comme PAGO ou RECEBIDO (baixa), par son numero (id). Utilise "
                "d'abord contas_financeiro pour trouver l'id. Ex. 'paguei a conta de luz', "
                "'recebi do cliente Acme'. Un titre recurrent cree automatiquement le suivant.",
    parametres={"type": "object", "properties": {
        "id": {"type": "integer"},
        "data": {"type": "string", "description": "Date du paiement ; vide = aujourd'hui."},
        "valor": {"type": "string", "description": "Valeur effectivement payee si differente."},
        "conta": {"type": "string", "description": "Compte utilise si different."},
    }, "required": ["id"]},
    confirmation=True, annonce=_annonce_baixar, affichage="toujours",
)
def baixar_conta(id, data="", valor="", conta=""):
    return fin.baixar(id, data or None, valor or None, conta or None)["message"]


def _annonce_cancelar(a):
    l = fin.lancamento(a.get("id", 0)) if str(a.get("id", "")).isdigit() else None
    if not l:
        return "Não encontrei esse lançamento." if _pt() else "Je ne trouve pas ce titre."
    return (f"Vou cancelar: #{l['id']} {l['descricao']}, R$ {_brl(l['valor'])}." if _pt()
            else f"Je vais annuler : #{l['id']} {l['descricao']}, {_brl(l['valor'])} R$.")


@outil(
    nom="cancelar_lancamento",
    description="Annule un titre financier ouvert par son numero (id). Ex. 'cancela a conta 12'.",
    parametres={"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
    confirmation=True, annonce=_annonce_cancelar,
)
def cancelar_lancamento(id):
    return fin.cancelar(id)["message"]


@outil(
    nom="resumo_financeiro",
    description="Resume financier : saldo des comptes, a payer/recevoir (en retard, aujourd'hui, "
                "7 et 30 jours) et fluxo de caixa projete (plus bas solde, date ou il devient "
                "negatif). Ex. 'como estao minhas financas', 'qual meu saldo', 'vou ficar negativo?'.",
    affichage="toujours",
)
def resumo_financeiro():
    r = fin.resumo()
    f = fin.fluxo_caixa(30)
    linhas = [
        f"Saldo nas contas: R$ {_brl(r['saldo_total'])}.",
        f"A pagar: R$ {_brl(r['pagar_atrasado'])} atrasado ({r['pagar_atrasado_qtd']}), "
        f"R$ {_brl(r['pagar_hoje'])} hoje, R$ {_brl(r['pagar_7d'])} em 7 dias, R$ {_brl(r['pagar_30d'])} em 30 dias.",
        f"A receber: R$ {_brl(r['receber_atrasado'])} atrasado, R$ {_brl(r['receber_7d'])} em 7 dias, "
        f"R$ {_brl(r['receber_30d'])} em 30 dias.",
        f"Saldo projetado em 30 dias: R$ {_brl(r['saldo_projetado_30d'])}.",
    ]
    if f["negativo"]:
        linhas.append(f"Atenção: o caixa fica negativo em {_d(f['data_menor_saldo'])} "
                      f"(mínimo R$ {_brl(f['menor_saldo'])}).")
    for c in fin.contas():
        linhas.append(f"- {c['nome']}: R$ {_brl(c['saldo'])}")
    return "\n".join(linhas)
