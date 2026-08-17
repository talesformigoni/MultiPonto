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

# ==========================================
# 1. Configuração Inicial (SEMPRE A PRIMEIRA COISA)
# ==========================================
st.set_page_config(page_title="Dashboard | MultiPonto", layout="wide", initial_sidebar_state="collapsed")
checar_login()
aplicar_css()

# ==========================================
# 2. FUNÇÕES DE UI E FORMATAÇÃO
# ==========================================
@st.dialog("🚀 Atualização Importante: MultiPonto 2.0!")
def mostrar_novidades_popup():
    st.markdown("""
    Fala, residente! O sistema acabou de ficar muito mais inteligente. Veja o que mudou:
    
    * 🟣 **O Extrato Nubank:** Agora a aba "Visão Geral" tem uma *Timeline* detalhada de todas as suas horas extras e dívidas dia a dia.
    * ⏱️ **Ponto Parcial na UBS:** Bateu o ponto na entrada? Agora você pode salvar só a hora de chegada! Quando for embora, é só abrir o app de novo e preencher a saída.
    * 🩺 **Metas Separadas:** A Prática e a Teórica agora são cobradas e exibidas separadamente para maior transparência.
    * 📅 **Aulas Específicas:** O motor agora calcula exatamente as semanas dos Eixos Transversais e Específicos automaticamente.
    * 🏥 **Atestados Parciais:** Se você trabalhar de manhã e pegar atestado à tarde, o sistema sabe calcular a dívida exata sem te prejudicar!
    
    *Aproveite a nova versão!*
    """)
    
    st.write("")
    if st.button("Entendi, vamos lá! 🎉", type="primary", width='stretch'):
        db.collection("usuarios").document(st.session_state.uid).set(
            {"viu_update_v2": True}, merge=True
        )
        st.session_state.viu_update_v2 = True
        st.rerun()

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
                if max(t_ent_ex, t_ent_nv) < min(t_sai_ex, t_sai_nv):
                    return True
    return False

# ==========================================
# 3. GATILHO DO POP-UP
# ==========================================
if "viu_update_v2" not in st.session_state:
    user_doc = db.collection("usuarios").document(st.session_state.uid).get()
    if user_doc.exists:
        dados_user = user_doc.to_dict()
        st.session_state.viu_update_v2 = dados_user.get("viu_update_v2", False)
    else:
        st.session_state.viu_update_v2 = False

if not st.session_state.viu_update_v2:
    mostrar_novidades_popup()

# ==========================================
# LÓGICA DE DATAS E CRONOGRAMA
# ==========================================
data_inicio = date(2026, 3, 2)

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

m1, m2, m3 = st.columns(3)

if m1.button("📊 Visão Geral", width='stretch', type="primary" if st.session_state.menu_atual == "Visão Geral" else "secondary"):
    st.session_state.menu_atual = "Visão Geral"
    st.rerun()
if m2.button("📅 Mensal e Semanal", width='stretch', type="primary" if st.session_state.menu_atual == "Mensal e Semanal" else "secondary"):
    st.session_state.menu_atual = "Mensal e Semanal"
    st.rerun()
