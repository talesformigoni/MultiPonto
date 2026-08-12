from datetime import datetime, timedelta, date
import calendar

# ==========================================
# REGRAS DE NEGÓCIO E CONSTANTES DA RESIDÊNCIA
# ==========================================
PERC_PRATICA = 0.80
PERC_TEORICA = 0.20
META_HORAS_SEMANA = 60
META_HORAS_MES = 240 
HORAS_DEBITO_FALTA = 9.0  # Atualizado para a carga diária padrão
DIAS_FERIAS_ANO = 30      # Férias são 30 dias anuais (contabilizadas por dia)

def obter_metas_do_dia(data_alvo):
    # 0 = Seg, 1 = Ter, 2 = Qua, 3 = Qui, 4 = Sex, 5 = Sáb, 6 = Dom
    dia_semana = data_alvo.weekday() 

    meta_pratica = 0.0
    meta_teorica = 0.0

    # ==================================================
    # 1. CARGA DE PRÁTICA (Fixo)
    # ==================================================
    if dia_semana == 0:   meta_pratica = 9.0  # Seg
    elif dia_semana == 1: meta_pratica = 12.0 # Ter
    elif dia_semana == 2: meta_pratica = 9.0  # Qua
    elif dia_semana == 3: meta_pratica = 9.0  # Qui
    elif dia_semana == 4: meta_pratica = 9.0  # Sex
    elif dia_semana == 5: meta_pratica = 0.0  # Sáb
    elif dia_semana == 6: meta_pratica = 0.0  # Dom

    # ==================================================
    # 2. CARGA TEÓRICA (Apenas Aulas Comprováveis)
    # ==================================================
    
    # A) Descobrindo qual é a "Semana Completa do Mês" baseada na Quinta-feira.
    # Se a quinta-feira cai no mês atual, aquela é uma semana válida do mês.
    quinta_da_semana = data_alvo + timedelta(days=(3 - dia_semana))
    mes_da_semana = quinta_da_semana.month
    semana_do_mes = (quinta_da_semana.day - 1) // 7 + 1
    
    # Se a semana "pertence" a outro mês, não cobramos as metas mensais neste dia
    # para evitar cobrar duas vezes na virada do mês.
    pertence_a_este_mes = (data_alvo.month == mes_da_semana)

    # B) Eixos Transversais (Semana 1 e 2 do mês âncora)
    if pertence_a_este_mes:
        if semana_do_mes == 1:
            # Transversal: Seg e Qui (2.5h)
            if dia_semana in [0, 3]: 
                meta_teorica += 2.5
        elif semana_do_mes == 2:
            # Concentração: Seg e Qui (2.5h)
            if dia_semana in [0, 3]:
                meta_teorica += 2.5

    # C) Eixo Específico (Todas as semanas, 1x na semana)
    # Duração: 3h nas primeiras 8 semanas (a partir da 1ª semana de Maio), depois 2h.
    duracao_especifico = 3.0
    
    # A primeira quinta-feira de Maio/2026 cai no dia 07/05
    primeira_quinta_maio = date(2026, 5, 7)
    
    if quinta_da_semana >= primeira_quinta_maio:
        semanas_passadas = (quinta_da_semana - primeira_quinta_maio).days // 7
        if semanas_passadas >= 8:
            duracao_especifico = 2.0
            
    # Ancoramos a cobrança do Eixo Específico na Quarta-feira
    if dia_semana == 2:
        meta_teorica += duracao_especifico

    return meta_pratica, meta_teorica


