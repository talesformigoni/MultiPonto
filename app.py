from pathlib import Path
import logging
import re

import requests
import streamlit as st

from firebase_config import db
from utils import aplicar_css


# ============================================================
# 1. CONFIGURAÇÃO DA PÁGINA
# ============================================================

st.set_page_config(
    page_title="MultiPonto | Acesso",
    page_icon="🩺",
    layout="centered",
    initial_sidebar_state="collapsed",
)

aplicar_css()


# ============================================================
# 2. CONFIGURAÇÕES GERAIS
# ============================================================

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
LOGO_PATH = BASE_DIR / "logo residencia.png"

PAGINA_DASHBOARD = "pages/1_🏠_Dashboard.py"
PAGINA_ADMIN = "pages/2_👑_Painel_ADM.py"
PAGINA_SOBRE = "pages/3_🔬_Sobre_o_Projeto.py"

TIMEOUT_FIREBASE = 10

# Preferencialmente configure ADMIN_UID no .streamlit/secrets.toml.
# O fallback mantém compatibilidade com o projeto atual.
ADMIN_UID = st.secrets.get(
    "ADMIN_UID",
    "CTEiPcg5JzLTDEL98eOWRiC5mJu1",
)

CHAVES_AUTH_SESSAO = [
    "logged_in",
    "uid",
    "id_token",
    "refresh_token",
    "email",
    "nome_completo",
    "profissao",
    "lotacao",
    "preceptor",
    "user_role",
    "status",
    "pedir_troca_senha",
]


# ============================================================
# 3. RENDERIZAÇÃO SEGURA DE HTML
# ============================================================

def render_html(html, **_kwargs):
    """
    Renderiza HTML sem deixar a indentação do Python virar
    bloco de código Markdown no Streamlit.

    A estratégia é propositalmente simples:
    - remove espaços no início/fim de cada linha;
    - remove linhas vazias;
    - envia o HTML como um bloco contínuo.

    Isso evita o problema clássico do Markdown interpretar
    HTML multilinha indentado como código.
    """
    bruto = str(html).strip()

    limpo = " ".join(
        linha.strip()
        for linha in bruto.splitlines()
        if linha.strip()
    )

    st.markdown(
        limpo,
        unsafe_allow_html=True,
    )


# ============================================================
# 4. CSS ESPECÍFICO DA TELA DE LOGIN
# ============================================================

