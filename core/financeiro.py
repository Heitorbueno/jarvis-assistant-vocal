"""Módulo financeiro : bancos/contas, contas a pagar e a receber, fluxo de caixa.

DOUTRINA (CLAUDE.md) : dados 100% LOCAIS (finances/financeiro.db, pasta não
versionada), nunca expostos ao MCP nem ao Hermes. Por voz, criar/baixar/cancelar
um lançamento pede confirmação (N2). Nenhum pagamento é executado : o Jarvis só
REGISTRA ; pagar de verdade continua com você no banco.

Tabelas :
  contas       bancos/carteiras/cartões com saldo inicial ;
  lancamentos  títulos a pagar/receber (vencimento, status, recorrência, parcelas) ;
  extrato      movimentos importados (OFX, Open Finance) para conciliação.

Saldo de uma conta = saldo inicial + recebimentos baixados − pagamentos baixados
(+ movimentos de extrato marcados como « conciliados sem título »).
"""
import datetime as dt
import hashlib
import json
import logging
import re
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from core.config import reglage

LOG = logging.getLogger("jarvis.financeiro")
_RACINE = Path(__file__).resolve().parent.parent
_VERROU = threading.RLock()

TIPOS_CONTA = ("corrente", "poupanca", "cartao", "carteira", "investimento")
CATEGORIAS_PADRAO = {
    "pagar": ["Moradia", "Energia", "Água", "Internet/Telefone", "Alimentação", "Transporte",
              "Saúde", "Educação", "Impostos", "Fornecedores", "Salários", "Cartão de crédito",
              "Assinaturas", "Lazer", "Outros"],
    "receber": ["Vendas", "Comissões", "Serviços", "Salário", "Aluguel recebido",
                "Reembolsos", "Rendimentos", "Outros"],
}
RECORRENCIAS = ("nenhuma", "semanal", "mensal", "anual")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS contas (
  id INTEGER PRIMARY KEY, nome TEXT NOT NULL UNIQUE, banco TEXT DEFAULT '',
  tipo TEXT DEFAULT 'corrente', saldo_inicial REAL DEFAULT 0, data_saldo TEXT,
  ativa INTEGER DEFAULT 1, externo_id TEXT DEFAULT '', criado_em TEXT);
CREATE TABLE IF NOT EXISTS lancamentos (
  id INTEGER PRIMARY KEY, tipo TEXT NOT NULL CHECK (tipo IN ('pagar','receber')),
  descricao TEXT NOT NULL, valor REAL NOT NULL CHECK (valor > 0), vencimento TEXT NOT NULL,
  conta_id INTEGER REFERENCES contas(id), categoria TEXT DEFAULT 'Outros',
  status TEXT DEFAULT 'aberto' CHECK (status IN ('aberto','baixado','cancelado')),
  data_baixa TEXT, valor_baixa REAL, recorrencia TEXT DEFAULT 'nenhuma',
  parcela INTEGER DEFAULT 0, parcelas INTEGER DEFAULT 0, grupo TEXT DEFAULT '',
  contraparte TEXT DEFAULT '', observacao TEXT DEFAULT '', origem TEXT DEFAULT 'painel',
  criado_em TEXT);
CREATE INDEX IF NOT EXISTS ix_lanc_venc ON lancamentos(status, vencimento);
CREATE TABLE IF NOT EXISTS extrato (
  id INTEGER PRIMARY KEY, conta_id INTEGER REFERENCES contas(id), data TEXT NOT NULL,
  descricao TEXT, valor REAL NOT NULL, hash TEXT UNIQUE, origem TEXT,
  lancamento_id INTEGER REFERENCES lancamentos(id), conciliado INTEGER DEFAULT 0);
