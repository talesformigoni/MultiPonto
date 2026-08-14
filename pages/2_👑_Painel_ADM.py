import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from firebase_admin import auth, firestore
from firebase_config import db
from utils import aplicar_css, checar_login
from calculadora_horas import obter_metas_do_dia

# ==========================================
# 1. SEGURANÇA MÁXIMA (O LEÃO DE CHÁCARA)
# ==========================================
st.set_page_config(page_title="Painel ADM | MultiPonto", layout="wide", initial_sidebar_state="collapsed")
checar_login()
aplicar_css()

# Blindagem nível militar usando o UID do Firebase!
UID_ADMIN = "CTEiPcg5JzLTDEL98eOWRiC5mJu1"

if st.session_state.get("uid") != UID_ADMIN:
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    st.error("⛔ **ACESSO NEGADO:** Esta área é de uso exclusivo da Coordenação da Residência.")
    st.image("https://http.cat/403", width=400) # Um toque de humor para quem tentar invadir
    st.stop() # Mata a execução da página aqui mesmo

# ==========================================
# 2. CABEÇALHO DO MEGAZORD
# ==========================================
st.markdown("""
<div style="background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 100%); padding: 30px; border-radius: 12px; color: white; display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
    <div>
        <h1 style="margin: 0; font-size: 2.2rem; font-weight: 800; color: white;">👑 Centro de Comando ADM</h1>
        <p style="margin: 5px 0 0 0; font-size: 1.1rem; opacity: 0.9;">Gestão completa da Residência Multiprofissional em Saúde</p>
    </div>
    <div style="background-color: rgba(255,255,255,0.2); padding: 10px 20px; border-radius: 8px; font-weight: 600;">
        Acesso Nível: Alpha
    </div>
</div>
""", unsafe_allow_html=True)

# --- BUSCA GLOBAL DE RESIDENTES (ANTES DAS ABAS) ---
try:
    residentes_ref = db.collection("residentes").get()
    lista_residentes = []
    for doc in residentes_ref:
        dados = doc.to_dict()
        dados["uid"] = doc.id 
        lista_residentes.append(dados)
except Exception as e:
    st.error(f"Erro ao buscar residentes globais: {e}")
    lista_residentes = []
# ---------------------------------------------------

# ==========================================
# 3. NAVEGAÇÃO SUPERIOR (UX MODERNA)
# ==========================================

# ==========================================
# UX NINJA: ESTILIZAÇÃO SUPREMA DAS ABAS
# ==========================================
st.markdown("""
<style>
    /* Espaçamento e linha de base das abas */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        border-bottom: 2px solid #e5e7eb;
        padding-bottom: 0px;
    }
    /* Estilo padrão (Abas Inativas) */
    .stTabs [data-baseweb="tab"] {
        height: 55px;
        background-color: #f3f4f6;
        border-radius: 10px 10px 0 0;
        padding: 10px 25px;
        font-size: 1.15rem;
        font-weight: 700;
        color: #6b7280;
        transition: all 0.3s ease-in-out;
        border: 1px solid #e5e7eb;
        border-bottom: none;
    }
    /* Estilo da Aba ATIVA (Selecionada) */
    .stTabs [aria-selected="true"] {
        background-color: #2563eb !important;
        color: #ffffff !important;
        border-color: #2563eb !important;
    }
    /* Efeito ao passar o mouse nas inativas */
    .stTabs [data-baseweb="tab"]:hover:not([aria-selected="true"]) {
        background-color: #e5e7eb;
        color: #1f2937;
    }
    /* Esconde aquela linhazinha fina padrão do Streamlit */
    .stTabs [data-baseweb="tab-highlight"] {
        display: none;
    }
</style>
""", unsafe_allow_html=True)

# Usamos abas nativas do Streamlit para não poluir a tela e dar sensação de um "App Único"
aba1, aba2, aba3 = st.tabs([
    "📊 Visão Geral (Raio-X)", 
    "👥 Gestão de Residentes", 
    "⏳ Auditoria de Horas"
])

# --- MÓDULO 1: VISÃO GERAL (RAIO-X GLOBAL) ---
with aba1:
    import pandas as pd
    import plotly.express as px
    import plotly.graph_objects as go
    import datetime as dt
    from datetime import date, timedelta
    
    st.markdown("<div class='card-title' style='margin-bottom: 20px;'>📊 Centro de Comando Global (Raio-X)</div>", unsafe_allow_html=True)
    
    if not lista_residentes:
        st.warning("⚠️ O sistema está vazio. Cadastre residentes no Módulo 2 para ver as métricas.")
    else:
        with st.spinner("Sincronizando Banco de Horas e Gerando Extratos..."):
            
            # =========================================================
            # MOTOR DE HORAS E PDF
            # =========================================================
            def formatar_horas_adm_pdf(horas_decimais):
                sinal = "-" if horas_decimais < 0 else ""
                horas_decimais = abs(horas_decimais)
                horas = int(horas_decimais)
                minutos = int(round((horas_decimais - horas) * 60))
                if minutos == 60:
                    horas += 1
                    minutos = 0
                if minutos == 0: return f"{sinal}{horas}h"
                return f"{sinal}{horas}h {minutos:02d}m"

