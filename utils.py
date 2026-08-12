import streamlit as st
from firebase_config import db  # Importante para conseguirmos salvar no banco de dados

def aplicar_css():
    st.markdown("""
        <style>
            .stApp { background-color: #f4f7fb; }
            
            /* MATANDO A BARRA LATERAL DE VEZ */
            section[data-testid="stSidebar"] { display: none !important; }
            button[data-testid="collapsedControl"] { display: none !important; }
            
            .block-container { padding-top: 2rem; padding-bottom: 2rem; }
            
            /* Colunas virando Cards */
            [data-testid="column"] { background-color: #ffffff; border-radius: 16px; box-shadow: 0px 4px 15px rgba(0, 0, 0, 0.03); padding: 20px 25px 20px 25px !important; margin-bottom: 1rem; }
            
            .card-title { color: #111827; font-size: 1.1rem; font-weight: 600; font-family: 'Segoe UI', sans-serif; margin-bottom: 5px; }
            .big-number { font-size: 2.5rem; font-weight: 700; color: #111827; font-family: 'Segoe UI', sans-serif; display: inline-block; margin-right: 15px; }
            
            /* Estilizando os botões */
            div.stButton > button { border-radius: 8px; font-weight: 600; height: 48px; border: 1px solid #e5e7eb; transition: all 0.2s ease; }
            button[kind="primary"] { background-color: #16a34a !important; border-color: #16a34a !important; color: white !important; box-shadow: 0px 4px 10px rgba(22, 163, 74, 0.3); }
            button[kind="primary"]:hover { background-color: #15803d !important; border-color: #15803d !important; }
            
            .badge-success { background-color: #16a34a; color: white; padding: 4px 12px; border-radius: 6px; font-size: 0.8rem; font-weight: 600; }
            .badge-failed { background-color: #dc2626; color: white; padding: 4px 12px; border-radius: 6px; font-size: 0.8rem; font-weight: 600; }
            .badge-pending { background-color: #1e40af; color: white; padding: 4px 12px; border-radius: 6px; font-size: 0.8rem; font-weight: 600; }
        </style>
    """, unsafe_allow_html=True)

def checar_login():
    if 'logged_in' not in st.session_state or not st.session_state.logged_in:
        st.switch_page("app.py")

def mostrar_cabecalho(titulo_pagina=""):
    nome = st.session_state.get('nome_completo', 'Usuário não identificado')
    profissao = st.session_state.get('profissao', 'Profissão')
    lotacao = st.session_state.get('lotacao', 'A definir (Atualize)')
    preceptor = st.session_state.get('preceptor', 'A definir (Atualize)')

    # Ajustei a proporção para a logo encaixar com classe
    col_perfil, col_sair = st.columns([4.5, 1])
    
    with col_perfil:
        if st.session_state.get("editando_perfil", False):
            st.markdown("<h3 style='margin-bottom: 15px; color: #111827;'>✏️ Atualizar Dados</h3>", unsafe_allow_html=True)
            
            c_lot, c_prec = st.columns(2)
            nova_lotacao = c_lot.text_input("Sua Lotação (Ex: UBS Setor 08)", value="" if "A definir" in lotacao else lotacao)
            novo_preceptor = c_prec.text_input("Nome do Preceptor(a)", value="" if "A definir" in preceptor else preceptor)
            
            c_btn1, c_btn2, _ = st.columns([1, 1, 2])
            if c_btn1.button("💾 Salvar Dados", type="primary", use_container_width=True):
                db.collection("residentes").document(st.session_state.uid).update({
                    "lotacao": nova_lotacao or "A definir (Atualize)",
                    "preceptor": novo_preceptor or "A definir (Atualize)"
                })
                st.session_state.lotacao = nova_lotacao or "A definir (Atualize)"
                st.session_state.preceptor = novo_preceptor or "A definir (Atualize)"
                st.session_state.editando_perfil = False
                st.rerun()
                
            if c_btn2.button("❌ Cancelar", use_container_width=True):
                st.session_state.editando_perfil = False
                st.rerun()
                
        else:
            st.markdown(f"<h2 style='color: #111827; margin: 0 0 12px 0; font-size: 1.6rem;'>👋 Olá, {nome}</h2>", unsafe_allow_html=True)
            
            info_html = f"""
            <div style='display: flex; flex-wrap: wrap; gap: 15px; color: #4b5563; font-size: 0.95rem; align-items: center; margin-bottom: 15px;'>
                <div style='background-color: #dcfce7; color: #16a34a; padding: 5px 12px; border-radius: 8px; font-weight: 700; border: 1px solid #bbf7d0;'>{profissao}</div>
                <div style='display: flex; align-items: center; gap: 6px; background-color: #f3f4f6; padding: 5px 12px; border-radius: 8px;'><span style='font-size: 1.1rem;'>📍</span> <b>Lotação:</b> {lotacao}</div>
                <div style='display: flex; align-items: center; gap: 6px; background-color: #f3f4f6; padding: 5px 12px; border-radius: 8px;'><span style='font-size: 1.1rem;'>👨‍⚕️</span> <b>Preceptor(a):</b> {preceptor}</div>
            </div>
            """
            st.markdown(info_html, unsafe_allow_html=True)
            
            if st.button("✏️ Atualizar Lotação/Preceptor"):
                st.session_state.editando_perfil = True
                st.rerun()
            
    with col_sair:
        # 🌟 MÁGICA AQUI: Logo puxada direto da pasta, alinhada no topo do card direito
        st.image("logo residencia.png", use_container_width=True)
        st.markdown("<div style='margin-bottom: 5px;'></div>", unsafe_allow_html=True) # Respiro visual
        
        if st.button("🚪 Sair", type="secondary", use_container_width=True):
            st.session_state.clear()
            st.switch_page("app.py")