"""


# ============================================================ base

def caminho():
    p = str(reglage("financeiro.banco", "") or "").strip()
    return Path(p) if p else _RACINE / "finances" / "financeiro.db"


@contextmanager
def _db():
    with _VERROU:
        c = caminho()
        c.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(c))
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(_SCHEMA)
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()


def _agora():
    return dt.datetime.now().isoformat(timespec="seconds")


def _hoje():
    return dt.date.today()


# ============================================================ validação / parsing

def valor_br(texto):
    """'1.234,56' | '1234.56' | 'R$ 230' | 230 -> 1234.56 (float > 0) ou levanta ValueError."""
    if isinstance(texto, (int, float)):
        v = float(texto)
    else:
        t = re.sub(r"[^\d,.\-]", "", str(texto or ""))
        if "," in t:
            t = t.replace(".", "").replace(",", ".")
        elif t.count(".") > 1 or re.match(r"^\d{1,3}(\.\d{3})+$", t):
            t = t.replace(".", "")
        v = float(t)
    v = round(abs(v), 2)
    if v <= 0 or v > 1e10:
        raise ValueError("valor inválido")
    return v


_DIAS_SEMANA = {"segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4,
                "sabado": 5, "domingo": 6}


def data_br(texto, base=None):
    """ISO, dd/mm[/aaaa], 'hoje', 'amanhã', 'dia 10', 'próxima sexta' -> date."""
    base = base or _hoje()
    if isinstance(texto, dt.date):
        return texto
    t = str(texto or "").strip().lower()
    t = (t.replace("ã", "a").replace("á", "a").replace("ç", "c").replace("é", "e")
          .replace("ê", "e").replace("í", "i").replace("ó", "o").replace("ú", "u"))
    if not t or t == "hoje":
        return base
    if t == "amanha":
        return base + dt.timedelta(days=1)
    if t in ("depois de amanha",):
        return base + dt.timedelta(days=2)
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", t)
    if m:
        return dt.date(int(m[1]), int(m[2]), int(m[3]))
    m = re.match(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$", t)
    if m:
        ano = int(m[3]) if m[3] else base.year
        ano = ano + 2000 if ano < 100 else ano
        d = dt.date(ano, int(m[2]), int(m[1]))
        if not m[3] and d < base - dt.timedelta(days=60):
            d = d.replace(year=d.year + 1)
        return d
    m = re.match(r"^(?:dia\s+)?(\d{1,2})$", t)
    if m:
        dia = int(m[1])
        d = _somar_meses(base.replace(day=1), 0, dia)
        return d if d >= base else _somar_meses(base.replace(day=1), 1, dia)
    for nome, idx in _DIAS_SEMANA.items():
        if nome in t:
            delta = (idx - base.weekday()) % 7 or 7
            return base + dt.timedelta(days=delta)
    m = re.match(r"^(?:em\s+)?(\d{1,3})\s+dias?$", t)
    if m:
        return base + dt.timedelta(days=int(m[1]))
    raise ValueError(f"data não reconhecida: {texto}")


def _somar_meses(d, n, dia=None):
    import calendar
    mes = d.month - 1 + n
    ano = d.year + mes // 12
    mes = mes % 12 + 1
    dia = min(dia or d.day, calendar.monthrange(ano, mes)[1])
    return dt.date(ano, mes, dia)


def _proximo(venc, recorrencia):
    if recorrencia == "semanal":
        return venc + dt.timedelta(days=7)
    if recorrencia == "mensal":
        return _somar_meses(venc, 1)
    if recorrencia == "anual":
        return _somar_meses(venc, 12)
    return None


def _txt(v, n=200):
    return " ".join(str(v or "").split())[:n]


# ============================================================ contas (bancos)

def contas(incluir_inativas=False):
    with _db() as con:
        rows = con.execute("SELECT * FROM contas" + ("" if incluir_inativas else " WHERE ativa=1")
                           + " ORDER BY nome").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["saldo"] = round(_saldo(con, r["id"]), 2)
            out.append(d)
        return out


def _saldo(con, conta_id, ate=None):
    r = con.execute("SELECT saldo_inicial FROM contas WHERE id=?", (conta_id,)).fetchone()
    saldo = float(r["saldo_inicial"] or 0) if r else 0.0
    filtro, args = "", [conta_id]
    if ate:
        filtro, args = " AND data_baixa<=?", [conta_id, ate]
    for tipo, sinal in (("receber", 1), ("pagar", -1)):
        v = con.execute("SELECT COALESCE(SUM(COALESCE(valor_baixa, valor)),0) FROM lancamentos "
                        f"WHERE conta_id=? AND status='baixado' AND tipo='{tipo}'" + filtro,
                        args).fetchone()[0]
        saldo += sinal * float(v)
    v = con.execute("SELECT COALESCE(SUM(valor),0) FROM extrato WHERE conta_id=? AND conciliado=2",
                    (conta_id,)).fetchone()[0]
    return saldo + float(v)


def conta_salvar(d):
    nome = _txt(d.get("nome"), 60)
    if not nome:
        return {"ok": False, "message": "Informe o nome da conta."}
    tipo = d.get("tipo") if d.get("tipo") in TIPOS_CONTA else "corrente"
    try:
        saldo = float(str(d.get("saldo_inicial", 0) or 0).replace(".", "").replace(",", ".")) \
            if isinstance(d.get("saldo_inicial"), str) else float(d.get("saldo_inicial") or 0)
    except ValueError:
        return {"ok": False, "message": "Saldo inicial inválido."}
    with _db() as con:
        if d.get("id"):
            con.execute("UPDATE contas SET nome=?, banco=?, tipo=?, saldo_inicial=?, ativa=? WHERE id=?",
                        (nome, _txt(d.get("banco"), 60), tipo, saldo,
                         1 if d.get("ativa", True) else 0, int(d["id"])))
            cid = int(d["id"])
        else:
            try:
                cid = con.execute("INSERT INTO contas(nome, banco, tipo, saldo_inicial, data_saldo, criado_em)"
                                  " VALUES (?,?,?,?,?,?)",
                                  (nome, _txt(d.get("banco"), 60), tipo, saldo,
                                   _hoje().isoformat(), _agora())).lastrowid
            except sqlite3.IntegrityError:
                return {"ok": False, "message": "Já existe uma conta com esse nome."}
    return {"ok": True, "id": cid, "message": f"Conta {nome} salva."}


def conta_por_nome(texto, con=None):
    """Acha a conta por nome/banco aproximado (« itaú », « nubank »)."""
    alvo = _sem_acento(texto)
    if not alvo:
        return None
    lista = contas()
    for c in lista:
        if _sem_acento(c["nome"]) == alvo:
            return c
    for c in lista:
        if alvo in _sem_acento(c["nome"]) or alvo in _sem_acento(c.get("banco", "")):
            return c
    return None


def _sem_acento(s):
    import unicodedata
    return "".join(ch for ch in unicodedata.normalize("NFD", str(s or "").lower())
                   if not unicodedata.combining(ch)).strip()


def conta_padrao():
    nome = str(reglage("financeiro.conta_padrao", "") or "")
    c = conta_por_nome(nome) if nome else None
    if c:
        return c
    lista = contas()
    return lista[0] if len(lista) == 1 else None


# ============================================================ lançamentos

def lancar(tipo, descricao, valor, vencimento=None, conta=None, categoria=None,
           recorrencia="nenhuma", parcelas=1, contraparte="", observacao="", origem="painel"):
    """Cria um título a pagar/receber (ou N parcelas). Retorna dict com ids."""
    if tipo not in ("pagar", "receber"):
        return {"ok": False, "message": "Tipo deve ser pagar ou receber."}
    descricao = _txt(descricao, 120)
    if not descricao:
        return {"ok": False, "message": "Informe a descrição."}
    try:
        total = valor_br(valor)
        venc = data_br(vencimento)
    except ValueError as e:
        return {"ok": False, "message": str(e).capitalize() + "."}
    recorrencia = recorrencia if recorrencia in RECORRENCIAS else "nenhuma"
    try:
        parcelas = max(1, min(int(parcelas or 1), 120))
    except (TypeError, ValueError):
        parcelas = 1
    if parcelas > 1 and recorrencia != "nenhuma":
        return {"ok": False, "message": "Use parcelas OU recorrência, não os dois."}
    conta_id = None
    if conta not in (None, "", 0):
        c = conta if isinstance(conta, dict) else (
            next((x for x in contas() if str(x["id"]) == str(conta)), None) or conta_por_nome(conta))
        if not c:
            return {"ok": False, "message": f"Conta « {conta} » não encontrada. Cadastre em Bancos."}
        conta_id = c["id"]
    elif conta_padrao():
        conta_id = conta_padrao()["id"]
    categoria = _txt(categoria, 40) or "Outros"
    grupo = hashlib.sha1(f"{descricao}{total}{venc}{_agora()}".encode()).hexdigest()[:10] if parcelas > 1 else ""
    valor_parcela = round(total / parcelas, 2)
    ids = []
    with _db() as con:
        for i in range(parcelas):
            v = valor_parcela if i < parcelas - 1 else round(total - valor_parcela * (parcelas - 1), 2)
            ids.append(con.execute(
                "INSERT INTO lancamentos(tipo, descricao, valor, vencimento, conta_id, categoria, "
                "recorrencia, parcela, parcelas, grupo, contraparte, observacao, origem, criado_em) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (tipo, descricao, v, _somar_meses(venc, i).isoformat(), conta_id, categoria,
                 recorrencia, i + 1 if parcelas > 1 else 0, parcelas if parcelas > 1 else 0, grupo,
                 _txt(contraparte, 80), _txt(observacao, 300), origem, _agora())).lastrowid)
    rotulo = "a pagar" if tipo == "pagar" else "a receber"
    extra = f" em {parcelas}x de R$ {_brl(valor_parcela)}" if parcelas > 1 else ""
    return {"ok": True, "ids": ids,
            "message": f"Lançado {rotulo}: {descricao}, R$ {_brl(total)}{extra}, vence {venc.strftime('%d/%m/%Y')}."}


def lancamento(lid):
    with _db() as con:
        r = con.execute("SELECT l.*, c.nome AS conta FROM lancamentos l LEFT JOIN contas c "
                        "ON c.id=l.conta_id WHERE l.id=?", (int(lid),)).fetchone()
        return dict(r) if r else None


def editar(lid, d):
    atual = lancamento(lid)
    if not atual:
        return {"ok": False, "message": "Lançamento não encontrado."}
    campos, args = [], []
    try:
        if "descricao" in d:
            campos.append("descricao=?"); args.append(_txt(d["descricao"], 120) or atual["descricao"])
        if "valor" in d:
            campos.append("valor=?"); args.append(valor_br(d["valor"]))
        if "vencimento" in d:
            campos.append("vencimento=?"); args.append(data_br(d["vencimento"]).isoformat())
        if "categoria" in d:
            campos.append("categoria=?"); args.append(_txt(d["categoria"], 40) or "Outros")
        if "conta_id" in d:
            campos.append("conta_id=?"); args.append(int(d["conta_id"]) if d["conta_id"] else None)
        if "observacao" in d:
            campos.append("observacao=?"); args.append(_txt(d["observacao"], 300))
        if "contraparte" in d:
            campos.append("contraparte=?"); args.append(_txt(d["contraparte"], 80))
    except ValueError as e:
        return {"ok": False, "message": str(e).capitalize() + "."}
    if not campos:
        return {"ok": True, "message": "Nada alterado."}
    with _db() as con:
        con.execute(f"UPDATE lancamentos SET {', '.join(campos)} WHERE id=?", args + [int(lid)])
    return {"ok": True, "message": "Lançamento atualizado."}


def baixar(lid, data=None, valor=None, conta=None):
    """Marca como pago/recebido. Se recorrente, cria o próximo."""
    atual = lancamento(lid)
    if not atual:
        return {"ok": False, "message": "Lançamento não encontrado."}
    if atual["status"] != "aberto":
        return {"ok": False, "message": f"Lançamento já está {atual['status']}."}
    try:
        quando = data_br(data) if data else _hoje()
        v = valor_br(valor) if valor not in (None, "") else float(atual["valor"])
    except ValueError as e:
        return {"ok": False, "message": str(e).capitalize() + "."}
    conta_id = atual["conta_id"]
    if conta:
        c = conta_por_nome(conta) or next((x for x in contas() if str(x["id"]) == str(conta)), None)
        if not c:
            return {"ok": False, "message": "Conta não encontrada."}
        conta_id = c["id"]
    proximo_id = None
    with _db() as con:
        con.execute("UPDATE lancamentos SET status='baixado', data_baixa=?, valor_baixa=?, conta_id=? "
                    "WHERE id=?", (quando.isoformat(), v, conta_id, int(lid)))
        prox = _proximo(dt.date.fromisoformat(atual["vencimento"]), atual["recorrencia"])
        if prox:
            proximo_id = con.execute(
                "INSERT INTO lancamentos(tipo, descricao, valor, vencimento, conta_id, categoria, "
                "recorrencia, contraparte, observacao, origem, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (atual["tipo"], atual["descricao"], atual["valor"], prox.isoformat(), atual["conta_id"],
                 atual["categoria"], atual["recorrencia"], atual["contraparte"], atual["observacao"],
                 "recorrencia", _agora())).lastrowid
    verbo = "Pago" if atual["tipo"] == "pagar" else "Recebido"
    msg = f"{verbo}: {atual['descricao']}, R$ {_brl(v)} em {quando.strftime('%d/%m/%Y')}."
    if proximo_id:
        msg += f" Próximo lançamento criado para {prox.strftime('%d/%m/%Y')}."
    return {"ok": True, "message": msg, "proximo_id": proximo_id}


def estornar(lid):
    atual = lancamento(lid)
    if not atual or atual["status"] != "baixado":
        return {"ok": False, "message": "Só é possível estornar um lançamento baixado."}
    with _db() as con:
        con.execute("UPDATE lancamentos SET status='aberto', data_baixa=NULL, valor_baixa=NULL WHERE id=?",
                    (int(lid),))
    return {"ok": True, "message": "Baixa estornada; lançamento voltou a aberto."}


def cancelar(lid):
    atual = lancamento(lid)
    if not atual:
        return {"ok": False, "message": "Lançamento não encontrado."}
    if atual["status"] == "baixado":
        return {"ok": False, "message": "Estorne a baixa antes de cancelar."}
    with _db() as con:
        con.execute("UPDATE lancamentos SET status='cancelado' WHERE id=?", (int(lid),))
    return {"ok": True, "message": f"Cancelado: {atual['descricao']}."}


def excluir(lid):
    """Exclusão definitiva (somente pelo painel local)."""
    with _db() as con:
        con.execute("UPDATE extrato SET lancamento_id=NULL, conciliado=0 WHERE lancamento_id=?", (int(lid),))
        n = con.execute("DELETE FROM lancamentos WHERE id=?", (int(lid),)).rowcount
    return {"ok": bool(n), "message": "Lançamento excluído." if n else "Lançamento não encontrado."}


def listar(tipo=None, status="aberto", de=None, ate=None, conta_id=None, busca="", limite=500):
    sql = ("SELECT l.*, c.nome AS conta FROM lancamentos l LEFT JOIN contas c ON c.id=l.conta_id "
           "WHERE 1=1")
    args = []
    if tipo in ("pagar", "receber"):
        sql += " AND l.tipo=?"; args.append(tipo)
    if status in ("aberto", "baixado", "cancelado"):
        sql += " AND l.status=?"; args.append(status)
    elif status == "atrasado":
        sql += " AND l.status='aberto' AND l.vencimento<?"; args.append(_hoje().isoformat())
    if de:
        sql += " AND l.vencimento>=?"; args.append(data_br(de).isoformat())
    if ate:
        sql += " AND l.vencimento<=?"; args.append(data_br(ate).isoformat())
    if conta_id:
        sql += " AND l.conta_id=?"; args.append(int(conta_id))
    if busca:
        sql += " AND (l.descricao LIKE ? OR l.contraparte LIKE ? OR l.categoria LIKE ?)"
        args += [f"%{busca}%"] * 3
    sql += " ORDER BY l.vencimento, l.id LIMIT ?"
    args.append(int(limite))
    with _db() as con:
        return [dict(r) for r in con.execute(sql, args).fetchall()]


def procurar(texto, tipo=None):
    """Lançamentos ABERTOS cuja descrição combina com o texto (para comandos de voz)."""
    alvo = _sem_acento(texto)
    candidatos = [l for l in listar(tipo=tipo, status="aberto")
                  if alvo and (alvo in _sem_acento(l["descricao"]) or alvo in _sem_acento(l["contraparte"]))]
    return candidatos


# ============================================================ resumo e fluxo de caixa

def resumo():
    hoje = _hoje()
    lim7 = (hoje + dt.timedelta(days=7)).isoformat()
    lim30 = (hoje + dt.timedelta(days=30)).isoformat()
    with _db() as con:
        def soma(tipo, cond, args):
            return round(float(con.execute(
                f"SELECT COALESCE(SUM(valor),0) FROM lancamentos WHERE status='aberto' AND tipo=? AND {cond}",
                [tipo] + args).fetchone()[0]), 2)

        def conta(tipo, cond, args):
            return con.execute(f"SELECT COUNT(*) FROM lancamentos WHERE status='aberto' AND tipo=? AND {cond}",
                               [tipo] + args).fetchone()[0]
        ids_contas = [r["id"] for r in con.execute("SELECT id FROM contas WHERE ativa=1")]
        saldo = round(sum(_saldo(con, i) for i in ids_contas), 2)
        h = hoje.isoformat()
        r = {
            "saldo_total": saldo,
            "pagar_atrasado": soma("pagar", "vencimento<?", [h]),
            "pagar_atrasado_qtd": conta("pagar", "vencimento<?", [h]),
            "pagar_hoje": soma("pagar", "vencimento=?", [h]),
            "pagar_7d": soma("pagar", "vencimento>=? AND vencimento<=?", [h, lim7]),
            "pagar_30d": soma("pagar", "vencimento>=? AND vencimento<=?", [h, lim30]),
            "receber_atrasado": soma("receber", "vencimento<?", [h]),
            "receber_7d": soma("receber", "vencimento>=? AND vencimento<=?", [h, lim7]),
            "receber_30d": soma("receber", "vencimento>=? AND vencimento<=?", [h, lim30]),
        }
        mes = hoje.strftime("%Y-%m")
        for tipo in ("pagar", "receber"):
            r[f"{tipo}_mes_baixado"] = round(float(con.execute(
                "SELECT COALESCE(SUM(COALESCE(valor_baixa,valor)),0) FROM lancamentos "
                "WHERE status='baixado' AND tipo=? AND substr(data_baixa,1,7)=?", (tipo, mes)).fetchone()[0]), 2)
    r["saldo_projetado_30d"] = round(saldo + r["receber_atrasado"] + r["receber_30d"]
                                     - r["pagar_atrasado"] - r["pagar_30d"], 2)
    return r


def fluxo_caixa(dias=30, conta_id=None):
    """Projeção diária: saldo hoje + recebimentos − pagamentos em aberto (atrasados entram hoje)."""
    dias = max(1, min(int(dias or 30), 365))
    hoje = _hoje()
    with _db() as con:
        ids = [conta_id] if conta_id else [r["id"] for r in con.execute("SELECT id FROM contas WHERE ativa=1")]
        saldo = sum(_saldo(con, i) for i in ids)
        sql = ("SELECT tipo, valor, vencimento FROM lancamentos WHERE status='aberto' AND vencimento<=?"
               + (" AND conta_id=?" if conta_id else ""))
        args = [(hoje + dt.timedelta(days=dias)).isoformat()] + ([conta_id] if conta_id else [])
        movs = con.execute(sql, args).fetchall()
    por_dia = {}
    for m in movs:
        d = max(dt.date.fromisoformat(m["vencimento"]), hoje)
        e = por_dia.setdefault(d, [0.0, 0.0])
        e[0 if m["tipo"] == "receber" else 1] += float(m["valor"])
    serie, acumulado, menor = [], saldo, (saldo, hoje)
    for i in range(dias + 1):
        d = hoje + dt.timedelta(days=i)
        ent, sai = por_dia.get(d, (0.0, 0.0))
        acumulado += ent - sai
        serie.append({"data": d.isoformat(), "entradas": round(ent, 2), "saidas": round(sai, 2),
                      "saldo": round(acumulado, 2)})
        if acumulado < menor[0]:
            menor = (acumulado, d)
    return {"saldo_inicial": round(saldo, 2), "serie": serie,
            "menor_saldo": round(menor[0], 2), "data_menor_saldo": menor[1].isoformat(),
            "negativo": menor[0] < 0}


def categorias():
    with _db() as con:
        usadas = {r[0] for r in con.execute("SELECT DISTINCT categoria FROM lancamentos")}
    return {t: sorted(set(c) | {u for u in usadas if u}) for t, c in CATEGORIAS_PADRAO.items()}


def _brl(v):
    return f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ============================================================ extrato (OFX) e conciliação

def _ofx_valor(tag, bloco):
    m = re.search(rf"<{tag}>\s*([^<\r\n]+)", bloco, re.I)
    return m.group(1).strip() if m else ""


def importar_ofx(conteudo, conta):
    """Importa um extrato OFX (todos os bancos brasileiros exportam). Sem duplicar."""
    c = conta if isinstance(conta, dict) else (conta_por_nome(conta) or next(
        (x for x in contas() if str(x["id"]) == str(conta)), None))
    if not c:
        return {"ok": False, "message": "Escolha a conta do extrato."}
    if isinstance(conteudo, bytes):
        for enc in ("utf-8", "cp1252", "latin-1"):
            try:
                conteudo = conteudo.decode(enc)
                break
            except UnicodeDecodeError:
                continue
    blocos = re.findall(r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|(?=</BANKTRANLIST>))",
                        str(conteudo), re.S | re.I)
    novos = dup = 0
    with _db() as con:
        for b in blocos:
            data = _ofx_valor("DTPOSTED", b)[:8]
            try:
                d = dt.date(int(data[:4]), int(data[4:6]), int(data[6:8]))
                v = round(float(_ofx_valor("TRNAMT", b).replace(",", ".")), 2)
            except (ValueError, IndexError):
                continue
            desc = _txt(_ofx_valor("MEMO", b) or _ofx_valor("NAME", b), 160)
            fitid = _ofx_valor("FITID", b)
            h = hashlib.sha1(f"{c['id']}|{fitid or ''}|{d}|{v}|{desc}".encode()).hexdigest()
            try:
                con.execute("INSERT INTO extrato(conta_id, data, descricao, valor, hash, origem) "
                            "VALUES (?,?,?,?,?,?)", (c["id"], d.isoformat(), desc, v, h, "ofx"))
                novos += 1
            except sqlite3.IntegrityError:
                dup += 1
    sugestoes = conciliar_sugestoes(c["id"])
    return {"ok": True, "novos": novos, "duplicados": dup, "sugestoes": len(sugestoes),
            "message": f"{novos} movimento(s) importado(s), {dup} já existiam. "
                       f"{len(sugestoes)} sugestão(ões) de conciliação."}


def extrato(conta_id=None, pendentes=True, limite=300):
    sql = "SELECT e.*, c.nome AS conta FROM extrato e LEFT JOIN contas c ON c.id=e.conta_id WHERE 1=1"
    args = []
    if conta_id:
        sql += " AND e.conta_id=?"; args.append(int(conta_id))
    if pendentes:
        sql += " AND e.conciliado=0"
    sql += " ORDER BY e.data DESC LIMIT ?"
    args.append(int(limite))
    with _db() as con:
        return [dict(r) for r in con.execute(sql, args).fetchall()]


def conciliar_sugestoes(conta_id=None):
    """Para cada movimento pendente, títulos abertos com mesmo valor e data ±5 dias."""
    out = []
    abertos = listar(status="aberto")
    for e in extrato(conta_id, pendentes=True):
        tipo = "receber" if e["valor"] > 0 else "pagar"
        d = dt.date.fromisoformat(e["data"])
        for l in abertos:
            if (l["tipo"] == tipo and abs(float(l["valor"]) - abs(e["valor"])) < 0.01
                    and abs((dt.date.fromisoformat(l["vencimento"]) - d).days) <= 5):
                out.append({"extrato_id": e["id"], "lancamento_id": l["id"],
                            "descricao_extrato": e["descricao"], "descricao_titulo": l["descricao"],
                            "valor": abs(e["valor"]), "data": e["data"]})
                break
    return out


def conciliar(extrato_id, lancamento_id=None):
    """Liga o movimento ao título (baixando-o) ou o registra como movimento avulso."""
    with _db() as con:
        e = con.execute("SELECT * FROM extrato WHERE id=?", (int(extrato_id),)).fetchone()
    if not e:
        return {"ok": False, "message": "Movimento não encontrado."}
    if lancamento_id:
        r = baixar(int(lancamento_id), data=e["data"], valor=abs(e["valor"]), conta=e["conta_id"])
        if not r["ok"]:
            return r
        with _db() as con:
            con.execute("UPDATE extrato SET conciliado=1, lancamento_id=? WHERE id=?",
                        (int(lancamento_id), int(extrato_id)))
        return {"ok": True, "message": "Conciliado e baixado."}
    with _db() as con:
        con.execute("UPDATE extrato SET conciliado=2 WHERE id=?", (int(extrato_id),))
    return {"ok": True, "message": "Movimento registrado no saldo sem título."}


# ============================================================ Open Finance (Pluggy, opcional)

def pluggy_configurado():
    return bool(reglage("financeiro.pluggy.client_id", "") and reglage("financeiro.pluggy.client_secret", ""))


def _pluggy_api_key():
    import requests
    r = requests.post("https://api.pluggy.ai/auth", timeout=15, json={
        "clientId": reglage("financeiro.pluggy.client_id", ""),
        "clientSecret": reglage("financeiro.pluggy.client_secret", "")})
    if r.status_code != 200:
        raise RuntimeError(f"Pluggy recusou as credenciais (HTTP {r.status_code}).")
    return r.json()["apiKey"]


def pluggy_sincronizar(dias=30):
    """Somente LEITURA : contas e transações dos itens (bancos) conectados no Pluggy.
    Os itens são conectados pelo usuário no Pluggy Connect (fora do Jarvis) ; aqui
    só informamos os itemIds em financeiro.pluggy.itens."""
    if not pluggy_configurado():
        return {"ok": False, "message": "Configure client_id e client_secret do Pluggy."}
    itens = [str(i).strip() for i in (reglage("financeiro.pluggy.itens", []) or []) if str(i).strip()]
    if not itens:
        return {"ok": False, "message": "Informe ao menos um itemId (banco conectado no Pluggy)."}
    import requests
    try:
        chave = _pluggy_api_key()
    except Exception as e:
        return {"ok": False, "message": str(e)[:200]}
    h = {"X-API-KEY": chave}
    desde = (_hoje() - dt.timedelta(days=max(1, min(int(dias), 365)))).isoformat()
    novas_contas = novos = 0
    try:
        for item in itens:
            r = requests.get("https://api.pluggy.ai/accounts", params={"itemId": item}, headers=h, timeout=20)
            r.raise_for_status()
            for a in r.json().get("results", []):
                nome = _txt(f"{a.get('name', 'Conta')} {a.get('number', '')}".strip(), 60)
                with _db() as con:
                    existe = con.execute("SELECT id FROM contas WHERE externo_id=?", (a["id"],)).fetchone()
                    if existe:
                        cid = existe["id"]
                    else:
                        cid = con.execute("INSERT INTO contas(nome, banco, tipo, saldo_inicial, data_saldo, "
                                          "externo_id, criado_em) VALUES (?,?,?,?,?,?,?)",
                                          (nome, _txt(a.get("bankData", {}).get("transferNumber", "") or "Open Finance", 60),
                                           "cartao" if a.get("type") == "CREDIT" else "corrente",
                                           float(a.get("balance") or 0), _hoje().isoformat(), a["id"],
                                           _agora())).lastrowid
                        novas_contas += 1
                tx = requests.get("https://api.pluggy.ai/transactions",
                                  params={"accountId": a["id"], "from": desde, "pageSize": 500},
                                  headers=h, timeout=30)
                tx.raise_for_status()
                with _db() as con:
                    for t in tx.json().get("results", []):
                        hsh = hashlib.sha1(f"pluggy|{t['id']}".encode()).hexdigest()
                        try:
                            con.execute("INSERT INTO extrato(conta_id, data, descricao, valor, hash, origem) "
                                        "VALUES (?,?,?,?,?,?)",
                                        (cid, str(t.get("date", ""))[:10], _txt(t.get("description"), 160),
                                         round(float(t.get("amount") or 0), 2), hsh, "pluggy"))
                            novos += 1
                        except sqlite3.IntegrityError:
                            pass
    except Exception as e:
        LOG.warning("pluggy: %s", type(e).__name__)
        return {"ok": False, "message": f"Falha ao sincronizar ({type(e).__name__})."}
    return {"ok": True, "message": f"Open Finance: {novas_contas} conta(s) nova(s), {novos} movimento(s) novo(s)."}


# ============================================================ exportação

def exportar_csv():
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["id", "tipo", "descricao", "valor", "vencimento", "status", "data_baixa",
                "valor_baixa", "conta", "categoria", "contraparte", "parcela", "recorrencia"])
    for l in listar(status=None, limite=100000):
        w.writerow([l["id"], l["tipo"], l["descricao"], _brl(l["valor"]), l["vencimento"], l["status"],
                    l["data_baixa"] or "", _brl(l["valor_baixa"]) if l["valor_baixa"] else "",
                    l["conta"] or "", l["categoria"], l["contraparte"],
                    f"{l['parcela']}/{l['parcelas']}" if l["parcelas"] else "", l["recorrencia"]])
    return buf.getvalue()


def json_seguro(obj):
    return json.loads(json.dumps(obj, default=str))