# --- GERADOR DO PDF NUBANK (ALTA PERFORMANCE E DETALHADO) ---
            def gerar_pdf_extrato(nome, nucleo, uid_res, todos_pontos):
                from fpdf import FPDF
                
                pontos_res = [p for p in todos_pontos if p.get('uid_residente') == uid_res]
                pontos_por_data = {}
                for pt in pontos_res:
                    d = pt.get('data_registro')
                    if d not in pontos_por_data: pontos_por_data[d] = []
                    pontos_por_data[d].append(pt)

                data_ini = date(2026, 3, 2)
                hoje = date.today()
                dias = (hoje - data_ini).days

                acum_p, acum_t = 0.0, 0.0
                soma_trab_p, soma_trab_t = 0.0, 0.0
                soma_meta_p, soma_meta_t = 0.0, 0.0
                
                historico = []

                for i in range(dias + 1):
                    d_obj = data_ini + timedelta(days=i)
                    d_str = d_obj.strftime("%Y-%m-%d")

                    mp, mt = obter_metas_do_dia(d_obj)
                    soma_meta_p += mp
                    soma_meta_t += mt
                    
                    pts_dia = pontos_por_data.get(d_str, [])

                    trab_p, trab_t = 0.0, 0.0
                    is_ausencia = False
                    ausencia_nome = ""
                    horarios = []

                    for pt in pts_dia:
                        cat = pt.get('categoria', '')
                        h = float(pt.get('horas_computadas', 0.0))
                        if pt.get('horarios_descritos'): horarios.extend(pt.get('horarios_descritos'))

                        if cat == 'Prática': trab_p += h
                        elif cat in ['Teórica', 'Teórico-prática']: trab_t += h
                        elif cat in ['Férias', 'Falta', 'Ausência justificada', 'Atestado', 'Feriado', 'Licença', 'Ponto facultativo']:
                            is_ausencia = True
                            ausencia_nome = cat

                    credito_p, credito_t = trab_p, trab_t
                    debito_p, debito_t = mp, mt

                    if is_ausencia:
                        if ausencia_nome == 'Férias': credito_p, credito_t = mp, mt
                        elif ausencia_nome == 'Falta': pass
                        else: debito_p, debito_t = 0.0, 0.0

                    # Adiciona aos totais reais do residente
                    soma_trab_p += credito_p
                    soma_trab_t += credito_t

                    saldo_dia_p = credito_p - debito_p
                    saldo_dia_t = credito_t - debito_t
                    saldo_total = saldo_dia_p + saldo_dia_t
                    
                    acum_p += saldo_dia_p
                    acum_t += saldo_dia_t

                    if saldo_total != 0 or trab_p > 0 or trab_t > 0:
                        historico.append({
                            'data_str': d_obj.strftime("%d/%m/%Y"),
                            'data_obj': d_obj,
                            'horarios': " | ".join(horarios) if horarios else ("Sem relogio" if is_ausencia else ""),
                            'saldo_dia': saldo_total,
                            'acumulado': acum_p + acum_t,
                            'acum_p': acum_p,
                            'acum_t': acum_t,
                            'trab_p': trab_p, 'meta_p': mp,
                            'trab_t': trab_t, 'meta_t': mt,
                            'ausencia': ausencia_nome
                        })

                # Ordena e agrupa por mês
                historico.sort(key=lambda x: x['data_obj'], reverse=True)
                
                meses_pt = ["", "JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]
                extrato_por_mes = {}
                for item in historico:
                    chave_mes = f"{meses_pt[item['data_obj'].month]} / {item['data_obj'].year}"
                    if chave_mes not in extrato_por_mes: extrato_por_mes[chave_mes] = []
                    extrato_por_mes[chave_mes].append(item)

                # ========================================================
                # INÍCIO DO DESENHO DO PDF
                # ========================================================
                pdf = FPDF()
                pdf.add_page()
                
                # --- CAPA (DASHBOARD GERENCIAL) ---
                pdf.set_fill_color(30, 58, 138) # Fundo Azul Escuro
                pdf.rect(0, 0, 210, 35, 'F')
                
                pdf.set_y(12)
                pdf.set_font('Arial', 'B', 18)
                pdf.set_text_color(255, 255, 255)
                pdf.cell(0, 8, 'RELATORIO EXECUTIVO - BANCO DE HORAS', ln=1, align='C')
                
                pdf.set_font('Arial', '', 11)
                pdf.set_text_color(209, 213, 219) # Cinza claro
                pdf.cell(0, 5, f'Data da Emissao: {dt.datetime.now().strftime("%d/%m/%Y %H:%M")}', ln=1, align='C')
                
                pdf.ln(15)
                
                # Dados do Residente
                pdf.set_font('Arial', 'B', 14)
                pdf.set_text_color(31, 41, 55)
                pdf.cell(0, 6, f"Residente: {nome}", ln=1)
                pdf.set_font('Arial', '', 11)
                pdf.set_text_color(107, 114, 128)
                pdf.cell(0, 6, f"Nucleo Profissional: {nucleo}", ln=1)
                
                pdf.ln(10)
                
                # --- PARÂMETROS GERAIS (GRÁFICOS NATIVOS NO PDF) ---
                pdf.set_font('Arial', 'B', 12)
                pdf.set_text_color(55, 65, 81)
                pdf.cell(0, 8, "PARAMETROS GERAIS ACUMULADOS (ATE HOJE)", border='B', ln=1)
                pdf.ln(6)
                
                def desenhar_barra_progresso(pdf_obj, titulo, realizado, meta, cor_rgb, y_pos):
                    pdf_obj.set_y(y_pos)
                    pdf_obj.set_font('Arial', 'B', 10)
                    pdf_obj.set_text_color(75, 85, 99)
                    pdf_obj.cell(50, 6, titulo, border=0)
                    
                    # Matemática da barra
                    largura_maxima = 100
                    porcentagem = (realizado / meta) if meta > 0 else 0
                    if porcentagem > 1: porcentagem = 1.0 # Trava em 100% no desenho
                    largura_preenchida = largura_maxima * porcentagem
                    
                    # Desenho Fundo (Cinza)
                    pdf_obj.set_fill_color(229, 231, 235)
                    pdf_obj.rect(60, y_pos + 1.5, largura_maxima, 4, 'F')
                    
                    # Desenho Preenchimento (Cor dinâmica)
                    pdf_obj.set_fill_color(*cor_rgb)
                    pdf_obj.rect(60, y_pos + 1.5, largura_preenchida, 4, 'F')
                    
                    # Textos
                    pdf_obj.set_x(165)
                    pdf_obj.set_font('Arial', 'B', 10)
                    pdf_obj.set_text_color(31, 41, 55)
                    pdf_obj.cell(30, 6, f"{formatar_horas_adm_pdf(realizado)} / {formatar_horas_adm_pdf(meta)}", border=0, ln=1)

                # Desenha Eixo Prático
                desenhar_barra_progresso(pdf, "Eixo Pratico:", soma_trab_p, soma_meta_p, (37, 99, 235), pdf.get_y())
                pdf.ln(3)
                # Desenha Eixo Teórico
                desenhar_barra_progresso(pdf, "Eixo Teorico:", soma_trab_t, soma_meta_t, (139, 92, 246), pdf.get_y())
                
                pdf.ln(8)
                
                # Card de Saldo Final
                saldo_global = acum_p + acum_t
                cor_saldo_final = (22, 163, 74) if saldo_global >= 0 else (220, 38, 38)
                pdf.set_fill_color(243, 244, 246)
                pdf.rect(10, pdf.get_y(), 190, 20, 'F')
                
                pdf.set_y(pdf.get_y() + 5)
                pdf.set_x(15)
                pdf.set_font('Arial', 'B', 12)
                pdf.set_text_color(75, 85, 99)
                pdf.cell(90, 10, "SALDO GLOBAL DO RESIDENTE:", border=0)
                
                pdf.set_font('Arial', 'B', 16)
                pdf.set_text_color(*cor_saldo_final)
                sinal_g = "+" if saldo_global > 0 else ""
                pdf.cell(90, 10, f"{sinal_g}{formatar_horas_adm_pdf(saldo_global)}", border=0, align='R', ln=1)

                pdf.ln(10)
                pdf.set_font('Arial', 'I', 9)
                pdf.set_text_color(156, 163, 175)
                pdf.multi_cell(0, 5, "Nota: O detalhamento abaixo oculta os dias com meta perfeitamente batida para facilitar a leitura da auditoria.")
                pdf.ln(5)

                # ========================================================
                # EXTRATO DIVIDIDO POR MESES
                # ========================================================
                for mes, itens_mes in extrato_por_mes.items():
                    # Quebra página se estiver muito no fim
                    if pdf.get_y() > 240: pdf.add_page()
                    
                    pdf.ln(5)
                    pdf.set_fill_color(243, 244, 246) # Fundo do cabeçalho do mês
                    pdf.rect(10, pdf.get_y(), 190, 8, 'F')
                    pdf.set_font('Arial', 'B', 11)
                    pdf.set_text_color(55, 65, 81)
                    pdf.set_y(pdf.get_y() + 1.5)
                    pdf.set_x(12)
                    pdf.cell(0, 5, f"COMPETENCIA: {mes}", border=0, ln=1)
                    pdf.ln(5)

                    for item in itens_mes:
                        if pdf.get_y() > 260: pdf.add_page()

                        pdf.set_font('Arial', 'B', 9)
                        pdf.set_text_color(107, 114, 128)
                        pdf.cell(0, 5, f"{item['data_str']} - {item['horarios']}", ln=1)

                        if item['saldo_dia'] > 0:
                            cor_titulo = (22, 163, 74)
                            titulo = "Credito de Horas / Horas Extras"
                        elif item['saldo_dia'] < 0:
                            cor_titulo = (220, 38, 38)
                            titulo = "Debito de Horas / Falta" if item['ausencia'] == 'Falta' else "Debito de Horas"
                        else:
                            cor_titulo = (30, 64, 175)
                            titulo = f"Movimentacao ({item['ausencia']})" if item['ausencia'] else "Meta Batida"

                        y_blocos = pdf.get_y()

                        # Esquerda
                        pdf.set_text_color(*cor_titulo)
                        pdf.set_font('Arial', 'B', 10)
                        pdf.cell(120, 5, titulo, border=0, ln=1)
                        
                        pdf.set_font('Arial', '', 8)
                        pdf.set_text_color(107, 114, 128)
                        str_p = f"Pratica: {formatar_horas_adm_pdf(item['trab_p'])} (Meta: {formatar_horas_adm_pdf(item['meta_p'])})"
                        str_t = f"Teorica: {formatar_horas_adm_pdf(item['trab_t'])} (Meta: {formatar_horas_adm_pdf(item['meta_t'])})"
                        pdf.cell(120, 5, f"{str_p}  |  {str_t}", border=0, ln=1)
                        
                        y_esquerda = pdf.get_y()

                        # Direita
                        pdf.set_y(y_blocos)
                        pdf.set_x(130)
                        pdf.set_text_color(*cor_titulo)
                        pdf.set_font('Arial', 'B', 11)
                        sinal = "+" if item['saldo_dia'] > 0 else ""
                        pdf.cell(70, 5, f"{sinal}{formatar_horas_adm_pdf(item['saldo_dia'])}", ln=1, align='R')
                        
                        pdf.set_x(130)
                        pdf.set_font('Arial', '', 8)
                        pdf.set_text_color(107, 114, 128)
                        pdf.cell(70, 4, "Acumulado Geral:", ln=1, align='R')
                        
                        pdf.set_x(130)
                        pdf.set_font('Arial', 'B', 9)
                        if item['acumulado'] >= 0: pdf.set_text_color(22, 163, 74)
                        else: pdf.set_text_color(220, 38, 38)
                        sinal_acum = "+" if item['acumulado'] > 0 else ""
                        pdf.cell(70, 4, f"{sinal_acum}{formatar_horas_adm_pdf(item['acumulado'])}", ln=1, align='R')

                        pdf.set_x(130)
                        pdf.set_font('Arial', '', 7)
                        if item['acum_p'] >= 0: pdf.set_text_color(37, 99, 235)
                        else: pdf.set_text_color(220, 38, 38)
                        sinal_p = "+" if item['acum_p'] > 0 else ""
                        pdf.cell(70, 3.5, f"Pratica: {sinal_p}{formatar_horas_adm_pdf(item['acum_p'])}", ln=1, align='R')

                        pdf.set_x(130)
                        if item['acum_t'] >= 0: pdf.set_text_color(139, 92, 246)
                        else: pdf.set_text_color(220, 38, 38)
                        sinal_t = "+" if item['acum_t'] > 0 else ""
                        pdf.cell(70, 3.5, f"Teorica: {sinal_t}{formatar_horas_adm_pdf(item['acum_t'])}", ln=1, align='R')

                        y_direita = pdf.get_y()
                        pdf.set_y(max(y_esquerda, y_direita))

                        pdf.set_draw_color(229, 231, 235)
                        pdf.line(10, pdf.get_y()+2, 200, pdf.get_y()+2)
                        pdf.ln(5)

                out = pdf.output(dest='S')
                if isinstance(out, str): return out.encode('latin-1', 'replace')
                return bytes(out)

            # CALCULA A META GLOBAL (Do dia 02/03/2026 até HOJE)
            data_inicio_residencia = date(2026, 3, 2)
            hoje = date.today()
            
            meta_global_pratica = 0.0
            meta_global_teorica = 0.0
            
            dias_passados = (hoje - data_inicio_residencia).days
            if dias_passados >= 0:
                for i in range(dias_passados + 1):
                    d = data_inicio_residencia + timedelta(days=i)
                    mp, mt = obter_metas_do_dia(d)
                    meta_global_pratica += mp
                    meta_global_teorica += mt
            
            meta_global_total = meta_global_pratica + meta_global_teorica

            try:
                todos_pontos_ref = db.collection("pontos").get()
                todos_pontos_adm = [p.to_dict() for p in todos_pontos_ref]
            except Exception as e:
                todos_pontos_adm = []

            # PROCESSAMENTO DA TROPA
            dados_tropa = []
            total_horas_realizadas = 0.0
            residentes_desatualizados = 0
            residentes_no_vermelho = 0
            
            for res in lista_residentes:
                uid = res.get('uid')
                nome = res.get('nome_completo', 'Desconhecido')
                prof = res.get('profissao', 'Outros')
                
                pontos_res = [p for p in todos_pontos_adm if p.get('uid_residente') == uid]
                
                trab_p, trab_t, ferias_p, ferias_t, faltas_p, faltas_t = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
                ultima_data_str = "1900-01-01"
                
                for pt in pontos_res:
                    cat = pt.get('categoria', '')
                    h = float(pt.get('horas_computadas', 0.0))
                    d_str = pt.get('data_registro')
                    
                    if d_str > ultima_data_str: ultima_data_str = d_str
                    
                    d_obj = dt.datetime.strptime(d_str, "%Y-%m-%d").date()
                    p_dia, t_dia = obter_metas_do_dia(d_obj)
                    
                    if cat == 'Prática': trab_p += h
                    elif cat in ['Teórica', 'Teórico-prática']: trab_t += h
                    elif cat == 'Férias': 
                        ferias_p += p_dia
                        ferias_t += t_dia
                    elif cat == 'Falta': 
                        faltas_p += p_dia
                        faltas_t += t_dia
                
                realizado_pratica = trab_p + ferias_p
                realizado_teorica = trab_t + ferias_t
                total_trabalhado = realizado_pratica + realizado_teorica
                total_horas_realizadas += total_trabalhado
                
                saldo_p = realizado_pratica - faltas_p - meta_global_pratica
                saldo_t = realizado_teorica - faltas_t - meta_global_teorica
                saldo_final = saldo_p + saldo_t
                
                if saldo_final < 0: residentes_no_vermelho += 1
                
                if ultima_data_str != "1900-01-01":
                    ult_d = dt.datetime.strptime(ultima_data_str, "%Y-%m-%d").date()
                    dias_off = (hoje - ult_d).days
                    if dias_off == 0: status_app = "Hoje"
                    elif dias_off == 1: status_app = "Ontem"
                    else: status_app = f"Há {dias_off} dias"
                else:
                    dias_off = 999
                    status_app = "Nunca lançou"
                
                if dias_off > 7: residentes_desatualizados += 1
                    
                dados_tropa.append({
                    "uid": uid,
                    "Nome": nome,
                    "Núcleo": prof,
                    "Prática (F)": realizado_pratica,
                    "Prática (M)": meta_global_pratica,
                    "Teórica (F)": realizado_teorica,
                    "Teórica (M)": meta_global_teorica,
                    "Saldo Final": saldo_final,
                    "Último Lançamento": status_app,
                    "_dias_off": dias_off,
                    "_total_feito": total_trabalhado
                })

            df_tropa = pd.DataFrame(dados_tropa)

            # ==========================================
            # LINHA DE CARDS SUPERIORES E GRÁFICOS
            # ==========================================
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown(f"<div style='background-color: #f8fafc; padding: 20px; border-radius: 12px; border: 1px solid #e5e7eb; border-left: 5px solid #3b82f6;'><div style='color: #6b7280; font-weight: 700; font-size: 0.85rem; text-transform: uppercase;'>Meta por Residente</div><div style='color: #1e3a8a; font-size: 2.2rem; font-weight: 800; margin-top: 5px;'>{meta_global_total:,.1f}h</div><div style='color: #6b7280; font-size: 0.8rem; margin-top: 5px;'>Acumulado até hoje</div></div>", unsafe_allow_html=True)
            with c2:
                media_tropa = total_horas_realizadas / len(lista_residentes) if len(lista_residentes) > 0 else 0
                cor_media = "#16a34a" if media_tropa >= meta_global_total else "#d97706"
                st.markdown(f"<div style='background-color: #f8fafc; padding: 20px; border-radius: 12px; border: 1px solid #e5e7eb; border-left: 5px solid {cor_media};'><div style='color: #6b7280; font-weight: 700; font-size: 0.85rem; text-transform: uppercase;'>Média Trabalhada</div><div style='color: {cor_media}; font-size: 2.2rem; font-weight: 800; margin-top: 5px;'>{media_tropa:,.1f}h</div><div style='color: #6b7280; font-size: 0.8rem; margin-top: 5px;'>O que a tropa entregou</div></div>", unsafe_allow_html=True)
            with c3:
                cor_alerta_saldo = "#dc2626" if residentes_no_vermelho > 0 else "#16a34a"
                st.markdown(f"<div style='background-color: #f8fafc; padding: 20px; border-radius: 12px; border: 1px solid #e5e7eb; border-left: 5px solid {cor_alerta_saldo};'><div style='color: #6b7280; font-weight: 700; font-size: 0.85rem; text-transform: uppercase;'>Tropa no Vermelho</div><div style='color: {cor_alerta_saldo}; font-size: 2.2rem; font-weight: 800; margin-top: 5px;'>{residentes_no_vermelho}</div><div style='color: #6b7280; font-size: 0.8rem; margin-top: 5px;'>Saldos Negativos</div></div>", unsafe_allow_html=True)
            with c4:
                cor_alerta_app = "#dc2626" if residentes_desatualizados > 0 else "#16a34a"
                st.markdown(f"<div style='background-color: #f8fafc; padding: 20px; border-radius: 12px; border: 1px solid #e5e7eb; border-left: 5px solid {cor_alerta_app};'><div style='color: #6b7280; font-weight: 700; font-size: 0.85rem; text-transform: uppercase;'>App Desatualizado</div><div style='color: {cor_alerta_app}; font-size: 2.2rem; font-weight: 800; margin-top: 5px;'>{residentes_desatualizados}</div><div style='color: #6b7280; font-size: 0.8rem; margin-top: 5px;'>Atraso > 7 dias</div></div>", unsafe_allow_html=True)

            # GRÁFICOS
            st.markdown("<hr style='border-color: #e5e7eb; margin-top: 30px; margin-bottom: 30px;'><h4 style='color: #374151; font-weight: 800; font-size: 1.4rem; margin-bottom: 5px;'>⚖️ Produção Acumulada por Residente</h4><span style='color: #6b7280; font-size: 0.95rem;'>Acompanhamento detalhado do desempenho em cada eixo da residência.</span>", unsafe_allow_html=True)
            
            if not df_tropa.empty:
                df_grafico = df_tropa.copy().sort_values('_total_feito', ascending=True)
                altura_grafico = max(450, len(df_grafico) * 65)
                
                st.markdown("<h5 style='color: #2563eb; font-weight: 800; margin-top: 35px; font-size: 1.1rem;'>🩺 Eixo Prático (Realizado vs Meta)</h5>", unsafe_allow_html=True)
                fig_p = go.Figure()
                fig_p.add_trace(go.Bar(x=df_grafico['Prática (F)'], y=df_grafico['Nome'], name='Prática Realizada', orientation='h', marker_color='#3b82f6', text=df_grafico['Prática (F)'].apply(lambda x: f"{x:.0f}h"), textposition='outside', textfont=dict(size=14, color='#3b82f6', weight='bold')))
                fig_p.add_trace(go.Bar(x=df_grafico['Prática (M)'], y=df_grafico['Nome'], name='Meta Prática Exigida', orientation='h', marker_color='#e5e7eb', text=df_grafico['Prática (M)'].apply(lambda x: f"{x:.0f}h"), textposition='auto', textfont=dict(size=14, color='#374151', weight='bold')))
                fig_p.update_layout(barmode='group', showlegend=True, margin=dict(l=0, r=0, t=15, b=0), height=altura_grafico, plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=14, weight='bold')), xaxis=dict(showgrid=True, gridcolor="#e5e7eb", zeroline=False), yaxis=dict(tickfont=dict(size=13, weight='bold', color='#1f2937')))
                st.plotly_chart(fig_p, use_container_width=True, config={'displayModeBar': False})

                st.markdown("<h5 style='color: #7c3aed; font-weight: 800; margin-top: 40px; font-size: 1.1rem;'>📚 Eixo Teórico (Realizado vs Meta)</h5>", unsafe_allow_html=True)
                fig_t = go.Figure()
                fig_t.add_trace(go.Bar(x=df_grafico['Teórica (F)'], y=df_grafico['Nome'], name='Teórica Realizada', orientation='h', marker_color='#8b5cf6', text=df_grafico['Teórica (F)'].apply(lambda x: f"{x:.0f}h" if x > 0 else ""), textposition='outside', textfont=dict(size=14, color='#8b5cf6', weight='bold')))
                fig_t.add_trace(go.Bar(x=df_grafico['Teórica (M)'], y=df_grafico['Nome'], name='Meta Teórica Exigida', orientation='h', marker_color='#e5e7eb', text=df_grafico['Teórica (M)'].apply(lambda x: f"{x:.0f}h"), textposition='auto', textfont=dict(size=14, color='#374151', weight='bold')))
                fig_t.update_layout(barmode='group', showlegend=True, margin=dict(l=0, r=0, t=15, b=0), height=altura_grafico, plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=14, weight='bold')), xaxis=dict(showgrid=True, gridcolor="#e5e7eb", zeroline=False), yaxis=dict(tickfont=dict(size=13, weight='bold', color='#1f2937')))
                st.plotly_chart(fig_t, use_container_width=True, config={'displayModeBar': False})

            # ==========================================
            # 7. LISTA DE AUDITORIA PREMIUM + BOTÃO DE PDF
            # ==========================================
            st.markdown("<hr style='border-color: #e5e7eb; margin-top: 40px; margin-bottom: 30px;'>", unsafe_allow_html=True)
            st.markdown("<h4 style='color: #374151; font-weight: 700; margin-bottom: 15px;'>🧾 Auditoria Detalhada de Banco de Horas</h4>", unsafe_allow_html=True)
            
            if not df_tropa.empty:
                df_exibicao = df_tropa.sort_values('Saldo Final', ascending=True)
                
                with st.container(height=650, border=False):
                    for _, row in df_exibicao.iterrows():
                        uid_row = row['uid']
                        nome = row['Nome']
                        nucleo = row['Núcleo']
                        p_feito, p_meta = row['Prática (F)'], row['Prática (M)']
                        t_feito, t_meta = row['Teórica (F)'], row['Teórica (M)']
                        saldo = row['Saldo Final']
                        app_uso = row['Último Lançamento']
                        
                        saldo_p_real = row['Prática (F)'] - row['Prática (M)']
                        saldo_t_real = row['Teórica (F)'] - row['Teórica (M)']
                        
                        cor_p = "#dc2626" if saldo_p_real < 0 else "#2563eb"
                        bg_p = "#fef2f2" if saldo_p_real < 0 else "#eff6ff"
                        icone_p = "🔻" if saldo_p_real < 0 else "✅"
                        sinal_p = "+" if saldo_p_real > 0 else ""
                        
                        cor_t = "#dc2626" if saldo_t_real < 0 else "#7c3aed"
                        bg_t = "#fef2f2" if saldo_t_real < 0 else "#f5f3ff"
                        icone_t = "🔻" if saldo_t_real < 0 else "✅"
                        sinal_t = "+" if saldo_t_real > 0 else ""
                        
                        cor_borda = "#dc2626" if saldo < 0 else "#16a34a"
                        
                        if "Hoje" in app_uso or "Ontem" in app_uso:
                            cor_app, text_app = "#dcfce7", "#166534" 
                        elif any(dia in app_uso for dia in ["Há 2", "Há 3", "Há 4", "Há 5", "Há 6", "Há 7"]):
                            cor_app, text_app = "#fef3c7", "#92400e" 
                        else:
                            cor_app, text_app = "#fee2e2", "#991b1b" 

                        # O layout agora usa colunas do Streamlit para poder embutir o botão do lado direito
                        col_card, col_btn = st.columns([4.5, 1.2])
                        
                        with col_card:
                            st.markdown(f"""
<div style='background-color: #ffffff; border: 1px solid #e5e7eb; border-left: 6px solid {cor_borda}; border-radius: 10px; padding: 14px; margin-bottom: 10px; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; box-shadow: 0 2px 5px rgba(0,0,0,0.03);'>
    <div style='flex: 1.5; min-width: 200px; margin-right: 15px; margin-bottom: 5px;'>
        <div style='font-size: 1.1rem; font-weight: 800; color: #1f2937; margin-bottom: 6px;'>{nome}</div>
        <div style='display: flex; gap: 8px; align-items: center; flex-wrap: wrap;'>
            <span style='background-color: #f3f4f6; color: #4b5563; padding: 4px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 700; letter-spacing: 0.5px;'>{nucleo.upper()}</span>
            <span style='background-color: {cor_app}; color: {text_app}; padding: 4px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 700;'>📱 {app_uso}</span>
        </div>
    </div>
    <div style='flex: 1; min-width: 110px; text-align: center; border-right: 1px solid #e5e7eb; padding: 0 5px; margin-bottom: 5px;'>
        <div style='font-size: 0.75rem; font-weight: 700; color: #6b7280; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px;'>🩺 Prática</div>
        <div style='font-size: 0.95rem; font-weight: 600; color: #374151;'>
            <span style='color: #111827; font-weight: 900;'>{p_feito:.1f}h</span> <span style='color: #9ca3af; font-size: 0.8rem;'>/ {p_meta:.0f}h</span>
        </div>
    </div>
    <div style='flex: 1; min-width: 110px; text-align: center; padding: 0 5px; margin-bottom: 5px;'>
        <div style='font-size: 0.75rem; font-weight: 700; color: #6b7280; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px;'>📚 Teórica</div>
        <div style='font-size: 0.95rem; font-weight: 600; color: #374151;'>
            <span style='color: #111827; font-weight: 900;'>{t_feito:.1f}h</span> <span style='color: #9ca3af; font-size: 0.8rem;'>/ {t_meta:.0f}h</span>
        </div>
    </div>
    <div style='flex: 1; min-width: 110px; text-align: center; background-color: {bg_p}; padding: 8px 10px; border-radius: 6px; margin-right: 8px; margin-bottom: 5px;'>
        <div style='font-size: 0.70rem; font-weight: 800; color: {cor_p}; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px;'>Saldo Prática</div>
        <div style='font-size: 1.15rem; font-weight: 900; color: {cor_p};'>{icone_p} {sinal_p}{saldo_p_real:.1f}h</div>
    </div>
    <div style='flex: 1; min-width: 110px; text-align: center; background-color: {bg_t}; padding: 8px 10px; border-radius: 6px; margin-bottom: 5px;'>
        <div style='font-size: 0.70rem; font-weight: 800; color: {cor_t}; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px;'>Saldo Teoria</div>
        <div style='font-size: 1.15rem; font-weight: 900; color: {cor_t};'>{icone_t} {sinal_t}{saldo_t_real:.1f}h</div>
    </div>
</div>
                            """, unsafe_allow_html=True)
                        
                        with col_btn:
                            st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
                            
                            # Gera o PDF dinamicamente na memória, pronto para ser baixado
                            pdf_bytes = gerar_pdf_extrato(nome, nucleo, uid_row, todos_pontos_adm)
                            
                            st.download_button(
                                label="📄 Baixar PDF",
                                data=pdf_bytes,
                                file_name=f"Extrato_Auditoria_{nome.split()[0]}.pdf",
                                mime="application/pdf",
                                key=f"dl_pdf_{uid_row}",
                                use_container_width=True,
                                type="primary"
                            )