if m3.button("🏷️ Por Categoria", width='stretch', type="primary" if st.session_state.menu_atual == "Por Categoria" else "secondary"):
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

    # ==============================================================
    # NOVO: O "EXTRATO NUBANK" DE BANCO DE HORAS (TIMELINE)
    # ==============================================================
    st.markdown("<hr style='margin: 35px 0 20px 0; border-color: #e5e7eb;'>", unsafe_allow_html=True)
    st.markdown("<div class='card-title' style='margin-bottom: 5px;'><span style='color: #8b5cf6;'>🟣</span> Extrato de Horas (Movimentações)</div>", unsafe_allow_html=True)
    st.info("Aqui aparecem apenas os dias que geraram **Crédito** (horas extras) ou **Débito** (faltas, atestados). Dias com meta batida perfeitamente ficam ocultos para simplificar a leitura do seu histórico.")

    # 1. Agrupar pontos por data para otimizar o cálculo
    pontos_por_dia = {}
    for p in todos_pontos:
        d = p.get("data_registro")
        if d:
            if d not in pontos_por_dia: pontos_por_dia[d] = []
            pontos_por_dia[d].append(p)

    extrato = []
    saldo_corrente_timeline = 0.0
    saldo_acumulado_pratica = 0.0
    saldo_acumulado_teorica = 0.0
    curr_d = data_inicio

    # 2. Máquina do Tempo: Viaja do primeiro dia da residência até o último dia do filtro
    while curr_d <= dt_fim_periodo:
        p_dia, t_dia = obter_metas_do_dia(curr_d)
        meta_dia = p_dia + t_dia
        
        d_str = curr_d.isoformat()
        regs_dia = pontos_por_dia.get(d_str, [])
        
        trabalhado_pratica = 0.0
        trabalhado_teorica = 0.0
        ferias_pratica = 0.0
        ferias_teorica = 0.0
        cats_dia = []
        justificativas = []
        horarios_dia = []
        
        for r in regs_dia:
            cat = r.get("categoria", "")
            horas = float(r.get("horas_computadas", 0.0))
            if cat and cat not in cats_dia: cats_dia.append(cat)
            
            if r.get("justificativa"): 
                justificativas.append(str(r.get("justificativa")).replace('\n', ' '))
                
            if r.get("horarios_descritos"):
                horarios_dia.extend(r.get("horarios_descritos"))
            
            # Subdividindo as horas descritivamente
            if cat == "Prática":
                trabalhado_pratica += horas
            elif cat in ["Teórica", "Teórico-prática"]:
                trabalhado_teorica += horas
            elif cat == "Férias":
                ferias_pratica = p_dia
                ferias_teorica = t_dia
                
        # Atualizando os saldos da Máquina do Tempo
        trabalhado_dia = trabalhado_pratica + trabalhado_teorica
        realizado_dia = trabalhado_dia + ferias_pratica + ferias_teorica
        
        saldo_dia = realizado_dia - meta_dia
        saldo_pratica_dia = (trabalhado_pratica + ferias_pratica) - p_dia
        saldo_teorica_dia = (trabalhado_teorica + ferias_teorica) - t_dia
        
        saldo_corrente_timeline += saldo_dia
        saldo_acumulado_pratica += saldo_pratica_dia
        saldo_acumulado_teorica += saldo_teorica_dia
        