def calcular_motor_horas(todos_pontos, data_inicio, data_hoje, lista_meses, meses_num_para_pt):
    pt_para_num = {v: k for k, v in meses_num_para_pt.items()}
    
    # 1. Inicializa o dicionário mensal com as Metas Dinâmicas do Calendário Real
    dados_mensais = {}
    
    for m in lista_meses:
        nome_mes, ano_str = m.split('/')
        mes_num = int(pt_para_num[nome_mes])
        ano_num = int(ano_str)
        
        _, dias_no_mes = calendar.monthrange(ano_num, mes_num)
        
        dt_inicio_mes = date(ano_num, mes_num, 1)
        dt_fim_mes = date(ano_num, mes_num, dias_no_mes)
        
        # Ajuste para o mês em que a residência começou
        if ano_num == data_inicio.year and mes_num == data_inicio.month:
            dt_inicio_mes = data_inicio
            
        exp_pratica_mes = 0.0
        exp_teorica_mes = 0.0
        
        curr_d = dt_inicio_mes
        while curr_d <= dt_fim_mes:
            p_dia, t_dia = obter_metas_do_dia(curr_d)
            exp_pratica_mes += p_dia
            exp_teorica_mes += t_dia
            curr_d += timedelta(days=1)
            
        dados_mensais[m] = {
            "trabalhadas": 0.0, "pratica": 0.0, "teorica": 0.0,
            "ferias": 0.0, "faltas_debito": 0.0,
            "dias_ausencia": 0, "dias_ferias_gozados": 0, "por_categoria": {},
            "meta_pratica_mes_exata": exp_pratica_mes,
            "meta_teorica_mes_exata": exp_teorica_mes,
            "meta_total_mes_exata": exp_pratica_mes + exp_teorica_mes
        }

    # 2. Inicializa os totalizadores gerais de performance do residente
    total_geral_trabalhado = 0.0
    total_geral_pratica = 0.0
    total_geral_teorica = 0.0
    
    total_geral_ferias_horas_abono = 0.0
    total_dias_ferias_gozados = 0
    ferias_pratica = 0.0
    ferias_teorica = 0.0
    
    total_geral_faltas_debito = 0.0
    faltas_pratica_debito = 0.0
    faltas_teorica_debito = 0.0

    # 3. Varre os pontos registrados no banco de dados
    for p in todos_pontos:
        cat = p.get("categoria", "")
        horas = float(p.get("horas_computadas", 0.0))
        data_str = p.get("data_registro", "")

        if data_str:
            ano_pt = data_str[0:4]
            mes_pt_num = data_str[5:7]
            chave_mes_ponto = f"{meses_num_para_pt.get(mes_pt_num, '')}/{ano_pt}"

            dt_obj = datetime.strptime(data_str, "%Y-%m-%d").date()
            meta_prat_dia, meta_teor_dia = obter_metas_do_dia(dt_obj)

            if chave_mes_ponto in dados_mensais:
                bucket = dados_mensais[chave_mes_ponto]
                if cat not in bucket["por_categoria"]:
                    bucket["por_categoria"][cat] = 0.0

                if cat in ["Prática", "Teórica", "Teórico-prática"]:
                    bucket["trabalhadas"] += horas
                    total_geral_trabalhado += horas
                    bucket["por_categoria"][cat] += horas
                    if cat == "Prática":
                        bucket["pratica"] += horas
                        total_geral_pratica += horas
                    else:
                        bucket["teorica"] += horas
                        total_geral_teorica += horas

                # APENAS Férias contam como isenção (abonam as horas exatas daquele dia)
                elif cat == "Férias":
                    credito_total_dia = meta_prat_dia + meta_teor_dia
                    bucket["ferias"] += credito_total_dia
                    bucket["dias_ferias_gozados"] += 1
                    
                    total_geral_ferias_horas_abono += credito_total_dia
                    total_dias_ferias_gozados += 1
                    
                    bucket["por_categoria"][cat] += credito_total_dia
                    ferias_pratica += meta_prat_dia
                    ferias_teorica += meta_teor_dia

                # Falta gera a penalidade fixa (dívida base)
                elif cat == "Falta":
                    debito_total_dia = meta_prat_dia + meta_teor_dia
                    bucket["faltas_debito"] += debito_total_dia
                    total_geral_faltas_debito += debito_total_dia
                    bucket["por_categoria"][cat] += debito_total_dia
                    bucket["dias_ausencia"] += 1
                    faltas_pratica_debito += meta_prat_dia
                    faltas_teorica_debito += meta_teor_dia

                # Feriados, Pontos Facultativos e demais justificativas geram a dívida natural 
                elif cat in ["Ausência justificada", "Licença", "Atestado", "ATESTADO", "Feriado", "Ponto facultativo"]:
                    bucket["dias_ausencia"] += 1
                    bucket["por_categoria"][cat] += horas

    # 4. Cálculo Dinâmico do Acumulado ATÉ HOJE
    horas_esperadas_pratica = 0.0
    horas_esperadas_teorica = 0.0
    dias_passados = (data_hoje - data_inicio).days
    
    if dias_passados >= 0:
        for i in range(dias_passados + 1):
            d = data_inicio + timedelta(days=i)
            p_dia, t_dia = obter_metas_do_dia(d)
            horas_esperadas_pratica += p_dia
            horas_esperadas_teorica += t_dia

    horas_esperadas_ate_hoje = horas_esperadas_pratica + horas_esperadas_teorica

    # 5. Cálculo para a Meta Anual exata e do Ciclo (2026 - 2030)
    ano_atual = data_hoje.year
    dt_inicio_ano = date(ano_atual, 1, 1) if ano_atual > data_inicio.year else data_inicio
    dt_fim_ano = date(ano_atual, 12, 31)
    
    meta_anual_pratica = 0.0
    meta_anual_teorica = 0.0
    
    curr_d = dt_inicio_ano
    while curr_d <= dt_fim_ano:
        p_dia, t_dia = obter_metas_do_dia(curr_d)
        meta_anual_pratica += p_dia
        meta_anual_teorica += t_dia
        curr_d += timedelta(days=1)

    dt_fim_ciclo = date(2030, 12, 31)
    meta_ciclo_total = 0.0
    curr_d = data_inicio
    while curr_d <= dt_fim_ciclo:
        p_dia, t_dia = obter_metas_do_dia(curr_d)
        meta_ciclo_total += (p_dia + t_dia)
        curr_d += timedelta(days=1)

    # 6. Cálculo dos Saldos Finais
    saldo_acumulado = (total_geral_trabalhado + total_geral_ferias_horas_abono) - total_geral_faltas_debito - horas_esperadas_ate_hoje
    saldo_pratica = (total_geral_pratica + ferias_pratica) - faltas_pratica_debito - horas_esperadas_pratica
    saldo_teorica = (total_geral_teorica + ferias_teorica) - faltas_teorica_debito - horas_esperadas_teorica

    cumprido_pratica = total_geral_pratica + ferias_pratica
    cumprido_teorica = total_geral_teorica + ferias_teorica

    # 7. Retorna os dados mapeados exatamente como a interface espera
    return {
        "dados_mensais": dados_mensais,
        "totais_gerais": {
            "trabalhado": total_geral_trabalhado,
            "pratica": total_geral_pratica,
            "teorica": total_geral_teorica,
            "ferias": total_geral_ferias_horas_abono,
            "dias_ferias_gozados": total_dias_ferias_gozados,
            "faltas_debito": total_geral_faltas_debito
        },
        "esperado": {
            "ate_hoje": horas_esperadas_ate_hoje,
            "pratica": horas_esperadas_pratica,
            "teorica": horas_esperadas_teorica,
            "meta_ano_atual": meta_anual_pratica + meta_anual_teorica,
            "meta_ciclo_2026_2030": meta_ciclo_total
        },
        "saldos": {
            "acumulado": saldo_acumulado,
            "pratica": saldo_pratica,
            "teorica": saldo_teorica
        },
        "cumprido": {
            "pratica": cumprido_pratica,
            "teorica": cumprido_teorica
        }
    }