# --- MÓDULO 2: GESTÃO DE RESIDENTES ---
with aba2:
    st.markdown("<div class='card-title' style='margin-bottom: 20px;'>Gestão de Pessoal</div>", unsafe_allow_html=True)
        
    col_lista, col_cadastro = st.columns([1.5, 1], gap="large")
    
    # --- LADO ESQUERDO: LISTA DE RESIDENTES (AGRUPADA POR NÚCLEO) ---
    with col_lista:
        st.markdown("<h3 style='color: #374151; font-size: 1.3rem; font-weight: 700;'>📋 Equipe por Núcleo Profissional</h3>", unsafe_allow_html=True)
        
        if not lista_residentes:
            st.info("Nenhum residente cadastrado no sistema ainda.")
        else:
            # Lógica de Agrupamento por Núcleo
            grupos_profissoes = {}
            for res in sorted(lista_residentes, key=lambda x: x.get('nome_completo', '')):
                prof = res.get('profissao', 'Outros')
                if prof not in grupos_profissoes:
                    grupos_profissoes[prof] = []
                grupos_profissoes[prof].append(res)
            
            # Exibição dos Núcleos
            for prof, membros in sorted(grupos_profissoes.items()):
                st.markdown(f"<div style='background-color: #f3f4f6; padding: 8px 15px; border-radius: 6px; font-weight: 800; color: #4b5563; margin-top: 15px; margin-bottom: 10px; border-left: 4px solid #3b82f6; text-transform: uppercase;'>Núcleo: {prof} ({len(membros)})</div>", unsafe_allow_html=True)
                
                for res in membros:
                    uid_res = res.get('uid')
                    with st.container(border=True):
                        # Card de Exibição
                        st.markdown(f"""
                        <div style='display: flex; justify-content: space-between; align-items: center;'>
                            <div>
                                <h4 style='margin: 0; color: #1e40af; font-size: 1.1rem;'>{res.get('nome_completo', 'Sem nome')}</h4>
                                <span style='font-size: 0.85rem; color: #6b7280; font-weight: 500;'>{res.get('email', '')} | Lotação: {res.get('lotacao', 'Não informada')}</span>
                            </div>
                            <div style='text-align: right;'>
                                <span style='background-color: #dbeafe; color: #1e40af; padding: 4px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: 800;'>{res.get('perfil', 'Residente').upper()}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Gaveta de Edição (Expander)
                        with st.expander("⚙️ Editar Dados ou Resetar Senha"):
                            # O formulário de edição amarrado ao UID do residente para não misturar os dados
                            with st.form(f"form_edit_{uid_res}", border=False):
                                e_nome = st.text_input("Nome Completo", value=res.get('nome_completo', ''))
                                e_lotacao = st.text_input("Lotação (UBS)", value=res.get('lotacao', ''))
                                e_preceptor = st.text_input("Preceptor(a)", value=res.get('preceptor', ''))
                                
                                profissoes_base = ["Enfermagem", "Odontologia", "Psicologia", "Nutrição", "Fisioterapia", "Farmácia", "Serviço Social", "Educação Física", "Outros"]
                                idx_prof = profissoes_base.index(prof) if prof in profissoes_base else 8
                                e_prof = st.selectbox("Núcleo / Profissão", profissoes_base, index=idx_prof)
                                
                                st.markdown("<span style='font-size: 0.8rem; color: #6b7280;'>O E-mail (login) não pode ser alterado por aqui por segurança.</span>", unsafe_allow_html=True)
                                
                                btn_salvar_edicao = st.form_submit_button("💾 Salvar Alterações", type="primary", use_container_width=True)
                                
                                if btn_salvar_edicao:
                                    try:
                                        # 1. Atualiza no Banco de Dados (Firestore)
                                        db.collection("residentes").document(uid_res).update({
                                            "nome_completo": e_nome.strip(),
                                            "lotacao": e_lotacao.strip(),
                                            "preceptor": e_preceptor.strip(),
                                            "profissao": e_prof
                                        })
                                        # 2. Atualiza o nome visual no Firebase Auth
                                        auth.update_user(uid_res, display_name=e_nome.strip())
                                        
                                        st.success("✅ Dados atualizados com sucesso!")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Erro ao salvar: {e}")
                            
                            # Botão fora do formulário para Resetar a Senha
                            if st.button(f"🔑 Resetar Senha ({e_nome.split()[0]})", key=f"reset_{uid_res}"):
                                try:
                                    # Força uma senha padrão e obriga a troca no próximo login
                                    auth.update_user(uid_res, password="Mudar@123")
                                    db.collection("residentes").document(uid_res).update({"primeiro_login": True})
                                    st.success("✅ Senha resetada para 'Mudar@123'. O residente precisará criar uma nova senha ao logar.")
                                except Exception as e:
                                    st.error(f"Erro ao resetar: {e}")

    # --- LADO DIREITO: FORMULÁRIO DE NOVO CADASTRO ---
    with col_cadastro:
        st.markdown("<h3 style='color: #374151; font-size: 1.3rem; font-weight: 700;'>➕ Novo Residente</h3>", unsafe_allow_html=True)
        
        with st.form("form_novo_residente", clear_on_submit=True):
            st.markdown("<span style='font-size: 0.85rem; color: #6b7280;'>Cria o acesso e a ficha do residente simultaneamente.</span>", unsafe_allow_html=True)
            st.write("")
            
            n_nome = st.text_input("Nome Completo*")
            n_email = st.text_input("E-mail (Login)*")
            n_senha = st.text_input("Senha Provisória*", type="password", help="Mínimo de 6 caracteres")
            n_profissao = st.selectbox("Profissão / Núcleo*", ["Enfermagem", "Odontologia", "Psicologia", "Nutrição", "Fisioterapia", "Farmácia", "Serviço Social", "Educação Física"])
            n_lotacao = st.text_input("Lotação (UBS)")
            n_preceptor = st.text_input("Preceptor(a)")
            
            st.write("")
            btn_cadastrar = st.form_submit_button("🚀 Cadastrar Residente no Sistema", type="primary", use_container_width=True)
            
            if btn_cadastrar:
                if not n_nome or not n_email or not n_senha:
                    st.error("⚠️ Nome, E-mail e Senha são obrigatórios!")
                elif len(n_senha) < 6:
                    st.error("⚠️ A senha deve ter no mínimo 6 caracteres!")
                else:
                    try:
                        # Injeção Dupla (Auth + Banco de Dados)
                        user_record = auth.create_user(
                            email=n_email.strip(),
                            password=n_senha,
                            display_name=n_nome.strip()
                        )
                        
                        novo_residente_dados = {
                            "uid": user_record.uid,
                            "nome_completo": n_nome.strip(),
                            "email": n_email.strip(),
                            "profissao": n_profissao,
                            "lotacao": n_lotacao.strip() if n_lotacao else "Não informada",
                            "preceptor": n_preceptor.strip() if n_preceptor else "Não informado",
                            "perfil": "Residente",
                            "primeiro_login": True,
                            "data_cadastro": firestore.SERVER_TIMESTAMP
                        }
                        db.collection("residentes").document(user_record.uid).set(novo_residente_dados)
                        
                        st.success(f"✅ {n_nome} cadastrado com sucesso! A lista será atualizada.")
                        st.rerun() 
                    except auth.EmailAlreadyExistsError:
                        st.error("⚠️ Este e-mail já está cadastrado no Firebase!")
                    except Exception as e:
                        st.error(f"Erro ao tentar cadastrar: {e}")

# --- MÓDULO 3: AUDITORIA DE HORAS (MÁQUINA DO TEMPO & EXTRATO) ---
with aba3:
    # Função interna para formatar os decimais perfeitamente na tela do ADM
    def formatar_horas_exatas_adm(horas_decimais):
        sinal = "-" if horas_decimais < 0 else ""
        horas_decimais = abs(horas_decimais)
        horas = int(horas_decimais)
        minutos = int(round((horas_decimais - horas) * 60))
        if minutos == 60:
            horas += 1
            minutos = 0
        if minutos == 0: return f"{sinal}{horas}h"
        return f"{sinal}{horas}h {minutos:02d}m"

    st.markdown("<div class='card-title' style='margin-bottom: 20px;'>⏳ Central de Auditoria e Extratos</div>", unsafe_allow_html=True)
    
    if not lista_residentes:
        st.warning("⚠️ Cadastre um residente no Módulo 2 primeiro.")
    else:
        # --- FILTRO MESTRE (Serve para as duas sub-abas) ---
        st.markdown("<div style='font-weight: 600; color: #374151; margin-bottom: 5px;'>Selecione o Residente alvo da Auditoria:</div>", unsafe_allow_html=True)
        dict_residentes = {f"{r.get('nome_completo')} ({r.get('profissao')})": r.get('uid') for r in lista_residentes}
        residente_selecionado = st.selectbox("Residente", options=list(dict_residentes.keys()), label_visibility="collapsed", key="sel_res_auditoria")
        uid_alvo = dict_residentes[residente_selecionado]

        st.write("")
        
        # Criação das Sub-Abas para não poluir a tela
        sub_aba_diaria, sub_aba_mensal, sub_aba_filtros = st.tabs(["📅 Edição Diária", "🏦 Extrato Mensal", "🔍 Filtro Investigativo"])

# ========================================================
        # SUB-ABA 1: A MÁQUINA DO TEMPO (Injeção e Edição Diária)
        # ========================================================
        with sub_aba_diaria:
            import datetime as dt
            
            col_data, _ = st.columns([1, 2])
            with col_data:
                st.markdown("<div style='font-weight: 600; color: #374151; margin-top: 10px; margin-bottom: 5px;'>Selecione a Data do Ponto</div>", unsafe_allow_html=True)
                data_auditoria = st.date_input("Data", value=dt.datetime.today(), label_visibility="collapsed", key="dt_auditoria")

            st.markdown("---")
            data_str_alvo = data_auditoria.strftime("%Y-%m-%d")
            
            try:
                pontos_ref = db.collection("pontos").where("uid_residente", "==", uid_alvo).where("data_registro", "==", data_str_alvo).get()
                pontos_alvo = [p.to_dict() | {"doc_id": p.id} for p in pontos_ref]
            except Exception as e:
                st.error(f"Erro ao buscar pontos: {e}")
                pontos_alvo = []

            col_registros, col_injetar = st.columns([1.5, 1], gap="large")

            # --- LADO ESQUERDO: O QUE TEM NO DIA (COM EDIÇÃO) ---
            with col_registros:
                st.markdown(f"<h3 style='color: #1e40af; font-size: 1.2rem; font-weight: 700;'>🔎 Registros salvos em {data_auditoria.strftime('%d/%m/%Y')}</h3>", unsafe_allow_html=True)
                
                if not pontos_alvo:
                    st.info("Nenhum registro encontrado para este residente nesta data.")
                else:
                    for pt in pontos_alvo:
                        cat = pt.get("categoria", "")
                        horas_decimais = pt.get("horas_computadas", 0.0)
                        obs = pt.get("justificativa", "Sem observações")
                        horarios = " | ".join(pt.get("horarios_descritos", []))
                        if not horarios: horarios = ""
                        
                        cor_borda = "#16a34a" if cat == "Prática" else ("#1e40af" if "Teórica" in cat else "#dc2626")
                        horas_formatadas = formatar_horas_exatas_adm(horas_decimais)
                        
                        with st.container(border=True):
                            # Visão Resumida do Card
                            st.markdown(f"""
                            <div style='display: flex; justify-content: space-between;'>
                                <div>
                                    <span style='font-weight: 800; color: {cor_borda}; font-size: 1.1rem;'>{cat}</span><br>
                                    <span style='font-size: 0.85rem; color: #6b7280;'>🕛 {horarios if horarios else "Dia Integral / Sem relógio"}</span><br>
                                    <span style='font-size: 0.85rem; color: #4b5563; font-style: italic;'>"{obs}"</span>
                                </div>
                                <div style='text-align: right; font-weight: 800; font-size: 1.3rem; color: {cor_borda};'>
                                    {horas_formatadas}
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                            
 # A GAVETA DE EDIÇÃO SUPREMA DO ADM
                            with st.expander("✏️ Editar ou Excluir Registro"):
                                # Quebra o decimal atual em HH e MM para preencher o formulário
                                h_atual = int(abs(horas_decimais))
                                m_atual = int(round((abs(horas_decimais) - h_atual) * 60))
                                if m_atual == 60:
                                    h_atual += 1
                                    m_atual = 0
                                
                                with st.form(key=f"form_edit_{pt['doc_id']}", border=False):
                                    opcoes_cat = ["Prática", "Teórica", "Teórico-prática", "Ausência justificada", "Falta", "Férias", "Feriado", "Licença", "Atestado", "Ponto facultativo"]
                                    idx_cat = opcoes_cat.index(cat) if cat in opcoes_cat else 0
                                    
                                    e_cat = st.selectbox("Categoria", opcoes_cat, index=idx_cat)
                                    
                                    st.markdown("<span style='font-size: 0.85rem; color: #d97706; font-weight: 600;'>Opção A: Lançamento Manual (Para Atestados/Faltas)</span>", unsafe_allow_html=True)
                                    c_h, c_m = st.columns(2)
                                    e_h = c_h.text_input("Horas (HH)", value=f"{h_atual:02d}")
                                    e_m = c_m.text_input("Minutos (MM)", value=f"{m_atual:02d}")
                                    
                                    st.markdown("<hr style='margin: 15px 0 10px 0; border-color: #e5e7eb;'>", unsafe_allow_html=True)
                                    st.markdown("<span style='font-size: 0.85rem; color: #16a34a; font-weight: 600;'>Opção B: Cálculo Automático Inteligente</span><br><span style='font-size: 0.8rem; color: #6b7280;'>Se você alterar os horários abaixo (ex: <i>07:00 às 12:00</i>), o sistema ignorará as caixinhas de cima e <b>calculará o total automaticamente</b> ao salvar!</span>", unsafe_allow_html=True)
                                    
                                    e_horarios = st.text_input("Horários (Use ' | ' para separar turnos)", value=horarios)
                                    e_obs = st.text_area("Justificativa", value=obs)
                                    
                                    btn_salvar_edicao = st.form_submit_button("💾 Salvar Alterações", type="primary", use_container_width=True)
                                
                                # Ações dos Botões
                                if btn_salvar_edicao:
                                    try:
                                        novos_horarios_lista = [h.strip() for h in e_horarios.split("|") if h.strip()]
                                        horas_calculadas = 0.0
                                        recalculo_ativado = False
                                        
                                        # ==========================================
                                        # O MOTOR EXTRATOR DE HORAS
                                        # ==========================================
                                        if any("às" in h for h in novos_horarios_lista):
                                            for turno in novos_horarios_lista:
                                                if "às" in turno:
                                                    try:
                                                        ent, sai = turno.split(" às ")
                                                        h1, m1 = map(int, ent.strip().split(":"))
                                                        h2, m2 = map(int, sai.strip().split(":"))
                                                        
                                                        min_ent = h1 * 60 + m1
                                                        min_sai = h2 * 60 + m2
                                                        if min_sai < min_ent: min_sai += 24 * 60 # Caso vire a madrugada
                                                        
                                                        horas_calculadas += (min_sai - min_ent) / 60.0
                                                        recalculo_ativado = True
                                                    except:
                                                        pass # Se estiver mal digitado, ele pula e ignora
                                        
                                        # Se o sistema achou horas válidas no texto, ele usa elas. Senão, usa o manual.
                                        if recalculo_ativado and horas_calculadas > 0:
                                            nova_hora_decimal = horas_calculadas
                                        else:
                                            hh_val = int(e_h) if e_h and e_h.isdigit() else 0
                                            mm_val = int(e_m) if e_m and e_m.isdigit() else 0
                                            nova_hora_decimal = hh_val + (mm_val / 60.0)
                                            
                                        # ==========================================

                                        db.collection("pontos").document(pt['doc_id']).update({
                                            "categoria": e_cat,
                                            "horas_computadas": nova_hora_decimal,
                                            "horarios_descritos": novos_horarios_lista,
                                            "justificativa": e_obs,
                                            "ultima_edicao": firestore.SERVER_TIMESTAMP
                                        })
                                        st.success("✅ Registro atualizado com sucesso!")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Erro ao atualizar: {e}")
                                
                                if st.button("🗑️ Forçar Exclusão", key=f"del_adm_{pt['doc_id']}", use_container_width=True):
                                    db.collection("pontos").document(pt['doc_id']).delete()
                                    st.success("✅ Ponto obliterado pelo Administrador!")
                                    st.rerun()

            # --- LADO DIREITO: INJEÇÃO DE HORAS ---
            with col_injetar:
                st.markdown("<h3 style='color: #d97706; font-size: 1.2rem; font-weight: 700;'>💉 Injetar Horas Manualmente</h3>", unsafe_allow_html=True)
                
                with st.form("form_injetar_adm", clear_on_submit=True):
                    i_cat = st.selectbox("Categoria", ["Prática", "Teórica", "Teórico-prática", "Ausência justificada", "Falta", "Férias", "Feriado", "Licença", "Atestado", "Ponto facultativo"])
                    
                    st.info("💡 **Atenção:** Se for ausência de dia integral, deixe as horas zeradas.")
                    
                    st.markdown("<span style='font-weight: 600; font-size: 0.95rem; color: #374151;'>Total de Horas a Computar:</span>", unsafe_allow_html=True)
                    col_h, col_m = st.columns(2)
                    i_hh = col_h.text_input("Horas (HH)", placeholder="00", max_chars=2)
                    i_mm = col_m.text_input("Minutos (MM)", placeholder="00", max_chars=2)
                    
                    i_obs = st.text_area("Justificativa / Motivo da injeção")
                    
                    btn_salvar_injecao = st.form_submit_button("💾 Injetar no Banco de Dados", type="primary", use_container_width=True)
                    
                    if btn_salvar_injecao:
                        hh_val = int(i_hh) if i_hh and i_hh.isdigit() else 0
                        mm_val = int(i_mm) if i_mm and i_mm.isdigit() else 0
                        horas_finais_decimais = hh_val + (mm_val / 60.0)
                        
                        doc_id_inj = f"{uid_alvo}_{data_str_alvo}_{i_cat.replace(' ', '')}"
                        
                        dados_inj = {
                            "uid_residente": uid_alvo,
                            "data_registro": data_str_alvo,
                            "mes_referencia": data_auditoria.strftime("%m/%Y"),
                            "categoria": i_cat,
                            "horas_computadas": horas_finais_decimais,
                            "horarios_descritos": [f"{hh_val:02d}h {mm_val:02d}m (Lançado via Painel ADM)"],
                            "justificativa": f"{i_obs} (Alteração realizada pela Coordenação)" if i_obs else "(Alteração ADM)",
                            "ultima_edicao": firestore.SERVER_TIMESTAMP
                        }
                        
                        try:
                            db.collection("pontos").document(doc_id_inj).set(dados_inj)
                            st.success("✅ Registro injetado com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao injetar horas: {e}")

        # ========================================================
        # SUB-ABA 2: O EXTRATO NUBANK (Visão Mensal)
        # ========================================================
        with sub_aba_mensal:
            import datetime as dt
            import calendar
            
            # Puxa os meses disponíveis baseados no ciclo
            meses_disponiveis = [f"{str(m).zfill(2)}/{ano}" for ano in [2026, 2027, 2028] for m in range(1, 13)]
            mes_atual_str = dt.datetime.today().strftime("%m/%Y")
            idx_mes = meses_disponiveis.index(mes_atual_str) if mes_atual_str in meses_disponiveis else 2 
            
            c_mes, _ = st.columns([1, 3])
            with c_mes:
                mes_extrato = st.selectbox("Selecione o Mês", meses_disponiveis, index=idx_mes, key="sel_mes_extrato")
            
            st.markdown("---")
            
            # --- MOTOR DE CÁLCULO DO EXTRATO ---
            try:
                pontos_extrato_ref = db.collection("pontos").where("uid_residente", "==", uid_alvo).where("mes_referencia", "==", mes_extrato).get()
                pontos_extrato = [p.to_dict() for p in pontos_extrato_ref]
            except:
                pontos_extrato = []
                
            if not pontos_extrato:
                st.info(f"Nenhuma movimentação registrada para {residente_selecionado.split('(')[0].strip()} no mês de {mes_extrato}.")
            else:
                import calendar
                from datetime import datetime, timedelta, date
                
                # ==========================================
                # 1. CÁLCULO DA META EXATA DO MÊS SELECIONADO
                # ==========================================
                mes_str, ano_str = mes_extrato.split('/')
                mes_num, ano_num = int(mes_str), int(ano_str)
                
                _, dias_no_mes = calendar.monthrange(ano_num, mes_num)
                meta_p_mes = 0.0
                meta_t_mes = 0.0
                
                for dia in range(1, dias_no_mes + 1):
                    p_meta, t_meta = obter_metas_do_dia(date(ano_num, mes_num, dia))
                    meta_p_mes += p_meta
                    meta_t_mes += t_meta

                # 2. CÁLCULO DO QUE FOI REALIZADO (O que fez de verdade)
                trab_p = 0.0
                trab_t = 0.0
                extrato_detalhado = []
                
                for pt in pontos_extrato:
                    cat = pt.get("categoria", "")
                    horas = float(pt.get("horas_computadas", 0.0))
                    data_str = pt.get("data_registro")
                    dt_obj = datetime.strptime(data_str, "%Y-%m-%d").date()
                    
                    p_dia, t_dia = obter_metas_do_dia(dt_obj)
                        
                    # 1. TRATAMENTO DE OURO: FÉRIAS É DIREITO (Abono integral da meta do dia)
                    if cat == "Férias":
                        trab_p += p_dia
                        trab_t += t_dia
                        valor_visual_p = f"Isento (+{formatar_horas_exatas_adm(p_dia)})"
                        valor_visual_t = f"Isento (+{formatar_horas_exatas_adm(t_dia)})"
                        cor_linha = "#eff6ff" # Azul clarinho (Destaque de benefício)
                        cor_texto = "#2563eb" # Azul forte
                        
                    # 2. AUSÊNCIAS COMUNS E FALTAS (Geram débito se não houver hora compensada no dia)
                    elif cat in ["Ausência justificada", "Falta", "Feriado", "Licença", "Atestado", "Ponto facultativo"]:
                        horas_trab_p_no_dia = sum(float(p2.get("horas_computadas", 0.0)) for p2 in pontos_extrato if p2.get("data_registro") == data_str and p2.get("categoria") == "Prática")
                        horas_trab_t_no_dia = sum(float(p2.get("horas_computadas", 0.0)) for p2 in pontos_extrato if p2.get("data_registro") == data_str and p2.get("categoria") in ["Teórica", "Teórico-prática"])
                        
                        deb_p = p_dia - horas_trab_p_no_dia if (p_dia - horas_trab_p_no_dia) > 0 else 0.0
                        deb_t = t_dia - horas_trab_t_no_dia if (t_dia - horas_trab_t_no_dia) > 0 else 0.0
                        
                        valor_visual_p = f"-{formatar_horas_exatas_adm(deb_p)}"
                        valor_visual_t = f"-{formatar_horas_exatas_adm(deb_t)}"
                        cor_linha = "#fef2f2" # Fundo avermelhado
                        cor_texto = "#dc2626"
                        
                    # 3. LANÇAMENTOS COMUNS DE TRABALHO
                    else:
                        if cat == "Prática": 
                            trab_p += horas
                            valor_visual_p = f"+{formatar_horas_exatas_adm(horas)}"
                            valor_visual_t = "0h"
                        else: 
                            trab_t += horas
                            valor_visual_p = "0h"
                            valor_visual_t = f"+{formatar_horas_exatas_adm(horas)}"
                            
                        cor_linha = "#ffffff"
                        cor_texto = "#16a34a"

                    obs = pt.get("justificativa", "Sem observações")
                    horarios = " | ".join(pt.get("horarios_descritos", []))
                    if not horarios: horarios = "Integral"
                    
                    extrato_detalhado.append({
                        "data_obj": dt_obj,
                        "categoria": cat,
                        "horarios": horarios,
                        "obs": obs,
                        "vp": valor_visual_p,
                        "vt": valor_visual_t,
                        "cor_bg": cor_linha,
                        "cor_tx": cor_texto
                    })

                saldo_p = trab_p - meta_p_mes
                saldo_t = trab_t - meta_t_mes

                # --- RENDERIZAÇÃO DOS CARDS ESTILO NUBANK ---
                c_p, c_t = st.columns(2)
                
                with c_p:
                    cor_saldo_p = "#16a34a" if saldo_p >= 0 else "#dc2626"
                    sinal_p = "+" if saldo_p > 0 else ""
                    st.markdown(f"""
                    <div style='background-color: #f8fafc; padding: 20px; border-radius: 12px; border: 1px solid #e5e7eb; border-top: 5px solid {cor_saldo_p}; text-align: center;'>
                        <div style='color: #6b7280; font-weight: 700; font-size: 0.95rem; text-transform: uppercase; margin-bottom: 15px; letter-spacing: 1px;'>Extrato: Prática</div>
                        <div style='display: flex; justify-content: space-around; margin-bottom: 20px;'>
                            <div>
                                <div style='font-size: 0.85rem; color: #6b7280; font-weight: 600;'>Horas Realizadas</div>
                                <div style='font-size: 1.4rem; font-weight: 800; color: #111827;'>{formatar_horas_exatas_adm(trab_p)}</div>
                            </div>
                            <div>
                                <div style='font-size: 0.85rem; color: #6b7280; font-weight: 600;'>Meta Prevista</div>
                                <div style='font-size: 1.4rem; font-weight: 800; color: #4b5563;'>{formatar_horas_exatas_adm(meta_p_mes)}</div>
                            </div>
                        </div>
                        <div style='background-color: {cor_saldo_p}15; padding: 12px; border-radius: 8px; border: 1px solid {cor_saldo_p}30;'>
                            <span style='font-size: 0.95rem; font-weight: 700; color: {cor_saldo_p}; text-transform: uppercase;'>Saldo do Mês:</span> 
                            <span style='font-size: 1.7rem; font-weight: 900; color: {cor_saldo_p}; margin-left: 10px;'>{sinal_p}{formatar_horas_exatas_adm(saldo_p)}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                with c_t:
                    cor_saldo_t = "#1e40af" if saldo_t >= 0 else "#dc2626"
                    sinal_t = "+" if saldo_t > 0 else ""
                    st.markdown(f"""
                    <div style='background-color: #f8fafc; padding: 20px; border-radius: 12px; border: 1px solid #e5e7eb; border-top: 5px solid {cor_saldo_t}; text-align: center;'>
                        <div style='color: #6b7280; font-weight: 700; font-size: 0.95rem; text-transform: uppercase; margin-bottom: 15px; letter-spacing: 1px;'>Extrato: Teórica</div>
                        <div style='display: flex; justify-content: space-around; margin-bottom: 20px;'>
                            <div>
                                <div style='font-size: 0.85rem; color: #6b7280; font-weight: 600;'>Horas Realizadas</div>
                                <div style='font-size: 1.4rem; font-weight: 800; color: #111827;'>{formatar_horas_exatas_adm(trab_t)}</div>
                            </div>
                            <div>
                                <div style='font-size: 0.85rem; color: #6b7280; font-weight: 600;'>Meta Prevista</div>
                                <div style='font-size: 1.4rem; font-weight: 800; color: #4b5563;'>{formatar_horas_exatas_adm(meta_t_mes)}</div>
                            </div>
                        </div>
                        <div style='background-color: {cor_saldo_t}15; padding: 12px; border-radius: 8px; border: 1px solid {cor_saldo_t}30;'>
                            <span style='font-size: 0.95rem; font-weight: 700; color: {cor_saldo_t}; text-transform: uppercase;'>Saldo do Mês:</span> 
                            <span style='font-size: 1.7rem; font-weight: 900; color: {cor_saldo_t}; margin-left: 10px;'>{sinal_t}{formatar_horas_exatas_adm(saldo_t)}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                
                st.write("")
                st.markdown("<h4 style='color: #374151; font-weight: 700;'>🧾 Histórico de Lançamentos (Ledger)</h4>", unsafe_allow_html=True)
                
                extrato_detalhado = sorted(extrato_detalhado, key=lambda k: k["data_obj"], reverse=True)
                
                for item in extrato_detalhado:
                    data_formatada = item["data_obj"].strftime("%d/%m/%Y")
                    st.markdown(f"""
                    <div style='background-color: {item["cor_bg"]}; padding: 15px; border-bottom: 1px solid #e5e7eb; display: flex; justify-content: space-between; align-items: center;'>
                        <div style='flex: 1;'>
                            <div style='font-size: 1rem; font-weight: 700; color: #111827;'>{data_formatada} <span style='font-weight: 500; color: #6b7280; font-size: 0.9rem; margin-left: 10px;'>{item['categoria']}</span></div>
                            <div style='font-size: 0.85rem; color: #4b5563; margin-top: 4px;'>🕛 {item['horarios']}</div>
                            <div style='font-size: 0.85rem; color: #9ca3af; font-style: italic; margin-top: 2px;'>{item['obs']}</div>
                        </div>
                        <div style='text-align: right;'>
                            <div style='font-size: 0.9rem; font-weight: 700; color: {item["cor_tx"]}; margin-bottom: 3px;'><span style='color: #9ca3af; font-weight: 500; font-size: 0.75rem; margin-right: 5px;'>PRÁT:</span> {item['vp']}</div>
                            <div style='font-size: 0.9rem; font-weight: 700; color: {item["cor_tx"]};'><span style='color: #9ca3af; font-weight: 500; font-size: 0.75rem; margin-right: 5px;'>TEÓR:</span> {item['vt']}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

# ========================================================
        # SUB-ABA 3: FILTRO INVESTIGATIVO (Busca Avançada)
        # ========================================================
        with sub_aba_filtros:
            st.markdown("<h3 style='color: #374151; font-weight: 800; margin-bottom: 5px;'>🔍 Filtro Investigativo por Categoria</h3>", unsafe_allow_html=True)
            st.markdown("<span style='color: #6b7280; font-size: 0.95rem;'>Selecione uma ou mais categorias abaixo para auditar o histórico isolado deste residente.</span><br><br>", unsafe_allow_html=True)
            
            opcoes_categorias = ["Feriado", "Ponto facultativo", "Falta", "Atestado", "Ausência justificada", "Licença", "Férias", "Prática", "Teórica", "Teórico-prática"]
            
            categorias_selecionadas = st.multiselect("Selecione as Categorias Alvo:", opcoes_categorias, placeholder="Ex: Feriado, Ponto facultativo, Atestado...")
            
            if categorias_selecionadas:
                with st.spinner("Puxando capivara do residente..."):
                    try:
                        # Busca no banco apenas os registros deste residente que batem com as categorias escolhidas
                        pontos_filtro_ref = db.collection("pontos").where("uid_residente", "==", uid_alvo).where("categoria", "in", categorias_selecionadas).get()
                        pontos_filtrados = [p.to_dict() for p in pontos_filtro_ref]
                    except Exception as e:
                        st.error(f"Erro ao buscar dados: {e}")
                        pontos_filtrados = []
                    
                    if not pontos_filtrados:
                        st.info("Nenhuma ocorrência encontrada para as categorias selecionadas.")
                    else:
                        import datetime as dt
                        # Ordenar por data decrescente (mais recente primeiro)
                        pontos_filtrados = sorted(pontos_filtrados, key=lambda k: k.get("data_registro", ""), reverse=True)
                        
                        datas_unicas = set()
                        total_trab_p, total_trab_t = 0.0, 0.0
                        total_deb_p, total_deb_t = 0.0, 0.0
                        total_abono_p, total_abono_t = 0.0, 0.0
                        
                        # --- NOVO MOTOR DE IMPACTO REAL NO BANCO DE HORAS (SEPARADO P/T) ---
                        for pt in pontos_filtrados:
                            cat = pt.get("categoria", "")
                            # Normaliza categorias importadas do Excel antigo (caso estejam em maiúsculo)
                            if cat.upper() == "ATESTADO": cat = "Atestado"
                            elif cat.upper() == "FERIADO": cat = "Feriado"
                            elif cat.upper() == "FALTA": cat = "Falta"
                            elif cat.upper() == "PONTO FACULTATIVO": cat = "Ponto facultativo"
                            
                            horas = float(pt.get("horas_computadas", 0.0))
                            data_str = pt.get("data_registro", "")
                            
                            if data_str:
                                datas_unicas.add(data_str)
                                dt_obj = dt.datetime.strptime(data_str, "%Y-%m-%d").date()
                                
                                # Puxa a meta do motor oficial separadamente
                                p_dia, t_dia = obter_metas_do_dia(dt_obj)
                                
                                if cat == "Férias":
                                    total_abono_p += p_dia
                                    total_abono_t += t_dia
                                elif cat in ["Ausência justificada", "Falta", "Feriado", "Licença", "Atestado", "Ponto facultativo"]:
                                    deb_p = p_dia
                                    deb_t = t_dia
                                    
                                    # Se lançou alguma hora no dia de falta, abate da dívida primeiro da prática
                                    if horas > 0:
                                        if deb_p >= horas: deb_p -= horas
                                        else:
                                            resto = horas - deb_p
                                            deb_p = 0.0
                                            deb_t = max(0.0, deb_t - resto)
                                    
                                    total_deb_p += deb_p
                                    total_deb_t += deb_t
                                elif cat == "Prática":
                                    total_trab_p += horas
                                else:
                                    total_trab_t += horas

                        # --- Montagem Visual Dinâmica do Impacto ---
                        html_impacto = ""
                        
                        # Bloco Prática
                        if total_trab_p > 0 or total_deb_p > 0 or total_abono_p > 0:
                            html_impacto += "<div style='margin-bottom: 10px;'>"
                            if total_trab_p > 0: html_impacto += f"<div style='font-size: 1.05rem; color: #2563eb; font-weight: 800;'>✅ +{total_trab_p:.1f}h (Prática Trabalhada)</div>"
                            if total_deb_p > 0: html_impacto += f"<div style='font-size: 1.05rem; color: #dc2626; font-weight: 800;'>🔻 -{total_deb_p:.1f}h (Débito de Prática)</div>"
                            if total_abono_p > 0: html_impacto += f"<div style='font-size: 1.05rem; color: #2563eb; font-weight: 800;'>🏖️ +{total_abono_p:.1f}h (Abono de Prática)</div>"
                            html_impacto += "</div>"
                            
                        # Bloco Teórica
                        if total_trab_t > 0 or total_deb_t > 0 or total_abono_t > 0:
                            html_impacto += "<div>"
                            if total_trab_t > 0: html_impacto += f"<div style='font-size: 1.05rem; color: #7c3aed; font-weight: 800;'>✅ +{total_trab_t:.1f}h (Teórica Trabalhada)</div>"
                            if total_deb_t > 0: html_impacto += f"<div style='font-size: 1.05rem; color: #dc2626; font-weight: 800;'>🔻 -{total_deb_t:.1f}h (Débito de Teórica)</div>"
                            if total_abono_t > 0: html_impacto += f"<div style='font-size: 1.05rem; color: #7c3aed; font-weight: 800;'>🏖️ +{total_abono_t:.1f}h (Abono de Teórica)</div>"
                            html_impacto += "</div>"
                            
                        if not html_impacto:
                            html_impacto = "<div style='font-size: 1.05rem; color: #6b7280; font-weight: 800;'>0.0h</div>"

                        # --- KPIs do Filtro ---
                        c1, c2 = st.columns([1, 1.8])
                        with c1:
                            st.markdown(f"""
                            <div style='background-color: #fcfaee; border: 1px solid #e5e7eb; border-left: 5px solid #d97706; padding: 15px; border-radius: 8px; height: 100%;'>
                                <div style='font-size: 0.85rem; color: #6b7280; font-weight: 700; text-transform: uppercase;'>Total de Dias (Ocorrências)</div>
                                <div style='font-size: 1.8rem; color: #b45309; font-weight: 800;'>{len(datas_unicas)} dias</div>
                            </div>
                            """, unsafe_allow_html=True)
                        with c2:
                            st.markdown(f"""
                            <div style='background-color: #f8fafc; border: 1px solid #e5e7eb; border-left: 5px solid #3b82f6; padding: 15px; border-radius: 8px; height: 100%; display: flex; flex-direction: column; justify-content: center;'>
                                <div style='font-size: 0.80rem; color: #6b7280; font-weight: 700; text-transform: uppercase; margin-bottom: 4px;'>O que isso causou no Banco de Horas:</div>
                                {html_impacto}
                            </div>
                            """, unsafe_allow_html=True)
                        
                        st.markdown("<hr style='border-color: #e5e7eb; margin: 25px 0 15px 0;'>", unsafe_allow_html=True)
                        st.markdown("<h4 style='color: #374151; font-weight: 700; font-size: 1.1rem; margin-bottom: 15px;'>📋 Lista Detalhada</h4>", unsafe_allow_html=True)
                        
                        # --- Lista de Resultados ---
                        for pt in pontos_filtrados:
                            data_pt_str = pt.get("data_registro", "")
                            cat = pt.get("categoria", "")
                            if cat.upper() == "ATESTADO": cat = "Atestado"
                            elif cat.upper() == "FERIADO": cat = "Feriado"
                            elif cat.upper() == "FALTA": cat = "Falta"
                            elif cat.upper() == "PONTO FACULTATIVO": cat = "Ponto facultativo"
                            
                            horas = float(pt.get("horas_computadas", 0.0))
                            obs = pt.get("justificativa", "Sem observações adicionais.")
                            
                            impacto_p = ""
                            impacto_t = ""
                            cor_cat = "#6b7280"
                            txt_color = "#6b7280"
                            
                            if data_pt_str:
                                dt_obj = dt.datetime.strptime(data_pt_str, "%Y-%m-%d").date()
                                p_dia, t_dia = obter_metas_do_dia(dt_obj)
                                
                                if cat == "Férias":
                                    impacto_p = f"+{p_dia:.1f}h (Abono)"
                                    impacto_t = f"+{t_dia:.1f}h (Abono)"
                                    cor_cat = "#2563eb"
                                    txt_color = "#2563eb"
                                elif cat in ["Ausência justificada", "Falta", "Feriado", "Licença", "Atestado", "Ponto facultativo"]:
                                    deb_p = p_dia
                                    deb_t = t_dia
                                    if horas > 0:
                                        if deb_p >= horas: deb_p -= horas
                                        else:
                                            resto = horas - deb_p
                                            deb_p = 0.0
                                            deb_t = max(0.0, deb_t - resto)
                                            
                                    impacto_p = f"-{deb_p:.1f}h (Débito)"
                                    impacto_t = f"-{deb_t:.1f}h (Débito)"
                                    cor_cat = "#dc2626"
                                    txt_color = "#dc2626"
                                elif cat == "Prática":
                                    impacto_p = f"+{horas:.1f}h (Trabalhada)"
                                    impacto_t = "0.0h"
                                    cor_cat = "#16a34a"
                                    txt_color = "#16a34a"
                                else:
                                    impacto_p = "0.0h"
                                    impacto_t = f"+{horas:.1f}h (Trabalhada)"
                                    cor_cat = "#7c3aed"
                                    txt_color = "#7c3aed"
                            
                                data_formatada = dt_obj.strftime("%d/%m/%Y")
                            else:
                                data_formatada = "Sem Data"
                                impacto_p = "0.0h"
                                impacto_t = "0.0h"
                                
                            st.markdown(f"""
                            <div style='display: flex; justify-content: space-between; align-items: center; background-color: #ffffff; border: 1px solid #e5e7eb; padding: 12px 18px; border-radius: 8px; margin-bottom: 10px; box-shadow: 0 1px 2px rgba(0,0,0,0.02);'>
                                <div style='flex: 1;'>
                                    <div style='font-weight: 800; color: #1f2937; font-size: 1.05rem;'>{data_formatada} <span style='font-weight: 700; font-size: 0.75rem; background-color: {cor_cat}15; color: {cor_cat}; padding: 4px 10px; border-radius: 20px; margin-left: 10px; text-transform: uppercase;'>{cat}</span></div>
                                    <div style='font-size: 0.9rem; color: #6b7280; margin-top: 5px; font-style: italic;'>"{obs}"</div>
                                </div>
                                <div style='text-align: right; min-width: 140px;'>
                                    <div style='font-size: 0.95rem; font-weight: 800; color: {txt_color}; margin-bottom: 4px;'><span style='color: #9ca3af; font-weight: 600; font-size: 0.75rem; margin-right: 5px;'>PRÁT:</span> {impacto_p}</div>
                                    <div style='font-size: 0.95rem; font-weight: 800; color: {txt_color};'><span style='color: #9ca3af; font-weight: 600; font-size: 0.75rem; margin-right: 5px;'>TEÓR:</span> {impacto_t}</div>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
