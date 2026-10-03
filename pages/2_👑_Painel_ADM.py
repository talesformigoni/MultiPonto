import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from uuid import uuid4
from firebase_admin import auth, firestore
from firebase_config import db
from utils import aplicar_css, checar_login
from calculadora_horas import (
    obter_metas_do_dia,
    calcular_motor_horas,
    calcular_periodo,
    normalizar_categoria,
    obter_fim_programa,
    obter_periodo_ano_residencia,
    META_ANUAL_PRATICA,
    META_ANUAL_TEORIA,
    DURACAO_PROGRAMA_ANOS,
)

# ==========================================
# CATEGORIAS OFICIAIS (PADRÃO DO SISTEMA)
# ==========================================
CATEGORIAS_OFICIAIS = [
    "Prática",
    "Teórica",
    "Estudo Auto-dirigido (AAD)",
    "Férias",
    "Falta",
    "Atestado / Licença Médica",
    "Feriado / Ponto Facultativo",
    "Ausência Justificada"
]

# Versão do contrato de cálculo gravado nos agregadores do Firebase.
# Se a regra mudar novamente, basta incrementar este número para forçar
# a reconstrução automática dos resumos sem quebrar o cache.
VERSAO_MOTOR_ADM = 103

CATEGORIAS_TRABALHO = {
    "Prática",
    "Teórica",
    "Teórico-prática",
    "Estudo Auto-dirigido (AAD)",
}

CATEGORIAS_AUSENCIA = {
    "Férias",
    "Falta",
    "Atestado / Licença Médica",
    "Feriado / Ponto Facultativo",
    "Ausência Justificada",
}

CATEGORIAS_REPOSICAO = {
    "Falta",
    "Atestado / Licença Médica",
    "Feriado / Ponto Facultativo",
    "Ausência Justificada",
}

FUSO_LOCAL = ZoneInfo("America/Porto_Velho")
DATA_INICIO_RESIDENCIA = date(2026, 3, 2)

def agora_local():
    return datetime.now(FUSO_LOCAL)

def hoje_local():
    return agora_local().date()

def calcular_referencia_curricular_adm(data_inicio, data_fim_referencia):
    """
    Meta curricular comum da turma. Férias individuais NÃO reduzem esta
    referência. Cada R é limitado a 2.304h práticas + 576h teóricas, isto é,
    48 semanas de 60h dentro do ano de residência.

    Esta função fica no próprio ADM para continuar compatível com o
    calculadora_horas.py 102 que já está funcionando no restante do sistema.
    """
    fim_programa = obter_fim_programa(data_inicio)
    limite = min(data_fim_referencia, fim_programa)

    if limite < data_inicio:
        return {"pratica": 0.0, "teoria": 0.0, "total": 0.0}

    ref_p = 0.0
    ref_t = 0.0

    for numero_r in range(1, DURACAO_PROGRAMA_ANOS + 1):
        ini_r, fim_r = obter_periodo_ano_residencia(data_inicio, numero_r)
        if limite < ini_r:
            break

        fim_apurado = min(limite, fim_r)
        bruto = calcular_periodo(
            [],
            ini_r,
            fim_apurado,
            data_inicio_programa=data_inicio,
            data_fim_programa=fim_programa,
        )

        ref_p += min(bruto["curricular_base_pratica"], META_ANUAL_PRATICA)
        ref_t += min(bruto["curricular_base_teoria"], META_ANUAL_TEORIA)

    return {"pratica": ref_p, "teoria": ref_t, "total": ref_p + ref_t}

# Disponível para todos os módulos/tabs sem depender da execução da aba Raio-X.
data_inicio_residencia = DATA_INICIO_RESIDENCIA

def _safe_float(valor):
    try:
        return float(valor or 0.0)
    except (TypeError, ValueError):
        return 0.0

def _parse_hhmm_duracao(hh_txt, mm_txt):
    """Valida uma duração diária manual e devolve horas decimais."""
    hh_txt = (hh_txt or "").strip()
    mm_txt = (mm_txt or "").strip()

    if hh_txt and not hh_txt.isdigit():
        raise ValueError("Horas devem conter apenas números.")
    if mm_txt and not mm_txt.isdigit():
        raise ValueError("Minutos devem conter apenas números.")

    hh = int(hh_txt) if hh_txt else 0
    mm = int(mm_txt) if mm_txt else 0

    if hh < 0 or hh > 24:
        raise ValueError("Horas devem ficar entre 0 e 24.")
    if mm < 0 or mm > 59:
        raise ValueError("Minutos devem ficar entre 0 e 59.")
    if hh == 24 and mm != 0:
        raise ValueError("24 horas não pode ser combinado com minutos adicionais.")

    return hh + (mm / 60.0), hh, mm

def _calc_diff_horario(ent, sai):
    """Calcula um turno HH:MM -> HH:MM, aceitando virada de meia-noite."""
    ent = (ent or "").strip()
    sai = (sai or "").strip()
    if not ent and not sai:
        return 0.0, ""
    if not ent or not sai:
        raise ValueError("Preencha entrada e saída do turno, ou deixe ambos vazios.")

    try:
        h1, m1 = map(int, ent.split(":"))
        h2, m2 = map(int, sai.split(":"))
    except Exception as exc:
        raise ValueError("Horário inválido. Use o formato HH:MM.") from exc

    for h, m in ((h1, m1), (h2, m2)):
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("Horário inválido. Use valores entre 00:00 e 23:59.")

    min1 = h1 * 60 + m1
    min2 = h2 * 60 + m2
    if min2 < min1:
        min2 += 24 * 60

    duracao = (min2 - min1) / 60.0
    if duracao <= 0 or duracao > 24:
        raise ValueError("A duração do turno precisa ser maior que 0 e no máximo 24h.")

    return duracao, f"{ent} às {sai}"

def _doc_id_lancamento(uid, data_str, categoria, *, unico_por_dia=False):
    base = categoria.replace(" ", "").replace("/", "-").replace("(", "").replace(")", "")
    if unico_por_dia:
        return f"{uid}_{data_str}_{base}"
    return f"{uid}_{data_str}_{base}_{uuid4().hex[:10]}"

# ==========================================
# FUNÇÕES GLOBAIS DE BANCO DE DADOS E TAGS
# ==========================================
@st.cache_data(ttl=300, show_spinner=False)
def carregar_nucleos():
    doc = db.collection("config").document("settings").get()
    if doc.exists:
        return doc.to_dict().get(
            "nucleos",
            ["Enfermagem", "Odontologia", "Psicologia", "Nutrição",
             "Fisioterapia", "Farmácia", "Serviço Social",
             "Educação Física", "Outros"]
        )
    return [
        "Enfermagem", "Odontologia", "Psicologia", "Nutrição",
        "Fisioterapia", "Farmácia", "Serviço Social",
        "Educação Física", "Outros"
    ]

def salvar_nucleos(lista_nucleos):
    db.collection("config").document("settings").set({"nucleos": lista_nucleos}, merge=True)

@st.cache_data(ttl=300, show_spinner=False)
def carregar_tags():
    doc = db.collection("config").document("settings").get()
    if doc.exists:
        return doc.to_dict().get(
            "tags",
            ["Rotina Padrão", "Compensação de Horas", "Ação Extramuro", "Educação em Saúde", "Mutirão"]
        )
    return ["Rotina Padrão", "Compensação de Horas", "Ação Extramuro", "Educação em Saúde", "Mutirão"]

def salvar_tags(lista_tags):
    db.collection("config").document("settings").set({"tags": lista_tags}, merge=True)

@st.cache_data(ttl=60, show_spinner=False)
def carregar_pontos_residente_adm(uid_residente):
    """
    Cache curto para proteger o Firestore durante auditorias, PDFs e Raio-X.
    Qualquer gravação feita pelo ADM chama invalidar_agregador(), que também
    limpa este cache para a tela refletir a alteração imediatamente.
    """
    refs = db.collection("pontos").where("uid_residente", "==", uid_residente).get()
    return [doc.to_dict() | {"doc_id": doc.id} for doc in refs]

def invalidar_agregador(uid_residente):
    """
    Invalida somente os resumos derivados. O cache de configuração permanece.
    O cache dos pontos é limpo após escrita para evitar leitura antiga.
    """
    try:
        db.collection("residentes").document(uid_residente).update({
            "agregadores": firestore.DELETE_FIELD
        })
    except Exception:
        pass

    try:
        carregar_pontos_residente_adm.clear()
    except Exception:
        pass

    try:
        fn_residentes = globals().get("carregar_residentes_adm")
        if fn_residentes is not None:
            fn_residentes.clear()
    except Exception:
        pass

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
    st.image("https://http.cat/403", width=400)
    st.stop()

flash_adm = st.session_state.pop("flash_adm", None)
if flash_adm:
    st.success(flash_adm)

# ==========================================
# GAVETA DE NOVIDADES (POP-UP)
# ==========================================
@st.dialog("🚀 Atualização de Sistema: Painel ADM 4.0!")
def mostrar_novidades_adm_popup():
    st.markdown("""
    Prezada Coordenação, o sistema MultiPonto acaba de receber a **Versão 4.0**, com foco total em flexibilidade de gestão e conformidade com a CNRMS/MEC. Veja as novidades:
    
    * ⚖️ **Motor Matemático CNRMS:** A calculadora foi ajustada cirurgicamente para as 60h semanais. O sistema agora computa automaticamente a variação do Eixo Específico (3h para 2h) e preenche as lacunas com o Estudo Auto-dirigido (AAD) para fechar 12h teóricas exatas por semana.
    * 🏷️ **Gerenciador de Marcadores (Tags):** Na Aba de Gestão, agora é possível criar *Tags* (ex: "Ação Extramuro", "Compensação de Horas"). O residente ganha a hora oficial (Prática/Teórica), mas o registro e o PDF ganham o detalhamento da atividade!
    * 🧹 **Limpeza e Padronização:** O sistema agora opera estritamente com as 8 categorias padronizadas do MultiPonto. Registros antigos fora do padrão são traduzidos e adaptados em tempo real na tela.
    * ⚡ **Sincronização Instantânea (Auto-Cura):** Qualquer edição, exclusão ou lançamento em lote feito por você agora atualiza o "Raio-X Global" e os saldos na mesma fração de segundo.
    * 🗂️ **Extrato Avançado:** O PDF de auditoria e a Timeline ganharam separação estrita de balanços entre Prática e Teórica.
    
    *O Painel Administrativo agora usa o mesmo motor de horas do painel do residente, evitando divergências entre telas e relatórios.*
    """)
    
    st.write("")
    
    # Detalhe de UX: Mostra quantas visualizações restam no botão
    views_restantes = 4 - st.session_state.contagem_update_v4
    if views_restantes > 1:
        texto_botao = f"Ciente, vamos ao trabalho! (Aviso sumirá em {views_restantes} acessos)"
    else:
        texto_botao = "Ciente, vamos ao trabalho! (Último aviso)"

    if st.button(texto_botao, type="primary", use_container_width=True):
        # Aumenta a contagem em +1
        nova_contagem = st.session_state.contagem_update_v4 + 1
        
        # Salva o número no banco
        db.collection("config").document(f"admin_prefs_{st.session_state.uid}").set(
            {"contagem_update_v4": nova_contagem}, merge=True
        )
        st.session_state.contagem_update_v4 = nova_contagem
        st.rerun()

# ==========================================
# GATILHO DO POP-UP (Repete até 4 vezes)
# ==========================================
if "contagem_update_v4" not in st.session_state:
    admin_doc = db.collection("config").document(f"admin_prefs_{st.session_state.uid}").get()
    if admin_doc.exists:
        dados_admin = admin_doc.to_dict()
        # Lê o número do banco, se não existir, assume 0
        st.session_state.contagem_update_v4 = dados_admin.get("contagem_update_v4", 0)
    else:
        st.session_state.contagem_update_v4 = 0

# Se o adm viu menos de 4 vezes, dispara o pop-up
if st.session_state.contagem_update_v4 < 4:
    mostrar_novidades_adm_popup()

# ==========================================
# 2. CABEÇALHO DO MEGAZORD E LOGOUT
# ==========================================
c_header, c_logout = st.columns([8, 1])

with c_header:
    st.markdown("""
    <div style="background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 100%); padding: 30px; border-radius: 12px; color: white; display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
        <div>
            <h1 style="margin: 0; font-size: 2.2rem; font-weight: 800; color: white;">Painel Administrativo da Residência</h1>
            <p style="margin: 5px 0 0 0; font-size: 1.1rem; opacity: 0.9;">Gestão completa da Residência Multiprofissional em Saúde</p>
        </div>
        <div style="background-color: rgba(255,255,255,0.2); padding: 10px 20px; border-radius: 8px; font-weight: 600;">
            Acesso Nível: Alpha
        </div>
    </div>
    """, unsafe_allow_html=True)

with c_logout:
    st.markdown("<div style='margin-top: 40px;'></div>", unsafe_allow_html=True) # Alinha o botão verticalmente
    if st.button("🚪 Sair", use_container_width=True):
        st.session_state.clear() # Destrói todas as variáveis de login da memória
        st.rerun() # Atualiza a página (o Leão de Chácara vai te chutar pro Login)

# --- BUSCA GLOBAL DE RESIDENTES ---
@st.cache_data(ttl=60, show_spinner=False)
def carregar_residentes_adm():
    residentes_ref = db.collection("residentes").get()
    lista = []
    for doc in residentes_ref:
        dados = doc.to_dict()
        dados["uid"] = doc.id
        lista.append(dados)
    return lista

try:
    lista_residentes = carregar_residentes_adm()
except Exception as e:
    st.error(f"Erro ao buscar residentes globais: {e}")
    lista_residentes = []

