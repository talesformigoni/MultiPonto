import streamlit as st
from datetime import date, datetime
from zoneinfo import ZoneInfo
from firebase_admin import firestore
from utils import aplicar_css, checar_login, mostrar_cabecalho
from firebase_config import db  # <--- IMPORTANTE: Importando a conexão com o banco

st.set_page_config(page_title="Lançar Horas | MultiPonto", layout="wide")
checar_login()
aplicar_css()

# ==========================================
# MOTORES INTELIGENTES (CÁLCULO E FUSO HORÁRIO)
# ==========================================
def preencher_hora_atual(chave_h, chave_m):
    """Pega a hora exata pelo fuso oficial de Rondônia"""
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

# AQUI ESTÁ A FUNÇÃO QUE VOCÊ PERGUNTOU:
def calcular_saldo_horas(entrada_str, saida_str):
    """Calcula a diferença entre duas strings de tempo (HH:MM) e retorna em decimal (float)"""
    if not entrada_str or not saida_str:
        return 0.0
    formato = "%H:%M"
    td_entrada = datetime.strptime(entrada_str, formato)
    td_saida = datetime.strptime(saida_str, formato)
    
    diferenca = td_saida - td_entrada
    segundos_totais = diferenca.total_seconds()
    
    # Se a saída for menor que a entrada (ex: virou a madrugada)
    if segundos_totais < 0:
        segundos_totais += 24 * 3600
        
    return round(segundos_totais / 3600, 2)

# ==========================================
# CÓDIGO DA PÁGINA
# ==========================================
data_inicio = date(2026, 3, 9) # Data de início da sua residência
data_hoje = date.today()

mostrar_cabecalho("📝 Lançar Horas")

col_form, col_dicas = st.columns([2, 1]) 

