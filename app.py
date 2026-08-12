import streamlit as st
import requests
from firebase_config import db
from utils import aplicar_css

# 1. Configuração da Página
st.set_page_config(page_title="Login | MultiPonto", layout="centered")
aplicar_css()

# ==========================================================
# 2. INTERCEPTADOR DE TROCA DE SENHA (PRIMEIRO LOGIN)
# ==========================================================
if st.session_state.get("pedir_troca_senha", False):
    st.markdown("<h2 style='text-align: center; color: #111827; margin-top: 50px;'>🔒 Atualização de Segurança</h2>", unsafe_allow_html=True)
    st.info("Como este é o seu primeiro acesso, é obrigatório definir uma nova senha pessoal e intransferível.")
    
    nova_senha = st.text_input("Nova Senha", type="password", placeholder="Mínimo 6 caracteres")
    confirma_senha = st.text_input("Confirme a Nova Senha", type="password")
    
    st.write("")
    if st.button("Salvar Senha e Entrar", type="primary", use_container_width=True):
        if len(nova_senha) < 6:
            st.error("A senha deve ter no mínimo 6 caracteres.")
        elif nova_senha != confirma_senha:
            st.error("As senhas digitadas não coincidem.")
        else:
            try:
                chave_api = st.secrets["FIREBASE_WEB_API_KEY"]
                url_update = f"https://identitytoolkit.googleapis.com/v1/accounts:update?key={chave_api}"
                
                payload = {
                    "idToken": st.session_state.id_token,
                    "password": nova_senha,
                    "returnSecureToken": True
                }
                res = requests.post(url_update, json=payload).json()
                
                if "idToken" in res:
                    uid = st.session_state.uid
                    db.collection("residentes").document(uid).update({"primeiro_login": False})
                    
                    st.session_state.pedir_troca_senha = False
                    st.session_state.logged_in = True
                    st.switch_page("pages/1_🏠_Dashboard.py")
                else:
                    st.error("Erro ao atualizar a senha no servidor. Tente novamente.")
            except Exception as e:
                st.error(f"Erro de conexão ao tentar alterar a senha: {e}")
    
    st.stop() 


# ==========================================================
# 3. FLUXO NORMAL DE LOGIN E RECUPERAÇÃO DE SENHA
# ==========================================================
st.write("") # Dá um pequeno respiro no topo

# Cria 3 colunas invisíveis. A do meio é onde a logo vai ficar. 
# Se achar que a logo ficou muito grande, aumente os números das pontas (ex: [2, 1, 2]).
_, col_logo, _ = st.columns([0.75, 1, 0.75]) 
with col_logo:
    st.image("logo residencia.png", use_container_width=True)

# Diminuí o margin-top de 50px para 10px para o texto não ficar muito longe da logo
st.markdown("<h2 style='text-align: center; color: #111827; margin-top: 10px;'>Bem-vindo ao MultiPonto</h2>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #6b7280; margin-bottom: 30px;'>Faça login para acessar o seu painel</p>", unsafe_allow_html=True)

email = st.text_input("E-mail", placeholder="Digite seu e-mail")
senha = st.text_input("Senha", type="password", placeholder="Digite sua senha")

st.write("")

c1, c2 = st.columns(2)
with c1:
    btn_entrar = st.button("Entrar no Sistema", type="primary", use_container_width=True)
with c2:
    btn_esqueci_senha = st.button("Esqueci minha senha", type="secondary", use_container_width=True)

# ---- AÇÃO DE LOGIN ----
if btn_entrar:
    if email and senha:
        try:
            chave_api = st.secrets["FIREBASE_WEB_API_KEY"]
            url_login = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={chave_api}"
            
            dados_login = {"email": email.strip(), "password": senha, "returnSecureToken": True}
            resposta = requests.post(url_login, json=dados_login)
            resultado = resposta.json()
            
            if "localId" in resultado:
                uid_do_usuario = resultado["localId"]
                st.session_state.logged_in = True
                st.session_state.uid = uid_do_usuario
                st.session_state.id_token = resultado["idToken"]
                
                doc_ref = db.collection("residentes").document(uid_do_usuario)
                doc = doc_ref.get()
                
                if doc.exists:
                    ficha = doc.to_dict()
                    st.session_state.nome_completo = ficha.get("nome_completo", "Sem Nome")
                    st.session_state.profissao = ficha.get("profissao", "Sem Profissão")
                    st.session_state.lotacao = ficha.get("lotacao", "Não informada")
                    st.session_state.preceptor = ficha.get("preceptor", "Não informado")
                    st.session_state.user_role = ficha.get("perfil", "Residente")
                    
                    if ficha.get("primeiro_login", False):
                        st.session_state.pedir_troca_senha = True
                        st.rerun()
                    else:
                        st.switch_page("pages/1_🏠_Dashboard.py")
                else:
                    st.error("Conta autenticada, mas a sua ficha não foi encontrada no banco de dados.")
            else:
                erro = resultado.get("error", {}).get("message", "")
                if erro in ["INVALID_LOGIN_CREDENTIALS", "INVALID_PASSWORD", "EMAIL_NOT_FOUND"]:
                    st.error("⚠️ E-mail ou senha incorretos.")
                else:
                    st.error(f"Erro no login: {erro}")
        except Exception as e:
            st.error("⚠️ Erro de conexão. Verifique se o arquivo secrets.toml está configurado corretamente.")
    else:
        st.warning("⚠️ Por favor, preencha o e-mail e a senha.")

# ---- AÇÃO DE ESQUECI MINHA SENHA ----
if btn_esqueci_senha:
    if email:
        try:
            chave_api = st.secrets["FIREBASE_WEB_API_KEY"]
            url_reset = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={chave_api}"
            
            payload = {"requestType": "PASSWORD_RESET", "email": email.strip()}
            res = requests.post(url_reset, json=payload).json()
            
            if "email" in res:
                st.success(f"✅ Um link de redefinição de senha foi enviado para **{email}**. Verifique sua caixa de entrada e Spam.")
            else:
                erro_reset = res.get("error", {}).get("message", "")
                if erro_reset == "EMAIL_NOT_FOUND":
                    st.error("⚠️ E-mail não encontrado no nosso banco de dados.")
                else:
                    st.error(f"⚠️ Erro ao enviar e-mail: {erro_reset}")
        except Exception as e:
            st.error("⚠️ Erro de conexão com os servidores do Google.")
    else:
        st.warning("💡 Digite o seu e-mail no campo acima primeiro, depois clique em 'Esqueci minha senha'.")