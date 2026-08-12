
import streamlit as st
import plotly.graph_objects as go
import calendar
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from firebase_admin import firestore
from firebase_config import db
from utils import aplicar_css, checar_login, mostrar_cabecalho


# 1. Configuracao Inicial
st.set_page_config(page_title="Dashboard | MultiPonto", layout="wide", initial_sidebar_state="collapsed")
checar_login()
aplicar_css()


# ==========================================
# MOTORES DO SISTEMA
# ==========================================
def preencher_hora_atual(chave_h, chave_m):
    agora = datetime.now(ZoneInfo("America/Porto_Velho"))
    st.session_state[chave_h] = agora.strftime("%H")
    st.session_state[chave_m] = agora.strftime("%M")


def processar_hora_separada(h_str, m_str):
    if not h_str and not m_str: return ""
    if bool(h_str) != bool(m_str): return "ERRO"
    try:
        h, m = int(h_str), int(m_str)
        if 0 <= h <= 23 and 0 <= m <= 59: return f"{h:02d}:{m:02d}"
    except ValueError: pass
    return "ERRO"


def calcular_saldo_horas(entrada_str, saida_str):
    if not entrada_str or not saida_str: return 0.0
    formato = "%H:%M"
    td_entrada = datetime.strptime(entrada_str, formato)
    td_saida = datetime.strptime(saida_str, formato)
    diferenca = td_saida - td_entrada
    segundos_totais = diferenca.total_seconds()
    if segundos_totais < 0:
        segundos_totais += 24 * 3600
    return round(segundos_totais / 3600, 2)


def formatar_horas_exatas(horas_decimais):
    sinal = "-" if horas_decimais < 0 else ""
    horas_decimais = abs(horas_decimais)
    horas = int(horas_decimais)
    minutos = int(round((horas_decimais - horas) * 60))
    if minutos == 60:
        horas += 1
        minutos = 0
    if minutos == 0: return f"{sinal}{horas}h"
    return f"{sinal}{horas}h {minutos:02d}m"


def calcular_panorama(pontos, dt_ini, dt_fim, meta_horas_semana, perc_pratica, perc_teorica, horas_credito_ferias=8.0, horas_debito_falta=8.0):
    """Calcula horas cumpridas/devidas de Pratica e Teorica dentro de um periodo,
    descontando proporcionalmente os dias de ferias da meta esperada."""
    horas_pratica = 0.0
    horas_teorica = 0.0
    horas_ferias_credito = 0.0
    horas_faltas_debito = 0.0
    dias_ferias = 0
    dias_falta = 0

    for p in pontos:
        d_str = p.get("data_registro", "")
        if not d_str:
            continue
        try:
            d_obj = date.fromisoformat(d_str)
        except ValueError:
            continue
        if not (dt_ini <= d_obj <= dt_fim):
            continue

        cat = p.get("categoria", "")
        horas = float(p.get("horas_computadas", 0.0))

        if cat == "Pratica":
            horas_pratica += horas
        elif cat in ["Teorica", "Teorico-pratica"]:
            horas_teorica += horas
        elif cat == "Ferias":
            horas_ferias_credito += horas_credito_ferias
            dias_ferias += 1
        elif cat == "Falta":
            horas_faltas_debito += horas_debito_falta
            dias_falta += 1

    dias_totais = (dt_fim - dt_ini).days + 1
    dias_uteis_efetivos = max(dias_totais - dias_ferias, 0)
    meta_diaria = meta_horas_semana / 7

    horas_esperadas_total = dias_uteis_efetivos * meta_diaria
    horas_esperadas_pratica = horas_esperadas_total * perc_pratica
    horas_esperadas_teorica = horas_esperadas_total * perc_teorica

    return {
        "horas_pratica": horas_pratica,
        "horas_teorica": horas_teorica,
        "horas_ferias_credito": horas_ferias_credito,
        "horas_faltas_debito": horas_faltas_debito,
        "dias_ferias": dias_ferias,
        "dias_falta": dias_falta,
        "dias_totais": dias_totais,
        "dias_uteis_efetivos": dias_uteis_efetivos,
        "horas_esperadas_total": horas_esperadas_total,
        "horas_esperadas_pratica": horas_esperadas_pratica,
        "horas_esperadas_teorica": horas_esperadas_teorica,
        "saldo_pratica": horas_pratica - horas_esperadas_pratica,
        "saldo_teorica": horas_teorica - horas_esperadas_teorica,
        "saldo_geral": (horas_pratica + horas_teorica + horas_ferias_credito) - horas_faltas_debito - horas_esperadas_total,
        "realizado_total": horas_pratica + horas_teorica + horas_ferias_credito - horas_faltas_debito,
    }