# Agora nós gravamos QUALQUER DIA que o residente tenha batido ponto OU que tenha gerado débito
        if dt_ini_periodo <= curr_d <= dt_fim_periodo:
            if len(regs_dia) > 0 or abs(saldo_dia) > 0.05:
                
                # Inteligência do Título com foco na PRÁTICA
                if "ATESTADO" in [c.upper() for c in cats_dia] or "Atestado" in cats_dia:
                    titulo = "🩺 Atestado Médico / Saúde"
                elif "Ausência justificada" in cats_dia or "Falta" in cats_dia:
                    titulo = "⚠️ Ausência / Débito Gerado"
                elif saldo_pratica_dia > 0 and p_dia == 0:
                    titulo = "🚀 Plantão Extra (Prática)"
                elif saldo_pratica_dia > 0:
                    titulo = "✨ Horas Extras de Prática"
                elif saldo_pratica_dia < -0.05:
                    titulo = "📉 Débito de Prática / Falta de Horas"
                else:
                    if saldo_teorica_dia < -0.05:
                        titulo = "📚 Pendência de Aula Teórica"
                    elif saldo_teorica_dia > 0.05:
                        titulo = "✨ Horas Extras de Teoria"
                    else:
                        titulo = "✅ Dia Completo (Meta Atingida)"
                    
                detalhe_just = " | ".join(justificativas) if justificativas else ", ".join(cats_dia)
                if not detalhe_just: detalhe_just = "Ponto normal"
                
                desc_horarios = " | ".join(horarios_dia) if horarios_dia else "Sem registros de relógio"
                
                extrato.append({
                    "data": curr_d,
                    "titulo": titulo,
                    "justificativa": detalhe_just,
                    "horarios": desc_horarios,
                    "pratica": trabalhado_pratica,
                    "teorica": trabalhado_teorica,
                    "meta_pratica": p_dia,
                    "meta_teorica": t_dia,
                    "saldo_dia": saldo_dia,
                    "saldo_pratica_dia": saldo_pratica_dia, # <--- Nova variável salva!
                    "saldo_teorica_dia": saldo_teorica_dia, 
                    "saldo_acumulado": saldo_corrente_timeline,
                    "saldo_acumulado_pratica": saldo_acumulado_pratica,
                    "saldo_acumulado_teorica": saldo_acumulado_teorica
                })
                
        curr_d += timedelta(days=1)

    # 3. Renderiza a Interface
    extrato.reverse() # Mais recentes no topo (Igual banco de verdade)

    if extrato:
        st.markdown("<div style='background-color: #fcfcfc; border: 1px solid #e5e7eb; border-radius: 10px; padding: 20px; max-height: 500px; overflow-y: auto;'>", unsafe_allow_html=True)
        
        for mov in extrato:
            # A cor e o sinal do número gigante agora respeitam APENAS a Prática
            cor_valor = "#16a34a" if mov["saldo_pratica_dia"] > 0 else ("#dc2626" if mov["saldo_pratica_dia"] < -0.05 else "#6b7280")
            sinal_valor = "+" if mov["saldo_pratica_dia"] > 0 else ""
            
            cor_acum = "#16a34a" if mov["saldo_acumulado"] >= 0 else "#dc2626"
            cor_acum_prat = "#16a34a" if mov["saldo_acumulado_pratica"] >= 0 else "#dc2626"
            cor_acum_teor = "#16a34a" if mov["saldo_acumulado_teorica"] >= 0 else "#dc2626"
            
            st.markdown(f"""
            <div style='display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 1px solid #f3f4f6; padding: 16px 0;'>
                <div style='flex: 1; padding-right: 15px;'>
                    <div style='font-size: 0.85rem; color: #6b7280; font-weight: 600; margin-bottom: 2px;'>{mov['data'].strftime('%d/%m/%Y')} &nbsp;•&nbsp; <span style='color: #4f46e5; font-weight: 800;'>{mov['horarios']}</span></div>
                    <div style='font-size: 1.05rem; color: #111827; font-weight: 700; margin-bottom: 6px;'>{mov['titulo']}</div>
                    <div style='display: flex; gap: 8px; margin-bottom: 6px; flex-wrap: wrap;'>
                        <span style='background-color: #e0e7ff; color: #3730a3; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: 700;'>Prática: {formatar_horas_exatas(mov['pratica'])}</span>
                        <span style='background-color: #f3f4f6; color: #4b5563; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: 700;'>Meta Prática: {formatar_horas_exatas(mov['meta_pratica'])}</span>
                        <span style='background-color: #fce7f3; color: #9d174d; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: 700; margin-left: 8px;'>Teórica: {formatar_horas_exatas(mov['teorica'])}</span>
                        <span style='background-color: #f3f4f6; color: #4b5563; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: 700;'>Meta Teórica: {formatar_horas_exatas(mov['meta_teorica'])}</span>
                    </div>
                    <div style='font-size: 0.85rem; color: #9ca3af; font-style: italic; max-width: 100%;'>{mov['justificativa']}</div>
                </div>
                <div style='text-align: right; min-width: 150px;'>
                    <div style='font-size: 1.3rem; font-weight: 800; color: {cor_valor};'>{sinal_valor}{formatar_horas_exatas(mov['saldo_pratica_dia'])}</div>
                    <div style='font-size: 0.85rem; color: #6b7280; font-weight: 600; margin-top: 4px;'>Acumulado Geral: <br><span style='color: {cor_acum}; font-weight: 800; font-size: 1.05rem;'>{formatar_horas_exatas(mov['saldo_acumulado'])}</span></div>
                    <div style='font-size: 0.75rem; color: #6b7280; font-weight: 600; margin-top: 6px; padding-top: 6px; border-top: 1px dashed #e5e7eb;'>
                        <span style='color: #1e40af;'>Prática:</span> <span style='color: {cor_acum_prat}; font-weight: 700;'>{formatar_horas_exatas(mov['saldo_acumulado_pratica'])}</span><br>
                        <span style='color: #d97706;'>Teórica:</span> <span style='color: {cor_acum_teor}; font-weight: 700;'>{formatar_horas_exatas(mov['saldo_acumulado_teorica'])}</span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.success("🎉 Você não possui registros neste período.")


elif st.session_state.menu_atual == "Mensal e Semanal":
        # 1. SELETORES DE MÊS E FILTRO 
        col_seletor, col_filtro = st.columns([1, 1])
        with col_seletor: 
            mes_foco = st.selectbox("📅 Selecione o Mês", lista_meses)
        with col_filtro:
            opcoes_filtro = ["Todas as Categorias", "Prática", "Teórica", "Ausência justificada", "Falta", "Férias", "Feriado", "Licença", "Atestado", "Ponto Facultativo"]
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
            
        # Ajuste para o mês de início da residência
        if ano_num == data_inicio.year and mes_num == data_inicio.month:
            dt_inicio_mes = data_inicio
            
        # O sistema só cobra a meta até ONTEM (se for o mês atual)
        # Isso evita que o dia de hoje (ainda não trabalhado) vire dívida automática
        if ano_num == data_hoje.year and mes_num == data_hoje.month:
            dt_fim_mes = data_hoje - timedelta(days=1)
        elif date(ano_num, mes_num, 1) > data_hoje:
            dt_fim_mes = dt_inicio_mes - timedelta(days=1)
            
        meta_pratica_mes = 0.0
        meta_teorica_mes = 0.0
        
        curr_d = dt_inicio_mes
        while curr_d <= dt_fim_mes:
            # Retiramos o if. A função agora tem o "cérebro" do cronograma oficial!
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
                    "Horas": formatar_horas_exatas(float(p.get("horas_computadas", 0))),
                    "Observações / Justificativa": p.get("justificativa", "")
                })
            st.dataframe(tabela_visual, width='stretch')
            
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
            width='stretch'
        )

elif st.session_state.menu_atual == "Por Categoria":
    col_cat_sel, _ = st.columns([1, 2])
    with col_cat_sel: 
        # Trocamos para MULTISELECT. Agora você pode selecionar quantas quiser!
        categorias_selecionadas = st.multiselect(
            "Filtrar por Categoria(s)", 
            ["Prática", "Teórica", "Teórico-prática", "Ausência justificada", "Falta", "Férias", "Feriado", "Licença", "Atestado", "Ponto facultativo"],
            default=["Prática"]
        )
    st.markdown("---")

    # Trava de segurança caso o usuário apague todas as opções do filtro
    if not categorias_selecionadas:
        st.info("👆 Selecione pelo menos uma categoria no filtro acima para visualizar o relatório.")
    else:
        # Paleta de cores dinâmica (baseada no que está dentro da seleção)
        cor_cat = "#16a34a" # Verde padrão (Prática)
        if any(c in ["Falta", "Ponto facultativo"] for c in categorias_selecionadas): 
            cor_cat = "#dc2626" # Vermelho
        elif any(c in ["Ausência justificada", "Férias", "Feriado", "Licença", "Atestado", "ATESTADO"] for c in categorias_selecionadas): 
            cor_cat = "#d97706" # Laranja
        elif any(c in ["Teórica", "Teórico-prática"] for c in categorias_selecionadas): 
            cor_cat = "#1e40af" # Azul

        # Nome dinâmico pro Card Principal
        titulo_card = ", ".join(categorias_selecionadas) if len(categorias_selecionadas) <= 2 else f"{len(categorias_selecionadas)} Categorias Selecionadas"

        soma_historica_ocorrencias = 0
        soma_debito_ausencias = 0.0 
        soma_horas_trabalho = 0.0 # NOVA VARIÁVEL: Para somar Prática/Teórica no mix
        soma_debito_p = 0.0 
        soma_debito_t = 0.0 
        evolucao_cat_y = []
        
        registros_detalhados = []

        # Varredura inteligente: analisa múltiplas categorias ao mesmo tempo
        for m in lista_meses_crono:
            ocorrencias_mes = 0
            valor_grafico_mes = 0.0 # Soma tudo que vai pro gráfico neste mês
            
            for p in todos_pontos:
                cat_registro = p.get("categoria", "")
                
                # A mágica: só processa se a categoria do ponto estiver na seleção
                if cat_registro in categorias_selecionadas:
                    data_str = p.get("data_registro", "")
                    if f"{meses_num_para_pt.get(data_str[5:7], '')}/{data_str[0:4]}" == m:
                        ocorrencias_mes += 1
                        
                        horas_lancadas = float(p.get("horas_computadas", 0.0))
                        dt_obj = datetime.strptime(data_str, "%Y-%m-%d").date()
                        p_dia, t_dia = obter_metas_do_dia(dt_obj)
                        
                        is_ausencia = cat_registro in ["Ausência justificada", "Falta", "Férias", "Feriado", "Licença", "Atestado", "ATESTADO", "Ponto facultativo"]
                        
                        if is_ausencia:
                            # Calcula quanto o residente trabalhou NESTE MESMO DIA
                            horas_trab_p = sum(float(p2.get("horas_computadas", 0.0)) for p2 in todos_pontos if p2.get("data_registro") == data_str and p2.get("categoria") == "Prática")
                            horas_trab_t = sum(float(p2.get("horas_computadas", 0.0)) for p2 in todos_pontos if p2.get("data_registro") == data_str and p2.get("categoria") in ["Teórica", "Teórico-prática"])
                            
                            # O débito real de cada eixo
                            debito_p = p_dia - horas_trab_p
                            if debito_p < 0: debito_p = 0.0 
                            
                            debito_t = t_dia - horas_trab_t
                            if debito_t < 0: debito_t = 0.0 
                            
                            debito_real = debito_p + debito_t
                            soma_debito_ausencias += debito_real
                            valor_grafico_mes += debito_real
                            
                            soma_debito_p += debito_p
                            soma_debito_t += debito_t
                            
                            peso_visual = f"-{formatar_horas_exatas(debito_real)}" if debito_real > 0 else "0h"
                            badge_p = f"-{formatar_horas_exatas(debito_p)}"
                            badge_t = f"-{formatar_horas_exatas(debito_t)}"
                        else:
                            # Se for Prática/Teórica
                            soma_horas_trabalho += horas_lancadas
                            valor_grafico_mes += horas_lancadas
                            
                            peso_visual = f"+{formatar_horas_exatas(horas_lancadas)}" if horas_lancadas > 0 else "0h"
                            if cat_registro == "Prática":
                                badge_p = f"+{formatar_horas_exatas(horas_lancadas)}"
                                badge_t = "0h"
                            else:
                                badge_p = "0h"
                                badge_t = f"+{formatar_horas_exatas(horas_lancadas)}"
                            
                        obs = p.get("justificativa", "")
                        if not obs: obs = "Sem observações detalhadas"
                        
                        h_desc = " | ".join(p.get("horarios_descritos", []))
                        if not h_desc: h_desc = "Dia Integral / Sem relógio"
                        
                        registros_detalhados.append({
                            "data_obj": dt_obj,
                            "horarios": h_desc,
                            "obs": obs,
                            "peso": peso_visual,
                            "badge_p": badge_p,
                            "badge_t": badge_t,
                            "is_ausencia": is_ausencia,
                            "nome_categoria": cat_registro # Salva a categoria para mostrar na etiqueta
                        })
            
            soma_historica_ocorrencias += ocorrencias_mes
            evolucao_cat_y.append(valor_grafico_mes)

        c1, c2 = st.columns([1, 2])
        
        # Análise do que o usuário misturou na seleção para exibir o texto perfeito
        tem_trabalho = any(c in ["Prática", "Teórica", "Teórico-prática"] for c in categorias_selecionadas)
        tem_ausencia = any(c in ["Ausência justificada", "Falta", "Férias", "Feriado", "Licença", "Atestado", "Ponto facultativo"] for c in categorias_selecionadas)

        with c1:
            # Mantendo toda a sua lógica de texto intacta, e adicionando o caso misto
            if tem_trabalho and tem_ausencia:
                texto_principal = f"{soma_historica_ocorrencias} registros"
                texto_secundario = f"Mistura de tipos de dados.<br><span style='color: #16a34a; font-weight: 600;'>Trabalhadas: +{formatar_horas_exatas(soma_horas_trabalho)}</span> | <span style='color: #dc2626; font-weight: 600;'>Ausências: -{formatar_horas_exatas(soma_debito_ausencias)}</span>"
            
            elif tem_ausencia:
                if "Férias" in categorias_selecionadas and len(categorias_selecionadas) == 1:
                    texto_principal = formatar_horas_exatas(soma_debito_ausencias)
                    texto_secundario = f"Abono de {soma_historica_ocorrencias} registro(s).<br><span style='color: #1e40af; font-weight: 600;'>Prática: {formatar_horas_exatas(soma_debito_p)}</span> | <span style='color: #d97706; font-weight: 600;'>Teórica: {formatar_horas_exatas(soma_debito_t)}</span>"
                else:
                    texto_principal = f"-{formatar_horas_exatas(soma_debito_ausencias)}" if soma_debito_ausencias > 0 else "0h"
                    texto_secundario = f"Corresponde a {soma_historica_ocorrencias} registro(s).<br><span style='color: #1e40af; font-weight: 600;'>Prática: -{formatar_horas_exatas(soma_debito_p)}</span> | <span style='color: #d97706; font-weight: 600;'>Teórica: -{formatar_horas_exatas(soma_debito_t)}</span>"
            
            else:
                texto_principal = formatar_horas_exatas(soma_horas_trabalho)
                texto_secundario = f"Distribuídos em {soma_historica_ocorrencias} registro(s)."

            st.markdown(f"""
                <div data-testid='column' style='background-color: #f8fafc; padding: 15px; border-radius: 8px; border: 1px solid #e5e7eb; border-left: 5px solid {cor_cat}; height: 100%;'>
                    <div class='card-title' style='color: #111827;'>Total Acumulado: {titulo_card}</div>
                    <div style='margin-top: 10px;'><span class='big-number' style='color: {cor_cat}; font-size: 2.2rem;'>{texto_principal}</span></div>
                    <div style='color: #6b7280; font-size: 0.9rem; margin-top: 10px; line-height: 1.4;'>{texto_secundario}</div>
                </div>
            """, unsafe_allow_html=True)
            
        with c2:
            st.markdown(f"<div class='card-title'>Evolução Mensal (Horas)</div>", unsafe_allow_html=True)
            if sum(evolucao_cat_y) == 0:
                st.info(f"Nenhum registro encontrado para essa combinação no período.")
            else:
                eixo_x_meses_abrev = [m.split('/')[0][:3] for m in lista_meses_crono]
                textos_barras = [formatar_horas_exatas(v) for v in evolucao_cat_y]
                
                fig_cat = go.Figure(go.Bar(
                    x=eixo_x_meses_abrev, 
                    y=evolucao_cat_y, 
                    marker_color=cor_cat, 
                    width=0.4,
                    text=textos_barras,
                    textposition='outside',
                    textfont=dict(color="#374151", size=11)
                ))
                
                fig_cat.update_layout(
                    height=220, 
                    margin=dict(l=0, r=0, t=20, b=0), 
                    paper_bgcolor="rgba(0,0,0,0)", 
                    plot_bgcolor="rgba(0,0,0,0)", 
                    xaxis=dict(color="#374151"), 
                    yaxis=dict(color="#374151", showgrid=True, gridcolor="#e5e7eb", zeroline=False)
                )
                
                st.plotly_chart(fig_cat, width='stretch', config={'displayModeBar': False})

        # =========================================================
        # NOVA SEÇÃO: LISTAGEM DETALHADA COM ETIQUETA DA CATEGORIA
        # =========================================================
        st.markdown("<hr style='margin-top: 30px; border-color: #e5e7eb;'>", unsafe_allow_html=True)
        st.markdown(f"<div class='card-title' style='margin-bottom: 15px;'>📋 Histórico Detalhado: {titulo_card}</div>", unsafe_allow_html=True)

        if registros_detalhados:
            registros_detalhados = sorted(registros_detalhados, key=lambda k: k["data_obj"], reverse=True)

            for reg in registros_detalhados:
                data_formatada = reg["data_obj"].strftime("%d/%m/%Y")
                
                bg_badge = "#fef2f2" if reg['is_ausencia'] else "#f0fdf4"
                text_badge = "#dc2626" if reg['is_ausencia'] else "#16a34a"
                
                st.markdown(f"""
                <div style='display: flex; justify-content: space-between; align-items: center; padding: 12px 15px; border: 1px solid #e5e7eb; border-left: 4px solid {cor_cat}; border-radius: 6px; margin-bottom: 10px; background-color: #f8fafc;'>
                    <div>
                        <div style='font-size: 0.95rem; font-weight: 700; color: #111827;'>
                            <span style='background-color: #e5e7eb; color: #374151; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; margin-right: 8px;'>{reg['nome_categoria']}</span>
                            {data_formatada} <span style='color: #6b7280; font-weight: 500; font-size: 0.85rem; margin-left: 8px;'>🕛 {reg['horarios']}</span>
                        </div>
                        <div style='display: flex; gap: 8px; margin-top: 6px; margin-bottom: 4px;'>
                            <span style='background-color: {bg_badge}; color: {text_badge}; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 700; border: 1px solid {text_badge}40;'>Prática: {reg['badge_p']}</span>
                            <span style='background-color: {bg_badge}; color: {text_badge}; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 700; border: 1px solid {text_badge}40;'>Teórica: {reg['badge_t']}</span>
                        </div>
                        <div style='font-size: 0.85rem; color: #4b5563; font-style: italic;'>{reg['obs']}</div>
                    </div>
                    <div style='text-align: right; font-weight: 800; color: {cor_cat}; font-size: 1.2rem;'>
                        {reg['peso']}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("Nenhum registro detalhado para essa combinação no momento.")