from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
import calendar
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ============================================================
# REGRAS DE NEGÓCIO DA RESIDÊNCIA
# ============================================================

PERC_PRATICA = 0.80
PERC_TEORICA = 0.20

META_HORAS_SEMANA = 60.0
META_SEMANAL_PRATICA = 48.0
META_SEMANAL_TEORIA = 12.0

META_ANUAL_TOTAL = 2880.0
META_ANUAL_PRATICA = 2304.0
META_ANUAL_TEORIA = 576.0

DURACAO_PROGRAMA_ANOS = 2
DIAS_FERIAS_ANO = 30
FREQUENCIA_MINIMA_TEORIA = 0.85

# Mantido APENAS para compatibilidade com módulos antigos.
# O motor novo NÃO usa meta mensal fixa.
META_HORAS_MES = 240.0

# Mantido APENAS para compatibilidade com imports legados.
# Débito real não é mais calculado por um valor fixo diário.
HORAS_DEBITO_FALTA = 9.0

# O AAD é meta semanal e completa as 12h teóricas.
# Para cálculos por dia/período, o restante do AAD é ancorado
# contabilmente no sábado. Isso NÃO obriga que o AAD seja feito
# especificamente no sábado; é somente uma convenção do motor.
DIA_CONTABIL_AAD = 5  # sábado

# Regra de negócio: SOMENTE férias retiram a meta do período.
# Feriado, ponto facultativo, falta, atestado/licença e ausência justificada
# mantêm integralmente a carga prevista e, se não cumpridos, geram reposição.
FERIADO_REDUZ_META_DIA = False  # compatibilidade; não é usado para retirar meta


CATEGORIAS_PRATICA = {"Prática"}
CATEGORIAS_TEORIA = {
    "Teórica",
    "Teórico-prática",
    "Estudo Auto-dirigido (AAD)",
}
CATEGORIAS_FERIAS = {"Férias"}
CATEGORIAS_FERIADO = {
    "Feriado / Ponto Facultativo",
    "Feriado",
    "Ponto facultativo",
}
CATEGORIAS_REPOSICAO = {
    "Falta",
    "Ausência Justificada",
    "Ausência justificada",
    "Atestado / Licença Médica",
    "Licença",
    "Atestado",
    "ATESTADO",
    "Feriado / Ponto Facultativo",
    "Feriado",
    "Ponto facultativo",
}


# ============================================================
# NORMALIZAÇÃO
# ============================================================

def normalizar_categoria(categoria: str) -> str:
    c = (categoria or "").strip()
    c_up = c.upper()

    if c_up in {"ATESTADO", "LICENÇA", "ATESTADO / LICENÇA MÉDICA"}:
        return "Atestado / Licença Médica"
    if c_up in {"FERIADO", "PONTO FACULTATIVO", "FERIADO / PONTO FACULTATIVO"}:
        return "Feriado / Ponto Facultativo"
    if c_up == "FALTA":
        return "Falta"
    if c_up == "FÉRIAS":
        return "Férias"
    if c_up in {"AUSÊNCIA JUSTIFICADA", "AUSENCIA JUSTIFICADA"}:
        return "Ausência Justificada"
    if c_up in {"TEÓRICO-PRÁTICA", "TEORICO-PRATICA"}:
        return "Teórico-prática"
    if c_up == "ESTUDO AUTO-DIRIGIDO (AAD)":
        return "Estudo Auto-dirigido (AAD)"
    if c_up == "PRÁTICA":
        return "Prática"
    if c_up == "TEÓRICA":
        return "Teórica"
    return c