def renderizar_card_categoria(icone, titulo, meta_pct, devido, cumprido, saldo, cor_positivo="#16a34a", cor_negativo="#dc2626"):
    cor = cor_positivo if saldo >= 0 else cor_negativo
    sinal = "+" if saldo > 0 else ""
    st.markdown(f"""
        <div data-testid='column'>
            <div class='card-title'>{icone} {titulo} (Meta {int(meta_pct*100)}% da carga)</div>
            <div style='display:flex; gap: 20px; margin-top: 8px; flex-wrap: wrap;'>
                <div><span style='color:#6b7280; font-size:0.85rem;'>Devido</span><br><span style='font-size:1.4rem; font-weight:700; color:#111827;'>{formatar_horas_exatas(devido)}</span></div>
                <div><span style='color:#6b7280; font-size:0.85rem;'>Cumprido</span><br><span style='font-size:1.4rem; font-weight:700; color:#1e40af;'>{formatar_horas_exatas(cumprido)}</span></div>
                <div><span style='color:#6b7280; font-size:0.85rem;'>Saldo</span><br><span style='font-size:1.4rem; font-weight:700; color:{cor};'>{sinal}{formatar_horas_exatas(saldo)}</span></div>
            </div>
        </div>
    """, unsafe_allow_html=True)


# ==========================================
# LOGICA DE DATAS E CRONOGRAMA
# ==========================================
data_inicio = date(2026, 3, 9)
data_hoje = date.today()

PERC_PRATICA = 0.80
PERC_TEORICA = 0.20
META_HORAS_SEMANA = 60
HORAS_DEBITO_FALTA = 8.0
HORAS_CREDITO_FERIAS = 8.0

mostrar_cabecalho()


meses_num_para_pt = {
    "01": "Janeiro", "02": "Fevereiro", "03": "Marco", "04": "Abril",
    "05": "Maio", "06": "Junho", "07": "Julho", "08": "Agosto",
    "09": "Setembro", "10": "Outubro", "11": "Novembro", "12": "Dezembro"
}


lista_meses = []
ano_atual = data_inicio.year
mes_atual = data_inicio.month
while (ano_atual < data_hoje.year) or (ano_atual == data_hoje.year and mes_atual <= data_hoje.month):
    chave_mes = f"{meses_num_para_pt[f'{mes_atual:02d}']}/{ano_atual}"
    lista_meses.append(chave_mes)
    mes_atual += 1
    if mes_atual > 12:
        mes_atual = 1
        ano_atual += 1


lista_meses_crono = list(lista_meses)
lista_meses.reverse()


# ==========================================
# MOTOR DE CALCULO (FIREBASE)
# ==========================================
pontos_ref = db.collection("pontos").where("uid_residente", "==", st.session_state.uid).stream()
todos_pontos = [p.to_dict() for p in pontos_ref]

# Panorama do ciclo completo (usado nos 3 cards gerais e como base padrao)
panorama_ciclo = calcular_panorama(todos_pontos, data_inicio, data_hoje, META_HORAS_SEMANA, PERC_PRATICA, PERC_TEORICA, HORAS_CREDITO_FERIAS, HORAS_DEBITO_FALTA)

st.markdown(f"<p style=\'color: #6b7280; font-size: 0.95rem; margin-top: -10px; margin-bottom: 20px; margin-left: 10px;\'>Seu ciclo iniciou em <b>09/03/2026</b>. Hoje e <b>{data_hoje.strftime('%d/%m/%Y')}</b>.</p>", unsafe_allow_html=True)


# ==========================================
# MENU DE NAVEGACAO "BOXES"
# ==========================================
if "menu_atual" not in st.session_state:
    st.session_state.menu_atual = "Visao Geral"


m1, m2, m3, m4 = st.columns(4)


if m1.button("Visao Geral", use_container_width=True, type="primary" if st.session_state.menu_atual == "Visao Geral" else "secondary"):
    st.session_state.menu_atual = "Visao Geral"
    st.rerun()
if m2.button("Mensal e Semanal", use_container_width=True, type="primary" if st.session_state.menu_atual == "Mensal e Semanal" else "secondary"):
    st.session_state.menu_atual = "Mensal e Semanal"
    st.rerun()
if m3.button("Calendario Diario", use_container_width=True, type="primary" if st.session_state.menu_atual == "Calendario Diario" else "secondary"):
    st.session_state.menu_atual = "Calendario Diario"
    st.rerun()