render_html(
    """
    <style>
        /* =====================================================
           FUNDO / PÁGINA
        ===================================================== */

        .stApp {
            background:
                radial-gradient(circle at 15% 15%, rgba(22, 163, 74, 0.08), transparent 28%),
                radial-gradient(circle at 85% 85%, rgba(37, 99, 235, 0.07), transparent 30%),
                linear-gradient(135deg, #f8fafc 0%, #f2f7f5 45%, #f4f7fb 100%) !important;
        }

        .block-container {
            max-width: 1180px !important;
            padding-top: 2.4rem !important;
            padding-bottom: 2rem !important;
        }

        /* Tira elementos visuais desnecessários da moldura */
        #MainMenu {
            visibility: hidden;
        }

        footer {
            visibility: hidden;
        }


        /* =====================================================
           COLUNA CENTRAL
        ===================================================== */

        .st-key-login_wrapper,
        .st-key-primeiro_acesso_wrapper {
            max-width: 520px;
            margin: 0 auto;
        }


        /* =====================================================
           CARD PRINCIPAL
        ===================================================== */

        .st-key-login_card,
        .st-key-primeiro_acesso_card {
            background: rgba(255, 255, 255, 0.96);
            border: 1px solid rgba(226, 232, 240, 0.95) !important;
            border-radius: 22px !important;
            padding: 30px 34px 28px 34px !important;
            box-shadow:
                0 20px 45px rgba(15, 23, 42, 0.08),
                0 4px 12px rgba(15, 23, 42, 0.04);
            backdrop-filter: blur(8px);
        }


        /* =====================================================
           INPUTS
        ===================================================== */

        .st-key-login_card [data-testid="stTextInput"] input,
        .st-key-primeiro_acesso_card [data-testid="stTextInput"] input {
            border-radius: 10px !important;
            min-height: 48px !important;
            background-color: #f8fafc !important;
            border-color: #dbe3ec !important;
        }

        .st-key-login_card [data-testid="stTextInput"] input:focus,
        .st-key-primeiro_acesso_card [data-testid="stTextInput"] input:focus {
            border-color: #16a34a !important;
            box-shadow: 0 0 0 1px #16a34a !important;
        }

        .st-key-login_card label,
        .st-key-primeiro_acesso_card label {
            color: #374151 !important;
            font-weight: 650 !important;
        }


        /* =====================================================
           BOTÕES DO CARD
        ===================================================== */

        .st-key-login_card div[data-testid="stFormSubmitButton"] button,
        .st-key-primeiro_acesso_card div[data-testid="stFormSubmitButton"] button {
            width: 100% !important;
            min-height: 48px !important;
            border-radius: 10px !important;
            font-weight: 700 !important;
        }

        .st-key-login_card button[kind="primary"],
        .st-key-primeiro_acesso_card button[kind="primary"] {
            background: linear-gradient(135deg, #16a34a 0%, #15803d 100%) !important;
            border-color: #15803d !important;
            color: white !important;
            box-shadow: 0 8px 18px rgba(22, 163, 74, 0.20) !important;
        }

        .st-key-login_card button[kind="primary"]:hover,
        .st-key-primeiro_acesso_card button[kind="primary"]:hover {
            background: linear-gradient(135deg, #15803d 0%, #166534 100%) !important;
            border-color: #166534 !important;
            transform: translateY(-1px);
        }

        .st-key-login_card button[kind="secondary"],
        .st-key-primeiro_acesso_card button[kind="secondary"] {
            background: #ffffff !important;
            border: 1px solid #dbe3ec !important;
            color: #475569 !important;
            box-shadow: none !important;
        }

        .st-key-login_card button[kind="secondary"]:hover,
        .st-key-primeiro_acesso_card button[kind="secondary"]:hover {
            background: #f8fafc !important;
            border-color: #cbd5e1 !important;
            color: #1f2937 !important;
        }


        /* =====================================================
           BOTÃO "SOBRE"
        ===================================================== */

        .st-key-sobre_wrapper button {
            border: none !important;
            background: transparent !important;
            color: #64748b !important;
            min-height: 38px !important;
            font-size: 0.88rem !important;
            box-shadow: none !important;
        }

        .st-key-sobre_wrapper button:hover {
            color: #166534 !important;
            background: rgba(22, 163, 74, 0.05) !important;
            transform: none !important;
        }


        /* =====================================================
           MOBILE
        ===================================================== */

        @media (max-width: 700px) {
            .block-container {
                padding-top: 1rem !important;
                padding-left: 1rem !important;
                padding-right: 1rem !important;
            }

            .st-key-login_card,
            .st-key-primeiro_acesso_card {
                padding: 24px 20px 22px 20px !important;
                border-radius: 18px !important;
            }
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 5. HELPERS DE SESSÃO E FIREBASE AUTH
# ============================================================

def _limpar_estado_autenticacao():
    """
    Remove apenas dados relacionados à autenticação.
    """
    for chave in CHAVES_AUTH_SESSAO:
        st.session_state.pop(chave, None)


def _firebase_api_key():
    """
    Recupera a chave Web API do Firebase.
    """
    try:
        chave = st.secrets["FIREBASE_WEB_API_KEY"]
    except Exception:
        logger.exception("FIREBASE_WEB_API_KEY não configurada.")
        raise RuntimeError("firebase_api_key_ausente")

    if not chave:
        raise RuntimeError("firebase_api_key_ausente")

    return chave


def _firebase_auth_request(endpoint, payload):
    """
    Centraliza chamadas REST ao Firebase Authentication.

    Retorna:
        (resultado_dict, erro_conexao)
    """
    try:
        chave_api = _firebase_api_key()

        url = (
            "https://identitytoolkit.googleapis.com/v1/"
            f"{endpoint}?key={chave_api}"
        )

        resposta = requests.post(
            url,
            json=payload,
            timeout=TIMEOUT_FIREBASE,
        )

        try:
            resultado = resposta.json()
        except ValueError:
            logger.error(
                "Firebase retornou resposta não JSON. "
                "endpoint=%s status=%s",
                endpoint,
                resposta.status_code,
            )
            return {}, True

        if resposta.status_code >= 500:
            logger.error(
                "Firebase indisponível. endpoint=%s status=%s",
                endpoint,
                resposta.status_code,
            )
            return resultado, True

        return resultado, False

    except requests.Timeout:
        logger.warning(
            "Timeout ao acessar Firebase Auth. endpoint=%s",
            endpoint,
        )
        return {}, True

    except requests.ConnectionError:
        logger.warning(
            "Falha de conexão com Firebase Auth. endpoint=%s",
            endpoint,
        )
        return {}, True

    except requests.RequestException:
        logger.exception(
            "Erro HTTP ao acessar Firebase Auth. endpoint=%s",
            endpoint,
        )
        return {}, True

    except RuntimeError:
        return {}, True

    except Exception:
        logger.exception(
            "Erro inesperado ao acessar Firebase Auth. endpoint=%s",
            endpoint,
        )
        return {}, True


def _normalizar_email(email):
    return str(email or "").strip().lower()


def _validar_nova_senha(senha):
    """
    Regra de primeiro acesso:
    - mínimo 8 caracteres;
    - ao menos uma letra;
    - ao menos um número.
    """
    senha = str(senha or "")

    if len(senha) < 8:
        return False, "A nova senha deve ter no mínimo 8 caracteres."

    if not re.search(r"[A-Za-zÀ-ÿ]", senha):
        return False, "A nova senha deve conter pelo menos uma letra."

    if not re.search(r"\d", senha):
        return False, "A nova senha deve conter pelo menos um número."

    return True, ""


def _carregar_ficha_residente(uid):
    """
    Busca a ficha do residente após a autenticação no Firebase Auth.
    """
    try:
        doc = db.collection("residentes").document(uid).get()

        if not doc.exists:
            return None

        return doc.to_dict() or {}

    except Exception:
        logger.exception(
            "Erro ao carregar ficha do residente. uid=%s",
            uid,
        )
        raise


def _preencher_sessao_residente(uid, email, ficha, tokens):
    """
    Preenche a sessão APÓS validar ficha e status.
    """
    st.session_state["uid"] = uid
    st.session_state["email"] = email
    st.session_state["id_token"] = tokens.get("idToken")

    if tokens.get("refreshToken"):
        st.session_state["refresh_token"] = tokens.get(
            "refreshToken"
        )

    st.session_state["nome_completo"] = ficha.get(
        "nome_completo",
        "Sem Nome",
    )
    st.session_state["profissao"] = ficha.get(
        "profissao",
        "Sem Profissão",
    )
    st.session_state["lotacao"] = ficha.get(
        "lotacao",
        "A definir (Atualize)",
    )
    st.session_state["preceptor"] = ficha.get(
        "preceptor",
        "A definir (Atualize)",
    )
    st.session_state["user_role"] = ficha.get(
        "perfil",
        "Residente",
    )
    st.session_state["status"] = ficha.get(
        "status",
        "Ativo",
    )


def _finalizar_login_admin(uid, email, resultado):
    """
    Cria a sessão administrativa após autenticação válida.
    """
    st.session_state["uid"] = uid
    st.session_state["email"] = email
    st.session_state["id_token"] = resultado.get("idToken")

    if resultado.get("refreshToken"):
        st.session_state["refresh_token"] = resultado.get(
            "refreshToken"
        )

    st.session_state["nome_completo"] = (
        "Coordenação Multiprofissional"
    )
    st.session_state["profissao"] = "Administração"
    st.session_state["lotacao"] = "Coordenação"
    st.session_state["preceptor"] = "Não se aplica"
    st.session_state["user_role"] = "Admin"
    st.session_state["status"] = "Ativo"
    st.session_state["pedir_troca_senha"] = False
    st.session_state["logged_in"] = True

    st.switch_page(PAGINA_ADMIN)


def _processar_login(email, senha):
    """
    1. autentica no Firebase;
    2. identifica ADM ou residente;
    3. valida ficha/status;
    4. trata primeiro acesso;
    5. só então libera a sessão.
    """
    email = _normalizar_email(email)

    if not email or not senha:
        st.warning(
            "⚠️ Preencha o e-mail e a senha para continuar."
        )
        return

    payload = {
        "email": email,
        "password": senha,
        "returnSecureToken": True,
    }

    resultado, erro_conexao = _firebase_auth_request(
        "accounts:signInWithPassword",
        payload,
    )

    if erro_conexao:
        st.error(
            "⚠️ Não foi possível conectar ao serviço de "
            "autenticação neste momento. Tente novamente."
        )
        return

    uid = resultado.get("localId")

    if not uid:
        erro = (
            resultado
            .get("error", {})
            .get("message", "")
        )

        logger.info(
            "Login recusado pelo Firebase. erro=%s",
            erro,
        )

        if erro in {
            "INVALID_LOGIN_CREDENTIALS",
            "INVALID_PASSWORD",
            "EMAIL_NOT_FOUND",
        }:
            st.error("⚠️ E-mail ou senha incorretos.")

        elif erro == "USER_DISABLED":
            st.error(
                "⚠️ Esta conta está desativada. "
                "Entre em contato com a Coordenação."
            )

        elif erro.startswith("TOO_MANY_ATTEMPTS_TRY_LATER"):
            st.error(
                "⚠️ Muitas tentativas de acesso. "
                "Aguarde alguns minutos e tente novamente."
            )

        else:
            st.error(
                "⚠️ Não foi possível realizar o login. "
                "Confira seus dados e tente novamente."
            )

        return

    # --------------------------------------------------------
    # ADMINISTRADOR
    # --------------------------------------------------------

    if uid == ADMIN_UID:
        _finalizar_login_admin(
            uid,
            email,
            resultado,
        )
        return

    # --------------------------------------------------------
    # RESIDENTE
    # --------------------------------------------------------

    try:
        ficha = _carregar_ficha_residente(uid)
    except Exception:
        _limpar_estado_autenticacao()

        st.error(
            "⚠️ Foi possível autenticar sua conta, mas não foi "
            "possível acessar sua ficha neste momento. "
            "Tente novamente em instantes."
        )
        return

    if ficha is None:
        _limpar_estado_autenticacao()

        st.error(
            "⚠️ Sua conta foi autenticada, mas não há uma ficha "
            "ativa vinculada a ela no MultiPonto. "
            "Entre em contato com a Coordenação."
        )
        return

    status = str(
        ficha.get("status", "Ativo")
    ).strip()

    if status != "Ativo":
        _limpar_estado_autenticacao()

        st.error(
            "⛔ Seu acesso ao MultiPonto está inativo. "
            "Se acredita que isso ocorreu por engano, "
            "entre em contato com a Coordenação."
        )

        logger.info(
            "Login bloqueado por status. uid=%s status=%s",
            uid,
            status,
        )
        return

    _preencher_sessao_residente(
        uid,
        email,
        ficha,
        resultado,
    )

    if ficha.get("primeiro_login", False):
        st.session_state["pedir_troca_senha"] = True
        st.session_state["logged_in"] = False
        st.rerun()
        return

    st.session_state["pedir_troca_senha"] = False
    st.session_state["logged_in"] = True

    st.switch_page(PAGINA_DASHBOARD)


def _processar_troca_senha(nova_senha, confirma_senha):
    """
    Troca obrigatória de senha no primeiro acesso.
    """
    valida, mensagem = _validar_nova_senha(
        nova_senha
    )

    if not valida:
        st.error(mensagem)
        return

    if nova_senha != confirma_senha:
        st.error(
            "As senhas digitadas não coincidem."
        )
        return

    uid = st.session_state.get("uid")
    id_token = st.session_state.get("id_token")

    if not uid or not id_token:
        _limpar_estado_autenticacao()

        st.error(
            "Sua sessão de primeiro acesso expirou. "
            "Faça login novamente."
        )
        return

    payload = {
        "idToken": id_token,
        "password": nova_senha,
        "returnSecureToken": True,
    }

    resultado, erro_conexao = _firebase_auth_request(
        "accounts:update",
        payload,
    )

    if erro_conexao:
        st.error(
            "⚠️ Não foi possível atualizar a senha neste "
            "momento. Tente novamente."
        )
        return

    novo_token = resultado.get("idToken")

    if not novo_token:
        erro = (
            resultado
            .get("error", {})
            .get("message", "")
        )

        logger.warning(
            "Falha ao trocar senha. uid=%s erro=%s",
            uid,
            erro,
        )

        if erro in {
            "INVALID_ID_TOKEN",
            "TOKEN_EXPIRED",
            "CREDENTIAL_TOO_OLD_LOGIN_AGAIN",
        }:
            _limpar_estado_autenticacao()

            st.error(
                "Sua sessão expirou. "
                "Faça login novamente para definir a nova senha."
            )

        elif erro == "WEAK_PASSWORD":
            st.error(
                "A senha escolhida não atende aos requisitos "
                "de segurança."
            )

        else:
            st.error(
                "Não foi possível atualizar a senha. "
                "Tente novamente."
            )

        return

    try:
        db.collection(
            "residentes"
        ).document(uid).update(
            {
                "primeiro_login": False,
            }
        )

    except Exception:
        logger.exception(
            "Senha alterada, mas falhou atualização "
            "de primeiro_login. uid=%s",
            uid,
        )

        st.error(
            "A senha foi alterada, mas não foi possível concluir "
            "a atualização do seu cadastro. "
            "Tente fazer login novamente."
        )

        _limpar_estado_autenticacao()
        return

    st.session_state["id_token"] = novo_token

    if resultado.get("refreshToken"):
        st.session_state["refresh_token"] = resultado.get(
            "refreshToken"
        )

    st.session_state["pedir_troca_senha"] = False
    st.session_state["logged_in"] = True

    st.switch_page(PAGINA_DASHBOARD)


def _processar_reset_senha(email):
    """
    Solicita e-mail de redefinição sem revelar se a conta existe.
    """
    email = _normalizar_email(email)

    if not email:
        st.warning(
            "💡 Digite o seu e-mail acima antes de solicitar "
            "a redefinição de senha."
        )
        return

    payload = {
        "requestType": "PASSWORD_RESET",
        "email": email,
    }

    resultado, erro_conexao = _firebase_auth_request(
        "accounts:sendOobCode",
        payload,
    )

    if erro_conexao:
        st.error(
            "⚠️ Não foi possível solicitar a recuperação "
            "de senha neste momento. Tente novamente."
        )
        return

    erro = (
        resultado
        .get("error", {})
        .get("message", "")
    )

    if erro and erro != "EMAIL_NOT_FOUND":
        logger.info(
            "Firebase recusou solicitação de reset. erro=%s",
            erro,
        )

        if erro.startswith("TOO_MANY_ATTEMPTS_TRY_LATER"):
            st.warning(
                "⚠️ Muitas solicitações foram feitas. "
                "Aguarde alguns minutos antes de tentar novamente."
            )
            return

    st.success(
        "✅ Se existir uma conta vinculada a este e-mail, "
        "as instruções de redefinição serão enviadas. "
        "Verifique também a pasta de Spam."
    )


# ============================================================
# 6. REDIRECIONAMENTO DE SESSÃO JÁ AUTENTICADA
# ============================================================

if (
    st.session_state.get("logged_in", False)
    and not st.session_state.get("pedir_troca_senha", False)
):
    if st.session_state.get("user_role") == "Admin":
        st.switch_page(PAGINA_ADMIN)
    else:
        st.switch_page(PAGINA_DASHBOARD)


# ============================================================
# 7. PRIMEIRO ACESSO / TROCA OBRIGATÓRIA DE SENHA
# ============================================================

if st.session_state.get("pedir_troca_senha", False):

    with st.container(key="primeiro_acesso_wrapper"):

        with st.container(
            border=True,
            key="primeiro_acesso_card",
        ):
            if LOGO_PATH.exists():
                c1, c_logo, c2 = st.columns(
                    [1.2, 1, 1.2]
                )
                with c_logo:
                    st.image(
                        str(LOGO_PATH),
                        use_container_width=True,
                    )

            render_html(
                """
                <div style="text-align:center; margin-top:2px;">
                    <div style="
                        display:inline-block;
                        background:#ecfdf5;
                        color:#166534;
                        border:1px solid #bbf7d0;
                        border-radius:999px;
                        padding:5px 11px;
                        font-size:0.72rem;
                        font-weight:800;
                        letter-spacing:0.6px;
                        text-transform:uppercase;
                        margin-bottom:12px;
                    ">
                        Primeiro acesso
                    </div>

                    <h2 style="
                        color:#0f172a;
                        margin:0;
                        font-size:1.8rem;
                        font-weight:800;
                    ">
                        Crie sua senha pessoal
                    </h2>

                    <p style="
                        color:#64748b;
                        margin:8px auto 22px auto;
                        font-size:0.94rem;
                        line-height:1.5;
                        max-width:390px;
                    ">
                        Antes de acessar o MultiPonto, defina uma senha
                        pessoal e intransferível.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            with st.form(
                "form_primeiro_acesso",
                clear_on_submit=False,
                border=False,
            ):
                nova_senha = st.text_input(
                    "Nova senha",
                    type="password",
                    placeholder="Mínimo 8 caracteres",
                )

                confirma_senha = st.text_input(
                    "Confirmar nova senha",
                    type="password",
                    placeholder="Digite novamente",
                )

                st.caption(
                    "Use pelo menos 8 caracteres, incluindo uma letra e um número."
                )

                st.write("")

                btn_salvar_senha = st.form_submit_button(
                    "🔐 Salvar senha e acessar",
                    type="primary",
                    use_container_width=True,
                )

            if btn_salvar_senha:
                _processar_troca_senha(
                    nova_senha,
                    confirma_senha,
                )

            if st.button(
                "← Voltar para o login",
                type="secondary",
                use_container_width=True,
                key="btn_cancelar_primeiro_acesso",
            ):
                _limpar_estado_autenticacao()
                st.rerun()

            render_html(
                """
                <div style="
                    margin-top:18px;
                    padding-top:14px;
                    border-top:1px solid #eef2f7;
                    text-align:center;
                    color:#94a3b8;
                    font-size:0.78rem;
                ">
                    🔒 Sua senha é processada pelo serviço seguro de autenticação.
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.stop()


# ============================================================
# 8. TELA NORMAL DE LOGIN
# ============================================================

with st.container(key="login_wrapper"):

    # --------------------------------------------------------
    # CARD CENTRAL
    # --------------------------------------------------------

    with st.container(
        border=True,
        key="login_card",
    ):
        # LOGO
        if LOGO_PATH.exists():
            c_logo_esq, c_logo, c_logo_dir = st.columns(
                [1.15, 1, 1.15]
            )

            with c_logo:
                st.image(
                    str(LOGO_PATH),
                    use_container_width=True,
                )

        # TÍTULO
        render_html(
            """
            <div style="text-align:center; margin-top:4px;">
                <div style="
                    display:inline-flex;
                    align-items:center;
                    gap:6px;
                    background:#ecfdf5;
                    color:#166534;
                    border:1px solid #bbf7d0;
                    border-radius:999px;
                    padding:5px 11px;
                    font-size:0.70rem;
                    font-weight:800;
                    letter-spacing:0.7px;
                    text-transform:uppercase;
                    margin-bottom:12px;
                ">
                    🩺 Residência Multiprofissional
                </div>

                <h1 style="
                    color:#0f172a;
                    margin:0;
                    font-size:2rem;
                    line-height:1.2;
                    font-weight:850;
                    letter-spacing:-0.5px;
                ">
                    Bem-vindo ao MultiPonto
                </h1>

                <p style="
                    color:#64748b;
                    margin:9px auto 24px auto;
                    font-size:0.95rem;
                    line-height:1.5;
                    max-width:390px;
                ">
                    Controle de carga horária da Residência
                    Multiprofissional em Saúde da Família
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # FORM LOGIN / RESET
        with st.form(
            "form_login",
            clear_on_submit=False,
            border=False,
        ):
            email = st.text_input(
                "E-mail institucional",
                placeholder="nome@exemplo.com",
                key="login_email",
            )

            senha = st.text_input(
                "Senha",
                type="password",
                placeholder="Digite sua senha",
                key="login_senha",
            )

            st.write("")

            btn_entrar = st.form_submit_button(
                "Entrar no MultiPonto",
                type="primary",
                use_container_width=True,
            )

            btn_esqueci_senha = st.form_submit_button(
                "Esqueci minha senha",
                type="secondary",
                use_container_width=True,
            )

        # AÇÕES
        if btn_entrar:
            _processar_login(
                email,
                senha,
            )

        if btn_esqueci_senha:
            _processar_reset_senha(email)

        # RODAPÉ DO CARD
        render_html(
            """
            <div style="
                margin-top:20px;
                padding-top:16px;
                border-top:1px solid #eef2f7;
                text-align:center;
            ">
                <div style="
                    color:#64748b;
                    font-size:0.78rem;
                    line-height:1.5;
                ">
                    🔒 Acesso restrito a residentes e coordenação
                </div>

                <div style="
                    color:#94a3b8;
                    font-size:0.72rem;
                    margin-top:4px;
                ">
                    Residência Multiprofissional em Saúde da Família • Buritis-RO
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ============================================================
# 9. SOBRE O PROJETO
# ============================================================

render_html(
    "<div style='height:14px;'></div>",
    unsafe_allow_html=True,
)

with st.container(key="sobre_wrapper"):

    col_espaco1, col_btn_sobre, col_espaco2 = st.columns(
        [1, 1.8, 1]
    )

    with col_btn_sobre:
        if st.button(
            "🔬 Sobre o Projeto e Autoria",
            type="tertiary",
            use_container_width=True,
            key="btn_sobre_projeto",
        ):
            st.switch_page(PAGINA_SOBRE)