def _safe_float(valor: Any) -> float:
    try:
        return float(valor or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _parse_date(valor: Any) -> Optional[date]:
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return valor
    if isinstance(valor, datetime):
        return valor.date()
    if not valor:
        return None
    try:
        return datetime.strptime(str(valor), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


# ============================================================
# CALENDÁRIO SEMANAL
# ============================================================

def segunda_da_semana(data_alvo: date) -> date:
    return data_alvo - timedelta(days=data_alvo.weekday())


def quinta_da_semana(data_alvo: date) -> date:
    return segunda_da_semana(data_alvo) + timedelta(days=3)


def primeira_quinta_de_maio(ano: int) -> date:
    d = date(ano, 5, 1)
    while d.weekday() != 3:
        d += timedelta(days=1)
    return d


def duracao_eixo_especifico(data_da_semana: date) -> float:
    """
    Preserva a regra já existente no app:
      - específico = 3h inicialmente;
      - a janela de 8 semanas começa na primeira quinta-feira de maio;
      - após essas 8 semanas, específico = 2h.

    Antes de maio continua 3h, como no comportamento legado.
    """
    quinta = quinta_da_semana(data_da_semana)
    inicio_janela = primeira_quinta_de_maio(quinta.year)

    if quinta < inicio_janela:
        return 3.0

    semanas_passadas = (quinta - inicio_janela).days // 7
    return 2.0 if semanas_passadas >= 8 else 3.0


def obter_componentes_teoria_semana(data_da_semana: date) -> Dict[str, float]:
    """
    Fecha SEMPRE 12h teóricas na semana-padrão.

    Exemplos após o específico cair para 2h:
      semana comum: 2h específico + 10h AAD = 12h
      semana transversal/concentração: 5h eixo + 2h específico + 5h AAD = 12h

    Enquanto específico = 3h:
      semana comum: 3h + 9h AAD = 12h
      semana transversal/concentração: 5h + 3h + 4h AAD = 12h
    """
    segunda = segunda_da_semana(data_da_semana)
    quinta = segunda + timedelta(days=3)
    semana_do_mes = ((quinta.day - 1) // 7) + 1

    transversal = 5.0 if semana_do_mes == 1 else 0.0
    concentracao = 5.0 if semana_do_mes == 2 else 0.0
    especifico = duracao_eixo_especifico(segunda)

    teoria_fixa = transversal + concentracao + especifico
    if teoria_fixa > META_SEMANAL_TEORIA + 1e-9:
        raise ValueError(
            f"A teoria fixa da semana iniciada em {segunda:%d/%m/%Y} "
            f"soma {teoria_fixa:.2f}h, acima da meta semanal de "
            f"{META_SEMANAL_TEORIA:.2f}h."
        )

    aad = META_SEMANAL_TEORIA - teoria_fixa

    return {
        "inicio_semana": segunda,
        "transversal": transversal,
        "concentracao": concentracao,
        "especifico": especifico,
        "teoria_fixa": teoria_fixa,
        "aad": aad,
        "teoria_total": teoria_fixa + aad,
    }


def obter_metas_do_dia(data_alvo: date) -> Tuple[float, float]:
    """
    Retorna a meta CURRICULAR BASE do dia, sem aplicar férias,
    feriados lançados ou outras isenções do residente.

    A semana-padrão sempre fecha:
        prática = 48h
        teoria  = 12h
        total   = 60h
    """
    dia_semana = data_alvo.weekday()
    segunda = segunda_da_semana(data_alvo)
    comp = obter_componentes_teoria_semana(segunda)

    pratica_por_dia = {
        0: 9.0,
        1: 12.0,
        2: 9.0,
        3: 9.0,
        4: 9.0,
        5: 0.0,
        6: 0.0,
    }
    meta_pratica = pratica_por_dia[dia_semana]
    meta_teorica = 0.0

    quinta = segunda + timedelta(days=3)
    semana_do_mes = ((quinta.day - 1) // 7) + 1

    # Não usamos mais "pertence_a_este_mes". A semana pertence ao mês
    # âncora da quinta-feira, mas segunda e quinta da MESMA semana devem
    # receber a carga normalmente, mesmo quando a semana cruza o mês.
    if semana_do_mes in (1, 2) and dia_semana in (0, 3):
        meta_teorica += 2.5

    if dia_semana == 2:  # quarta
        meta_teorica += comp["especifico"]

    if dia_semana == DIA_CONTABIL_AAD:
        meta_teorica += comp["aad"]

    return meta_pratica, meta_teorica


def validar_semana(data_da_semana: date) -> Dict[str, float]:
    segunda = segunda_da_semana(data_da_semana)
    p = 0.0
    t = 0.0
    for i in range(7):
        p_d, t_d = obter_metas_do_dia(segunda + timedelta(days=i))
        p += p_d
        t += t_d
    return {
        "pratica": p,
        "teoria": t,
        "total": p + t,
        "ok": (
            abs(p - META_SEMANAL_PRATICA) < 1e-9
            and abs(t - META_SEMANAL_TEORIA) < 1e-9
            and abs((p + t) - META_HORAS_SEMANA) < 1e-9
        ),
    }


# ============================================================
# ANO-RESIDÊNCIA
# ============================================================

def obter_periodo_ano_residencia(data_inicio: date, numero_r: int) -> Tuple[date, date]:
    if numero_r < 1 or numero_r > DURACAO_PROGRAMA_ANOS:
        raise ValueError("Ano-residência fora da duração configurada do programa.")

    inicio_r = date(
        data_inicio.year + numero_r - 1,
        data_inicio.month,
        data_inicio.day,
    )
    inicio_proximo = date(
        data_inicio.year + numero_r,
        data_inicio.month,
        data_inicio.day,
    )
    return inicio_r, inicio_proximo - timedelta(days=1)


def obter_numero_r(data_alvo: date, data_inicio: date) -> Optional[int]:
    for numero_r in range(1, DURACAO_PROGRAMA_ANOS + 1):
        ini, fim = obter_periodo_ano_residencia(data_inicio, numero_r)
        if ini <= data_alvo <= fim:
            return numero_r
    return None


def obter_fim_programa(data_inicio: date) -> date:
    inicio_apos_programa = date(
        data_inicio.year + DURACAO_PROGRAMA_ANOS,
        data_inicio.month,
        data_inicio.day,
    )
    return inicio_apos_programa - timedelta(days=1)


# ============================================================
# ÍNDICE DOS REGISTROS
# ============================================================

def _preparar_pontos(todos_pontos: Iterable[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    pontos: List[Dict[str, Any]] = []
    avisos: List[str] = []

    for original in todos_pontos:
        d = _parse_date(original.get("data_registro"))
        if d is None:
            avisos.append("Registro ignorado por possuir data_registro inválida ou ausente.")
            continue

        cat = normalizar_categoria(original.get("categoria", ""))
        horas = _safe_float(original.get("horas_computadas", 0.0))

        pontos.append({
            **original,
            "_data": d,
            "_categoria": cat,
            "_horas": horas,
        })

    return pontos, avisos


def _indexar_por_dia(pontos: Iterable[Dict[str, Any]]) -> Dict[date, List[Dict[str, Any]]]:
    indice: Dict[date, List[Dict[str, Any]]] = defaultdict(list)
    for p in pontos:
        indice[p["_data"]].append(p)
    return indice


# ============================================================
# CÁLCULO DE UM PERÍODO QUALQUER
# ============================================================

def calcular_periodo(
    todos_pontos: Iterable[Dict[str, Any]],
    data_inicio_periodo: date,
    data_fim_periodo: date,
    *,
    data_inicio_programa: Optional[date] = None,
    data_fim_programa: Optional[date] = None,
    feriado_reduz_meta_dia: bool = FERIADO_REDUZ_META_DIA,  # legado; ignorado
) -> Dict[str, Any]:
    """
    ÚNICA fonte de verdade para metas/saldos do dashboard.

    Regra de negócio:
      - SOMENTE FÉRIAS retiram a expectativa do dia;
      - feriado/ponto facultativo, falta, atestado/licença e ausência justificada
        NÃO reduzem a expectativa e geram reposição quando não cumpridos;
      - nenhuma ausência vira hora realizada;
      - "horas_reposicao" é apenas informativa e NÃO é subtraída de novo.
    """
    pontos, avisos = _preparar_pontos(todos_pontos)
    indice = _indexar_por_dia(pontos)

    inicio = data_inicio_periodo
    fim = data_fim_periodo

    if data_inicio_programa is not None:
        inicio = max(inicio, data_inicio_programa)
    if data_fim_programa is not None:
        fim = min(fim, data_fim_programa)

    vazio = inicio > fim

    totais = {
        "esperado_pratica": 0.0,
        "esperado_teoria": 0.0,
        "esperado_total": 0.0,
        "curricular_base_pratica": 0.0,
        "curricular_base_teoria": 0.0,
        "curricular_base_total": 0.0,
        "realizado_pratica": 0.0,
        "realizado_teoria": 0.0,
        "realizado_total": 0.0,
        "saldo_pratica": 0.0,
        "saldo_teoria": 0.0,
        "saldo_total": 0.0,
        "horas_retiradas_ferias_pratica": 0.0,
        "horas_retiradas_ferias_teoria": 0.0,
        "horas_retiradas_ferias_total": 0.0,
        "horas_retiradas_feriado_pratica": 0.0,
        "horas_retiradas_feriado_teoria": 0.0,
        "horas_retiradas_feriado_total": 0.0,
        "horas_reposicao_pratica": 0.0,
        "horas_reposicao_teoria": 0.0,
        "horas_reposicao_total": 0.0,
        "dias_ferias": 0,
        "dias_ausencia": 0,
        "dias_feriado": 0,
    }

    por_categoria: Dict[str, float] = defaultdict(float)
    por_dia: List[Dict[str, Any]] = []

    if vazio:
        return {
            **totais,
            "por_categoria": {},
            "por_dia": [],
            "avisos": avisos,
            "inicio": inicio,
            "fim": fim,
        }

    curr = inicio
    while curr <= fim:
        regs = indice.get(curr, [])
        cats = {r["_categoria"] for r in regs}

        base_p, base_t = obter_metas_do_dia(curr)
        exp_p, exp_t = base_p, base_t

        tem_ferias = bool(cats & CATEGORIAS_FERIAS)
        tem_feriado = bool(cats & CATEGORIAS_FERIADO)
        tem_reposicao = bool(cats & CATEGORIAS_REPOSICAO)

        motivo_isencao = None

        # ÚNICA situação que retira a meta do dia: férias.
        if tem_ferias:
            exp_p = 0.0
            exp_t = 0.0
            motivo_isencao = "Férias"
            totais["dias_ferias"] += 1
            totais["horas_retiradas_ferias_pratica"] += base_p
            totais["horas_retiradas_ferias_teoria"] += base_t

        # Feriado/ponto facultativo NÃO reduz a meta.
        # Ele é apenas classificado para auditoria e reposição.
        if tem_feriado:
            totais["dias_feriado"] += 1

        real_p = sum(r["_horas"] for r in regs if r["_categoria"] in CATEGORIAS_PRATICA)
        real_t = sum(r["_horas"] for r in regs if r["_categoria"] in CATEGORIAS_TEORIA)

        for r in regs:
            por_categoria[r["_categoria"]] += r["_horas"]

        saldo_p = real_p - exp_p
        saldo_t = real_t - exp_t

        repos_p = 0.0
        repos_t = 0.0
        if tem_reposicao:
            totais["dias_ausencia"] += 1
            repos_p = max(0.0, exp_p - real_p)
            repos_t = max(0.0, exp_t - real_t)
            totais["horas_reposicao_pratica"] += repos_p
            totais["horas_reposicao_teoria"] += repos_t

        if tem_ferias and (real_p > 0.0 or real_t > 0.0):
            avisos.append(
                f"{curr:%d/%m/%Y}: há férias e horas trabalhadas no mesmo dia. "
                "As horas realizadas foram mantidas, mas a meta operacional do dia foi zerada."
            )
        if tem_ferias and tem_reposicao:
            avisos.append(
                f"{curr:%d/%m/%Y}: há férias e ausência/reposição no mesmo dia. Verifique o lançamento."
            )

        totais["curricular_base_pratica"] += base_p
        totais["curricular_base_teoria"] += base_t
        totais["esperado_pratica"] += exp_p
        totais["esperado_teoria"] += exp_t
        totais["realizado_pratica"] += real_p
        totais["realizado_teoria"] += real_t

        por_dia.append({
            "data": curr,
            "meta_base_pratica": base_p,
            "meta_base_teoria": base_t,
            "meta_base_total": base_p + base_t,
            "meta_pratica": exp_p,
            "meta_teoria": exp_t,
            "meta_total": exp_p + exp_t,
            "realizado_pratica": real_p,
            "realizado_teoria": real_t,
            "realizado_total": real_p + real_t,
            "saldo_pratica": saldo_p,
            "saldo_teoria": saldo_t,
            "saldo_total": saldo_p + saldo_t,
            "reposicao_pratica": repos_p,
            "reposicao_teoria": repos_t,
            "reposicao_total": repos_p + repos_t,
            "categorias": sorted(cats),
            "motivo_isencao": motivo_isencao,
            "registros": regs,
        })

        curr += timedelta(days=1)

    totais["curricular_base_total"] = (
        totais["curricular_base_pratica"] + totais["curricular_base_teoria"]
    )
    totais["esperado_total"] = totais["esperado_pratica"] + totais["esperado_teoria"]
    totais["realizado_total"] = totais["realizado_pratica"] + totais["realizado_teoria"]
    totais["saldo_pratica"] = totais["realizado_pratica"] - totais["esperado_pratica"]
    totais["saldo_teoria"] = totais["realizado_teoria"] - totais["esperado_teoria"]
    totais["saldo_total"] = totais["realizado_total"] - totais["esperado_total"]

    totais["horas_retiradas_ferias_total"] = (
        totais["horas_retiradas_ferias_pratica"]
        + totais["horas_retiradas_ferias_teoria"]
    )
    totais["horas_retiradas_feriado_total"] = (
        totais["horas_retiradas_feriado_pratica"]
        + totais["horas_retiradas_feriado_teoria"]
    )
    totais["horas_reposicao_total"] = (
        totais["horas_reposicao_pratica"] + totais["horas_reposicao_teoria"]
    )

    return {
        **totais,
        "por_categoria": dict(por_categoria),
        "por_dia": por_dia,
        "avisos": avisos,
        "inicio": inicio,
        "fim": fim,
    }


# ============================================================
# MOTOR GERAL USADO PELO DASHBOARD
# ============================================================

def calcular_motor_horas(
    todos_pontos: Iterable[Dict[str, Any]],
    data_inicio: date,
    data_hoje: date,
    lista_meses: Iterable[str],
    meses_num_para_pt: Dict[str, str],
) -> Dict[str, Any]:
    fim_programa = obter_fim_programa(data_inicio)
    data_limite = min(data_hoje, fim_programa)

    geral = calcular_periodo(
        todos_pontos,
        data_inicio,
        data_limite,
        data_inicio_programa=data_inicio,
        data_fim_programa=fim_programa,
    )

    pt_para_num = {nome: int(num) for num, nome in meses_num_para_pt.items()}
    dados_mensais: Dict[str, Dict[str, Any]] = {}

    for chave_mes in lista_meses:
        nome_mes, ano_txt = chave_mes.split("/")
        mes = pt_para_num[nome_mes]
        ano = int(ano_txt)
        _, ultimo_dia = calendar.monthrange(ano, mes)

        ini_mes = max(date(ano, mes, 1), data_inicio)
        fim_mes = min(date(ano, mes, ultimo_dia), data_limite, fim_programa)

        periodo = calcular_periodo(
            todos_pontos,
            ini_mes,
            fim_mes,
            data_inicio_programa=data_inicio,
            data_fim_programa=fim_programa,
        )

        dados_mensais[chave_mes] = {
            "trabalhadas": periodo["realizado_total"],
            "pratica": periodo["realizado_pratica"],
            "teorica": periodo["realizado_teoria"],
            # Compatibilidade: agora significa carga RETIRADA da expectativa por férias.
            "ferias": periodo["horas_retiradas_ferias_total"],
            "ferias_pratica": periodo["horas_retiradas_ferias_pratica"],
            "ferias_teorica": periodo["horas_retiradas_ferias_teoria"],
            "feriados": 0.0,  # feriado não retira meta
            "feriados_pratica": 0.0,
            "feriados_teorica": 0.0,
            # Compatibilidade: "meta_dispensada" agora significa SOMENTE férias.
            "meta_dispensada_total": periodo["horas_retiradas_ferias_total"],
            "meta_dispensada_pratica": periodo["horas_retiradas_ferias_pratica"],
            "meta_dispensada_teorica": periodo["horas_retiradas_ferias_teoria"],
            # Compatibilidade: informativo; NÃO deve ser subtraído novamente do saldo.
            "faltas_debito": periodo["horas_reposicao_total"],
            "faltas_pratica_debito": periodo["horas_reposicao_pratica"],
            "faltas_teorica_debito": periodo["horas_reposicao_teoria"],
            "dias_ausencia": periodo["dias_ausencia"],
            "dias_ferias_gozados": periodo["dias_ferias"],
            "por_categoria": periodo["por_categoria"],
            "meta_pratica_mes_exata": periodo["esperado_pratica"],
            "meta_teorica_mes_exata": periodo["esperado_teoria"],
            "meta_total_mes_exata": periodo["esperado_total"],
            "meta_curricular_pratica_mes": periodo["curricular_base_pratica"],
            "meta_curricular_teorica_mes": periodo["curricular_base_teoria"],
            "meta_curricular_total_mes": periodo["curricular_base_total"],
            "saldo_pratica": periodo["saldo_pratica"],
            "saldo_teorica": periodo["saldo_teoria"],
            "saldo_total": periodo["saldo_total"],
        }

    # Auditoria semanal: não altera saldo; serve para interface/diagnóstico.
    auditoria_semanal: List[Dict[str, Any]] = []
    segunda = segunda_da_semana(data_inicio)
    ultima_segunda = segunda_da_semana(data_limite)

    while segunda <= ultima_segunda:
        domingo = segunda + timedelta(days=6)
        fim_semana_calculo = min(domingo, data_limite)
        semana = calcular_periodo(
            todos_pontos,
            max(segunda, data_inicio),
            fim_semana_calculo,
            data_inicio_programa=data_inicio,
            data_fim_programa=fim_programa,
        )
        comp = obter_componentes_teoria_semana(segunda)
        validacao = validar_semana(segunda)

        auditoria_semanal.append({
            "inicio_semana": segunda.isoformat(),
            "fim_semana": domingo.isoformat(),
            "semana_encerrada": domingo <= data_limite,
            "meta_semana_padrao": META_HORAS_SEMANA,
            "meta_pratica_padrao": META_SEMANAL_PRATICA,
            "meta_teoria_padrao": META_SEMANAL_TEORIA,
            "meta_transversal": comp["transversal"],
            "meta_concentracao": comp["concentracao"],
            "meta_especifico": comp["especifico"],
            "meta_aad": comp["aad"],
            "teoria_fecha_12h": validacao["ok"],
            "esperado_ate_data": semana["esperado_total"],
            "esperado_pratica_ate_data": semana["esperado_pratica"],
            "esperado_teoria_ate_data": semana["esperado_teoria"],
            "realizado": semana["realizado_total"],
            "realizado_pratica": semana["realizado_pratica"],
            "realizado_teoria": semana["realizado_teoria"],
            "saldo": semana["saldo_total"],
        })
        segunda += timedelta(days=7)

    # Auditoria dos R: meta GLOBAL é fixa em 2.880h/ano-residência.
    auditoria_anos: Dict[int, Dict[str, Any]] = {}
    for r in range(1, DURACAO_PROGRAMA_ANOS + 1):
        ini_r, fim_r = obter_periodo_ano_residencia(data_inicio, r)
        fim_apurado = min(fim_r, data_limite)

        if fim_apurado >= ini_r:
            apurado = calcular_periodo(
                todos_pontos,
                ini_r,
                fim_apurado,
                data_inicio_programa=data_inicio,
                data_fim_programa=fim_programa,
            )
        else:
            apurado = calcular_periodo([], ini_r, ini_r - timedelta(days=1))

        auditoria_anos[r] = {
            "inicio": ini_r.isoformat(),
            "fim": fim_r.isoformat(),
            "meta_global_total": META_ANUAL_TOTAL,
            "meta_global_pratica": META_ANUAL_PRATICA,
            "meta_global_teoria": META_ANUAL_TEORIA,
            "realizado_total": apurado["realizado_total"],
            "realizado_pratica": apurado["realizado_pratica"],
            "realizado_teoria": apurado["realizado_teoria"],
            "restante_total": max(0.0, META_ANUAL_TOTAL - apurado["realizado_total"]),
            "restante_pratica": max(0.0, META_ANUAL_PRATICA - apurado["realizado_pratica"]),
            "restante_teoria": max(0.0, META_ANUAL_TEORIA - apurado["realizado_teoria"]),
            "dias_ferias_gozados": apurado["dias_ferias"],
            "ferias_restantes_dias": max(0, DIAS_FERIAS_ANO - apurado["dias_ferias"]),
            "minimo_85_teoria": META_ANUAL_TEORIA * FREQUENCIA_MINIMA_TEORIA,
        }

    r_atual = obter_numero_r(data_limite, data_inicio)
    if r_atual:
        ini_r_atual, fim_r_atual = obter_periodo_ano_residencia(data_inicio, r_atual)
    else:
        ini_r_atual = fim_r_atual = None

    return {
        "dados_mensais": dados_mensais,
        "totais_gerais": {
            "trabalhado": geral["realizado_total"],
            "pratica": geral["realizado_pratica"],
            "teorica": geral["realizado_teoria"],
            "ferias": geral["horas_retiradas_ferias_total"],
            "dias_ferias_gozados": geral["dias_ferias"],
            "faltas_debito": geral["horas_reposicao_total"],
            "horas_reposicao": geral["horas_reposicao_total"],
        },
        "esperado": {
            "ate_hoje": geral["esperado_total"],
            "pratica": geral["esperado_pratica"],
            "teorica": geral["esperado_teoria"],
            "curricular_bruto_ate_hoje": geral["curricular_base_total"],
            "curricular_bruto_pratica_ate_hoje": geral["curricular_base_pratica"],
            "curricular_bruto_teoria_ate_hoje": geral["curricular_base_teoria"],
            "retirado_por_ferias": geral["horas_retiradas_ferias_total"],
            "retirado_por_feriados": 0.0,  # feriado/ponto facultativo mantém a meta
            "meta_ano_atual": META_ANUAL_TOTAL,
            "meta_ano_pratica": META_ANUAL_PRATICA,
            "meta_ano_teoria": META_ANUAL_TEORIA,
            "meta_ciclo_total": META_ANUAL_TOTAL * DURACAO_PROGRAMA_ANOS,
            # compatibilidade com nome legado da UI
            "meta_ciclo_2026_2030": META_ANUAL_TOTAL * DURACAO_PROGRAMA_ANOS,
        },
        "saldos": {
            "acumulado": geral["saldo_total"],
            "pratica": geral["saldo_pratica"],
            "teorica": geral["saldo_teoria"],
        },
        "cumprido": {
            "pratica": geral["realizado_pratica"],
            "teorica": geral["realizado_teoria"],
            "total": geral["realizado_total"],
        },
        "reposicao": {
            "total": geral["horas_reposicao_total"],
            "pratica": geral["horas_reposicao_pratica"],
            "teorica": geral["horas_reposicao_teoria"],
        },
        "ano_residencia_atual": {
            "numero": r_atual,
            "inicio": ini_r_atual.isoformat() if ini_r_atual else None,
            "fim": fim_r_atual.isoformat() if fim_r_atual else None,
        },
        "auditoria_anos": auditoria_anos,
        "auditoria_semanal": auditoria_semanal,
        "por_dia": geral["por_dia"],
        "regras": {
            "meta_semanal_total": META_HORAS_SEMANA,
            "meta_semanal_pratica": META_SEMANAL_PRATICA,
            "meta_semanal_teoria": META_SEMANAL_TEORIA,
            "meta_anual_total": META_ANUAL_TOTAL,
            "meta_anual_pratica": META_ANUAL_PRATICA,
            "meta_anual_teoria": META_ANUAL_TEORIA,
            "dias_ferias_ano": DIAS_FERIAS_ANO,
            "frequencia_minima_teoria": FREQUENCIA_MINIMA_TEORIA,
        },
        "avisos": geral["avisos"],
    }
