import streamlit as st
import plotly.graph_objects as go
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from firebase_admin import firestore
from firebase_config import db
from utils import aplicar_css, checar_login, mostrar_cabecalho

# === NOVO: IMPORTANDO O MOTOR DE CÁLCULO ===
from calculadora_horas import (
    calcular_motor_horas, 
    obter_metas_do_dia, 
    PERC_PRATICA, PERC_TEORICA, 
    META_HORAS_SEMANA, META_HORAS_MES, 
    HORAS_DEBITO_FALTA, DIAS_FERIAS_ANO
)

# 1. Configuração Inicial
st.set_page_config(page_title="Dashboard | MultiPonto", layout="wide", initial_sidebar_state="collapsed")
checar_login()
aplicar_css()


# ==========================================
# FUNÇÕES DE UI E FORMATAÇÃO
# ==========================================
def preencher_hora_atual(chave_h, chave_m):
    """Fuso único e correto: Rondônia não observa horário de verão."""
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

def checar_sobreposicao(novos_horarios, registros_existentes, cat_atual):
    for reg in registros_existentes:
        # Se for a mesma categoria, o sistema vai sobrescrever, então liberamos!
        if reg.get("categoria") == cat_atual: continue 
        
        for h_existente in reg.get("horarios_descritos", []):
            if " às " not in h_existente: continue
            ent_ex, sai_ex = h_existente.split(" às ")
            t_ent_ex = datetime.strptime(ent_ex.strip(), "%H:%M")
            t_sai_ex = datetime.strptime(sai_ex.strip(), "%H:%M")
            
            for h_novo in novos_horarios:
                ent_nv, sai_nv = h_novo.split(" às ")
                t_ent_nv = datetime.strptime(ent_nv.strip(), "%H:%M")
                t_sai_nv = datetime.strptime(sai_nv.strip(), "%H:%M")
                
                # A mágica matemática que detecta se os horários se cruzam
                if max(t_ent_ex, t_ent_nv) < min(t_sai_ex, t_sai_nv):
                    return True
    return False


# ==========================================
# LÓGICA DE DATAS E CRONOGRAMA
# ==========================================
data_inicio = date(2026, 3, 2)
data_hoje = date.today()

mostrar_cabecalho()