with col_form:
    st.markdown("<div class='card-title' style='margin-bottom: 20px;'>Preencha os dados da atividade</div>", unsafe_allow_html=True)
    
    data_ponto = st.date_input("Data do Registro", value=data_hoje, min_value=data_inicio, max_value=data_hoje, format="DD/MM/YYYY")
    categoria = st.selectbox("Categoria da Ocorrência", ["Prática", "Teórica", "Teórico-prática", "Ausência justificada", "Falta", "Férias", "Licença"])
    
    st.markdown("<hr style='margin: 15px 0px; border-color: #f3f4f6;'>", unsafe_allow_html=True)
    
    st.markdown("<div class='card-title' style='font-size: 1rem;'>⏱️ Horários (Entrada - Saída)</div>", unsafe_allow_html=True)
    st.markdown("<p style='color: #6b7280; font-size: 0.85rem;'>Digite ou use o botão para puxar a hora automática do celular/PC.</p>", unsafe_allow_html=True)
    
    # --- 1º EXPEDIENTE ---
    st.markdown("**1º Expediente**")
    c1, c2, c3, c4 = st.columns(4)
    h_e1 = c1.text_input("Entrada (HH)", placeholder="07", max_chars=2, key="he1")
    m_e1 = c2.text_input("Min (MM)", placeholder="00", max_chars=2, key="me1")
    h_s1 = c3.text_input("Saída (HH)", placeholder="12", max_chars=2, key="hs1")
    m_s1 = c4.text_input("Min (MM)", placeholder="00", max_chars=2, key="ms1")
    
    b1, b2 = st.columns(2)
    b1.button("🕒 Puxar Hora Atual", on_click=preencher_hora_atual, args=("he1", "me1"), key="btn_e1")
    b2.button("🕒 Puxar Hora Atual", on_click=preencher_hora_atual, args=("hs1", "ms1"), key="btn_s1")
    st.write("") 
    
    # --- 2º EXPEDIENTE ---
    st.markdown("**2º Expediente**")
    c5, c6, c7, c8 = st.columns(4)
    h_e2 = c5.text_input("Entrada (HH)", placeholder="13", max_chars=2, key="he2")
    m_e2 = c6.text_input("Min (MM)", placeholder="30", max_chars=2, key="me2")
    h_s2 = c7.text_input("Saída (HH)", placeholder="17", max_chars=2, key="hs2")
    m_s2 = c8.text_input("Min (MM)", placeholder="30", max_chars=2, key="ms2")
    
    b3, b4 = st.columns(2)
    b3.button("🕒 Puxar Hora Atual", on_click=preencher_hora_atual, args=("he2", "me2"), key="btn_e2")
    b4.button("🕒 Puxar Hora Atual", on_click=preencher_hora_atual, args=("hs2", "ms2"), key="btn_s2")
    st.write("")
    
    # --- 3º EXPEDIENTE ---
    st.markdown("**3º Expediente (Opcional - Ex: Terça à noite)**")
    c9, c10, c11, c12 = st.columns(4)
    h_e3 = c9.text_input("Entrada (HH)", placeholder="--", max_chars=2, key="he3")
    m_e3 = c10.text_input("Min (MM)", placeholder="--", max_chars=2, key="me3")
    h_s3 = c11.text_input("Saída (HH)", placeholder="--", max_chars=2, key="hs3")
    m_s3 = c12.text_input("Min (MM)", placeholder="--", max_chars=2, key="ms3")
    
    b5, b6 = st.columns(2)
    b5.button("🕒 Puxar Hora Atual", on_click=preencher_hora_atual, args=("he3", "me3"), key="btn_e3")
    b6.button("🕒 Puxar Hora Atual", on_click=preencher_hora_atual, args=("hs3", "ms3"), key="btn_s3")
    
    st.markdown("<hr style='margin: 15px 0px; border-color: #f3f4f6;'>", unsafe_allow_html=True)
    
    observacao = st.text_area("Observações / Justificativa", placeholder="Escreva aqui se necessário...")
    
    st.write("") 
    if st.button("Gravar Registro no Firebase", type="primary", use_container_width=True):
        
        horarios_formatados = []
        total_do_dia = 0.0 # Começa a somar as horas do dia aqui
        erro_no_relogio = False
        
        for h_ent, m_ent, h_sai, m_sai in [(h_e1, m_e1, h_s1, m_s1), (h_e2, m_e2, h_s2, m_s2), (h_e3, m_e3, h_s3, m_s3)]:
            ent_ok = processar_hora_separada(h_ent, m_ent)
            sai_ok = processar_hora_separada(h_sai, m_sai)
            
            if ent_ok == "ERRO" or sai_ok == "ERRO":
                erro_no_relogio = True
            elif ent_ok and sai_ok:
                horarios_formatados.append(f"{ent_ok} às {sai_ok}")
                # Faz a matemática usando a função nova
                total_do_dia += calcular_saldo_horas(ent_ok, sai_ok) 
        
        categorias_ausencia = ["Ausência justificada", "Falta", "Licença"]
        
        if erro_no_relogio:
            st.error("⚠️ Erro nos horários! Verifique as horas e minutos informados.")
        elif categoria in categorias_ausencia and observacao.strip() == "":
            st.error(f"⚠️ Para registrar '{categoria}', é obrigatório preencher a Justificativa.")
        else:
            # ========================================================
            # AQUI ESTÁ O SEU CÓDIGO DE SALVAR NO BANCO DE DADOS
            # ========================================================
            try:
                dados_do_ponto = {
                    "uid_residente": st.session_state.uid,              
                    "data_registro": data_ponto.isoformat(),            
                    "mes_referencia": data_ponto.strftime("%m/%Y"),     
                    "categoria": categoria,                             
                    "horas_computadas": total_do_dia,                   
                    "horarios_descritos": horarios_formatados, # Salva o texto "07:00 às 12:00" para ver na tela depois
                    "justificativa": observacao,
                    "registrado_em": firestore.SERVER_TIMESTAMP # Carimbo automático de quando o clique ocorreu
                }
                
                # Manda para a nuvem na coleção 'pontos'
                db.collection("pontos").add(dados_do_ponto)
                
                st.success(f"✅ Registro ({categoria}) gravado com sucesso para o dia {data_ponto.strftime('%d/%m/%Y')}!")
                if total_do_dia > 0:
                    st.info(f"🕒 **Carga Horária Computada:** {total_do_dia} horas ({', '.join(horarios_formatados)})")
            
            except Exception as e:
                st.error(f"Erro ao salvar no banco de dados: {e}")

with col_dicas:
    st.markdown("<div class='card-title' style='margin-bottom: 15px;'>💡 Dicas de Preenchimento</div>", unsafe_allow_html=True)
    st.info("**Ponto Automático:**\nChegou no posto? Clique em `🕒 Puxar Hora Atual` na Entrada. Vai embora? Clique na Saída. O sistema faz o resto.")
    st.warning("**Abonos e Licenças:**\nSe tirar atestado do dia todo, deixe as horas em branco. Selecione a categoria e justifique.")