if m4.button("Por Categoria", use_container_width=True, type="primary" if st.session_state.menu_atual == "Por Categoria" else "secondary"):
    st.session_state.menu_atual = "Por Categoria"
    st.rerun()


st.markdown("<hr style=\'margin-top: 5px; margin-bottom: 25px; border-color: #f3f4f6;\'>", unsafe_allow_html=True)


# ==========================================
# RENDERIZACAO DINAMICA DAS PAGINAS
# ==========================================


if st.session_state.menu_atual == "Visao Geral":

    st.markdown("<div class=\'card-title\' style=\'margin-bottom: 10px;\'>Panorama Geral do Ciclo</div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1: st.markdown(f"<div data-testid=\'column\'><div class=\'card-title\'>Deveria ter cumprido (Ate hoje)</div><div><span class=\'big-number\'>{formatar_horas_exatas(panorama_ciclo['horas_esperadas_total'])}</span></div></div>", unsafe_allow_html=True)
    with c2: st.markdown(f"<div data-testid=\'column\'><div class=\'card-title\'>Realizado (Trabalhadas + Ferias - Faltas)</div><div><span class=\'big-number\' style=\'color: #16a34a;\'>{formatar_horas_exatas(panorama_ciclo['realizado_total'])}</span></div></div>", unsafe_allow_html=True)
    with c3:
        saldo_geral = panorama_ciclo['saldo_geral']
        cor_saldo = "#dc2626" if saldo_geral < 0 else "#16a34a"
        texto_saldo = "Devendo" if saldo_geral < 0 else "Horas Extras"
        sinal = "+" if saldo_geral > 0 else ""
        st.markdown(f"<div data-testid=\'column\'><div class=\'card-title\'>Balanco Acumulado</div><div><span class=\'big-number\' style=\'color: {cor_saldo};\'>{sinal}{formatar_horas_exatas(saldo_geral)}</span><span style=\'color: {cor_saldo}; font-size: 0.9rem; font-weight: 600; background-color: #fee2e2; padding: 2px 8px; border-radius: 12px; display: inline-block; vertical-align: super;\'>{texto_saldo}</span></div></div>", unsafe_allow_html=True)

    st.write("")
    st.markdown("<hr style=\'margin: 10px 0px 20px 0px; border-color: #f3f4f6;\'>", unsafe_allow_html=True)

    # ==========================================
    # NOVO: FILTRO DE DATA PARA O PANORAMA POR CATEGORIA
    # ==========================================
    st.markdown("<div class=\'card-title\' style=\'margin-bottom: 10px;\'>Panorama por Tipo de Carga Horaria</div>", unsafe_allow_html=True)

    cf1, cf2, cf3 = st.columns([1, 1, 1])
    with cf1:
        filtro_inicio = st.date_input("De", value=data_inicio, min_value=data_inicio, max_value=data_hoje, format="DD/MM/YYYY", key="filtro_panorama_inicio")
    with cf2:
        filtro_fim = st.date_input("Ate", value=data_hoje, min_value=data_inicio, max_value=data_hoje, format="DD/MM/YYYY", key="filtro_panorama_fim")
    with cf3:
        st.write("")
        st.write("")
        if st.button("Ver Ciclo Completo", use_container_width=True):
            st.session_state.filtro_panorama_inicio = data_inicio
            st.session_state.filtro_panorama_fim = data_hoje
            st.rerun()

    if filtro_inicio > filtro_fim:
        st.error("A data inicial nao pode ser maior que a data final.")
        panorama_filtrado = panorama_ciclo
    else:
        panorama_filtrado = calcular_panorama(todos_pontos, filtro_inicio, filtro_fim, META_HORAS_SEMANA, PERC_PRATICA, PERC_TEORICA, HORAS_CREDITO_FERIAS, HORAS_DEBITO_FALTA)

        if panorama_filtrado["dias_ferias"] > 0:
            st.caption(f"ℹ️ {panorama_filtrado['dias_ferias']} dia(s) de ferias no periodo foram descontados da meta esperada.")

    cp1, cp2 = st.columns(2)
    with cp1:
        renderizar_card_categoria("🩺", "Pratica", PERC_PRATICA, panorama_filtrado["horas_esperadas_pratica"], panorama_filtrado["horas_pratica"], panorama_filtrado["saldo_pratica"])
    with cp2:
        renderizar_card_categoria("📚", "Teorica", PERC_TEORICA, panorama_filtrado["horas_esperadas_teorica"], panorama_filtrado["horas_teorica"], panorama_filtrado["saldo_teorica"])

    st.write("")
    st.markdown("<div data-testid=\'column\'><div class=\'card-title\'>Curva de Progressao (2026)</div>", unsafe_allow_html=True)

    dados_mensais_curva = {m: {"trabalhadas": 0.0, "ferias": 0.0, "faltas_debito": 0.0} for m in lista_meses_crono}
    for p in todos_pontos:
        cat = p.get("categoria", "")
        horas = float(p.get("horas_computadas", 0.0))
        data_str = p.get("data_registro", "")
        if data_str:
            ano_pt = data_str[0:4]
            mes_pt_num = data_str[5:7]
            chave_mes_ponto = f"{meses_num_para_pt.get(mes_pt_num, '')}/{ano_pt}"
            if chave_mes_ponto in dados_mensais_curva:
                if cat in ["Pratica", "Teorica", "Teorico-pratica"]:
                    dados_mensais_curva[chave_mes_ponto]["trabalhadas"] += horas
                elif cat == "Ferias":
                    dados_mensais_curva[chave_mes_ponto]["ferias"] += HORAS_CREDITO_FERIAS
                elif cat == "Falta":
                    dados_mensais_curva[chave_mes_ponto]["faltas_debito"] += HORAS_DEBITO_FALTA

    eixo_x_meses = []
    eixo_y_acumulado = []
    soma_curva = 0.0
    for m in lista_meses_crono:
        eixo_x_meses.append(m.split('/')[0][:3])
        soma_curva += (dados_mensais_curva[m]["trabalhadas"] + dados_mensais_curva[m]["ferias"] - dados_mensais_curva[m]["faltas_debito"])
        eixo_y_acumulado.append(soma_curva)

    fig_area = go.Figure()
    fig_area.add_trace(go.Scatter(x=eixo_x_meses, y=eixo_y_acumulado, fill='tozeroy', mode='lines+markers', line=dict(color='#16a34a', width=4, shape='spline'), marker=dict(size=8), fillcolor='rgba(22, 163, 74, 0.15)'))
    fig_area.update_layout(height=220, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis=dict(showgrid=False, zeroline=False, showline=False, color="#374151"), yaxis=dict(showgrid=True, gridcolor="#e5e7eb", zeroline=False, showline=False, tickfont=dict(color="#374151")))
    st.plotly_chart(fig_area, width='stretch', config={'displayModeBar': False})
    st.markdown("</div>", unsafe_allow_html=True)


elif st.session_state.menu_atual == "Mensal e Semanal":
    col_seletor, _ = st.columns([1, 3])
    with col_seletor: mes_foco = st.selectbox("Selecione o Mes", lista_meses)
    st.markdown("---")

    idx_mes = list(meses_num_para_pt.values()).index(mes_foco.split('/')[0]) + 1
    ano_mes_foco = int(mes_foco.split('/')[1])
    primeiro_dia_mes = date(ano_mes_foco, idx_mes, 1)
    ultimo_dia_num = calendar.monthrange(ano_mes_foco, idx_mes)[1]
    ultimo_dia_mes = date(ano_mes_foco, idx_mes, ultimo_dia_num)
    ultimo_dia_mes = min(ultimo_dia_mes, data_hoje)

    panorama_mes = calcular_panorama(todos_pontos, primeiro_dia_mes, ultimo_dia_mes, META_HORAS_SEMANA, PERC_PRATICA, PERC_TEORICA, HORAS_CREDITO_FERIAS, HORAS_DEBITO_FALTA)

    m1, m2, m3, m4 = st.columns(4)
    m1.markdown(f"<div data-testid=\'column\'><div class=\'card-title\'>Trabalhadas</div><div style=\'font-size: 1.8rem; font-weight: 700; color: #1e40af;\'>{formatar_horas_exatas(panorama_mes['horas_pratica'] + panorama_mes['horas_teorica'])}</div></div>", unsafe_allow_html=True)
    m2.markdown(f"<div data-testid=\'column\'><div class=\'card-title\'>Ferias (Credito)</div><div style=\'font-size: 1.8rem; font-weight: 700; color: #16a34a;\'>{formatar_horas_exatas(panorama_mes['horas_ferias_credito'])}</div></div>", unsafe_allow_html=True)
    m3.markdown(f"<div data-testid=\'column\'><div class=\'card-title\'>Faltas (Debito)</div><div style=\'font-size: 1.8rem; font-weight: 700; color: #dc2626;\'>{formatar_horas_exatas(panorama_mes['horas_faltas_debito'])}</div></div>", unsafe_allow_html=True)
    cor_saldo_mes = "#16a34a" if panorama_mes['saldo_geral'] >= 0 else "#dc2626"
    sinal_mes = "+" if panorama_mes['saldo_geral'] > 0 else ""
    m4.markdown(f"<div data-testid=\'column\'><div class=\'card-title\'>Saldo do Mes</div><div style=\'font-size: 1.8rem; font-weight: 700; color: {cor_saldo_mes};\'>{sinal_mes}{formatar_horas_exatas(panorama_mes['saldo_geral'])}</div></div>", unsafe_allow_html=True)

    if panorama_mes["dias_ferias"] > 0:
        st.caption(f"ℹ️ {panorama_mes['dias_ferias']} dia(s) de ferias neste mes foram descontados da meta esperada.")

    st.write("")
    mp1, mp2 = st.columns(2)
    with mp1:
        renderizar_card_categoria("🩺", "Pratica", PERC_PRATICA, panorama_mes["horas_esperadas_pratica"], panorama_mes["horas_pratica"], panorama_mes["saldo_pratica"])
    with mp2:
        renderizar_card_categoria("📚", "Teorica", PERC_TEORICA, panorama_mes["horas_esperadas_teorica"], panorama_mes["horas_teorica"], panorama_mes["saldo_teorica"])

    col_graf1, space, col_graf2 = st.columns([1, 0.05, 1])
    with col_graf1:
        st.markdown("<div class=\'card-title\'>Horas Trabalhadas (Soma por Dia da Semana)</div>", unsafe_allow_html=True)
        dias_semana_soma = {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0, 6: 0.0}
        for p in todos_pontos:
            d_str = p.get("data_registro", "")
            if d_str and p.get("categoria") in ["Pratica", "Teorica", "Teorico-pratica"]:
                try:
                    dt_obj = date.fromisoformat(d_str)
                except ValueError:
                    continue
                if primeiro_dia_mes <= dt_obj <= ultimo_dia_mes:
                    dias_semana_soma[dt_obj.weekday()] += float(p.get("horas_computadas", 0.0))

        y_semana = [dias_semana_soma[i] for i in range(7)]
        fig_bar = go.Figure(go.Bar(x=['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom'], y=y_semana, marker_color='#1e40af', width=0.5))
        fig_bar.update_layout(height=200, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis=dict(color="#374151"), yaxis=dict(color="#374151"))
        st.plotly_chart(fig_bar, width='stretch', config={'displayModeBar': False})

    with col_graf2:
        st.markdown("<div class=\'card-title\'>Distribuicao Mensal (Pratica vs Teoria)</div>", unsafe_allow_html=True)
        if panorama_mes['horas_pratica'] == 0 and panorama_mes['horas_teorica'] == 0:
            st.info("Sem horas registradas neste mes para gerar grafico.")
        else:
            fig_donut = go.Figure(data=[go.Pie(labels=['Pratica', 'Teorica'], values=[panorama_mes['horas_pratica'], panorama_mes['horas_teorica']], hole=0.65, marker=dict(colors=['#16a34a', '#1e40af']))])
            fig_donut.update_layout(height=200, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)", showlegend=True)
            st.plotly_chart(fig_donut, width='stretch', config={'displayModeBar': False})


elif st.session_state.menu_atual == "Calendario Diario":
    col_cal, col_form = st.columns([1, 1.5])

    with col_cal:
        st.markdown("<div class=\'card-title\'>1. Tipo de Lancamento</div>", unsafe_allow_html=True)

        tipo_lancamento = st.radio("Selecione:", ["Individual", "Em Lote"], horizontal=True, label_visibility="collapsed")
        st.write("")

        if tipo_lancamento == "Individual":
            st.markdown("<div style=\'font-weight: 600; font-size: 0.95rem; color: #374151; margin-bottom: 5px;\'>Selecione a Data</div>", unsafe_allow_html=True)
            data_selecionada = st.date_input("Data unica", value=data_hoje, min_value=data_inicio, max_value=data_hoje, format="DD/MM/YYYY", label_visibility="collapsed")
        else:
            st.markdown("<div style=\'font-weight: 600; font-size: 0.95rem; color: #374151; margin-bottom: 5px;\'>Selecione o Periodo (Inicio e Fim)</div>", unsafe_allow_html=True)
            st.info("Clique na data de inicio e depois na data de fim.")
            data_selecionada = st.date_input("Periodo", value=(data_hoje, data_hoje), min_value=data_inicio, max_value=data_hoje, format="DD/MM/YYYY", label_visibility="collapsed")

        st.markdown("---")

    if isinstance(data_selecionada, tuple):
        if len(data_selecionada) == 2:
            dt_inicio, dt_fim = data_selecionada
        elif len(data_selecionada) == 1:
            dt_inicio = dt_fim = data_selecionada[0]
        else:
            dt_inicio = dt_fim = data_hoje
    else:
        dt_inicio = dt_fim = data_selecionada

    is_single_day = (dt_inicio == dt_fim)

    if st.session_state.get("data_selecionada_memoria") != str(data_selecionada):
        st.session_state.modo_edicao_diario = False
        st.session_state.data_selecionada_memoria = str(data_selecionada)

    registros_existentes = []
    if is_single_day:
        registros_existentes = [p for p in todos_pontos if p.get("data_registro") == dt_inicio.isoformat()]

    if is_single_day and registros_existentes and not st.session_state.get("modo_edicao_diario", False):
        with col_cal:
            st.markdown("<div class=\'card-title\' style=\'margin-bottom: 15px;\'>Detalhes do(s) Registro(s)</div>", unsafe_allow_html=True)
            for reg in registros_existentes:
                cat_reg = reg.get('categoria', '')
                horas_reg = reg.get('horas_computadas', 0.0)

                st.markdown(f"""
                <div style="background-color: #f9fafb; border: 1px solid #e5e7eb; border-radius: 12px; padding: 15px; margin-bottom: 15px;">
                    <div style="display: flex; justify-content: space-between; border-bottom: 1px dashed #d1d5db; padding-bottom: 8px; margin-bottom: 8px;">
                        <span style="color: #6b7280; font-weight: 500;">Categoria:</span>
                        <span style="color: #111827; font-weight: 600;">{cat_reg}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="color: #6b7280; font-weight: 500;">Horas / Status:</span>
                        <div>
                            <span style="font-weight: 700; color: #1e40af; font-size: 1.1rem; margin-right: 10px;">{formatar_horas_exatas(horas_reg)}</span>
                            <span class='badge-success'>Salvo na Nuvem</span>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        with col_form:
            st.markdown("<div class=\'card-title\'>2. Resumo do Ponto</div>", unsafe_allow_html=True)
            st.info(f"**Data:** {dt_inicio.strftime('%d/%m/%Y')}\\n\\nEste dia possui **{len(registros_existentes)}** registro(s) salvo(s).")

            st.write("")
            if st.button("Lancar nova Categoria ou Editar Ponto", type="secondary", width='stretch'):
                st.session_state.modo_edicao_diario = True
                st.rerun()

    else:
        he1, me1 = st.session_state.get("ed_he1", ""), st.session_state.get("ed_me1", "")
        hs1, ms1 = st.session_state.get("ed_hs1", ""), st.session_state.get("ed_ms1", "")
        he2, me2 = st.session_state.get("ed_he2", ""), st.session_state.get("ed_me2", "")
        hs2, ms2 = st.session_state.get("ed_hs2", ""), st.session_state.get("ed_ms2", "")
        he3, me3 = st.session_state.get("ed_he3", ""), st.session_state.get("ed_me3", "")
        hs3, ms3 = st.session_state.get("ed_hs3", ""), st.session_state.get("ed_ms3", "")

        total_dinamico = 0.0
        erro_dinamico = False
        horarios_formatados = []

        for h_e, m_e, h_s, m_s in [(he1, me1, hs1, ms1), (he2, me2, hs2, ms2), (he3, me3, hs3, ms3)]:
            ent = processar_hora_separada(h_e, m_e)
            sai = processar_hora_separada(h_s, m_s)
            if ent == "ERRO" or sai == "ERRO":
                erro_dinamico = True
            elif ent and sai:
                horarios_formatados.append(f"{ent} as {sai}")
                total_dinamico += calcular_saldo_horas(ent, sai)

        with col_cal:
            cat_atual = st.session_state.get("ed_categoria", "Pratica")
            cor_calculo = "#dc2626" if erro_dinamico else "#1e40af"
            texto_calculo = "ERRO" if erro_dinamico else formatar_horas_exatas(total_dinamico)

            status_html = "<span class='badge-pending'>Nao Salvo</span>" if total_dinamico > 0 else "<span class='badge-pending'>Vazio</span>"
            if erro_dinamico: status_html = "<span class='badge-failed'>Ajuste as Horas</span>"

            st.markdown(f"""
            <div>
                <div class='card-title' style='margin-bottom: 15px;'>Detalhes do Novo Registro</div>
                <div style="background-color: #f9fafb; border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 12px; border-bottom: 1px dashed #d1d5db; padding-bottom: 10px;">
                        <span style="color: #6b7280; font-weight: 500;">Categoria:</span>
                        <span style="color: #111827; font-weight: 600;">{cat_atual}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 12px; border-bottom: 1px dashed #d1d5db; padding-bottom: 10px;">
                        <span style="color: #6b7280; font-weight: 500;">Horas:</span>
                        <span style="font-weight: 700; color: {cor_calculo}; font-size: 1.1rem;">{texto_calculo}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="color: #6b7280; font-weight: 500;">Status:</span>
                        {status_html}
                    </div>
                </div>
                <p style="margin-top: 15px; font-size: 0.85rem; color: #6b7280;">
                    <b>Nota de Inteligencia:</b> Se voce lancar uma categoria que ja existe nesta data, ela sera atualizada/substituida. Se lancar uma categoria diferente, elas vao coexistir no banco de dados!
                </p>
            </div>
            """, unsafe_allow_html=True)

        with col_form:
            if not is_single_day:
                st.markdown(f"<div class=\'card-title\' style=\'color: #1e40af;\'>2. Lancamento em Lote ({dt_inicio.strftime('%d/%m/%Y')} a {dt_fim.strftime('%d/%m/%Y')})</div>", unsafe_allow_html=True)
            elif registros_existentes:
                st.markdown("<div class=\'card-title\' style=\'color: #d97706;\'>Adicionar ou Substituir no dia</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div class=\'card-title\'>2. Lancar Novo Ponto</div>", unsafe_allow_html=True)

            edit_categoria = st.selectbox("Selecione a Categoria", ["Pratica", "Teorica", "Teorico-pratica", "Ausencia justificada", "Falta", "Ferias", "Licenca"], key="ed_categoria")
            st.markdown("<div style=\'margin-top: 15px; margin-bottom: 5px; font-weight: 600; font-size: 0.95rem; color: #374151;\'>Horarios (Deixe em branco para o dia inteiro, ex: Atestados)</div>", unsafe_allow_html=True)

            c1, c2, c3, c4 = st.columns(4)
            ed_he1 = c1.text_input("Entrada (HH)", placeholder="07", max_chars=2, key="ed_he1")
            ed_me1 = c2.text_input("Min (MM)", placeholder="00", max_chars=2, key="ed_me1")
            ed_hs1 = c3.text_input("Saida (HH)", placeholder="12", max_chars=2, key="ed_hs1")
            ed_ms1 = c4.text_input("Min (MM)", placeholder="00", max_chars=2, key="ed_ms1")
            b1, b2 = st.columns(2)
            b1.button("Puxar Hora", on_click=preencher_hora_atual, args=("ed_he1", "ed_me1"), key="ed_btn_e1", width='stretch')
            b2.button("Puxar Hora", on_click=preencher_hora_atual, args=("ed_hs1", "ed_ms1"), key="ed_btn_s1", width='stretch')

            c5, c6, c7, c8 = st.columns(4)
            ed_he2 = c5.text_input("Entrada (HH)", placeholder="13", max_chars=2, key="ed_he2")
            ed_me2 = c6.text_input("Min (MM)", placeholder="30", max_chars=2, key="ed_me2")
            ed_hs2 = c7.text_input("Saida (HH)", placeholder="17", max_chars=2, key="ed_hs2")
            ed_ms2 = c8.text_input("Min (MM)", placeholder="30", max_chars=2, key="ed_ms2")
            b3, b4 = st.columns(2)
            b3.button("Puxar Hora", on_click=preencher_hora_atual, args=("ed_he2", "ed_me2"), key="ed_btn_e2", width='stretch')
            b4.button("Puxar Hora", on_click=preencher_hora_atual, args=("ed_hs2", "ed_ms2"), key="ed_btn_s2", width='stretch')

            c9, c10, c11, c12 = st.columns(4)
            ed_he3 = c9.text_input("Entrada (HH)", placeholder="--", max_chars=2, key="ed_he3")
            ed_me3 = c10.text_input("Min (MM)", placeholder="--", max_chars=2, key="ed_me3")
            ed_hs3 = c11.text_input("Saida (HH)", placeholder="--", max_chars=2, key="ed_hs3")
            ed_ms3 = c12.text_input("Min (MM)", placeholder="--", max_chars=2, key="ed_ms3")
            b5, b6 = st.columns(2)
            b5.button("Puxar Hora", on_click=preencher_hora_atual, args=("ed_he3", "ed_me3"), key="ed_btn_e3", width='stretch')
            b6.button("Puxar Hora", on_click=preencher_hora_atual, args=("ed_hs3", "ed_ms3"), key="ed_btn_s3", width='stretch')

            edit_obs = st.text_area("Observacoes / Justificativa (Opcional)", key="ed_obs")

            st.write("")
            btn_texto = "Salvar Alteracao(oes) no Banco"
            if st.button(btn_texto, type="primary", width='stretch'):
                if erro_dinamico:
                    st.error("Horario invalido detectado na edicao. Verifique as horas e os minutos.")
                elif total_dinamico == 0 and edit_categoria not in ["Ausencia justificada", "Falta", "Ferias", "Licenca"]:
                    st.error("Voce precisa preencher ao menos um horario para esta categoria.")
                else:
                    try:
                        num_dias = (dt_fim - dt_inicio).days + 1

                        for i in range(num_dias):
                            data_loop = dt_inicio + timedelta(days=i)
                            doc_id = f"{st.session_state.uid}_{data_loop.strftime('%Y-%m-%d')}_{edit_categoria.replace(' ', '')}"

                            dados_ponto = {
                                "uid_residente": st.session_state.uid,
                                "data_registro": data_loop.isoformat(),
                                "mes_referencia": data_loop.strftime("%m/%Y"),
                                "categoria": edit_categoria,
                                "horas_computadas": total_dinamico,
                                "horarios_descritos": horarios_formatados,
                                "justificativa": edit_obs,
                                "ultima_edicao": firestore.SERVER_TIMESTAMP
                            }
                            db.collection("pontos").document(doc_id).set(dados_ponto)

                        st.session_state.modo_edicao_diario = False
                        msg_sucesso = f"Ponto de {dt_inicio.strftime('%d/%m/%Y')} salvo com sucesso!"
                        if num_dias > 1:
                            msg_sucesso = f"{num_dias} dias lancados em lote com sucesso!"
                        st.success(msg_sucesso)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar no banco de dados: {e}")

            if registros_existentes and is_single_day:
                if st.button("Cancelar Edicao", width='stretch'):
                    st.session_state.modo_edicao_diario = False
                    st.rerun()


elif st.session_state.menu_atual == "Por Categoria":
    col_cat_sel, _ = st.columns([1, 2])
    with col_cat_sel: cat_analise = st.selectbox("Filtrar por Categoria", ["Pratica", "Teorica", "Teorico-pratica", "Ausencia justificada", "Falta", "Ferias", "Licenca"])
    st.markdown("---")

    cor_cat = "#16a34a"
    if cat_analise == "Falta": cor_cat = "#dc2626"
    elif cat_analise in ["Ausencia justificada", "Ferias", "Licenca"]: cor_cat = "#6b7280"
    elif cat_analise in ["Teorica", "Teorico-pratica"]: cor_cat = "#1e40af"

    soma_historica_cat = 0.0
    evolucao_cat_y = []
    dados_por_categoria_mes = {m: 0.0 for m in lista_meses_crono}
    for p in todos_pontos:
        cat = p.get("categoria", "")
        if cat != cat_analise:
            continue
        horas = float(p.get("horas_computadas", 0.0))
        data_str = p.get("data_registro", "")
        if data_str:
            ano_pt = data_str[0:4]
            mes_pt_num = data_str[5:7]
            chave_mes_ponto = f"{meses_num_para_pt.get(mes_pt_num, '')}/{ano_pt}"
            if chave_mes_ponto in dados_por_categoria_mes:
                dados_por_categoria_mes[chave_mes_ponto] += horas

    for m in lista_meses_crono:
        valor_mes_cat = dados_por_categoria_mes[m]
        soma_historica_cat += valor_mes_cat
        evolucao_cat_y.append(valor_mes_cat)

    c1, c2 = st.columns([1, 2])
    with c1:
        st.markdown(f"""
            <div data-testid=\'column\'>
                <div class=\'card-title\'>Total Lancado: {cat_analise}</div>
                <div><span class=\'big-number\' style=\'color: {cor_cat};\'>{formatar_horas_exatas(soma_historica_cat)}</span></div>
                <div style=\'color: #6b7280; font-size: 0.85rem; margin-top: 5px;\'>Acumulado desde o inicio do ciclo.</div>
            </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown("<div class=\'card-title\'>Evolucao Mensal desta Categoria</div>", unsafe_allow_html=True)
        if sum(evolucao_cat_y) == 0:
            st.info(f"Nenhum registro de '{cat_analise}' encontrado.")
        else:
            eixo_x_meses_abrev = [m.split('/')[0][:3] for m in lista_meses_crono]
            fig_cat = go.Figure(go.Bar(x=eixo_x_meses_abrev, y=evolucao_cat_y, marker_color=cor_cat, width=0.4))
            fig_cat.update_layout(height=180, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis=dict(color="#374151"), yaxis=dict(color="#374151"))
            st.plotly_chart(fig_cat, width='stretch', config={'displayModeBar': False})