meses_num_para_pt = {
    "01": "Janeiro", "02": "Fevereiro", "03": "Março", "04": "Abril",
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
# REQUISIÇÃO AO FIREBASE E MOTOR DE CÁLCULO
# ==========================================
pontos_ref = db.collection("pontos").where("uid_residente", "==", st.session_state.uid).stream()
todos_pontos = []
for p in pontos_ref:
    d = p.to_dict()
    d["doc_id"] = p.id # Salvando o ID para a lixeira funcionar!
    todos_pontos.append(d)

# MÁGICA AQUI: O motor externo faz todo o cálculo pesado e devolve os resultados
resultados_calculo = calcular_motor_horas(todos_pontos, data_inicio, data_hoje, lista_meses, meses_num_para_pt)

# Desempacotando as variáveis para que a Interface visual continue funcionando sem nenhuma alteração
dados_mensais = resultados_calculo["dados_mensais"]

total_geral_trabalhado = resultados_calculo["totais_gerais"]["trabalhado"]
total_geral_pratica = resultados_calculo["totais_gerais"]["pratica"]
total_geral_teorica = resultados_calculo["totais_gerais"]["teorica"]
total_geral_ferias = resultados_calculo["totais_gerais"]["ferias"]
total_geral_faltas_debito = resultados_calculo["totais_gerais"]["faltas_debito"]

horas_esperadas_ate_hoje = resultados_calculo["esperado"]["ate_hoje"]
horas_esperadas_pratica = resultados_calculo["esperado"]["pratica"]
horas_esperadas_teorica = resultados_calculo["esperado"]["teorica"]

saldo_acumulado = resultados_calculo["saldos"]["acumulado"]
saldo_pratica = resultados_calculo["saldos"]["pratica"]
saldo_teorica = resultados_calculo["saldos"]["teorica"]

cumprido_pratica = resultados_calculo["cumprido"]["pratica"]
cumprido_teorica = resultados_calculo["cumprido"]["teorica"]


st.markdown(f"<p style='color: #6b7280; font-size: 0.95rem; margin-top: -10px; margin-bottom: 20px; margin-left: 10px;'>Seu ciclo iniciou em <b>02/03/2026</b>. Hoje é <b>{data_hoje.strftime('%d/%m/%Y')}</b>.</p>", unsafe_allow_html=True)


# ==========================================
# MENU DE NAVEGAÇÃO "BOXES"
# ==========================================
if "menu_atual" not in st.session_state:
    st.session_state.menu_atual = "Visão Geral"

m1, m2, m3, m4 = st.columns(4)

if m1.button("📊 Visão Geral", use_container_width=True, type="primary" if st.session_state.menu_atual == "Visão Geral" else "secondary"):
    st.session_state.menu_atual = "Visão Geral"
    st.rerun()
if m2.button("📅 Mensal e Semanal", use_container_width=True, type="primary" if st.session_state.menu_atual == "Mensal e Semanal" else "secondary"):
    st.session_state.menu_atual = "Mensal e Semanal"
    st.rerun()
if m3.button("✏️ Calendário Diário", use_container_width=True, type="primary" if st.session_state.menu_atual == "Calendário Diário" else "secondary"):
    st.session_state.menu_atual = "Calendário Diário"
    st.rerun()
if m4.button("🏷️ Por Categoria", use_container_width=True, type="primary" if st.session_state.menu_atual == "Por Categoria" else "secondary"):
    st.session_state.menu_atual = "Por Categoria"
    st.rerun()

st.markdown("<hr style='margin-top: 5px; margin-bottom: 25px; border-color: #f3f4f6;'>", unsafe_allow_html=True)


# ==========================================
# RENDERIZAÇÃO DINÂMICA DAS PÁGINAS
# ==========================================

if st.session_state.menu_atual == "Visão Geral":

    st.markdown("<div class='card-title' style='margin-bottom: 10px;'>Filtro Inteligente de Período</div>", unsafe_allow_html=True)

    meses_opcoes = lista_meses_crono
    
    # Barra de arrastar para selecionar o intervalo de meses
    mes_inicio, mes_fim = st.select_slider(
        "Arraste para escolher o intervalo de meses para análise:",
        options=meses_opcoes,
        value=(meses_opcoes[0], meses_opcoes[-1])
    )

    # --- Lógica do Motor Dinâmico (Lê o calendário exato do intervalo) ---
    import calendar
    pt_para_num = {v: k for k, v in meses_num_para_pt.items()}

    # Descobrindo o primeiro dia do mês inicial
    n_ini, a_ini = mes_inicio.split('/')
    dt_ini_periodo = date(int(a_ini), int(pt_para_num[n_ini]), 1)
    if dt_ini_periodo < data_inicio: 
        dt_ini_periodo = data_inicio

    # Descobrindo o último dia do mês final
    n_fim, a_fim = mes_fim.split('/')
    m_fim_num = int(pt_para_num[n_fim])
    a_fim_num = int(a_fim)
    _, dias_no_mes_fim = calendar.monthrange(a_fim_num, m_fim_num)
    dt_fim_periodo = date(a_fim_num, m_fim_num, dias_no_mes_fim)

    # O sistema limita a cobrança apenas até o dia de hoje
    if dt_fim_periodo > data_hoje: 
        dt_fim_periodo = data_hoje

    # --- Cálculos Dinâmicos ---
    dyn_exp_pratica = 0.0
    dyn_exp_teorica = 0.0

    if dt_ini_periodo <= dt_fim_periodo:
        curr_d = dt_ini_periodo
        while curr_d <= dt_fim_periodo:
            p_dia, t_dia = obter_metas_do_dia(curr_d)
            dyn_exp_pratica += p_dia
            dyn_exp_teorica += t_dia
            curr_d += timedelta(days=1)

    dyn_exp_total = dyn_exp_pratica + dyn_exp_teorica

    dyn_real_pratica = 0.0
    dyn_real_teorica = 0.0
    dyn_ferias_prat = 0.0
    dyn_ferias_teor = 0.0
    dyn_faltas_prat = 0.0
    dyn_faltas_teor = 0.0

    # Varrendo o banco de dados apenas no período selecionado
    for p in todos_pontos:
        d_str = p.get("data_registro", "")
        if not d_str: continue
        d_obj = datetime.strptime(d_str, "%Y-%m-%d").date()

        if dt_ini_periodo <= d_obj <= dt_fim_periodo:
            cat = p.get("categoria", "")
            horas = float(p.get("horas_computadas", 0.0))
            p_dia, t_dia = obter_metas_do_dia(d_obj)

            if cat == "Prática": dyn_real_pratica += horas
            elif cat in ["Teórica", "Teórico-prática"]: dyn_real_teorica += horas
            elif cat == "Férias":
                dyn_ferias_prat += p_dia
                dyn_ferias_teor += t_dia
            elif cat == "Falta":
                dyn_faltas_prat += p_dia
                dyn_faltas_teor += t_dia

    # Matemática dos Saldos
    dyn_saldo_pratica = (dyn_real_pratica + dyn_ferias_prat) - dyn_faltas_prat - dyn_exp_pratica
    dyn_saldo_teorica = (dyn_real_teorica + dyn_ferias_teor) - dyn_faltas_teor - dyn_exp_teorica
    dyn_saldo_total = dyn_saldo_pratica + dyn_saldo_teorica

    dyn_cumprido_pratica = dyn_real_pratica + dyn_ferias_prat
    dyn_cumprido_teorica = dyn_real_teorica + dyn_ferias_teor
    dyn_cumprido_total = dyn_cumprido_pratica + dyn_cumprido_teorica

    # ==============================================================
    # RENDERIZAÇÃO DA INTERFACE (CONSOLIDADO E SEPARADO)
    # ==============================================================
    
    st.markdown(f"<div class='card-title' style='margin-top: 20px; margin-bottom: 10px;'>📊 Balanço Consolidado: Prática + Teoria ({mes_inicio} a {mes_fim})</div>", unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns(3)
    with c1: 
        st.markdown(f"<div data-testid='column'><div class='card-title'>Deveria ter cumprido (Meta)</div><div><span class='big-number'>{formatar_horas_exatas(dyn_exp_total)}</span></div></div>", unsafe_allow_html=True)
    with c2: 
        st.markdown(f"<div data-testid='column'><div class='card-title'>Realizado (Trabalhadas + Férias)</div><div><span class='big-number' style='color: #16a34a;'>{formatar_horas_exatas(dyn_cumprido_total - (dyn_faltas_prat+dyn_faltas_teor))}</span></div></div>", unsafe_allow_html=True)
    with c3:
        cor_saldo = "#dc2626" if dyn_saldo_total < 0 else "#16a34a"
        texto_saldo = "Devendo Juntos" if dyn_saldo_total < 0 else "Horas Extras Juntos"
        sinal = "+" if dyn_saldo_total > 0 else ""
        st.markdown(f"<div data-testid='column'><div class='card-title'>Balanço Total</div><div><span class='big-number' style='color: {cor_saldo};'>{sinal}{formatar_horas_exatas(dyn_saldo_total)}</span><span style='color: {cor_saldo}; font-size: 0.9rem; font-weight: 600; background-color: #fee2e2; padding: 2px 8px; border-radius: 12px; display: inline-block; vertical-align: super;'>{texto_saldo}</span></div></div>", unsafe_allow_html=True)

    st.markdown("<hr style='margin: 25px 0; border-color: #e5e7eb;'>", unsafe_allow_html=True)
    st.markdown(f"<div class='card-title' style='margin-bottom: 15px;'>🔍 Balanço Detalhado: Prática e Teoria Separados</div>", unsafe_allow_html=True)

    cp1, cp2 = st.columns(2)
    with cp1:
        cor_pratica = "#dc2626" if dyn_saldo_pratica < 0 else "#16a34a"
        sinal_pratica = "+" if dyn_saldo_pratica > 0 else ""
        texto_prat = "DÍVIDA" if dyn_saldo_pratica < 0 else "SALDO EXTRA"
        bg_prat = "#fef2f2" if dyn_saldo_pratica < 0 else "#f0fdf4"

        st.markdown(f"""
            <div style='background-color: #f8fafc; border: 1px solid #e5e7eb; border-left: 5px solid #1e40af; border-radius: 8px; padding: 15px;'>
                <div style='font-size: 1.1rem; font-weight: 700; color: #111827; margin-bottom: 12px;'>🩺 Apenas Prática</div>
                <div style='display:flex; justify-content: space-between; margin-bottom: 10px; border-bottom: 1px dashed #d1d5db; padding-bottom: 5px;'>
                    <span style='color:#6b7280; font-weight: 600;'>Meta do Período:</span>
                    <span style='font-weight:700; color:#111827;'>{formatar_horas_exatas(dyn_exp_pratica)}</span>
                </div>
                <div style='display:flex; justify-content: space-between; margin-bottom: 10px; border-bottom: 1px dashed #d1d5db; padding-bottom: 5px;'>
                    <span style='color:#6b7280; font-weight: 600;'>Cumprido (c/ Férias):</span>
                    <span style='font-weight:700; color:#1e40af;'>{formatar_horas_exatas(dyn_cumprido_pratica)}</span>
                </div>
                <div style='display:flex; justify-content: space-between; align-items: center; background-color: {bg_prat}; padding: 10px; border-radius: 6px; border: 1px solid {cor_pratica}40;'>
                    <span style='color:{cor_pratica}; font-weight: 800; font-size: 0.9rem;'>{texto_prat} DE PRÁTICA:</span>
                    <span style='font-size:1.5rem; font-weight:800; color:{cor_pratica};'>{sinal_pratica}{formatar_horas_exatas(dyn_saldo_pratica)}</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

    with cp2:
        cor_teorica = "#dc2626" if dyn_saldo_teorica < 0 else "#16a34a"
        sinal_teorica = "+" if dyn_saldo_teorica > 0 else ""
        texto_teo = "DÍVIDA" if dyn_saldo_teorica < 0 else "SALDO EXTRA"
        bg_teo = "#fef2f2" if dyn_saldo_teorica < 0 else "#f0fdf4"

        st.markdown(f"""
            <div style='background-color: #f8fafc; border: 1px solid #e5e7eb; border-left: 5px solid #d97706; border-radius: 8px; padding: 15px;'>
                <div style='font-size: 1.1rem; font-weight: 700; color: #111827; margin-bottom: 12px;'>📚 Apenas Teórica</div>
                <div style='display:flex; justify-content: space-between; margin-bottom: 10px; border-bottom: 1px dashed #d1d5db; padding-bottom: 5px;'>
                    <span style='color:#6b7280; font-weight: 600;'>Meta do Período:</span>
                    <span style='font-weight:700; color:#111827;'>{formatar_horas_exatas(dyn_exp_teorica)}</span>
                </div>
                <div style='display:flex; justify-content: space-between; margin-bottom: 10px; border-bottom: 1px dashed #d1d5db; padding-bottom: 5px;'>
                    <span style='color:#6b7280; font-weight: 600;'>Cumprido (c/ Férias):</span>
                    <span style='font-weight:700; color:#1e40af;'>{formatar_horas_exatas(dyn_cumprido_teorica)}</span>
                </div>
                <div style='display:flex; justify-content: space-between; align-items: center; background-color: {bg_teo}; padding: 10px; border-radius: 6px; border: 1px solid {cor_teorica}40;'>
                    <span style='color:{cor_teorica}; font-weight: 800; font-size: 0.9rem;'>{texto_teo} DE TEORIA:</span>
                    <span style='font-size:1.5rem; font-weight:800; color:{cor_teorica};'>{sinal_teorica}{formatar_horas_exatas(dyn_saldo_teorica)}</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

    st.write("")
    st.markdown("<div data-testid='column'><div class='card-title' style='margin-top: 15px;'>Curva de Progressão Acumulada (Global)</div>", unsafe_allow_html=True)

    eixo_x_meses = []
    eixo_y_acumulado = []
    soma_curva = 0.0
    for m in lista_meses_crono:
        eixo_x_meses.append(m.split('/')[0][:3])
        soma_curva += (dados_mensais[m]["trabalhadas"] + dados_mensais[m]["ferias"] - dados_mensais[m]["faltas_debito"])
        eixo_y_acumulado.append(soma_curva)

    fig_area = go.Figure()
    fig_area.add_trace(go.Scatter(x=eixo_x_meses, y=eixo_y_acumulado, fill='tozeroy', mode='lines+markers', line=dict(color='#16a34a', width=4, shape='spline'), marker=dict(size=8), fillcolor='rgba(22, 163, 74, 0.15)'))
    fig_area.update_layout(height=220, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis=dict(showgrid=False, zeroline=False, showline=False, color="#374151"), yaxis=dict(showgrid=True, gridcolor="#e5e7eb", zeroline=False, showline=False, tickfont=dict(color="#374151")))
    st.plotly_chart(fig_area, width='stretch', config={'displayModeBar': False})
    st.markdown("</div>", unsafe_allow_html=True)


elif st.session_state.menu_atual == "Mensal e Semanal":
    # 1. SELETORES DE MÊS E FILTRO 
    col_seletor, col_filtro = st.columns([1, 1])
    with col_seletor: 
        mes_foco = st.selectbox("📅 Selecione o Mês", lista_meses)
    with col_filtro:
        opcoes_filtro = ["Todas as Categorias", "Prática", "Teórica", "Ausência justificada", "Falta", "Férias", "Feriado" "Licença", "Atestado", "Ponto Facultativo"]
        cat_filtro = st.selectbox("🏷️ Filtrar Registros Específicos", opcoes_filtro)
    st.markdown("---")

    # --- NOVA MÁGICA: CÁLCULO EXATO DO MÊS (Dia a Dia, Minuto a Minuto) ---
    import calendar
    from datetime import date, timedelta
    
    pt_para_num = {v: k for k, v in meses_num_para_pt.items()}
    nome_mes, ano_str = mes_foco.split('/')
    mes_num = int(pt_para_num[nome_mes])
    ano_num = int(ano_str)
    
    _, dias_no_mes = calendar.monthrange(ano_num, mes_num)
    dt_inicio_mes = date(ano_num, mes_num, 1)
    dt_fim_mes = date(ano_num, mes_num, dias_no_mes)
    
    # Ajuste para o mês de início da residência
    if ano_num == data_inicio.year and mes_num == data_inicio.month:
        dt_inicio_mes = data_inicio
        
    # O sistema só cobra a meta até o dia de hoje (se for o mês atual)
    if ano_num == data_hoje.year and mes_num == data_hoje.month:
        dt_fim_mes = data_hoje
    elif date(ano_num, mes_num, 1) > data_hoje:
        dt_fim_mes = dt_inicio_mes - timedelta(days=1)
        
    meta_pratica_mes = 0.0
    meta_teorica_mes = 0.0
    
    curr_d = dt_inicio_mes
    while curr_d <= dt_fim_mes:
        p_dia, t_dia = obter_metas_do_dia(curr_d)
        meta_pratica_mes += p_dia
        meta_teorica_mes += t_dia
        curr_d += timedelta(days=1)
        
    meta_mes_dinamica = meta_pratica_mes + meta_teorica_mes

    dados_foco = dados_mensais[mes_foco]
    
    # Saldos reais globais do mês EXATOS baseados no calendário lido acima
    saldo_mes = (dados_foco["trabalhadas"] + dados_foco["ferias"]) - meta_mes_dinamica
    saldo_pratica_mes = (dados_foco["pratica"] + (dados_foco["ferias"] * PERC_PRATICA)) - meta_pratica_mes
    saldo_teorica_mes = (dados_foco["teorica"] + (dados_foco["ferias"] * PERC_TEORICA)) - meta_teorica_mes

    cor_saldo_mes = "#16a34a" if saldo_mes >= 0 else "#dc2626"
    sinal_mes = "+" if saldo_mes > 0 else ""

    m1, m2, m3, m4 = st.columns(4)
    m1.markdown(f"<div data-testid='column'><div class='card-title'>Trabalhadas</div><div style='font-size: 1.8rem; font-weight: 700; color: #1e40af;'>{formatar_horas_exatas(dados_foco['trabalhadas'])}</div></div>", unsafe_allow_html=True)
    m2.markdown(f"<div data-testid='column'><div class='card-title'>Férias (Crédito)</div><div style='font-size: 1.8rem; font-weight: 700; color: #16a34a;'>{formatar_horas_exatas(dados_foco['ferias'])}</div></div>", unsafe_allow_html=True)
    m3.markdown(f"<div data-testid='column'><div class='card-title'>Ausências/Faltas</div><div style='font-size: 1.8rem; font-weight: 700; color: #dc2626;'>{dados_foco['dias_ausencia']} dias</div></div>", unsafe_allow_html=True)
    m4.markdown(f"<div data-testid='column'><div class='card-title'>Saldo do Mês</div><div style='font-size: 1.8rem; font-weight: 700; color: {cor_saldo_mes};'>{sinal_mes}{formatar_horas_exatas(saldo_mes)}</div></div>", unsafe_allow_html=True)

    st.write("")
    
    # =========================================================
    # NOVO VISUAL DETALHADO PARA PRÁTICA E TEÓRICA
    # =========================================================
    mp1, mp2 = st.columns(2)
    with mp1:
        cor_p = "#16a34a" if saldo_pratica_mes >= 0 else "#dc2626"
        sinal_p = "+" if saldo_pratica_mes > 0 else "-"
        texto_saldo_p = "Horas em Crédito" if saldo_pratica_mes >= 0 else "Horas em Débito"
        
        st.markdown(f"""
        <div data-testid='column' style='background-color: #f8fafc; padding: 15px; border-radius: 8px; border: 1px solid #e5e7eb; border-left: 4px solid #1e40af;'>
            <div class='card-title' style='margin-bottom: 12px; color: #111827;'>🩺 Prática (Meta: {formatar_horas_exatas(meta_pratica_mes)})</div>
            <div style='display: flex; justify-content: space-between; border-bottom: 1px dashed #d1d5db; padding-bottom: 8px; margin-bottom: 8px;'>
                <span style='color: #4b5563; font-weight: 600;'>Horas cumpridas no mês:</span>
                <span style='font-weight: 700; color: #1e40af; font-size: 1.1rem;'>{formatar_horas_exatas(dados_foco['pratica'])}</span>
            </div>
            <div style='display: flex; justify-content: space-between; align-items: center; margin-top: 5px;'>
                <span style='color: {cor_p}; font-weight: 700;'>{texto_saldo_p}:</span>
                <span style='font-weight: 800; color: {cor_p}; font-size: 1.3rem;'>{sinal_p}{formatar_horas_exatas(abs(saldo_pratica_mes))}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with mp2:
        cor_t = "#16a34a" if saldo_teorica_mes >= 0 else "#dc2626"
        sinal_t = "+" if saldo_teorica_mes > 0 else "-"
        texto_saldo_t = "Horas em Crédito" if saldo_teorica_mes >= 0 else "Horas em Débito"
        
        st.markdown(f"""
        <div data-testid='column' style='background-color: #f8fafc; padding: 15px; border-radius: 8px; border: 1px solid #e5e7eb; border-left: 4px solid #d97706;'>
            <div class='card-title' style='margin-bottom: 12px; color: #111827;'>📚 Teórica (Meta: {formatar_horas_exatas(meta_teorica_mes)})</div>
            <div style='display: flex; justify-content: space-between; border-bottom: 1px dashed #d1d5db; padding-bottom: 8px; margin-bottom: 8px;'>
                <span style='color: #4b5563; font-weight: 600;'>Horas cumpridas no mês:</span>
                <span style='font-weight: 700; color: #d97706; font-size: 1.1rem;'>{formatar_horas_exatas(dados_foco['teorica'])}</span>
            </div>
            <div style='display: flex; justify-content: space-between; align-items: center; margin-top: 5px;'>
                <span style='color: {cor_t}; font-weight: 700;'>{texto_saldo_t}:</span>
                <span style='font-weight: 800; color: {cor_t}; font-size: 1.3rem;'>{sinal_t}{formatar_horas_exatas(abs(saldo_teorica_mes))}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    # =========================================================

    col_graf1, space, col_graf2 = st.columns([1, 0.05, 1])
    with col_graf1:
        st.markdown("<div class='card-title'>Horas Trabalhadas (Soma por Dia da Semana)</div>", unsafe_allow_html=True)
        dias_semana_soma = {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0, 6: 0.0}
        for p in todos_pontos:
            d_str = p.get("data_registro", "")
            if d_str and p.get("categoria") in ["Prática", "Teórica", "Teórico-prática"]:
                ano_pt = d_str[0:4]
                mes_pt_num = d_str[5:7]
                if f"{meses_num_para_pt.get(mes_pt_num, '')}/{ano_pt}" == mes_foco:
                    dt_obj = datetime.strptime(d_str, "%Y-%m-%d")
                    dias_semana_soma[dt_obj.weekday()] += float(p.get("horas_computadas", 0.0))

        y_semana = [dias_semana_soma[i] for i in range(7)]
        fig_bar = go.Figure(go.Bar(x=['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'], y=y_semana, marker_color='#1e40af', width=0.5))
        fig_bar.update_layout(height=200, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis=dict(color="#374151"), yaxis=dict(color="#374151"))
        st.plotly_chart(fig_bar, width='stretch', config={'displayModeBar': False})

    with col_graf2:
        st.markdown("<div class='card-title'>Distribuição Mensal (Prática vs Teoria)</div>", unsafe_allow_html=True)
        if dados_foco['pratica'] == 0 and dados_foco['teorica'] == 0:
            st.info("Sem horas registradas neste mês para gerar gráfico.")
        else:
            fig_donut = go.Figure(data=[go.Pie(labels=['Prática', 'Teórica'], values=[dados_foco['pratica'], dados_foco['teorica']], hole=0.65, marker=dict(colors=['#16a34a', '#1e40af']))])
            fig_donut.update_layout(height=200, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)", showlegend=True)
            st.plotly_chart(fig_donut, width='stretch', config={'displayModeBar': False})

    # --- TABELA DE DETALHAMENTO, LEGENDA E EXPORTAÇÃO ---
    st.markdown("<hr style='margin-top: 30px;'>", unsafe_allow_html=True)
    
    titulo_tabela = f"🗂️ Lista de Registros ({cat_filtro})" if cat_filtro != "Todas as Categorias" else "🗂️ Lista Completa de Registros do Mês"
    st.markdown(f"<div class='card-title'>{titulo_tabela}</div>", unsafe_allow_html=True)
    
    pontos_mes_export = []
    for p in todos_pontos:
        d_str = p.get("data_registro", "")
        if d_str:
            if f"{meses_num_para_pt.get(d_str[5:7], '')}/{d_str[0:4]}" == mes_foco:
                if cat_filtro == "Todas as Categorias" or p.get("categoria", "") == cat_filtro:
                    pontos_mes_export.append(p)
                    
    pontos_mes_export = sorted(pontos_mes_export, key=lambda k: k.get("data_registro", ""))
    
    # 1. Renderiza a Tabela
    if pontos_mes_export:
        tabela_visual = []
        for p in pontos_mes_export:
            tabela_visual.append({
                "Data": "/".join(p.get("data_registro", "").split("-")[::-1]),
                "Categoria": p.get("categoria", ""),
                "Horários Lançados": " | ".join(p.get("horarios_descritos", [])),
                "Horas": formatar_horas_exatas(float(p.get("horas_computadas", 0))), # <--- SOLUÇÃO APLICADA
                "Observações / Justificativa": p.get("justificativa", "")
            })
        st.dataframe(tabela_visual, use_container_width=True)
        
        # 2. Motor da LEGENDA DINÂMICA INTELIGENTE
        soma_horas_filtro = sum(float(p.get("horas_computadas", 0.0)) for p in pontos_mes_export)
        
        categorias_ausencia = ["Ausência justificada", "Falta", "Licença", "Atestado", "ATESTADO", "Ponto Facultativo"]
        dias_ausencia_filtro = sum(1 for p in pontos_mes_export if p.get("categoria", "") in categorias_ausencia)
        
        # O Saldo exibido na legenda foca agora estritamente na PRÁTICA (salvo se filtrado por teoria)
        if cat_filtro in ["Teórica", "Teórico-prática"]:
            saldo_real_exibir = saldo_teorica_mes
        else:
            saldo_real_exibir = saldo_pratica_mes
            
        # Inteligência visual: muda a cor e o título baseado no saldo
        if saldo_real_exibir < 0:
            titulo_saldo = "DÍVIDA REAL DO MÊS"
            cor_saldo = "#dc2626" # Vermelho
            texto_saldo = f"-{formatar_horas_exatas(abs(saldo_real_exibir))}"
        else:
            titulo_saldo = "SALDO EXTRA DO MÊS"
            cor_saldo = "#16a34a" # Verde
            texto_saldo = f"+{formatar_horas_exatas(saldo_real_exibir)}"
            
        st.markdown(f"""
        <div style='display: flex; gap: 20px; padding: 15px; background-color: #f8fafc; border: 1px solid #e5e7eb; border-left: 5px solid #1e40af; border-radius: 8px; margin-top: -10px; margin-bottom: 25px;'>
            <div style='flex: 1;'>
                <div style='color: #6b7280; font-size: 0.85rem; font-weight: 600; text-transform: uppercase;'>Horas Computadas ({cat_filtro})</div>
                <div style='color: #1e40af; font-size: 1.5rem; font-weight: 700;'>{formatar_horas_exatas(soma_horas_filtro)}</div>
            </div>
            <div style='flex: 1; border-left: 1px solid #e5e7eb; padding-left: 20px;'>
                <div style='color: #6b7280; font-size: 0.85rem; font-weight: 600; text-transform: uppercase;'>Dias de Ausência/Falta</div>
                <div style='color: #dc2626; font-size: 1.5rem; font-weight: 700;'>{dias_ausencia_filtro} dia(s)</div>
            </div>
            <div style='flex: 1; border-left: 1px solid #e5e7eb; padding-left: 20px;'>
                <div style='color: #6b7280; font-size: 0.85rem; font-weight: 600; text-transform: uppercase;'>{titulo_saldo}</div>
                <div style='color: {cor_saldo}; font-size: 1.5rem; font-weight: 700;'>{texto_saldo}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
    else:
        st.info("Nenhum registro encontrado com este filtro para o mês selecionado.")
    
    # 3. Preparando os dados para Exportação em CSV
    csv_data = "Data,Categoria,Horarios,Horas Computadas,Justificativa\n"
    for p in pontos_mes_export:
        data_pt = "/".join(p.get("data_registro", "").split("-")[::-1])
        cat = p.get("categoria", "")
        horarios = " | ".join(p.get("horarios_descritos", []))
        horas = p.get("horas_computadas", 0)
        obs = str(p.get("justificativa", "")).replace('\n', ' ').replace(',', '')
        csv_data += f"{data_pt},{cat},{horarios},{horas},{obs}\n"
        
    texto_botao = f"📊 Baixar Planilha Oficial ({cat_filtro})" if cat_filtro != "Todas as Categorias" else f"📊 Baixar Planilha Oficial ({mes_foco})"
    
    st.download_button(
        label=texto_botao,
        data=csv_data.encode('utf-8-sig'),
        file_name=f"Relatorio_{st.session_state.get('nome_completo', 'Residente').replace(' ', '_')}_{mes_foco.replace('/', '_')}.csv",
        mime="text/csv",
        type="primary",
        use_container_width=True
    )

elif st.session_state.menu_atual == "Calendário Diário":
    col_cal, col_form = st.columns([1, 1.5])

    with col_cal:
        st.markdown("<div class='card-title'>1. Tipo de Lançamento</div>", unsafe_allow_html=True)

        tipo_lancamento = st.radio("Selecione:", ["📅 Individual", "🗓️ Em Lote"], horizontal=True, label_visibility="collapsed")
        st.write("")

        if tipo_lancamento == "📅 Individual":
            st.markdown("<div style='font-weight: 600; font-size: 0.95rem; color: #374151; margin-bottom: 5px;'>Selecione a Data</div>", unsafe_allow_html=True)
            data_selecionada = st.date_input("Data única", value=data_hoje, min_value=data_inicio, max_value=data_hoje, format="DD/MM/YYYY", label_visibility="collapsed")
        else:
            st.markdown("<div style='font-weight: 600; font-size: 0.95rem; color: #374151; margin-bottom: 5px;'>Selecione o Período (Início e Fim)</div>", unsafe_allow_html=True)
            st.info("💡 Clique na data de início e depois na data de fim.")
            data_selecionada = st.date_input("Período", value=(data_hoje, data_hoje), min_value=data_inicio, max_value=data_hoje, format="DD/MM/YYYY", label_visibility="collapsed")

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

    # ==========================================
    # MODO 1: RESUMO DO DIA
    # ==========================================
    if is_single_day and registros_existentes and not st.session_state.get("modo_edicao_diario", False):
        with col_cal:
            st.markdown("<div class='card-title' style='margin-bottom: 15px;'>Detalhes do(s) Registro(s)</div>", unsafe_allow_html=True)
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

                # BOTÃO DA LIXEIRA
                if st.button(f"🗑️ Excluir registro de {cat_reg}", key=f"del_{reg['doc_id']}", type="secondary"):
                    db.collection("pontos").document(reg['doc_id']).delete()
                    st.success(f"Registro apagado do banco de dados!")
                    st.session_state.modo_edicao_diario = False
                    st.rerun()

        with col_form:
            st.markdown("<div class='card-title'>2. Resumo do Ponto</div>", unsafe_allow_html=True)
            st.info(f"**Data:** {dt_inicio.strftime('%d/%m/%Y')}\n\nEste dia possui **{len(registros_existentes)}** registro(s) salvo(s).")

            st.write("")
            if st.button("✏️ Lançar nova Categoria ou Editar Ponto", type="secondary", width='stretch'):
                st.session_state.modo_edicao_diario = True
                st.rerun()

    # ==========================================
    # MODO 2: FORMULÁRIO DE LANÇAMENTO/LOTE
    # ==========================================
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
                horarios_formatados.append(f"{ent} às {sai}")
                total_dinamico += calcular_saldo_horas(ent, sai)

        with col_cal:
            cat_atual = st.session_state.get("ed_categoria", "Prática")
            cor_calculo = "#dc2626" if erro_dinamico else "#1e40af"
            texto_calculo = "ERRO" if erro_dinamico else formatar_horas_exatas(total_dinamico)

            status_html = "<span class='badge-pending'>Não Salvo</span>" if total_dinamico > 0 else "<span class='badge-pending'>Vazio</span>"
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
                    <b>Nota de Inteligência:</b> Se você lançar uma categoria que já existe nesta data, ela será atualizada/substituída. Se lançar uma categoria diferente, elas vão coexistir no banco de dados!
                </p>
            </div>
            """, unsafe_allow_html=True)

        with col_form:
            if not is_single_day:
                st.markdown(f"<div class='card-title' style='color: #1e40af;'>2. Lançamento em Lote ({dt_inicio.strftime('%d/%m/%Y')} a {dt_fim.strftime('%d/%m/%Y')})</div>", unsafe_allow_html=True)
            elif registros_existentes:
                st.markdown("<div class='card-title' style='color: #d97706;'>✏️ Adicionar ou Substituir no dia</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div class='card-title'>2. Lançar Novo Ponto</div>", unsafe_allow_html=True)

            edit_categoria = st.selectbox("Selecione a Categoria", ["Prática", "Teórica", "Teórico-prática", "Ausência justificada", "Falta", "Férias", "Licença", "Atestado"], key="ed_categoria")
            st.markdown("<div style='margin-top: 15px; margin-bottom: 5px; font-weight: 600; font-size: 0.95rem; color: #374151;'>Horários (Deixe em branco para o dia inteiro, ex: Atestados)</div>", unsafe_allow_html=True)

            c1, c2, c3, c4 = st.columns(4)
            ed_he1 = c1.text_input("Entrada (HH)", placeholder="07", max_chars=2, key="ed_he1")
            ed_me1 = c2.text_input("Min (MM)", placeholder="00", max_chars=2, key="ed_me1")
            ed_hs1 = c3.text_input("Saída (HH)", placeholder="12", max_chars=2, key="ed_hs1")
            ed_ms1 = c4.text_input("Min (MM)", placeholder="00", max_chars=2, key="ed_ms1")
            b1, b2 = st.columns(2)
            b1.button("🕒 Puxar Hora", on_click=preencher_hora_atual, args=("ed_he1", "ed_me1"), key="ed_btn_e1", width='stretch')
            b2.button("🕒 Puxar Hora", on_click=preencher_hora_atual, args=("ed_hs1", "ed_ms1"), key="ed_btn_s1", width='stretch')

            c5, c6, c7, c8 = st.columns(4)
            ed_he2 = c5.text_input("Entrada (HH)", placeholder="13", max_chars=2, key="ed_he2")
            ed_me2 = c6.text_input("Min (MM)", placeholder="30", max_chars=2, key="ed_me2")
            ed_hs2 = c7.text_input("Saída (HH)", placeholder="17", max_chars=2, key="ed_hs2")
            ed_ms2 = c8.text_input("Min (MM)", placeholder="30", max_chars=2, key="ed_ms2")
            b3, b4 = st.columns(2)
            b3.button("🕒 Puxar Hora", on_click=preencher_hora_atual, args=("ed_he2", "ed_me2"), key="ed_btn_e2", width='stretch')
            b4.button("🕒 Puxar Hora", on_click=preencher_hora_atual, args=("ed_hs2", "ed_ms2"), key="ed_btn_s2", width='stretch')

            c9, c10, c11, c12 = st.columns(4)
            ed_he3 = c9.text_input("Entrada (HH)", placeholder="--", max_chars=2, key="ed_he3")
            ed_me3 = c10.text_input("Min (MM)", placeholder="--", max_chars=2, key="ed_me3")
            ed_hs3 = c11.text_input("Saída (HH)", placeholder="--", max_chars=2, key="ed_hs3")
            ed_ms3 = c12.text_input("Min (MM)", placeholder="--", max_chars=2, key="ed_ms3")
            b5, b6 = st.columns(2)
            b5.button("🕒 Puxar Hora", on_click=preencher_hora_atual, args=("ed_he3", "ed_me3"), key="ed_btn_e3", width='stretch')
            b6.button("🕒 Puxar Hora", on_click=preencher_hora_atual, args=("ed_hs3", "ed_ms3"), key="ed_btn_s3", width='stretch')

            edit_obs = st.text_area("Observações / Justificativa (Opcional)", key="ed_obs")

            st.write("")
            btn_texto = "💾 Salvar Alteração(ões) no Banco"
            if st.button(btn_texto, type="primary", width='stretch'):
                if erro_dinamico:
                    st.error("⚠️ Horário inválido detectado na edição. Verifique as horas e os minutos.")
                elif total_dinamico == 0 and edit_categoria not in ["Ausência justificada", "Falta", "Férias", "Licença", "Atestado"]:
                    st.error("⚠️ Você precisa preencher ao menos um horário para esta categoria.")
                elif checar_sobreposicao(horarios_formatados, registros_existentes if is_single_day else [], edit_categoria):
                    st.error("⚠️ Ops! O horário digitado entra em conflito com outra categoria já salva neste dia.")
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
                        msg_sucesso = f"✅ Ponto de {dt_inicio.strftime('%d/%m/%Y')} salvo com sucesso!"
                        if num_dias > 1:
                            msg_sucesso = f"✅ {num_dias} dias lançados em lote com sucesso!"
                        st.success(msg_sucesso)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar no banco de dados: {e}")

            if registros_existentes and is_single_day:
                if st.button("❌ Cancelar Edição", width='stretch'):
                    st.session_state.modo_edicao_diario = False
                    st.rerun()

elif st.session_state.menu_atual == "Por Categoria":
    col_cat_sel, _ = st.columns([1, 2])
    with col_cat_sel: 
        cat_analise = st.selectbox("Filtrar por Categoria", ["Prática", "Teórica", "Teórico-prática", "Ausência justificada", "Falta", "Férias", "Feriado", "Licença", "Atestado", "Ponto facultativo"])
    st.markdown("---")

    # Paleta de cores dinâmica
    cor_cat = "#16a34a" # Verde padrão (Prática)
    if cat_analise == ["Falta", "Ponto facultativo"]: cor_cat = "#dc2626" # Vermelho
    elif cat_analise in ["Ausência justificada", "Férias", "Feriado", "Licença", "Atestado", "ATESTADO"]: cor_cat = "#d97706" # Laranja
    elif cat_analise in ["Teórica", "Teórico-prática"]: cor_cat = "#1e40af" # Azul

    soma_historica_horas = 0.0
    soma_historica_dias = 0
    evolucao_cat_y = []

    # Varredura inteligente: separa o que é 'Hora' do que é 'Dia'
    for m in lista_meses_crono:
        horas_mes = dados_mensais[m]["por_categoria"].get(cat_analise, 0.0)
        
        # Puxa no banco a quantidade exata de DIAS que o residente usou essa categoria no mês
        dias_mes = sum(
            1 for p in todos_pontos 
            if p.get("categoria", "") == cat_analise and 
            f"{meses_num_para_pt.get(p.get('data_registro', '')[5:7], '')}/{p.get('data_registro', '')[0:4]}" == m
        )
        
        soma_historica_horas += horas_mes
        soma_historica_dias += dias_mes
        
        # O gráfico muda de comportamento dependendo do que faz sentido para a categoria
        if cat_analise in ["Ausência justificada", "Falta", "Férias", "Feriado", "Licença", "Atestado", "ATESTADO", "Ponto facultativo"]:
            evolucao_cat_y.append(dias_mes)
            unidade_grafico = "Dias"
        else:
            evolucao_cat_y.append(horas_mes)
            unidade_grafico = "Horas"

    c1, c2 = st.columns([1, 2])
    with c1:
        # Textos customizados para respeitar a regra da residência (Ex: Férias = 30 dias/ano)
        if cat_analise == "Férias":
            texto_principal = f"{soma_historica_dias} dia(s)"
            texto_secundario = f"Equivale a {formatar_horas_exatas(soma_historica_horas)} de abono.<br>Você tem direito a {DIAS_FERIAS_ANO} dias por ano."
        elif cat_analise in ["Ausência justificada", "Falta", "Licença", "Atestado", "ATESTADO"]:
            texto_principal = f"{soma_historica_dias} dia(s)"
            texto_secundario = f"Total de horas registradas nesses dias: {formatar_horas_exatas(soma_historica_horas)}" if soma_historica_horas > 0 else "Gera ausência na carga horária do dia."
        else:
            texto_principal = formatar_horas_exatas(soma_historica_horas)
            texto_secundario = f"Distribuídos em {soma_historica_dias} dias de registro."

        st.markdown(f"""
            <div data-testid='column' style='background-color: #f8fafc; padding: 15px; border-radius: 8px; border: 1px solid #e5e7eb; border-left: 5px solid {cor_cat}; height: 100%;'>
                <div class='card-title' style='color: #111827;'>Total Acumulado: {cat_analise}</div>
                <div style='margin-top: 10px;'><span class='big-number' style='color: {cor_cat}; font-size: 2.2rem;'>{texto_principal}</span></div>
                <div style='color: #6b7280; font-size: 0.9rem; margin-top: 10px; line-height: 1.4;'>{texto_secundario}</div>
            </div>
        """, unsafe_allow_html=True)
        
    with c2:
        st.markdown(f"<div class='card-title'>Evolução Mensal ({unidade_grafico})</div>", unsafe_allow_html=True)
        if sum(evolucao_cat_y) == 0:
            st.info(f"Nenhum registro de '{cat_analise}' encontrado no período.")
        else:
            eixo_x_meses_abrev = [m.split('/')[0][:3] for m in lista_meses_crono]
            
            # Formata o texto que vai flutuar acima das barras do gráfico
            textos_barras = [f"{v} d" if unidade_grafico == "Dias" else formatar_horas_exatas(v) for v in evolucao_cat_y]
            
            fig_cat = go.Figure(go.Bar(
                x=eixo_x_meses_abrev, 
                y=evolucao_cat_y, 
                marker_color=cor_cat, 
                width=0.4,
                text=textos_barras,
                textposition='outside', # Coloca o número acima da barra
                textfont=dict(color="#374151", size=11)
            ))
            
            fig_cat.update_layout(
                height=220, 
                margin=dict(l=0, r=0, t=20, b=0), 
                paper_bgcolor="rgba(0,0,0,0)", 
                plot_bgcolor="rgba(0,0,0,0)", 
                xaxis=dict(color="#374151"), 
                yaxis=dict(color="#374151", showgrid=True, gridcolor="#e5e7eb", zeroline=False, tickformat="d" if unidade_grafico == "Dias" else None)
            )
            
            st.plotly_chart(fig_cat, width='stretch', config={'displayModeBar': False})