# ==========================================
# 3. NAVEGAÇÃO SUPERIOR
# ==========================================
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] { gap: 8px; border-bottom: 2px solid #e5e7eb; padding-bottom: 0px; }
    .stTabs [data-baseweb="tab"] { height: 55px; background-color: #f3f4f6; border-radius: 10px 10px 0 0; padding: 10px 25px; font-size: 1.15rem; font-weight: 700; color: #6b7280; transition: all 0.3s ease-in-out; border: 1px solid #e5e7eb; border-bottom: none; }
    .stTabs [aria-selected="true"] { background-color: #2563eb !important; color: #ffffff !important; border-color: #2563eb !important; }
    .stTabs [data-baseweb="tab"]:hover:not([aria-selected="true"]) { background-color: #e5e7eb; color: #1f2937; }
    .stTabs [data-baseweb="tab-highlight"] { display: none; }
</style>
""", unsafe_allow_html=True)

aba1, aba2, aba3, aba4 = st.tabs([
    "📊 Visão Geral (Raio-X)", 
    "👥 Gestão de Pessoal", 
    "⏳ Auditoria de Horas",
    "📥 Central de Lançamentos"
])

# --- MÓDULO 1: VISÃO GERAL (RAIO-X GLOBAL) ---
with aba1:
    import pandas as pd
    import plotly.graph_objects as go
    import datetime as dt
    from datetime import date, timedelta

    st.markdown("<div class='card-title' style='margin-bottom: 20px;'>📊 Centro de Comando Global (Raio-X)</div>", unsafe_allow_html=True)
    
    if not lista_residentes:
            st.warning("⚠️ O sistema está vazio. Cadastre residentes no Módulo 2 para ver as métricas.")
    else:
        c_filtro, _ = st.columns([1.5, 3])
        with c_filtro:
            filtro_rx = st.selectbox("Filtrar Exibição da Tropa:", ["Ativos (Padrão)", "Arquivo Interno (Inativos)", "Mostrar Todos"])
            
        lista_rx = []
        for r in lista_residentes:
            st_r = r.get('status', 'Ativo')
            if filtro_rx == "Ativos (Padrão)" and st_r == "Ativo": lista_rx.append(r)
            elif filtro_rx == "Arquivo Interno (Inativos)" and st_r != "Ativo": lista_rx.append(r)
            elif filtro_rx == "Mostrar Todos": lista_rx.append(r)

        with st.spinner("Sincronizando Banco de Horas e Gerando Extratos..."):
            data_inicio_residencia = DATA_INICIO_RESIDENCIA
            hoje = hoje_local()
            
            meses_num_para_pt = {
                "01": "JANEIRO", "02": "FEVEREIRO", "03": "MARÇO", "04": "ABRIL",
                "05": "MAIO", "06": "JUNHO", "07": "JULHO", "08": "AGOSTO",
                "09": "SETEMBRO", "10": "OUTUBRO", "11": "NOVEMBRO", "12": "DEZEMBRO"
            }
            lista_meses = [f"{meses_num_para_pt[f'{m:02d}']}/{ano}" for ano in range(2026, 2031) for m in range(1, 13)]

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

            # --- GERADOR DO PDF ---
            def gerar_pdf_extrato(nome, nucleo, uid_res, todos_pontos, motor_res):
                from fpdf import FPDF
                
                # PROGRESSO CURRICULAR: referência comum da turma.
                # Férias NÃO diminuem estas metas.
                referencia_pdf = calcular_referencia_curricular_adm(data_inicio_residencia, hoje)
                soma_meta_p = referencia_pdf["pratica"]
                soma_meta_t = referencia_pdf["teoria"]
                soma_meta_total = referencia_pdf["total"]

                # BANCO DE HORAS: cobrança operacional diária.
                # Durante férias não há débito do dia, mas a meta anual permanece 2.880h.
                soma_meta_oper_p = motor_res["esperado"]["pratica"]
                soma_meta_oper_t = motor_res["esperado"]["teorica"]
                soma_meta_oper_total = motor_res["esperado"]["ate_hoje"]

                soma_trab_p = motor_res["cumprido"]["pratica"]
                soma_trab_t = motor_res["cumprido"]["teorica"]
                saldo_p_real = motor_res["saldos"]["pratica"]
                saldo_t_real = motor_res["saldos"]["teorica"]
                saldo_global = motor_res["saldos"]["acumulado"]

                pontos_res = [
                    p for p in todos_pontos
                    if p.get("uid_residente") == uid_res
                    and data_inicio_residencia.isoformat() <= p.get("data_registro", "") <= hoje.isoformat()
                ]
                pontos_por_data = {}
                for pt in pontos_res:
                    d = pt.get('data_registro')
                    if d not in pontos_por_data: pontos_por_data[d] = []
                    pontos_por_data[d].append(pt)

                # O PDF NÃO recalcula regra de negócio. Ele apenas apresenta o
                # resultado diário devolvido pelo mesmo motor usado no dashboard.
                acum_p, acum_t = 0.0, 0.0
                historico = []

                prioridade_ausencia = [
                    "Férias",
                    "Falta",
                    "Atestado / Licença Médica",
                    "Ausência Justificada",
                    "Feriado / Ponto Facultativo",
                ]

                for dia_motor in motor_res.get("por_dia", []):
                    d_obj = dia_motor["data"]
                    d_str = d_obj.strftime("%Y-%m-%d")
                    pts_dia = pontos_por_data.get(d_str, [])

                    categorias_dia = [normalizar_categoria(pt.get("categoria", "")) for pt in pts_dia]
                    ausencia_nome = next((c for c in prioridade_ausencia if c in categorias_dia), "")

                    horarios = []
                    for pt in pts_dia:
                        tag = pt.get("tag", "Rotina Padrão")
                        desc_obs = str(pt.get("justificativa", "") or "")
                        if tag and tag != "Rotina Padrão":
                            desc_obs = f"[{tag}] {desc_obs}".strip()

                        descritos = pt.get("horarios_descritos") or []
                        if descritos:
                            horarios.extend([f"{h_d} | {desc_obs}" if desc_obs else str(h_d) for h_d in descritos])

                    trab_p = dia_motor["realizado_pratica"]
                    trab_t = dia_motor["realizado_teoria"]
                    mp = dia_motor["meta_pratica"]
                    mt = dia_motor["meta_teoria"]
                    saldo_dia_p = dia_motor["saldo_pratica"]
                    saldo_dia_t = dia_motor["saldo_teoria"]
                    saldo_total = dia_motor["saldo_total"]

                    acum_p += saldo_dia_p
                    acum_t += saldo_dia_t

                    # Mostra movimentações, débitos e ocorrências administrativas,
                    # inclusive férias (saldo zero, mas relevantes para auditoria).
                    if abs(saldo_total) > 0.0001 or trab_p > 0 or trab_t > 0 or categorias_dia:
                        if horarios:
                            horario_txt = " || ".join(horarios)
                        elif ausencia_nome:
                            horario_txt = "Integral / ocorrência administrativa"
                        else:
                            horario_txt = "Sem relógio"

                        historico.append({
                            "data_str": d_obj.strftime("%d/%m/%Y"),
                            "data_obj": d_obj,
                            "horarios": horario_txt,
                            "saldo_dia": saldo_total,
                            "acumulado": acum_p + acum_t,
                            "acum_p": acum_p,
                            "acum_t": acum_t,
                            "trab_p": trab_p,
                            "meta_p": mp,
                            "trab_t": trab_t,
                            "meta_t": mt,
                            "ausencia": ausencia_nome,
                        })

                historico.sort(key=lambda x: x["data_obj"], reverse=True)
                
                meses_pt = ["", "JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]
                extrato_por_mes = {}
                for item in historico:
                    chave_mes = f"{meses_pt[item['data_obj'].month]} / {item['data_obj'].year}"
                    if chave_mes not in extrato_por_mes: extrato_por_mes[chave_mes] = []
                    extrato_por_mes[chave_mes].append(item)

                pdf = FPDF()
                pdf.add_page()
                
                def txt(texto):
                    return str(texto).encode('latin-1', 'replace').decode('latin-1')
                
                pdf.set_fill_color(30, 58, 138)
                pdf.rect(0, 0, 210, 35, 'F')
                
                pdf.set_y(12)
                pdf.set_font('Arial', 'B', 18)
                pdf.set_text_color(255, 255, 255)
                pdf.cell(0, 8, txt('RELATÓRIO EXECUTIVO - BANCO DE HORAS'), ln=1, align='C')
                
                pdf.set_font('Arial', '', 11)
                pdf.set_text_color(209, 213, 219)
                pdf.cell(0, 5, txt(f'Data da Emissão: {agora_local().strftime("%d/%m/%Y %H:%M")}'), ln=1, align='C')
                
                pdf.ln(15)
                
                pdf.set_font('Arial', 'B', 14)
                pdf.set_text_color(31, 41, 55)
                pdf.cell(0, 6, txt(f"Residente: {nome}"), ln=1)
                pdf.set_font('Arial', '', 11)
                pdf.set_text_color(107, 114, 128)
                pdf.cell(0, 6, txt(f"Núcleo Profissional: {nucleo}"), ln=1)
                
                # Estatística por categoria: horas trabalhadas são somadas por
                # registro; dívidas de ausência são apuradas UMA VEZ por data,
                # usando o resultado do motor para impedir dupla contagem.
                cat_stats = {}
                ausencias_por_data = {}

                for pt in pontos_res:
                    c = normalizar_categoria(pt.get("categoria", "Outros"))
                    if c not in cat_stats:
                        cat_stats[c] = {"horas_trab": 0.0, "ocorrencias": 0, "debito_p": 0.0, "debito_t": 0.0}

                    cat_stats[c]["ocorrencias"] += 1
                    if c in CATEGORIAS_TRABALHO:
                        cat_stats[c]["horas_trab"] += _safe_float(pt.get("horas_computadas", 0.0))

                    data_str = pt.get("data_registro", "")
                    if data_str and c in CATEGORIAS_AUSENCIA:
                        ausencias_por_data.setdefault(data_str, set()).add(c)

                motor_por_data = {dia["data"].isoformat(): dia for dia in motor_res.get("por_dia", [])}
                prioridade_debito = [
                    "Falta",
                    "Atestado / Licença Médica",
                    "Ausência Justificada",
                    "Feriado / Ponto Facultativo",
                ]

                for data_str, cats_dia in ausencias_por_data.items():
                    # Férias são a única ocorrência que retira a meta. Se houver
                    # lançamento contraditório no mesmo dia, o motor já gera aviso.
                    if "Férias" in cats_dia:
                        continue

                    dia_motor = motor_por_data.get(data_str)
                    if not dia_motor:
                        continue

                    categoria_debito = next((c for c in prioridade_debito if c in cats_dia), None)
                    if not categoria_debito:
                        continue

                    deb_p = dia_motor.get("reposicao_pratica", 0.0)
                    deb_t = dia_motor.get("reposicao_teoria", 0.0)
                    cat_stats.setdefault(categoria_debito, {"horas_trab": 0.0, "ocorrencias": 0, "debito_p": 0.0, "debito_t": 0.0})
                    cat_stats[categoria_debito]["debito_p"] += deb_p
                    cat_stats[categoria_debito]["debito_t"] += deb_t

                pdf.ln(5)
                pdf.set_font('Arial', 'B', 12)
                pdf.set_text_color(55, 65, 81)
                pdf.cell(0, 8, txt("1. SALDOS ACUMULADOS (PRÁTICA E TEÓRICA)"), border='B', ln=1)
                pdf.ln(4)
                
                y_saldos = pdf.get_y()
                
                pdf.set_fill_color(243, 244, 246)
                pdf.rect(10, y_saldos, 60, 18, 'F')
                pdf.set_y(y_saldos + 2)
                pdf.set_x(10)
                pdf.set_font('Arial', 'B', 8)
                pdf.set_text_color(107, 114, 128)
                pdf.cell(60, 5, txt("SALDO PRÁTICA"), align='C', ln=1)
                pdf.set_x(10)
                pdf.set_font('Arial', 'B', 12)
                if saldo_p_real >= 0:
                    pdf.set_text_color(22, 163, 74)
                    pdf.cell(60, 8, f"+{formatar_horas_adm_pdf(saldo_p_real)}", align='C', ln=1)
                else:
                    pdf.set_text_color(220, 38, 38)
                    pdf.cell(60, 8, f"-{formatar_horas_adm_pdf(abs(saldo_p_real))} (Débito)", align='C', ln=1)

                pdf.set_y(y_saldos)
                pdf.set_x(75)
                pdf.set_fill_color(243, 244, 246)
                pdf.rect(75, y_saldos, 60, 18, 'F')
                pdf.set_y(y_saldos + 2)
                pdf.set_x(75)
                pdf.set_font('Arial', 'B', 8)
                pdf.set_text_color(107, 114, 128)
                pdf.cell(60, 5, txt("SALDO TEÓRICA"), align='C', ln=1)
                pdf.set_x(75)
                pdf.set_font('Arial', 'B', 12)
                if saldo_t_real >= 0:
                    pdf.set_text_color(22, 163, 74)
                    pdf.cell(60, 8, f"+{formatar_horas_adm_pdf(saldo_t_real)}", align='C', ln=1)
                else:
                    pdf.set_text_color(220, 38, 38)
                    pdf.cell(60, 8, f"-{formatar_horas_adm_pdf(abs(saldo_t_real))} (Débito)", align='C', ln=1)

                pdf.set_y(y_saldos)
                pdf.set_x(140)
                cor_bg_global = (220, 252, 231) if saldo_global >= 0 else (254, 226, 226)
                pdf.set_fill_color(*cor_bg_global)
                pdf.rect(140, y_saldos, 60, 18, 'F')
                pdf.set_y(y_saldos + 2)
                pdf.set_x(140)
                pdf.set_font('Arial', 'B', 8)
                pdf.set_text_color(31, 41, 55)
                pdf.cell(60, 5, txt("SALDO GLOBAL"), align='C', ln=1)
                pdf.set_x(140)
                pdf.set_font('Arial', 'B', 14)
                if saldo_global >= 0:
                    pdf.set_text_color(22, 101, 52) 
                    pdf.cell(60, 8, f"+{formatar_horas_adm_pdf(saldo_global)}", align='C', ln=1)
                else:
                    pdf.set_text_color(153, 27, 27) 
                    pdf.cell(60, 8, f"-{formatar_horas_adm_pdf(abs(saldo_global))}", align='C', ln=1)

                pdf.ln(8)
                
                pdf.set_font('Arial', 'B', 12)
                pdf.set_text_color(55, 65, 81)
                pdf.cell(0, 8, txt("2. CUMPRIMENTO DE METAS (PROGRESSO)"), border='B', ln=1)
                pdf.ln(4)
                
                def desenhar_barra_progresso(pdf_obj, titulo, realizado, meta, cor_rgb, y_pos):
                    pdf_obj.set_y(y_pos)
                    pdf_obj.set_font('Arial', 'B', 9)
                    pdf_obj.set_text_color(75, 85, 99)
                    pdf_obj.cell(40, 6, txt(titulo), border=0)
                    
                    largura_maxima = 100
                    porcentagem = (realizado / meta) if meta > 0 else 0
                    if porcentagem > 1: porcentagem = 1.0 
                    largura_preenchida = largura_maxima * porcentagem
                    
                    pdf_obj.set_fill_color(229, 231, 235)
                    pdf_obj.rect(50, y_pos + 1.5, largura_maxima, 4, 'F')
                    
                    pdf_obj.set_fill_color(*cor_rgb)
                    pdf_obj.rect(50, y_pos + 1.5, largura_preenchida, 4, 'F')
                    
                    pdf_obj.set_x(155)
                    pdf_obj.set_font('Arial', 'B', 9)
                    pdf_obj.set_text_color(31, 41, 55)
                    porc_str = f"{(realizado/meta*100):.1f}%" if meta > 0 else "0%"
                    pdf_obj.cell(45, 6, f"{formatar_horas_adm_pdf(realizado)} / {formatar_horas_adm_pdf(meta)} ({porc_str})", border=0, ln=1)

                desenhar_barra_progresso(pdf, "Eixo Prático:", soma_trab_p, soma_meta_p, (37, 99, 235), pdf.get_y())
                pdf.ln(2)
                desenhar_barra_progresso(pdf, "Eixo Teórico:", soma_trab_t, soma_meta_t, (139, 92, 246), pdf.get_y())
                
                pdf.ln(6)
                
                pdf.set_font('Arial', 'B', 12)
                pdf.set_text_color(55, 65, 81)
                pdf.cell(0, 8, txt("3. DISTRIBUIÇÃO POR CATEGORIA (OCORRÊNCIAS TOTAIS)"), border='B', ln=1)
                pdf.ln(4)
                
                paleta_pdf = {
                    "PRÁTICA": {"cor": (22, 163, 74), "bg": (220, 252, 231)},
                    "TEÓRICA": {"cor": (139, 92, 246), "bg": (243, 232, 255)},
                    "TEÓRICO-PRÁTICA": {"cor": (202, 138, 4), "bg": (254, 240, 138)},
                    "ESTUDO AUTO-DIRIGIDO (AAD)": {"cor": (202, 138, 4), "bg": (254, 240, 138)},
                    "ATESTADO / LICENÇA MÉDICA": {"cor": (234, 88, 12), "bg": (255, 237, 213)},
                    "FALTA": {"cor": (220, 38, 38), "bg": (254, 226, 226)},
                    "FÉRIAS": {"cor": (2, 132, 199), "bg": (224, 242, 254)},
                    "FERIADO / PONTO FACULTATIVO": {"cor": (30, 64, 175), "bg": (219, 234, 254)},
                    "AUSÊNCIA JUSTIFICADA": {"cor": (234, 179, 8), "bg": (254, 249, 195)}
                }
                
                col_w = 63
                x_start = 10
                col_index = 0
                
                start_y = pdf.get_y()
                
                for cat, dados in sorted(cat_stats.items(), key=lambda item: item[1]['ocorrencias'], reverse=True):
                    cat_upper = str(cat).upper()
                    estilo = paleta_pdf.get(cat_upper, {"cor": (107, 114, 128), "bg": (243, 244, 246)})
                    
                    x_pos = x_start + (col_index * col_w)
                    
                    pdf.set_fill_color(248, 250, 252)
                    pdf.rect(x_pos, start_y, col_w - 3, 16, 'F')
                    
                    pdf.set_fill_color(*estilo["cor"])
                    pdf.rect(x_pos, start_y, 1.5, 16, 'F')
                    
                    pdf.set_fill_color(*estilo["bg"])
                    pdf.rect(x_pos + 3, start_y + 1.5, col_w - 9, 4.5, 'F')
                    
                    pdf.set_xy(x_pos + 3, start_y + 1.5)
                    pdf.set_font('Arial', 'B', 6)
                    pdf.set_text_color(*estilo["cor"])
                    pdf.cell(col_w - 9, 4.5, txt(cat_upper), border=0, ln=0, align='C')
                    
                    pdf.set_xy(x_pos + 3, start_y + 7.5)
                    pdf.set_text_color(31, 41, 55)
                    
                    if cat_upper in ["PRÁTICA", "TEÓRICA", "ESTUDO AUTO-DIRIGIDO (AAD)", "TEÓRICO-PRÁTICA"]:
                        pdf.set_font('Arial', 'B', 9)
                        horas_str = formatar_horas_adm_pdf(dados['horas_trab'])
                        pdf.cell(col_w - 9, 4, txt(f"{horas_str}"), border=0, ln=0, align='C')
                        
                    elif cat_upper == "FÉRIAS":
                        pdf.set_font('Arial', 'B', 7.5)
                        pdf.set_text_color(2, 132, 199)
                        pdf.cell(col_w - 9, 4, txt("Férias: sem cobrança diária"), border=0, ln=0, align='C')
                        
                    else:
                        pdf.set_font('Arial', 'B', 6.5)
                        deb_p = dados.get('debito_p', 0.0)
                        deb_t = dados.get('debito_t', 0.0)
                        
                        str_dp = formatar_horas_adm_pdf(deb_p).replace(" ", "")
                        str_dt = formatar_horas_adm_pdf(deb_t).replace(" ", "")
                        
                        if deb_p == 0 and deb_t == 0:
                            pdf.cell(col_w - 9, 4, txt("S/ Débito (Fora de Escala)"), border=0, ln=0, align='C')
                        else:
                            pdf.set_text_color(220, 38, 38)
                            pdf.cell(col_w - 9, 4, txt(f"Débito: -{str_dp}(P) | -{str_dt}(T)"), border=0, ln=0, align='C')
                    
                    pdf.set_xy(x_pos + 3, start_y + 12)
                    pdf.set_font('Arial', '', 7)
                    pdf.set_text_color(107, 114, 128)
                    pdf.cell(col_w - 9, 3, txt(f"Em {dados['ocorrencias']} dia(s) de registro"), border=0, ln=0, align='C')
                    
                    col_index += 1
                    if col_index == 3:
                        col_index = 0
                        start_y += 18 
                        pdf.set_y(start_y)
                
                if col_index != 0:
                    start_y += 18
                    pdf.set_y(start_y)
                    
                pdf.ln(2)
                pdf.set_font('Arial', 'I', 8)
                pdf.set_text_color(156, 163, 175)
                pdf.multi_cell(0, 4, txt("Nota: a meta curricular anual permanece fixa em 2.880h (2.304h prática + 576h teoria). Férias apenas suspendem a cobrança diária durante o período gozado; não reduzem a meta curricular anual. As demais ausências mantêm a cobrança e podem gerar reposição."))
                pdf.ln(3)

                for mes, itens_mes in extrato_por_mes.items():
                    if pdf.get_y() > 240: pdf.add_page()
                    
                    pdf.ln(5)
                    pdf.set_fill_color(243, 244, 246)
                    pdf.rect(10, pdf.get_y(), 190, 8, 'F')
                    pdf.set_font('Arial', 'B', 11)
                    pdf.set_text_color(55, 65, 81)
                    pdf.set_y(pdf.get_y() + 1.5)
                    pdf.set_x(12)
                    pdf.cell(0, 5, txt(f"COMPETÊNCIA: {mes}"), border=0, ln=1)
                    pdf.ln(5)

                    for item in itens_mes:
                        if pdf.get_y() > 260: pdf.add_page()

                        pdf.set_font('Arial', 'B', 9)
                        pdf.set_text_color(107, 114, 128)
                        
                        texto_horario = item['horarios'][:80] + "..." if len(item['horarios']) > 80 else item['horarios']
                        pdf.cell(0, 5, txt(f"{item['data_str']} - {texto_horario}"), ln=1)

                        if item['saldo_dia'] > 0:
                            cor_titulo = (22, 163, 74)
                            titulo = "Crédito de Horas / Horas Extras"
                        elif item['saldo_dia'] < 0:
                            cor_titulo = (220, 38, 38)
                            titulo = "Débito de Horas / Falta" if item['ausencia'] == 'Falta' else "Débito de Horas"
                        else:
                            cor_titulo = (30, 64, 175)
                            titulo = f"Movimentação ({item['ausencia']})" if item['ausencia'] else "Meta Batida"

                        y_blocos = pdf.get_y()

                        pdf.set_text_color(*cor_titulo)
                        pdf.set_font('Arial', 'B', 10)
                        pdf.cell(120, 5, txt(titulo), border=0, ln=1)
                        
                        pdf.set_font('Arial', '', 8)
                        pdf.set_text_color(107, 114, 128)
                        str_p = f"Prática: {formatar_horas_adm_pdf(item['trab_p'])} (Meta: {formatar_horas_adm_pdf(item['meta_p'])})"
                        str_t = f"Teórica: {formatar_horas_adm_pdf(item['trab_t'])} (Meta: {formatar_horas_adm_pdf(item['meta_t'])})"
                        pdf.cell(120, 5, txt(f"{str_p}  |  {str_t}"), border=0, ln=1)
                        
                        y_esquerda = pdf.get_y()

                        pdf.set_y(y_blocos)
                        pdf.set_x(130)
                        pdf.set_text_color(*cor_titulo)
                        pdf.set_font('Arial', 'B', 11)
                        sinal = "+" if item['saldo_dia'] > 0 else ""
                        pdf.cell(70, 5, f"{sinal}{formatar_horas_adm_pdf(item['saldo_dia'])}", ln=1, align='R')
                        
                        pdf.set_x(130)
                        pdf.set_font('Arial', '', 8)
                        pdf.set_text_color(107, 114, 128)
                        pdf.cell(70, 4, txt("Acumulado Geral:"), ln=1, align='R')
                        
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
                        pdf.cell(70, 3.5, txt(f"Prática: {sinal_p}{formatar_horas_adm_pdf(item['acum_p'])}"), ln=1, align='R')

                        pdf.set_x(130)
                        if item['acum_t'] >= 0: pdf.set_text_color(139, 92, 246)
                        else: pdf.set_text_color(220, 38, 38)
                        sinal_t = "+" if item['acum_t'] > 0 else ""
                        pdf.cell(70, 3.5, txt(f"Teórica: {sinal_t}{formatar_horas_adm_pdf(item['acum_t'])}"), ln=1, align='R')

                        y_direita = pdf.get_y()
                        pdf.set_y(max(y_esquerda, y_direita))

                        pdf.set_draw_color(229, 231, 235)
                        pdf.line(10, pdf.get_y()+2, 200, pdf.get_y()+2)
                        pdf.ln(5)

                out = pdf.output(dest='S')
                if isinstance(out, str): return out.encode('latin-1', 'replace')
                return bytes(out)

            # META CURRICULAR DE REFERÊNCIA DA TURMA.
            # É igual para todos e NÃO diminui porque alguém já gozou férias.
            # A referência é limitada a 48 semanas por R:
            # 2.304h prática + 576h teoria = 2.880h/ano-residência.
            fim_programa = obter_fim_programa(data_inicio_residencia)
            referencia_turma = calcular_referencia_curricular_adm(
                data_inicio_residencia,
                min(hoje, fim_programa),
            )
            meta_base_pratica = referencia_turma["pratica"]
            meta_base_teorica = referencia_turma["teoria"]
            meta_base_total = referencia_turma["total"]

            dados_tropa = []
            total_horas_realizadas = 0.0
            total_meta_operacional = 0.0
            residentes_desatualizados = 0
            residentes_no_vermelho = 0
            recalculou_agregadores = False

            for res in lista_rx:
                uid = res.get("uid")
                nome = res.get("nome_completo", "Desconhecido")
                prof = res.get("profissao", "Outros")

                agregador = res.get("agregadores") or {}
                agregador_valido = agregador.get("versao_motor") == VERSAO_MOTOR_ADM

                if not agregador_valido:
                    pts = carregar_pontos_residente_adm(uid)
                    motor_res = calcular_motor_horas(
                        pts, data_inicio_residencia, hoje, lista_meses, meses_num_para_pt
                    )

                    datas_validas = [
                        p.get("data_registro", "")
                        for p in pts
                        if p.get("data_registro", "") and p.get("data_registro", "") <= hoje.isoformat()
                    ]
                    ultima_data_str = max(datas_validas) if datas_validas else "1900-01-01"

                    agregador = {
                        "versao_motor": VERSAO_MOTOR_ADM,
                        "pratica_realizada": motor_res["cumprido"]["pratica"],
                        "teorica_realizada": motor_res["cumprido"]["teorica"],
                        "total_trabalhado": motor_res["cumprido"]["total"],
                        # Meta curricular de referência: comum da turma e NÃO reduzida por férias.
                        "meta_referencia_pratica": meta_base_pratica,
                        "meta_referencia_teorica": meta_base_teorica,
                        "meta_referencia_total": meta_base_total,
                        # Meta cobrável operacional: usada somente para saldo do banco.
                        "meta_operacional_pratica": motor_res["esperado"]["pratica"],
                        "meta_operacional_teorica": motor_res["esperado"]["teorica"],
                        "meta_operacional_total": motor_res["esperado"]["ate_hoje"],
                        "saldo_pratica": motor_res["saldos"]["pratica"],
                        "saldo_teorica": motor_res["saldos"]["teorica"],
                        "saldo_total": motor_res["saldos"]["acumulado"],
                        "horas_reposicao": motor_res["reposicao"]["total"],
                        "cobranca_suspensa_ferias": motor_res["esperado"]["retirado_por_ferias"],
                        "ultima_data_lancamento": ultima_data_str,
                    }
                    db.collection("residentes").document(uid).update({"agregadores": agregador})
                    recalculou_agregadores = True

                feito_p = _safe_float(agregador.get("pratica_realizada", 0.0))
                feito_t = _safe_float(agregador.get("teorica_realizada", 0.0))
                total_trabalhado = _safe_float(agregador.get("total_trabalhado", feito_p + feito_t))

                # A barra de META nos gráficos e cartões é CURRICULAR e comum da turma.
                # Férias não podem encolher esta referência.
                meta_p_referencia = _safe_float(agregador.get("meta_referencia_pratica", meta_base_pratica))
                meta_t_referencia = _safe_float(agregador.get("meta_referencia_teorica", meta_base_teorica))
                meta_total_referencia = _safe_float(agregador.get("meta_referencia_total", meta_p_referencia + meta_t_referencia))

                # A meta operacional existe apenas para o BANCO DE HORAS: férias suspendem
                # a cobrança dos dias gozados, sem reduzir a meta curricular anual.
                meta_p_operacional = _safe_float(agregador.get("meta_operacional_pratica", meta_p_referencia))
                meta_t_operacional = _safe_float(agregador.get("meta_operacional_teorica", meta_t_referencia))
                meta_total_operacional = _safe_float(agregador.get("meta_operacional_total", meta_p_operacional + meta_t_operacional))

                saldo_p_real = _safe_float(agregador.get("saldo_pratica", feito_p - meta_p_operacional))
                saldo_t_real = _safe_float(agregador.get("saldo_teorica", feito_t - meta_t_operacional))
                saldo_final = _safe_float(agregador.get("saldo_total", total_trabalhado - meta_total_operacional))
                horas_reposicao = _safe_float(agregador.get("horas_reposicao", 0.0))
                ferias_cobranca_suspensa = _safe_float(agregador.get("cobranca_suspensa_ferias", 0.0))
                ultima_data_str = agregador.get("ultima_data_lancamento", "1900-01-01")

                total_horas_realizadas += total_trabalhado
                total_meta_operacional += meta_total_operacional
                if saldo_final < -0.0001:
                    residentes_no_vermelho += 1

                if ultima_data_str != "1900-01-01":
                    try:
                        ult_d = dt.datetime.strptime(ultima_data_str, "%Y-%m-%d").date()
                        dias_off = max(0, (hoje - ult_d).days)
                        if dias_off == 0:
                            status_app = "Hoje"
                        elif dias_off == 1:
                            status_app = "Ontem"
                        else:
                            status_app = f"Há {dias_off} dias"
                    except ValueError:
                        dias_off = 999
                        status_app = "Data inválida"
                else:
                    dias_off = 999
                    status_app = "Nunca lançou"

                if dias_off > 7:
                    residentes_desatualizados += 1

                dados_tropa.append({
                    "uid": uid,
                    "Nome": nome,
                    "Núcleo": prof,
                    "Prática (F)": feito_p,
                    "Prática (M)": meta_p_referencia,
                    "Teórica (F)": feito_t,
                    "Teórica (M)": meta_t_referencia,
                    "Meta Total": meta_total_referencia,
                    "Meta Operacional P": meta_p_operacional,
                    "Meta Operacional T": meta_t_operacional,
                    "Meta Operacional Total": meta_total_operacional,
                    "Saldo Final": saldo_final,
                    "Saldo P": saldo_p_real,
                    "Saldo T": saldo_t_real,
                    "Reposição": horas_reposicao,
                    "Férias - cobrança suspensa": ferias_cobranca_suspensa,
                    "Último Lançamento": status_app,
                    "_dias_off": dias_off,
                    "_total_feito": total_trabalhado,
                })

            if recalculou_agregadores:
                carregar_residentes_adm.clear()

            df_tropa = pd.DataFrame(dados_tropa)

            media_meta_operacional = total_meta_operacional / len(lista_rx) if len(lista_rx) > 0 else 0.0
            media_tropa = total_horas_realizadas / len(lista_rx) if len(lista_rx) > 0 else 0.0

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown(f"<div style='background-color: #f8fafc; padding: 20px; border-radius: 12px; border: 1px solid #e5e7eb; border-left: 5px solid #3b82f6;'><div style='color: #6b7280; font-weight: 700; font-size: 0.85rem; text-transform: uppercase;'>Meta Curricular de Referência</div><div style='color: #1e3a8a; font-size: 2.2rem; font-weight: 800; margin-top: 5px;'>{meta_base_total:,.1f}h</div><div style='color: #6b7280; font-size: 0.8rem; margin-top: 5px;'>Igual para todos • férias não reduzem</div></div>", unsafe_allow_html=True)
            with c2:
                cor_media = "#16a34a" if media_tropa >= meta_base_total else "#d97706"
                st.markdown(f"<div style='background-color: #f8fafc; padding: 20px; border-radius: 12px; border: 1px solid #e5e7eb; border-left: 5px solid {cor_media};'><div style='color: #6b7280; font-weight: 700; font-size: 0.85rem; text-transform: uppercase;'>Média Trabalhada</div><div style='color: {cor_media}; font-size: 2.2rem; font-weight: 800; margin-top: 5px;'>{media_tropa:,.1f}h</div><div style='color: #6b7280; font-size: 0.8rem; margin-top: 5px;'>Referência curricular: {meta_base_total:,.1f}h</div></div>", unsafe_allow_html=True)
            with c3:
                cor_alerta_saldo = "#dc2626" if residentes_no_vermelho > 0 else "#16a34a"
                st.markdown(f"<div style='background-color: #f8fafc; padding: 20px; border-radius: 12px; border: 1px solid #e5e7eb; border-left: 5px solid {cor_alerta_saldo};'><div style='color: #6b7280; font-weight: 700; font-size: 0.85rem; text-transform: uppercase;'>Tropa no Vermelho</div><div style='color: {cor_alerta_saldo}; font-size: 2.2rem; font-weight: 800; margin-top: 5px;'>{residentes_no_vermelho}</div><div style='color: #6b7280; font-size: 0.8rem; margin-top: 5px;'>Saldos Negativos</div></div>", unsafe_allow_html=True)
            with c4:
                cor_alerta_app = "#dc2626" if residentes_desatualizados > 0 else "#16a34a"
                st.markdown(f"<div style='background-color: #f8fafc; padding: 20px; border-radius: 12px; border: 1px solid #e5e7eb; border-left: 5px solid {cor_alerta_app};'><div style='color: #6b7280; font-weight: 700; font-size: 0.85rem; text-transform: uppercase;'>App Desatualizado</div><div style='color: {cor_alerta_app}; font-size: 2.2rem; font-weight: 800; margin-top: 5px;'>{residentes_desatualizados}</div><div style='color: #6b7280; font-size: 0.8rem; margin-top: 5px;'>Atraso > 7 dias</div></div>", unsafe_allow_html=True)

            st.markdown("<hr style='border-color: #e5e7eb; margin-top: 30px; margin-bottom: 30px;'><h4 style='color: #374151; font-weight: 800; font-size: 1.4rem; margin-bottom: 5px;'>⚖️ Produção Acumulada por Residente</h4><span style='color: #6b7280; font-size: 0.95rem;'>A barra cinza é a <b>meta curricular de referência</b>, igual para todos da turma. Férias não diminuem essa meta; elas apenas suspendem a cobrança diária do banco durante o período gozado.</span>", unsafe_allow_html=True)
            
            if not df_tropa.empty:
                df_grafico = df_tropa.copy().sort_values('_total_feito', ascending=True)
                altura_grafico = max(450, len(df_grafico) * 65)
                
                st.markdown("<h5 style='color: #2563eb; font-weight: 800; margin-top: 35px; font-size: 1.1rem;'>🩺 Eixo Prático (Realizado vs Meta)</h5>", unsafe_allow_html=True)
                fig_p = go.Figure()
                fig_p.add_trace(go.Bar(x=df_grafico['Prática (F)'], y=df_grafico['Nome'], name='Prática Realizada', orientation='h', marker_color='#3b82f6', text=df_grafico['Prática (F)'].apply(lambda x: f"{x:.0f}h"), textposition='outside', textfont=dict(size=14, color='#3b82f6', weight='bold')))
                fig_p.add_trace(go.Bar(x=df_grafico['Prática (M)'], y=df_grafico['Nome'], name='Meta Curricular Prática', orientation='h', marker_color='#e5e7eb', text=df_grafico['Prática (M)'].apply(lambda x: f"{x:.0f}h"), textposition='auto', textfont=dict(size=14, color='#374151', weight='bold')))
                fig_p.update_layout(barmode='group', showlegend=True, margin=dict(l=0, r=0, t=15, b=0), height=altura_grafico, plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=14, weight='bold')), xaxis=dict(showgrid=True, gridcolor="#e5e7eb", zeroline=False), yaxis=dict(tickfont=dict(size=13, weight='bold', color='#1f2937')))
                st.plotly_chart(fig_p, use_container_width=True, config={'displayModeBar': False})

                st.markdown("<h5 style='color: #7c3aed; font-weight: 800; margin-top: 40px; font-size: 1.1rem;'>📚 Eixo Teórico (Realizado vs Meta)</h5>", unsafe_allow_html=True)
                fig_t = go.Figure()
                fig_t.add_trace(go.Bar(x=df_grafico['Teórica (F)'], y=df_grafico['Nome'], name='Teórica Realizada', orientation='h', marker_color='#8b5cf6', text=df_grafico['Teórica (F)'].apply(lambda x: f"{x:.0f}h" if x > 0 else ""), textposition='outside', textfont=dict(size=14, color='#8b5cf6', weight='bold')))
                fig_t.add_trace(go.Bar(x=df_grafico['Teórica (M)'], y=df_grafico['Nome'], name='Meta Curricular Teórica', orientation='h', marker_color='#e5e7eb', text=df_grafico['Teórica (M)'].apply(lambda x: f"{x:.0f}h"), textposition='auto', textfont=dict(size=14, color='#374151', weight='bold')))
                fig_t.update_layout(barmode='group', showlegend=True, margin=dict(l=0, r=0, t=15, b=0), height=altura_grafico, plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=14, weight='bold')), xaxis=dict(showgrid=True, gridcolor="#e5e7eb", zeroline=False), yaxis=dict(tickfont=dict(size=13, weight='bold', color='#1f2937')))
                st.plotly_chart(fig_t, use_container_width=True, config={'displayModeBar': False})

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
                        
                        saldo_p_real = row['Saldo P']
                        saldo_t_real = row['Saldo T']
                        
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
                            
                            @st.fragment
                            def renderizar_btn_pdf(u_frag, n_frag, p_frag):
                                if st.button("📄 Gerar Relatório", key=f"btn_prep_pdf_{u_frag}", use_container_width=True):
                                    with st.spinner("Compilando..."):
                                        pts_frag = carregar_pontos_residente_adm(u_frag)
                                        
                                        meses_n = {"01": "JANEIRO", "02": "FEVEREIRO", "03": "MARÇO", "04": "ABRIL", "05": "MAIO", "06": "JUNHO", "07": "JULHO", "08": "AGOSTO", "09": "SETEMBRO", "10": "OUTUBRO", "11": "NOVEMBRO", "12": "DEZEMBRO"}
                                        l_meses = [f"{meses_n[f'{m:02d}']}/{ano}" for ano in range(2026, 2031) for m in range(1, 13)]
                                        
                                        from calculadora_horas import calcular_motor_horas
                                        motor_frag = calcular_motor_horas(pts_frag, data_inicio_residencia, hoje, l_meses, meses_n)
                                        
                                        pdf_bytes = gerar_pdf_extrato(n_frag, p_frag, u_frag, pts_frag, motor_frag)
                                        
                                        st.download_button("⬇️ Baixar PDF", data=pdf_bytes, file_name=f"Auditoria_{n_frag.split()[0]}.pdf", mime="application/pdf", key=f"dl_pdf_final_{u_frag}", use_container_width=True, type="primary")

                            renderizar_btn_pdf(uid_row, nome, nucleo)

# --- MÓDULO 2: GESTÃO DE Pessoal e Categorias ---
with aba2:
    st.markdown("<div class='card-title' style='margin-bottom: 20px;'>Gestão de Pessoal e Categorias</div>", unsafe_allow_html=True)

    col_lista, col_cadastro = st.columns([1.5, 1], gap="large")

    with st.expander("⚙️ Configurações de Núcleos Profissionais"):
        nucleos_atuais = carregar_nucleos()
        
        col1, col2 = st.columns([2, 1])
        with col1:
            novo_nucleo = st.text_input("Adicionar novo núcleo:", placeholder="Ex: Terapia Ocupacional")
        with col2:
            st.write("<br>", unsafe_allow_html=True)
            if st.button("➕ Adicionar"):
                if novo_nucleo and novo_nucleo not in nucleos_atuais:
                    nucleos_atuais.append(novo_nucleo)
                    salvar_nucleos(nucleos_atuais)
                    carregar_nucleos.clear()
                    st.rerun()

        st.markdown("##### Núcleos Cadastrados:")
        for n in nucleos_atuais:
            c_label, c_del = st.columns([4, 1])
            c_label.write(f"- {n}")
            if c_del.button("🗑️", key=f"del_{n}"):
                if len(nucleos_atuais) > 1:
                    nucleos_atuais.remove(n)
                    salvar_nucleos(nucleos_atuais)
                    carregar_nucleos.clear()
                    st.rerun()
                else:
                    st.error("Você precisa de pelo menos um núcleo.")

    # NOVO: Gerenciador de Tags de Atividade
    with st.expander("🏷️ Configurações de Marcadores (Tags de Atividade)"):
        st.markdown("<span style='font-size: 0.85rem; color: #6b7280;'>Crie marcadores livres (ex: 'Ação Extramuro', 'Mutirão') para anexar aos registros sem quebrar a matemática do MEC.</span>", unsafe_allow_html=True)
        tags_atuais = carregar_tags()
        
        c_tag1, c_tag2 = st.columns([2, 1])
        with c_tag1:
            nova_tag = st.text_input("Adicionar novo marcador:", placeholder="Ex: Produção de Vídeo")
        with c_tag2:
            st.write("<br>", unsafe_allow_html=True)
            if st.button("➕ Adicionar Tag", type="secondary"):
                if nova_tag and nova_tag not in tags_atuais:
                    tags_atuais.append(nova_tag)
                    salvar_tags(tags_atuais)
                    carregar_tags.clear()
                    st.rerun()

        st.markdown("##### Marcadores Cadastrados:")
        for t in tags_atuais:
            c_label, c_del = st.columns([4, 1])
            c_label.write(f"🏷️ {t}")
            if c_del.button("🗑️", key=f"del_tag_{t}"):
                if len(tags_atuais) > 1:
                    tags_atuais.remove(t)
                    salvar_tags(tags_atuais)
                    carregar_tags.clear()
                    st.rerun()
                else:
                    st.error("Você precisa de pelo menos uma tag padrão.")

    with col_lista:
        st.markdown("<h3 style='color: #374151; font-size: 1.3rem; font-weight: 700;'>📋 Equipe por Turma e Núcleo</h3>", unsafe_allow_html=True)
        
        if not lista_residentes:
            st.info("Nenhum residente cadastrado no sistema ainda.")
        else:
            grupos_anos = {"R1": {}, "R2": {}}
            arquivo_morto = []
            
            for res in sorted(lista_residentes, key=lambda x: x.get('nome_completo', '')):
                status_atual = res.get('status', 'Ativo')
                ano_res = res.get('ano_residencia', 'R1')
                prof = res.get('profissao', 'Outros')
                
                if status_atual == 'Ativo':
                    if ano_res not in grupos_anos: grupos_anos[ano_res] = {}
                    if prof not in grupos_anos[ano_res]: grupos_anos[ano_res][prof] = []
                    grupos_anos[ano_res][prof].append(res)
                else:
                    arquivo_morto.append(res)
            
            for ano in ["R1", "R2"]:
                if grupos_anos[ano]:
                    cor_turma = "#1e3a8a" if ano == "R1" else "#047857"
                    bg_turma = "#eff6ff" if ano == "R1" else "#ecfdf5"
                    
                    st.markdown(f"<div style='background-color: {bg_turma}; padding: 10px; border-radius: 8px; margin-top: 20px; margin-bottom: 15px; border-left: 5px solid {cor_turma};'><h3 style='color: {cor_turma}; margin: 0; font-size: 1.3rem; font-weight: 800;'>🎓 Turma {ano}</h3></div>", unsafe_allow_html=True)
                    
                    for prof, membros in sorted(grupos_anos[ano].items()):
                        st.markdown(f"""
                        <div style='background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 100%); 
                                    padding: 8px 15px; 
                                    border-radius: 6px; 
                                    font-weight: 800; 
                                    color: white; 
                                    margin-bottom: 10px; 
                                    border-left: 5px solid #172554; 
                                    text-transform: uppercase; 
                                    font-size: 0.95rem; 
                                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);'>
                            📍 NÚCLEO: {prof} ({len(membros)})
                        </div>
                        """, unsafe_allow_html=True)
                        
                        for res in membros:
                            uid_res = res.get('uid')
                            ano_atual = res.get('ano_residencia', 'R1')
                            
                            with st.container(border=True):
                                st.markdown(f"""
                                <div style='display: flex; justify-content: space-between; align-items: center;'>
                                    <div>
                                        <h4 style='margin: 0; color: #1f2937; font-size: 1.1rem;'>{res.get('nome_completo', 'Sem nome')}</h4>
                                        <span style='font-size: 0.85rem; color: #6b7280; font-weight: 500;'>{res.get('email', '')} | Lotação: {res.get('lotacao', 'Não informada')}</span>
                                    </div>
                                    <div style='text-align: right; display: flex; gap: 8px;'>
                                        <span style='background-color: #f3f4f6; color: #4b5563; padding: 4px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: 800;'>{ano_atual}</span>
                                        <span style='background-color: #dcfce7; color: #166534; padding: 4px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: 800;'>ATIVO</span>
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
                                
                                with st.expander("⚙️ Editar Dados ou Alterar Status"):
                                    with st.form(f"form_edit_{uid_res}", border=False):
                                        e_nome = st.text_input("Nome Completo", value=res.get('nome_completo', ''))
                                        
                                        c1, c2 = st.columns(2)
                                        e_lotacao = c1.text_input("Lotação (UBS)", value=res.get('lotacao', ''))
                                        e_preceptor = c2.text_input("Preceptor(a)", value=res.get('preceptor', ''))
                                        
                                        profissoes_base = carregar_nucleos()
                                        idx_prof = profissoes_base.index(prof) if prof in profissoes_base else None
                                        if idx_prof is None:
                                            st.warning(f"⚠️ Atenção: O núcleo anterior deste residente ('{prof}') foi excluído. Vincule-o a um novo núcleo válido.")
                                        
                                        c3, c4, c5 = st.columns([2, 1, 1.5])
                                        e_prof = c3.selectbox("Núcleo / Profissão", profissoes_base, index=idx_prof, placeholder="Selecione...")
                                        e_ano = c4.selectbox("Turma", ["R1", "R2"], index=0 if ano_atual == "R1" else 1)
                                        
                                        status_opcoes = ["Ativo", "Egresso (Graduado)", "Desistente", "Desligado"]
                                        e_status = c5.selectbox("Status Operacional", status_opcoes, index=0)
                                        
                                        st.markdown("<span style='font-size: 0.8rem; color: #6b7280;'>O E-mail (login) não pode ser alterado por segurança.</span>", unsafe_allow_html=True)
                                        
                                        btn_salvar_edicao = st.form_submit_button("💾 Salvar Alterações", type="primary", use_container_width=True)
                                        
                                        if btn_salvar_edicao:
                                            if not e_prof:
                                                st.error("⛔ Operação Bloqueada: Selecione um Núcleo válido antes de salvar.")
                                            else:
                                                try:
                                                    db.collection("residentes").document(uid_res).update({
                                                        "nome_completo": e_nome.strip(),
                                                        "lotacao": e_lotacao.strip(),
                                                        "preceptor": e_preceptor.strip(),
                                                        "profissao": e_prof,
                                                        "ano_residencia": e_ano,
                                                        "status": e_status
                                                    })
                                                    carregar_residentes_adm.clear()
                                                    auth.update_user(uid_res, display_name=e_nome.strip())
                                                    st.success("✅ Dados atualizados com sucesso!")
                                                    st.rerun()
                                                except Exception as e:
                                                    st.error(f"Erro ao salvar: {e}")
                                    
                                    if st.button(f"🔑 Resetar Senha ({e_nome.split()[0]})", key=f"reset_{uid_res}"):
                                        try:
                                            auth.update_user(uid_res, password="Mudar@123")
                                            db.collection("residentes").document(uid_res).update({"primeiro_login": True})
                                            st.success("✅ Senha resetada para 'Mudar@123'.")
                                            carregar_residentes_adm.clear()
                                        except Exception as e:
                                            st.error(f"Erro ao resetar: {e}")

            if arquivo_morto:
                st.markdown("<hr style='border-color: #e5e7eb; margin: 40px 0 20px 0;'>", unsafe_allow_html=True)
                with st.expander(f"🗄️ Arquivo Interno (Egressos e Inativos) - {len(arquivo_morto)} registros", expanded=False):
                    st.markdown("<span style='font-size: 0.85rem; color: #6b7280;'>Residentes que concluíram o programa ou foram desligados. Seus dados permanecem salvos por exigência de auditoria.</span><br><br>", unsafe_allow_html=True)
                    
                    for res in arquivo_morto:
                        uid_res = res.get('uid')
                        prof = res.get('profissao', 'Outros')
                        status_res = res.get('status', 'Inativo')
                        
                        cor_st = "#dc2626" if status_res in ["Desistente", "Desligado"] else "#b45309"
                        bg_st = "#fef2f2" if status_res in ["Desistente", "Desligado"] else "#fffbeb"
                        
                        with st.container(border=True):
                            st.markdown(f"""
                            <div style='display: flex; justify-content: space-between; align-items: center; opacity: 0.7;'>
                                <div>
                                    <h4 style='margin: 0; color: #4b5563; font-size: 1.1rem; text-decoration: line-through;'>{res.get('nome_completo', 'Sem nome')}</h4>
                                    <span style='font-size: 0.85rem; color: #9ca3af; font-weight: 500;'>{res.get('email', '')} | Núcleo: {prof}</span>
                                </div>
                                <div style='text-align: right;'>
                                    <span style='background-color: {bg_st}; color: {cor_st}; padding: 4px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: 800;'>{status_res.upper()}</span>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            with st.expander("⚙️ Reativar, Alterar Status ou Excluir"):
                                with st.form(f"form_reativar_{uid_res}", border=False):
                                    lista_status_op = ["Ativo", "Egresso (Graduado)", "Desistente", "Desligado"]
                                    idx_st = lista_status_op.index(status_res) if status_res in lista_status_op else 1
                                    
                                    novo_status = st.selectbox("Mudar Status para:", lista_status_op, index=idx_st)
                                    btn_reativar = st.form_submit_button("Atualizar Situação", type="primary")
                                    
                                    if btn_reativar:
                                        try:
                                            db.collection("residentes").document(uid_res).update({"status": novo_status})
                                            st.success("✅ Status do residente atualizado com sucesso!")
                                            carregar_residentes_adm.clear()
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Erro ao atualizar: {e}")
                                
                                st.markdown("<hr style='border-color: #fca5a5; margin: 15px 0;'>", unsafe_allow_html=True)
                                st.markdown("<span style='color: #dc2626; font-weight: 800;'>⚠️ Zona de Perigo: Exclusão Permanente</span>", unsafe_allow_html=True)
                                st.markdown("<span style='color: #ef4444; font-size: 0.85rem;'>Atenção: Esta ação apagará a ficha do residente e revogará seu acesso (Login) permanentemente.</span>", unsafe_allow_html=True)
                                
                                checkbox_confirmar = st.checkbox(f"Sim, tenho certeza que desejo excluir o cadastro de {res.get('nome_completo', 'este residente')}.", key=f"check_del_{uid_res}")
                                
                                if checkbox_confirmar:
                                    if st.button("🗑️ Excluir Residente Definitivamente", type="primary", key=f"btn_excluir_{uid_res}"):
                                        try:
                                            db.collection("residentes").document(uid_res).delete()
                                            try:
                                                auth.delete_user(uid_res)
                                            except Exception as auth_e:
                                                st.warning(f"Residente removido do banco, mas houve um aviso no painel de autenticação: {auth_e}")
                                            
                                            carregar_residentes_adm.clear()
                                            carregar_pontos_residente_adm.clear()
                                            st.success("✅ Cadastro e acesso do residente removidos com sucesso.")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Erro ao excluir residente: {e}")

    with col_cadastro:
        st.markdown("<h3 style='color: #374151; font-size: 1.3rem; font-weight: 700;'>➕ Novo Residente</h3>", unsafe_allow_html=True)
        
        with st.form("form_novo_residente", clear_on_submit=True):
            st.markdown("<span style='font-size: 0.85rem; color: #6b7280;'>Cria o acesso e a ficha do residente simultaneamente.</span>", unsafe_allow_html=True)
            st.write("")
            
            n_nome = st.text_input("Nome Completo*")
            n_email = st.text_input("E-mail (Login)*")
            n_senha = st.text_input("Senha Provisória*", type="password", help="Mínimo de 6 caracteres")
            
            c1, c2 = st.columns(2)
            n_profissao = c1.selectbox("Profissão / Núcleo*", carregar_nucleos())
            n_ano = c2.selectbox("Classificação*", ["R1", "R2"])
            
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
                            "ano_residencia": n_ano,
                            "lotacao": n_lotacao.strip() if n_lotacao else "Não informada",
                            "preceptor": n_preceptor.strip() if n_preceptor else "Não informado",
                            "perfil": "Residente",
                            "status": "Ativo",
                            "primeiro_login": True,
                            "data_cadastro": firestore.SERVER_TIMESTAMP
                        }
                        db.collection("residentes").document(user_record.uid).set(novo_residente_dados)
                        
                        carregar_residentes_adm.clear()
                        st.success(f"✅ {n_nome} cadastrado com sucesso! A lista será atualizada.")
                        st.rerun() 
                    except auth.EmailAlreadyExistsError:
                        st.error("⚠️ Este e-mail já está cadastrado no Firebase!")
                    except Exception as e:
                        st.error(f"Erro ao tentar cadastrar: {e}")

# --- MÓDULO 3: AUDITORIA DE HORAS (MÁQUINA DO TEMPO & EXTRATO) ---
with aba3:
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
        st.markdown("<div style='font-weight: 600; color: #374151; margin-bottom: 5px;'>Selecione o Residente alvo da Auditoria:</div>", unsafe_allow_html=True)
        dict_residentes = {f"{r.get('nome_completo')} ({r.get('profissao')})": r.get('uid') for r in lista_residentes}
        residente_selecionado = st.selectbox("Residente", options=list(dict_residentes.keys()), label_visibility="collapsed", key="sel_res_auditoria")
        uid_alvo = dict_residentes[residente_selecionado]

        try:
            pontos_residente_auditoria = carregar_pontos_residente_adm(uid_alvo)
        except Exception as e:
            st.error(f"Erro ao carregar o histórico do residente: {e}")
            pontos_residente_auditoria = []

        st.write("")
        sub_aba_diaria, sub_aba_mensal, sub_aba_filtros = st.tabs(["📅 Edição Diária", "🏦 Extrato Mensal", "🔍 Filtro Investigativo"])

        with sub_aba_diaria:
            import datetime as dt
            
            col_data, _ = st.columns([1, 2])
            with col_data:
                st.markdown("<div style='font-weight: 600; color: #374151; margin-top: 10px; margin-bottom: 5px;'>Selecione a Data do Ponto</div>", unsafe_allow_html=True)
                data_auditoria = st.date_input("Data", value=hoje_local(), label_visibility="collapsed", key="dt_auditoria")

            st.markdown("---")
            data_str_alvo = data_auditoria.strftime("%Y-%m-%d")
            
            pontos_alvo = [
                p for p in pontos_residente_auditoria
                if p.get("data_registro") == data_str_alvo
            ]

            col_registros, col_injetar = st.columns([1.5, 1], gap="large")

            with col_registros:
                st.markdown(f"<h3 style='color: #1e40af; font-size: 1.2rem; font-weight: 700;'>🔎 Registros salvos em {data_auditoria.strftime('%d/%m/%Y')}</h3>", unsafe_allow_html=True)
                
                if not pontos_alvo:
                    st.info("Nenhum registro encontrado para este residente nesta data.")
                else:
                    for pt in pontos_alvo:
                        cat = normalizar_categoria(pt.get("categoria", ""))
                        horas_decimais = pt.get("horas_computadas", 0.0)
                        
                        tag = pt.get("tag", "Rotina Padrão")
                        obs = pt.get("justificativa", "Sem observações")
                        horarios = " | ".join(pt.get("horarios_descritos", []))
                        if not horarios: horarios = ""
                        
                        cor_borda = "#16a34a" if cat == "Prática" else ("#1e40af" if "Teórica" in cat else "#dc2626")
                        horas_formatadas = formatar_horas_exatas_adm(horas_decimais)
                        
                        with st.container(border=True):
                            st.markdown(f"""
                            <div style='display: flex; justify-content: space-between;'>
                                <div>
                                    <span style='font-weight: 800; color: {cor_borda}; font-size: 1.1rem;'>{cat}</span><br>
                                    <span style='font-size: 0.85rem; color: #6b7280;'>🕛 {horarios if horarios else "Dia Integral / Sem relógio"}</span><br>
                                    <span style='font-size: 0.85rem; color: #1e3a8a; font-weight: 600;'>🏷️ {tag}</span><br>
                                    <span style='font-size: 0.85rem; color: #4b5563; font-style: italic;'>"{obs}"</span>
                                </div>
                                <div style='text-align: right; font-weight: 800; font-size: 1.3rem; color: {cor_borda};'>
                                    {horas_formatadas}
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            with st.expander("✏️ Editar ou Excluir Registro"):
                                h_atual = int(abs(horas_decimais))
                                m_atual = int(round((abs(horas_decimais) - h_atual) * 60))
                                if m_atual == 60:
                                    h_atual += 1
                                    m_atual = 0
                                
                                with st.form(key=f"form_edit_{pt['doc_id']}", border=False):
                                    idx_cat = CATEGORIAS_OFICIAIS.index(cat) if cat in CATEGORIAS_OFICIAIS else 0
                                    e_cat = st.selectbox("Categoria Oficial", CATEGORIAS_OFICIAIS, index=idx_cat)
                                    
                                    lista_tags_edit = carregar_tags()
                                    idx_tag = lista_tags_edit.index(tag) if tag in lista_tags_edit else 0
                                    e_tag = st.selectbox("Marcador / Tag (Opcional)", lista_tags_edit, index=idx_tag)
                                    
                                    st.markdown("<span style='font-size: 0.85rem; color: #d97706; font-weight: 600;'>Opção A: Lançamento Manual (Para Atestados/Faltas)</span>", unsafe_allow_html=True)
                                    c_h, c_m = st.columns(2)
                                    e_h = c_h.text_input("Horas (HH)", value=f"{h_atual:02d}")
                                    e_m = c_m.text_input("Minutos (MM)", value=f"{m_atual:02d}")
                                    
                                    st.markdown("<hr style='margin: 15px 0 10px 0; border-color: #e5e7eb;'>", unsafe_allow_html=True)
                                    st.markdown("<span style='font-size: 0.85rem; color: #16a34a; font-weight: 600;'>Opção B: Cálculo Automático Inteligente</span><br><span style='font-size: 0.8rem; color: #6b7280;'>Se você alterar os horários abaixo (ex: <i>07:00 às 12:00</i>), o sistema ignorará as caixinhas de cima e <b>calculará o total automaticamente</b> ao salvar!</span>", unsafe_allow_html=True)
                                    
                                    e_horarios = st.text_input("Horários (Use ' | ' para separar turnos)", value=horarios)
                                    e_obs = st.text_area("Justificativa", value=obs)
                                    
                                    btn_salvar_edicao = st.form_submit_button("💾 Salvar Alterações", type="primary", use_container_width=True)
                                
                                if btn_salvar_edicao:
                                    try:
                                        novos_horarios_lista = [h.strip() for h in e_horarios.split("|") if h.strip()]

                                        if e_cat in CATEGORIAS_AUSENCIA:
                                            # Ocorrência administrativa nunca cria hora trabalhada.
                                            # Se houve trabalho parcial no dia, ele deve existir em registro
                                            # próprio de Prática/Teoria.
                                            nova_hora_decimal = 0.0
                                        else:
                                            horas_calculadas = 0.0
                                            turnos_validos = 0

                                            for turno in novos_horarios_lista:
                                                if "às" in turno:
                                                    partes = turno.split(" às ", 1)
                                                    if len(partes) != 2:
                                                        raise ValueError(f"Turno inválido: {turno}. Use HH:MM às HH:MM.")
                                                    h_turno, _ = _calc_diff_horario(partes[0], partes[1])
                                                    horas_calculadas += h_turno
                                                    turnos_validos += 1

                                            if turnos_validos > 0:
                                                nova_hora_decimal = horas_calculadas
                                            else:
                                                nova_hora_decimal, _, _ = _parse_hhmm_duracao(e_h, e_m)

                                            if nova_hora_decimal <= 0:
                                                raise ValueError("Registros de Prática/Teoria/AAD precisam ter carga horária maior que zero.")

                                        db.collection("pontos").document(pt["doc_id"]).update({
                                            "categoria": e_cat,
                                            "tag": e_tag if e_cat not in CATEGORIAS_AUSENCIA else "Rotina Padrão",
                                            "horas_computadas": nova_hora_decimal,
                                            "horarios_descritos": novos_horarios_lista,
                                            "justificativa": e_obs,
                                            "modificado_por": st.session_state.get("nome_completo", "Administrador"),
                                            "ultima_edicao": firestore.SERVER_TIMESTAMP,
                                            "origem_ultima_edicao": "Painel ADM",
                                        })

                                        invalidar_agregador(uid_alvo)
                                        st.session_state["flash_adm"] = "✅ Registro atualizado com sucesso!"
                                        st.rerun()
                                    except ValueError as e:
                                        st.error(f"⚠️ {e}")
                                    except Exception as e:
                                        st.error(f"Erro ao atualizar: {e}")
                                
                                if st.button("🗑️ Forçar Exclusão", key=f"del_adm_{pt['doc_id']}", use_container_width=True):
                                    db.collection("pontos").document(pt['doc_id']).delete()
                                    invalidar_agregador(uid_alvo)
                                    st.session_state["flash_adm"] = "✅ Registro excluído pelo Administrador!"
                                    st.rerun()

            with col_injetar:
                st.markdown("<h3 style='color: #d97706; font-size: 1.2rem; font-weight: 700;'>💉 Novo Lançamento Manual</h3>", unsafe_allow_html=True)
                
                with st.form("form_injetar_adm", clear_on_submit=True):
                    i_cat = st.selectbox("Categoria Oficial", CATEGORIAS_OFICIAIS)
                    categoria_injecao_ui = normalizar_categoria(i_cat)
                    ausencia_injecao_ui = categoria_injecao_ui in CATEGORIAS_AUSENCIA
                    i_tag_injecao = st.selectbox("Marcador / Tag (Opcional)", carregar_tags(), disabled=ausencia_injecao_ui)
                    
                    st.info("💡 **Regra:** ocorrências de ausência são gravadas com 0h; a carga devida é calculada automaticamente pelo motor.")
                    
                    st.markdown("<span style='font-weight: 600; font-size: 0.95rem; color: #374151;'>Total de Horas a Computar:</span>", unsafe_allow_html=True)
                    col_h, col_m = st.columns(2)
                    i_hh = col_h.text_input("Horas (HH)", placeholder="00", max_chars=2, disabled=ausencia_injecao_ui)
                    i_mm = col_m.text_input("Minutos (MM)", placeholder="00", max_chars=2, disabled=ausencia_injecao_ui)
                    
                    i_obs = st.text_area("Justificativa / Motivo da injeção")
                    
                    btn_salvar_injecao = st.form_submit_button("💾 Injetar no Banco de Dados", type="primary", use_container_width=True)
                    
                    if btn_salvar_injecao:
                        try:
                            categoria_final = normalizar_categoria(i_cat)
                            fim_programa = obter_fim_programa(DATA_INICIO_RESIDENCIA)
                            if not (DATA_INICIO_RESIDENCIA <= data_auditoria <= fim_programa):
                                raise ValueError(
                                    f"A data deve ficar entre {DATA_INICIO_RESIDENCIA:%d/%m/%Y} "
                                    f"e {fim_programa:%d/%m/%Y}."
                                )

                            if categoria_final in CATEGORIAS_AUSENCIA:
                                horas_finais_decimais = 0.0
                                hh_val, mm_val = 0, 0
                                horarios_injecao = ["Integral (Lançamento via Painel ADM)"]
                                tag_final = "Rotina Padrão"
                                unico_por_dia = True
                            else:
                                horas_finais_decimais, hh_val, mm_val = _parse_hhmm_duracao(i_hh, i_mm)
                                if horas_finais_decimais <= 0:
                                    raise ValueError("Informe uma carga maior que zero para Prática/Teoria/AAD.")
                                horarios_injecao = [f"{hh_val:02d}h {mm_val:02d}m (Lançado via Painel ADM)"]
                                tag_final = i_tag_injecao
                                unico_por_dia = False

                            doc_id_inj = _doc_id_lancamento(
                                uid_alvo, data_str_alvo, categoria_final, unico_por_dia=unico_por_dia
                            )

                            dados_inj = {
                                "uid_residente": uid_alvo,
                                "data_registro": data_str_alvo,
                                "mes_referencia": data_auditoria.strftime("%m/%Y"),
                                "categoria": categoria_final,
                                "tag": tag_final,
                                "horas_computadas": horas_finais_decimais,
                                "horarios_descritos": horarios_injecao,
                                "justificativa": f"{i_obs} (Alteração realizada pela Coordenação)" if i_obs else "(Alteração ADM)",
                                "criado_em": firestore.SERVER_TIMESTAMP,
                                "ultima_edicao": firestore.SERVER_TIMESTAMP,
                                "criado_por": st.session_state.get("nome_completo", "Administrador"),
                                "modificado_por": st.session_state.get("nome_completo", "Administrador"),
                                "origem": "Painel ADM",
                            }

                            db.collection("pontos").document(doc_id_inj).set(dados_inj)
                            invalidar_agregador(uid_alvo)
                            st.session_state["flash_adm"] = "✅ Lançamento gravado com sucesso!"
                            st.rerun()
                        except ValueError as e:
                            st.error(f"⚠️ {e}")
                        except Exception as e:
                            st.error(f"Erro ao gravar lançamento: {e}")

        with sub_aba_mensal:
            import datetime as dt
            import calendar
            
            meses_disponiveis = [f"{str(m).zfill(2)}/{ano}" for ano in [2026, 2027, 2028] for m in range(1, 13)]
            mes_atual_str = agora_local().strftime("%m/%Y")
            idx_mes = meses_disponiveis.index(mes_atual_str) if mes_atual_str in meses_disponiveis else 2 
            
            c_mes, _ = st.columns([1, 3])
            with c_mes:
                mes_extrato = st.selectbox("Selecione o Mês", meses_disponiveis, index=idx_mes, key="sel_mes_extrato")
            
            st.markdown("---")
            mes_str, ano_str = mes_extrato.split("/")
            mes_num, ano_num = int(mes_str), int(ano_str)
            _, dias_no_mes = calendar.monthrange(ano_num, mes_num)

            inicio_mes = date(ano_num, mes_num, 1)
            fim_mes = date(ano_num, mes_num, dias_no_mes)
            fim_programa = obter_fim_programa(data_inicio_residencia)
            inicio_calculo = max(inicio_mes, data_inicio_residencia)
            fim_calculo = min(fim_mes, hoje_local(), fim_programa)

            periodo_mes = calcular_periodo(
                pontos_residente_auditoria,
                inicio_calculo,
                fim_calculo,
                data_inicio_programa=data_inicio_residencia,
                data_fim_programa=fim_programa,
            )

            meta_ref_p_mes = periodo_mes["curricular_base_pratica"]
            meta_ref_t_mes = periodo_mes["curricular_base_teoria"]
            meta_p_mes = periodo_mes["esperado_pratica"]  # cobrança operacional do mês
            meta_t_mes = periodo_mes["esperado_teoria"]  # cobrança operacional do mês
            trab_p = periodo_mes["realizado_pratica"]
            trab_t = periodo_mes["realizado_teoria"]
            saldo_p = periodo_mes["saldo_pratica"]
            saldo_t = periodo_mes["saldo_teoria"]

            motor_dia_mes = {d["data"].isoformat(): d for d in periodo_mes.get("por_dia", [])}
            pontos_extrato = [
                p for p in pontos_residente_auditoria
                if p.get("data_registro", "") in motor_dia_mes
            ]

            extrato_detalhado = []
            for pt in pontos_extrato:
                cat = normalizar_categoria(pt.get("categoria", ""))
                horas = _safe_float(pt.get("horas_computadas", 0.0))
                data_str = pt.get("data_registro", "")
                dia_motor = motor_dia_mes.get(data_str)
                if not dia_motor:
                    continue

                dt_obj = dia_motor["data"]

                if cat == "Férias":
                    retirado_p = max(0.0, dia_motor["meta_base_pratica"] - dia_motor["meta_pratica"])
                    retirado_t = max(0.0, dia_motor["meta_base_teoria"] - dia_motor["meta_teoria"])
                    valor_visual_p = f"Férias: cobrança suspensa {formatar_horas_exatas_adm(retirado_p)}" if retirado_p > 0 else "0h"
                    valor_visual_t = f"Férias: cobrança suspensa {formatar_horas_exatas_adm(retirado_t)}" if retirado_t > 0 else "0h"
                    cor_linha = "#eff6ff"
                    cor_texto = "#2563eb"

                elif cat in CATEGORIAS_REPOSICAO:
                    deb_p = dia_motor.get("reposicao_pratica", 0.0)
                    deb_t = dia_motor.get("reposicao_teoria", 0.0)
                    if deb_p <= 0 and deb_t <= 0:
                        valor_visual_p = "Sem dívida"
                        valor_visual_t = "Sem dívida"
                        cor_linha = "#f8fafc"
                        cor_texto = "#6b7280"
                    else:
                        valor_visual_p = f"-{formatar_horas_exatas_adm(deb_p)}" if deb_p > 0 else "0h"
                        valor_visual_t = f"-{formatar_horas_exatas_adm(deb_t)}" if deb_t > 0 else "0h"
                        cor_linha = "#fef2f2"
                        cor_texto = "#dc2626"

                elif cat == "Prática":
                    valor_visual_p = f"+{formatar_horas_exatas_adm(horas)}"
                    valor_visual_t = "0h"
                    cor_linha = "#ffffff"
                    cor_texto = "#16a34a"

                elif cat in {"Teórica", "Teórico-prática", "Estudo Auto-dirigido (AAD)"}:
                    valor_visual_p = "0h"
                    valor_visual_t = f"+{formatar_horas_exatas_adm(horas)}"
                    cor_linha = "#ffffff"
                    cor_texto = "#16a34a"

                else:
                    valor_visual_p = "0h"
                    valor_visual_t = "0h"
                    cor_linha = "#ffffff"
                    cor_texto = "#6b7280"

                tag_label = pt.get("tag", "Rotina Padrão")
                obs = pt.get("justificativa", "Sem observações")
                if tag_label and tag_label != "Rotina Padrão":
                    obs = f"[{tag_label}] {obs}"

                horarios = " | ".join(pt.get("horarios_descritos", []) or [])
                if not horarios:
                    horarios = "Integral" if cat in CATEGORIAS_AUSENCIA else "Sem horário detalhado"

                extrato_detalhado.append({
                    "data_obj": dt_obj,
                    "categoria": cat,
                    "horarios": horarios,
                    "obs": obs,
                    "vp": valor_visual_p,
                    "vt": valor_visual_t,
                    "cor_bg": cor_linha,
                    "cor_tx": cor_texto,
                })

            if inicio_calculo > fim_calculo:
                st.info("Este mês está fora do período já transcorrido da residência.")
            elif not pontos_extrato:
                st.info("Nenhum lançamento neste mês. O saldo abaixo continua sendo calculado normalmente pela meta prevista.")

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
                            <div style='font-size: 0.85rem; color: #6b7280; font-weight: 600;'>Meta Curricular</div>
                            <div style='font-size: 1.4rem; font-weight: 800; color: #4b5563;'>{formatar_horas_exatas_adm(meta_ref_p_mes)}</div>
                            <div style='font-size: 0.72rem; color: #9ca3af; margin-top: 2px;'>Cobrança no mês: {formatar_horas_exatas_adm(meta_p_mes)}</div>
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
                            <div style='font-size: 0.85rem; color: #6b7280; font-weight: 600;'>Meta Curricular</div>
                            <div style='font-size: 1.4rem; font-weight: 800; color: #4b5563;'>{formatar_horas_exatas_adm(meta_ref_t_mes)}</div>
                            <div style='font-size: 0.72rem; color: #9ca3af; margin-top: 2px;'>Cobrança no mês: {formatar_horas_exatas_adm(meta_t_mes)}</div>
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

        with sub_aba_filtros:
            st.markdown("<h3 style='color: #374151; font-weight: 800; margin-bottom: 5px;'>🔍 Filtro Investigativo por Categoria</h3>", unsafe_allow_html=True)
            st.markdown("<span style='color: #6b7280; font-size: 0.95rem;'>Selecione uma ou mais categorias abaixo para auditar o histórico isolado deste residente.</span><br><br>", unsafe_allow_html=True)
            
            categorias_selecionadas = st.multiselect("Selecione as Categorias Alvo:", CATEGORIAS_OFICIAIS, placeholder="Ex: Feriado / Ponto Facultativo, Atestado / Licença Médica...")
            
            if categorias_selecionadas:
                with st.spinner("Puxando capivara do residente..."):
                    categorias_alvo_norm = {normalizar_categoria(c) for c in categorias_selecionadas}
                    pontos_filtrados = []
                    for p in pontos_residente_auditoria:
                        cat_norm = normalizar_categoria(p.get("categoria", ""))
                        if cat_norm in categorias_alvo_norm:
                            item = dict(p)
                            item["_categoria_norm"] = cat_norm
                            pontos_filtrados.append(item)

                    pontos_filtrados.sort(key=lambda k: k.get("data_registro", ""), reverse=True)

                    if not pontos_filtrados:
                        st.info("Nenhuma ocorrência encontrada para as categorias selecionadas.")
                    else:
                        fim_programa = obter_fim_programa(DATA_INICIO_RESIDENCIA)
                        periodo_auditoria = calcular_periodo(
                            pontos_residente_auditoria,
                            DATA_INICIO_RESIDENCIA,
                            min(hoje_local(), fim_programa),
                            data_inicio_programa=DATA_INICIO_RESIDENCIA,
                            data_fim_programa=fim_programa,
                        )
                        motor_por_data = {d["data"].isoformat(): d for d in periodo_auditoria.get("por_dia", [])}

                        datas_unicas = {p.get("data_registro") for p in pontos_filtrados if p.get("data_registro")}
                        total_trab_p = sum(_safe_float(p.get("horas_computadas")) for p in pontos_filtrados if p["_categoria_norm"] == "Prática")
                        total_trab_t = sum(_safe_float(p.get("horas_computadas")) for p in pontos_filtrados if p["_categoria_norm"] in {"Teórica", "Teórico-prática", "Estudo Auto-dirigido (AAD)"})
                        total_deb_p = total_deb_t = 0.0
                        total_retirado_p = total_retirado_t = 0.0

                        # Impactos administrativos são somados uma única vez por data,
                        # evitando multiplicar a mesma dívida quando há dois documentos
                        # administrativos no mesmo dia.
                        for data_str in datas_unicas:
                            dia_motor = motor_por_data.get(data_str)
                            if not dia_motor:
                                continue
                            cats_dia_filtradas = {p["_categoria_norm"] for p in pontos_filtrados if p.get("data_registro") == data_str}

                            if "Férias" in cats_dia_filtradas:
                                total_retirado_p += max(0.0, dia_motor["meta_base_pratica"] - dia_motor["meta_pratica"])
                                total_retirado_t += max(0.0, dia_motor["meta_base_teoria"] - dia_motor["meta_teoria"])

                            if cats_dia_filtradas & CATEGORIAS_REPOSICAO:
                                total_deb_p += dia_motor.get("reposicao_pratica", 0.0)
                                total_deb_t += dia_motor.get("reposicao_teoria", 0.0)

                        html_impacto = ""
                        if total_trab_p > 0 or total_deb_p > 0 or total_retirado_p > 0:
                            html_impacto += "<div style='margin-bottom: 10px;'>"
                            if total_trab_p > 0:
                                html_impacto += f"<div style='font-size: 1.05rem; color: #2563eb; font-weight: 800;'>✅ +{total_trab_p:.1f}h (Prática trabalhada)</div>"
                            if total_deb_p > 0:
                                html_impacto += f"<div style='font-size: 1.05rem; color: #dc2626; font-weight: 800;'>🔻 -{total_deb_p:.1f}h (Reposição de prática)</div>"
                            if total_retirado_p > 0:
                                html_impacto += f"<div style='font-size: 1.05rem; color: #2563eb; font-weight: 800;'>🏖️ {total_retirado_p:.1f}h sem cobrança diária durante férias (meta anual preservada)</div>"
                            html_impacto += "</div>"

                        if total_trab_t > 0 or total_deb_t > 0 or total_retirado_t > 0:
                            html_impacto += "<div>"
                            if total_trab_t > 0:
                                html_impacto += f"<div style='font-size: 1.05rem; color: #7c3aed; font-weight: 800;'>✅ +{total_trab_t:.1f}h (Teoria/AAD trabalhada)</div>"
                            if total_deb_t > 0:
                                html_impacto += f"<div style='font-size: 1.05rem; color: #dc2626; font-weight: 800;'>🔻 -{total_deb_t:.1f}h (Reposição teórica)</div>"
                            if total_retirado_t > 0:
                                html_impacto += f"<div style='font-size: 1.05rem; color: #7c3aed; font-weight: 800;'>🏖️ {total_retirado_t:.1f}h sem cobrança diária durante férias (meta anual preservada)</div>"
                            html_impacto += "</div>"

                        if not html_impacto:
                            html_impacto = "<div style='font-size: 1.05rem; color: #6b7280; font-weight: 800;'>Sem impacto acumulado até hoje.</div>"

                        c1, c2 = st.columns([1, 1.8])
                        with c1:
                            st.markdown(f"<div style='background-color: #fcfaee; border: 1px solid #e5e7eb; border-left: 5px solid #d97706; padding: 15px; border-radius: 8px; height: 100%;'><div style='font-size: 0.85rem; color: #6b7280; font-weight: 700; text-transform: uppercase;'>Total de Dias (Ocorrências)</div><div style='font-size: 1.8rem; color: #b45309; font-weight: 800;'>{len(datas_unicas)} dias</div></div>", unsafe_allow_html=True)
                        with c2:
                            st.markdown(f"<div style='background-color: #f8fafc; border: 1px solid #e5e7eb; border-left: 5px solid #3b82f6; padding: 15px; border-radius: 8px; height: 100%; display: flex; flex-direction: column; justify-content: center;'><div style='font-size: 0.80rem; color: #6b7280; font-weight: 700; text-transform: uppercase; margin-bottom: 4px;'>Impacto no banco de horas:</div>{html_impacto}</div>", unsafe_allow_html=True)

                        st.markdown("<hr style='border-color: #e5e7eb; margin: 25px 0 15px 0;'>", unsafe_allow_html=True)
                        st.markdown("<h4 style='color: #374151; font-weight: 700; font-size: 1.1rem; margin-bottom: 15px;'>📋 Lista Detalhada</h4>", unsafe_allow_html=True)

                        for pt in pontos_filtrados:
                            data_pt_str = pt.get("data_registro", "")
                            cat = pt["_categoria_norm"]
                            horas = _safe_float(pt.get("horas_computadas", 0.0))
                            tag_label = pt.get("tag", "Rotina Padrão")
                            obs = pt.get("justificativa", "Sem observações adicionais.")
                            if tag_label and tag_label != "Rotina Padrão":
                                obs = f"[{tag_label}] {obs}"

                            impacto_p = "0.0h"
                            impacto_t = "0.0h"
                            cor_cat = "#6b7280"
                            txt_color = "#6b7280"
                            dia_motor = motor_por_data.get(data_pt_str)

                            if data_pt_str:
                                try:
                                    dt_obj = datetime.strptime(data_pt_str, "%Y-%m-%d").date()
                                    data_formatada = dt_obj.strftime("%d/%m/%Y")
                                except ValueError:
                                    dt_obj = None
                                    data_formatada = "Data inválida"
                            else:
                                dt_obj = None
                                data_formatada = "Sem Data"

                            if cat == "Férias" and dia_motor:
                                retirado_p = max(0.0, dia_motor["meta_base_pratica"] - dia_motor["meta_pratica"])
                                retirado_t = max(0.0, dia_motor["meta_base_teoria"] - dia_motor["meta_teoria"])
                                impacto_p = f"{retirado_p:.1f}h sem cobrança no dia" if retirado_p > 0 else "0.0h"
                                impacto_t = f"{retirado_t:.1f}h sem cobrança no dia" if retirado_t > 0 else "0.0h"
                                cor_cat = txt_color = "#2563eb"
                            elif cat in CATEGORIAS_REPOSICAO and dia_motor:
                                deb_p = dia_motor.get("reposicao_pratica", 0.0)
                                deb_t = dia_motor.get("reposicao_teoria", 0.0)
                                impacto_p = f"-{deb_p:.1f}h (dívida do dia)" if deb_p > 0 else "0.0h"
                                impacto_t = f"-{deb_t:.1f}h (dívida do dia)" if deb_t > 0 else "0.0h"
                                cor_cat = txt_color = "#dc2626"
                            elif cat == "Prática":
                                impacto_p = f"+{horas:.1f}h (trabalhada)"
                                cor_cat = txt_color = "#16a34a"
                            elif cat in {"Teórica", "Teórico-prática", "Estudo Auto-dirigido (AAD)"}:
                                impacto_t = f"+{horas:.1f}h (trabalhada)"
                                cor_cat = txt_color = "#7c3aed"
                            elif dt_obj and dt_obj > hoje_local():
                                impacto_p = impacto_t = "Programado / ainda sem impacto"

                            st.markdown(f"<div style='display: flex; justify-content: space-between; align-items: center; background-color: #ffffff; border: 1px solid #e5e7eb; padding: 12px 18px; border-radius: 8px; margin-bottom: 10px; box-shadow: 0 1px 2px rgba(0,0,0,0.02);'><div style='flex: 1;'><div style='font-weight: 800; color: #1f2937; font-size: 1.05rem;'>{data_formatada} <span style='font-weight: 700; font-size: 0.75rem; background-color: {cor_cat}15; color: {cor_cat}; padding: 4px 10px; border-radius: 20px; margin-left: 10px; text-transform: uppercase;'>{cat}</span></div><div style='font-size: 0.9rem; color: #6b7280; margin-top: 5px; font-style: italic;'>&quot;{obs}&quot;</div></div><div style='text-align: right; min-width: 180px;'><div style='font-size: 0.95rem; font-weight: 800; color: {txt_color}; margin-bottom: 4px;'><span style='color: #9ca3af; font-weight: 600; font-size: 0.75rem; margin-right: 5px;'>PRÁT:</span> {impacto_p}</div><div style='font-size: 0.95rem; font-weight: 800; color: {txt_color};'><span style='color: #9ca3af; font-weight: 600; font-size: 0.75rem; margin-right: 5px;'>TEÓR:</span> {impacto_t}</div></div></div>", unsafe_allow_html=True)

# --- MÓDULO 4: CENTRAL DE LANÇAMENTOS (BULK INSERT) ---
with aba4:
    import datetime as dt
    from datetime import timedelta
    
    st.markdown("<div class='card-title' style='margin-bottom: 5px; color: #1e3a8a;'>📥 Central de Lançamentos Múltiplos</div>", unsafe_allow_html=True)
    st.markdown("<span style='color: #6b7280; font-size: 0.95rem;'>Módulo corporativo para inserção de ocorrências em lote, permitindo o alcance de múltiplos residentes e múltiplos dias simultaneamente.</span><br><br>", unsafe_allow_html=True)

    if not lista_residentes:
        st.warning("⚠️ O sistema não possui residentes cadastrados para realizar lançamentos.")
    else:
        with st.container(border=True):
            st.markdown("<h4 style='color: #374151; font-weight: 700; font-size: 1.1rem;'>1. Definição de Alvo</h4>", unsafe_allow_html=True)
            
            tipo_alvo = st.radio("Selecione a abrangência do lançamento:", ["Residente Específico", "Global (Residentes Ativos)"], horizontal=True, label_visibility="collapsed")

            alvos_selecionados = []
            if tipo_alvo == "Residente Específico":
                dict_residentes_lote = {f"{r.get('nome_completo')} ({r.get('profissao')})": r.get('uid') for r in lista_residentes}
                res_selecionado = st.selectbox("Selecione o Residente:", options=list(dict_residentes_lote.keys()))
                alvos_selecionados.append(dict_residentes_lote[res_selecionado])
            else:
                incluir_inativos = st.checkbox("Incluir residentes inativos/egressos neste lançamento global", value=False)
                if incluir_inativos:
                    residentes_alvo_global = lista_residentes
                else:
                    residentes_alvo_global = [r for r in lista_residentes if r.get("status", "Ativo") == "Ativo"]
                alvos_selecionados = [r.get("uid") for r in residentes_alvo_global if r.get("uid")]
                st.info(f"🌐 Lançamento Global: {len(alvos_selecionados)} residente(s) selecionado(s). Por padrão, somente residentes ativos são incluídos.")

        with st.container(border=True):
            st.markdown("<h4 style='color: #374151; font-weight: 700; font-size: 1.1rem;'>2. Parâmetros da Ocorrência</h4>", unsafe_allow_html=True)
            
            c_tipo_dt, c_dt = st.columns([1, 2])
            with c_tipo_dt:
                tipo_data = st.radio("Formato da Data:", ["Data Única", "Período (Múltiplos Dias)"])
            with c_dt:
                if tipo_data == "Data Única":
                    periodo_lote = st.date_input("Selecione a Data Alvo", value=hoje_local())
                else:
                    periodo_lote = st.date_input("Selecione a Data Inicial e Final", value=[hoje_local(), hoje_local() + timedelta(days=1)])
            
            st.markdown("<hr style='margin: 15px 0; border-color: #e5e7eb;'>", unsafe_allow_html=True)
            
            # --- O BOTÃO MÁGICO QUE ABRE O POPOVER (À PROVA DE BUGS) ---
            c_titulo_expresso, c_btn_nova_tag = st.columns([3, 1.5])
            with c_titulo_expresso:
                st.markdown("<span style='font-size: 0.85rem; font-weight: 600; color: #374151;'>Preenchimento Expresso (Opcional):</span>", unsafe_allow_html=True)
            with c_btn_nova_tag:
                # O st.popover é perfeito para menus flutuantes dentro de colunas!
                with st.popover("➕ Criar Nova Tag Rápida", use_container_width=True):
                    st.markdown("<span style='color: #6b7280; font-size: 0.85rem;'>Crie uma nova tag para organizar os lançamentos.</span>", unsafe_allow_html=True)
                    n_tag = st.text_input("Nome do Marcador", placeholder="Ex: Reunião Geral...", key="input_nova_tag_rapida")
                    
                    if st.button("💾 Salvar Marcador", type="primary", use_container_width=True, key="btn_salvar_tag_rapida"):
                        if n_tag.strip():
                            tags_atuais = carregar_tags()
                            if n_tag.strip() not in tags_atuais:
                                tags_atuais.append(n_tag.strip())
                                salvar_tags(tags_atuais)
                                carregar_tags.clear()
                                st.rerun()
                            else:
                                st.warning("⚠️ Essa tag já existe!")
                        else:
                            st.error("Digite um nome válido.")
            acao_expressa = st.pills("Configuração Rápida:", 
                ["Personalizado (Preencher Manualmente)", "Aula Teórica", "Estudo Auto-dirigido", "Falta Integral", "Atestado / Licença Médica", "Ausência Justificada", "Feriado / Ponto Facultativo", "Férias"], 
                default="Personalizado (Preencher Manualmente)", 
                label_visibility="collapsed"
            )

            with st.form("form_lote_adm", clear_on_submit=True):
                is_express_cat = acao_expressa != "Personalizado (Preencher Manualmente)"
                is_ausencia_integral = acao_expressa in ["Falta Integral", "Atestado / Licença Médica", "Ausência Justificada", "Feriado / Ponto Facultativo", "Férias"]
                
                cat_padrao = "Prática"
                if acao_expressa == "Aula Teórica": cat_padrao = "Teórica"
                elif acao_expressa == "Estudo Auto-dirigido": cat_padrao = "Estudo Auto-dirigido (AAD)"
                elif acao_expressa == "Falta Integral": cat_padrao = "Falta"
                elif acao_expressa == "Atestado / Licença Médica": cat_padrao = "Atestado / Licença Médica"
                elif acao_expressa == "Ausência Justificada": cat_padrao = "Ausência Justificada"
                elif acao_expressa == "Feriado / Ponto Facultativo": cat_padrao = "Feriado / Ponto Facultativo"
                elif acao_expressa == "Férias": cat_padrao = "Férias"
                
                c_cat, c_tag = st.columns(2)
                with c_cat:
                    st.markdown("<div style='font-size: 0.95rem; font-weight: 600; color: #374151; margin-bottom: 5px;'>Vínculo da Categoria:</div>", unsafe_allow_html=True)
                    i_cat = st.selectbox("Categoria Oficial", CATEGORIAS_OFICIAIS, index=CATEGORIAS_OFICIAIS.index(cat_padrao), disabled=is_express_cat, label_visibility="collapsed")

                categoria_final_lote = normalizar_categoria(i_cat)
                is_ausencia_categoria = categoria_final_lote in CATEGORIAS_AUSENCIA

                with c_tag:
                    st.markdown("<div style='font-size: 0.95rem; font-weight: 600; color: #374151; margin-bottom: 5px;'>Marcador / Tag (Opcional):</div>", unsafe_allow_html=True)
                    i_tag_lote = st.selectbox("Marcador / Tag", carregar_tags(), disabled=is_ausencia_categoria, label_visibility="collapsed")
                
                st.markdown("<div style='font-size: 0.95rem; font-weight: 600; color: #374151; margin-top: 15px;'>Carga Horária (Apenas para lançamentos personalizados ou aulas):</div>", unsafe_allow_html=True)
                
                c_m, c_t, c_n = st.columns(3)
                
                with c_m:
                    with st.container(border=True):
                        st.markdown("<div style='background-color: #fef9c3; padding: 8px; border-radius: 6px; text-align: center; color: #a16207; font-weight: 800; letter-spacing: 0.5px; margin-bottom: 10px; border: 1px solid #fde047;'>☀️ MANHÃ</div>", unsafe_allow_html=True)
                        m_ent = st.text_input("Entrada (ex: 08:00)", disabled=is_ausencia_categoria, key="m_ent")
                        m_sai = st.text_input("Saída (ex: 12:00)", disabled=is_ausencia_categoria, key="m_sai")
                        
                with c_t:
                    with st.container(border=True):
                        st.markdown("<div style='background-color: #ffedd5; padding: 8px; border-radius: 6px; text-align: center; color: #c2410c; font-weight: 800; letter-spacing: 0.5px; margin-bottom: 10px; border: 1px solid #fdba74;'>🌤️ TARDE</div>", unsafe_allow_html=True)
                        t_ent = st.text_input("Entrada (ex: 14:00)", disabled=is_ausencia_categoria, key="t_ent")
                        t_sai = st.text_input("Saída (ex: 18:00)", disabled=is_ausencia_categoria, key="t_sai")
                        
                with c_n:
                    with st.container(border=True):
                        st.markdown("<div style='background-color: #e0e7ff; padding: 8px; border-radius: 6px; text-align: center; color: #4338ca; font-weight: 800; letter-spacing: 0.5px; margin-bottom: 10px; border: 1px solid #a5b4fc;'>🌙 NOITE</div>", unsafe_allow_html=True)
                        n_ent = st.text_input("Entrada (ex: 19:00)", disabled=is_ausencia_categoria, key="n_ent")
                        n_sai = st.text_input("Saída (ex: 22:00)", disabled=is_ausencia_categoria, key="n_sai")

                st.markdown("<span style='font-size: 0.85rem; color: #6b7280;'>Ou insira o total manual diretamente (sobrepõe os turnos acima):</span>", unsafe_allow_html=True)
                c_h, c_min = st.columns(2)
                i_hh = c_h.text_input("Total Horas (HH)", disabled=is_ausencia_categoria)
                i_mm = c_min.text_input("Total Minutos (MM)", disabled=is_ausencia_categoria)
                
                st.markdown("<div style='font-size: 0.95rem; font-weight: 600; color: #374151; margin-top: 15px;'>Justificativa / Observação:</div>", unsafe_allow_html=True)
                i_obs = st.text_area("Motivo ou descrição oficial", label_visibility="collapsed")
                
                submit_lote = st.form_submit_button("✅ Executar Lançamento", type="primary", use_container_width=True)
                
                if submit_lote:
                    try:
                        # --------------------------------------------------
                        # 1) Resolve e valida o período
                        # --------------------------------------------------
                        dt_inicio = dt_fim = None
                        if tipo_data == "Data Única" and periodo_lote:
                            dt_inicio = dt_fim = periodo_lote
                        elif tipo_data == "Período (Múltiplos Dias)":
                            if isinstance(periodo_lote, (tuple, list)):
                                if len(periodo_lote) == 2:
                                    dt_inicio, dt_fim = periodo_lote
                                elif len(periodo_lote) == 1:
                                    dt_inicio = dt_fim = periodo_lote[0]

                        if not dt_inicio or not dt_fim:
                            raise ValueError("Selecione corretamente a data inicial e final.")
                        if dt_fim < dt_inicio:
                            raise ValueError("A data final não pode ser anterior à data inicial.")
                        if not alvos_selecionados:
                            raise ValueError("Nenhum residente foi selecionado para o lançamento.")

                        inicio_programa = DATA_INICIO_RESIDENCIA
                        fim_programa = obter_fim_programa(inicio_programa)
                        if dt_inicio < inicio_programa or dt_fim > fim_programa:
                            raise ValueError(
                                f"O lançamento deve ficar dentro do período da residência: "
                                f"{inicio_programa:%d/%m/%Y} a {fim_programa:%d/%m/%Y}."
                            )

                        # --------------------------------------------------
                        # 2) Calcula/valida a carga do lançamento
                        # --------------------------------------------------
                        categoria_final_lote = normalizar_categoria(i_cat)
                        ausencia_final = categoria_final_lote in CATEGORIAS_AUSENCIA
                        desc_horarios = []

                        if ausencia_final:
                            # Ausência nunca gera hora trabalhada. O motor calcula
                            # automaticamente a carga a repor; somente férias retiram meta.
                            horas_finais_decimais = 0.0
                            desc_horarios = ["Integral (Lançamento Coordenação)"]
                            tag_final = "Rotina Padrão"
                        else:
                            tag_final = i_tag_lote
                            manual_preenchido = bool((i_hh or "").strip() or (i_mm or "").strip())

                            if manual_preenchido:
                                horas_finais_decimais, hh_val, mm_val = _parse_hhmm_duracao(i_hh, i_mm)
                                if horas_finais_decimais <= 0:
                                    raise ValueError("A carga manual precisa ser maior que zero.")
                                desc_horarios = [f"{hh_val:02d}h {mm_val:02d}m (Total Manual)"]
                            else:
                                horas_finais_decimais = 0.0
                                for ent, sai in ((m_ent, m_sai), (t_ent, t_sai), (n_ent, n_sai)):
                                    if (ent or "").strip() or (sai or "").strip():
                                        h_turno, desc_turno = _calc_diff_horario(ent, sai)
                                        horas_finais_decimais += h_turno
                                        desc_horarios.append(desc_turno)

                                if horas_finais_decimais <= 0:
                                    raise ValueError("Informe pelo menos um turno completo ou uma carga horária manual.")
                                if horas_finais_decimais > 24:
                                    raise ValueError("A carga de um único dia não pode ultrapassar 24 horas.")

                        # --------------------------------------------------
                        # 3) Executa a gravação em lotes seguros no Firestore
                        # --------------------------------------------------
                        batch = db.batch()
                        contador_ops = 0
                        total_gravacoes = 0
                        administrador = st.session_state.get("nome_completo", "Administrador")

                        for uid in alvos_selecionados:
                            data_atual = dt_inicio
                            while data_atual <= dt_fim:
                                data_str_lote = data_atual.strftime("%Y-%m-%d")
                                mes_str_lote = data_atual.strftime("%m/%Y")

                                # Ocorrências administrativas são únicas por dia/categoria
                                # para impedir duplicidade acidental. Horas efetivamente
                                # trabalhadas recebem ID único e nunca sobrescrevem outro
                                # lançamento de Prática/Teoria/AAD do mesmo dia.
                                doc_id_lote = _doc_id_lancamento(
                                    uid,
                                    data_str_lote,
                                    categoria_final_lote,
                                    unico_por_dia=ausencia_final,
                                )
                                doc_ref = db.collection("pontos").document(doc_id_lote)

                                just_final = i_obs.strip() if i_obs and i_obs.strip() else "Registro Oficial (Coordenação)"

                                dados_lote = {
                                    "uid_residente": uid,
                                    "data_registro": data_str_lote,
                                    "mes_referencia": mes_str_lote,
                                    "categoria": categoria_final_lote,
                                    "tag": tag_final,
                                    "horas_computadas": horas_finais_decimais,
                                    "horarios_descritos": list(desc_horarios),
                                    "justificativa": just_final,
                                    "criado_em": firestore.SERVER_TIMESTAMP,
                                    "ultima_edicao": firestore.SERVER_TIMESTAMP,
                                    "criado_por": administrador,
                                    "modificado_por": administrador,
                                    "origem": "Painel ADM",
                                }

                                batch.set(doc_ref, dados_lote)
                                contador_ops += 1
                                total_gravacoes += 1

                                if contador_ops >= 450:
                                    batch.commit()
                                    batch = db.batch()
                                    contador_ops = 0

                                data_atual += timedelta(days=1)

                        if contador_ops > 0:
                            batch.commit()

                        # --------------------------------------------------
                        # 4) Invalida SOMENTE caches derivados
                        # --------------------------------------------------
                        for uid in set(alvos_selecionados):
                            invalidar_agregador(uid)
                        carregar_residentes_adm.clear()

                        st.session_state["flash_adm"] = (
                            f"✔️ {total_gravacoes} lançamento(s) gravado(s) com sucesso. "
                            "Os agregadores foram invalidados e recalculam automaticamente pelo motor 102."
                        )
                        st.rerun()

                    except ValueError as e:
                        st.error(f"⚠️ {e}")
                    except Exception as e:
                        st.error(f"Erro ao processar transação: {e}")
