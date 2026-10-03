from pathlib import Path
from html import escape
import logging

import streamlit as st

from firebase_config import db


# ============================================================
# CONFIGURAÇÕES GERAIS
# ============================================================

PAGINA_LOGIN = "app.py"

TEXTO_LOTACAO_PADRAO = "A definir (Atualize)"
TEXTO_PRECEPTOR_PADRAO = "A definir (Atualize)"

BASE_DIR = Path(__file__).resolve().parent
LOGO_PATH = BASE_DIR / "logo residencia.png"

logger = logging.getLogger(__name__)


# ============================================================
# CSS GLOBAL
# ============================================================

def aplicar_css():
    """
    Aplica estilos globais do MultiPonto.

    Importante:
    - Não estiliza todas as st.columns() como cards.
    - Mantém classes utilitárias já usadas pelo projeto.
    - Evita interferir em formulários, filtros e layouts internos.
    """

    st.markdown(
        """
        <style>
            /* ==================================================
               APP
            ================================================== */

            .stApp {
                background-color: #f4f7fb;
            }

            .block-container {
                padding-top: 2rem;
                padding-bottom: 2rem;
            }


            /* ==================================================
               SIDEBAR
            ================================================== */

            section[data-testid="stSidebar"] {
                display: none !important;
            }

            button[data-testid="collapsedControl"] {
                display: none !important;
            }


            /* ==================================================
               COMPONENTES VISUAIS
            ================================================== */

            .card-title {
                color: #111827;
                font-size: 1.1rem;
                font-weight: 600;
                font-family: "Segoe UI", sans-serif;
                margin-bottom: 5px;
            }

            .big-number {
                font-size: 2.5rem;
                font-weight: 700;
                color: #111827;
                font-family: "Segoe UI", sans-serif;
                display: inline-block;
                margin-right: 15px;
            }

            .multiponto-card {
                background-color: #ffffff;
                border-radius: 16px;
                box-shadow: 0 4px 15px rgba(0, 0, 0, 0.03);
                padding: 20px 25px;
                margin-bottom: 1rem;
                border: 1px solid #eef2f7;
            }


            /* ==================================================
               BOTÕES
            ================================================== */

            div.stButton > button {
                border-radius: 8px;
                font-weight: 600;
                min-height: 48px;
                border: 1px solid #e5e7eb;
                transition:
                    background-color 0.2s ease,
                    border-color 0.2s ease,
                    box-shadow 0.2s ease,
                    transform 0.2s ease;
            }

            div.stButton > button:hover {
                transform: translateY(-1px);
            }

            div.stButton > button[kind="primary"] {
                background-color: #16a34a !important;
                border-color: #16a34a !important;
                color: #ffffff !important;
                box-shadow: 0 4px 10px rgba(22, 163, 74, 0.25);
            }

            div.stButton > button[kind="primary"]:hover {
                background-color: #15803d !important;
                border-color: #15803d !important;
            }


            /* ==================================================
               BADGES
            ================================================== */

            .badge-success {
                background-color: #16a34a;
                color: #ffffff;
                padding: 4px 12px;
                border-radius: 6px;
                font-size: 0.8rem;
                font-weight: 600;
            }

            .badge-failed {
                background-color: #dc2626;
                color: #ffffff;
                padding: 4px 12px;
                border-radius: 6px;
                font-size: 0.8rem;
                font-weight: 600;
            }

            .badge-pending {
                background-color: #1e40af;
                color: #ffffff;
                padding: 4px 12px;
                border-radius: 6px;
                font-size: 0.8rem;
                font-weight: 600;
            }


            /* ==================================================
               RESPONSIVIDADE
            ================================================== */

            @media (max-width: 768px) {
                .block-container {
                    padding-top: 1rem;
                    padding-left: 1rem;
                    padding-right: 1rem;
                }

                .big-number {
                    font-size: 2rem;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# AUTENTICAÇÃO
# ============================================================

def checar_login():
    """
    Bloqueia o acesso a páginas protegidas caso a sessão
    não esteja autenticada ou não possua UID.
    """

    logged_in = bool(st.session_state.get("logged_in", False))
    uid = st.session_state.get("uid")

    if not logged_in or not uid:
        st.switch_page(PAGINA_LOGIN)
        st.stop()


def fazer_logout():
    """
    Limpa completamente a sessão atual e retorna ao login.
    """

    st.session_state.clear()
    st.switch_page(PAGINA_LOGIN)


# ============================================================
# HELPERS
# ============================================================

def _valor_perfil(chave, padrao):
    """
    Recupera um valor da sessão, remove espaços extras
    e aplica um valor padrão caso esteja vazio.
    """

    valor = st.session_state.get(chave)

    if valor is None:
        return padrao

    valor = str(valor).strip()
    return valor if valor else padrao


def _seguro_html(valor):
    """
    Escapa valores dinâmicos antes de inseri-los em HTML.
    Evita que conteúdo vindo do Firebase seja interpretado
    como marcação HTML.
    """

    return escape(str(valor or ""), quote=True)


def _normalizar_texto_perfil(valor, padrao):
    """
    Normaliza entradas editáveis do perfil antes de gravar
    no Firebase.
    """

    valor = str(valor or "").strip()
    return valor if valor else padrao


# ============================================================
# CABEÇALHO DO RESIDENTE
# ============================================================

def mostrar_cabecalho(titulo_pagina=""):
    """
    Renderiza o cabeçalho padrão do residente.

    Mantém compatibilidade com as chamadas já existentes:
        mostrar_cabecalho()
        mostrar_cabecalho("Título opcional")
    """

    nome = _valor_perfil(
        "nome_completo",
        "Usuário não identificado",
    )

    profissao = _valor_perfil(
        "profissao",
        "Profissão",
    )

    lotacao = _valor_perfil(
        "lotacao",
        TEXTO_LOTACAO_PADRAO,
    )

    preceptor = _valor_perfil(
        "preceptor",
        TEXTO_PRECEPTOR_PADRAO,
    )

    uid = st.session_state.get("uid")

    # --------------------------------------------------------
    # TÍTULO OPCIONAL
    # --------------------------------------------------------

    if titulo_pagina:
        titulo_html = _seguro_html(titulo_pagina)

        st.markdown(
            f"""
            <div style="
                color: #6b7280;
                font-size: 0.85rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin-bottom: 8px;
            ">{titulo_html}</div>
            """,
            unsafe_allow_html=True,
        )

    # --------------------------------------------------------
    # LAYOUT PRINCIPAL
    # --------------------------------------------------------

    col_perfil, col_sair = st.columns(
        [4.5, 1],
        gap="large",
    )

    # ========================================================
    # PERFIL
    # ========================================================

    with col_perfil:

        if st.session_state.get("editando_perfil", False):

            st.markdown(
                """
                <h3 style="
                    margin-bottom: 15px;
                    color: #111827;
                ">✏️ Atualizar Dados</h3>
                """,
                unsafe_allow_html=True,
            )

            c_lot, c_prec = st.columns(2)

            valor_lotacao = (
                ""
                if lotacao == TEXTO_LOTACAO_PADRAO
                else lotacao
            )

            valor_preceptor = (
                ""
                if preceptor == TEXTO_PRECEPTOR_PADRAO
                else preceptor
            )

            nova_lotacao = c_lot.text_input(
                "Sua Lotação",
                value=valor_lotacao,
                placeholder="Ex: UBS Setor 08",
                key="perfil_lotacao",
            )

            novo_preceptor = c_prec.text_input(
                "Nome do Preceptor(a)",
                value=valor_preceptor,
                placeholder="Ex: Maria Silva",
                key="perfil_preceptor",
            )

            c_btn1, c_btn2, _ = st.columns(
                [1.2, 1, 2]
            )

            # ------------------------------------------------
            # SALVAR
            # ------------------------------------------------

            if c_btn1.button(
                "💾 Salvar Dados",
                type="primary",
                use_container_width=True,
                key="btn_salvar_perfil_header",
            ):

                if not uid:
                    st.error(
                        "Não foi possível identificar "
                        "o usuário autenticado."
                    )
                    st.stop()

                lotacao_final = _normalizar_texto_perfil(
                    nova_lotacao,
                    TEXTO_LOTACAO_PADRAO,
                )

                preceptor_final = _normalizar_texto_perfil(
                    novo_preceptor,
                    TEXTO_PRECEPTOR_PADRAO,
                )

                try:
                    db.collection(
                        "residentes"
                    ).document(uid).update(
                        {
                            "lotacao": lotacao_final,
                            "preceptor": preceptor_final,
                        }
                    )

                    # Atualiza a sessão imediatamente.
                    # Assim não é necessário reler o Firebase
                    # apenas para refletir a mudança no cabeçalho.
                    st.session_state["lotacao"] = lotacao_final
                    st.session_state["preceptor"] = preceptor_final
                    st.session_state["editando_perfil"] = False

                    st.success(
                        "✅ Dados atualizados com sucesso!"
                    )

                    st.rerun()

                except Exception:
                    logger.exception(
                        "Erro ao atualizar lotação/preceptor."
                    )

                    st.error(
                        "Não foi possível atualizar os dados "
                        "neste momento. Tente novamente."
                    )

            # ------------------------------------------------
            # CANCELAR
            # ------------------------------------------------

            if c_btn2.button(
                "❌ Cancelar",
                use_container_width=True,
                key="btn_cancelar_perfil_header",
            ):
                st.session_state["editando_perfil"] = False
                st.rerun()

        # ====================================================
        # VISUALIZAÇÃO NORMAL
        # ====================================================

        else:

            nome_html = _seguro_html(nome)
            profissao_html = _seguro_html(profissao)
            lotacao_html = _seguro_html(lotacao)
            preceptor_html = _seguro_html(preceptor)

            st.markdown(
                f"""
                <h2 style="
                    color: #111827;
                    margin: 0 0 12px 0;
                    font-size: 1.6rem;
                ">👋 Olá, {nome_html}</h2>
                """,
                unsafe_allow_html=True,
            )

            info_html = f"""
            <div style="display:flex; flex-wrap:wrap; gap:15px; color:#4b5563; font-size:0.95rem; align-items:center; margin-bottom:15px;">
                <div style="background-color:#dcfce7; color:#16a34a; padding:5px 12px; border-radius:8px; font-weight:700; border:1px solid #bbf7d0;">{profissao_html}</div>
                <div style="display:flex; align-items:center; gap:6px; background-color:#f3f4f6; padding:5px 12px; border-radius:8px;"><span style="font-size:1.1rem;">📍</span><b>Lotação:</b> {lotacao_html}</div>
                <div style="display:flex; align-items:center; gap:6px; background-color:#f3f4f6; padding:5px 12px; border-radius:8px;"><span style="font-size:1.1rem;">👨‍⚕️</span><b>Preceptor(a):</b> {preceptor_html}</div>
            </div>
            """

            st.markdown(
                info_html,
                unsafe_allow_html=True,
            )

            if st.button(
                "✏️ Atualizar Lotação/Preceptor",
                key="btn_editar_perfil_header",
            ):
                st.session_state["editando_perfil"] = True
                st.rerun()

    # ========================================================
    # LOGO + LOGOUT
    # ========================================================

    with col_sair:

        if LOGO_PATH.exists():
            st.image(
                str(LOGO_PATH),
                use_container_width=True,
            )
        else:
            # Fallback visual: a ausência da imagem não deve
            # impedir a página inteira de funcionar.
            st.markdown(
                """
                <div style="height:80px; display:flex; align-items:center; justify-content:center; color:#9ca3af; font-size:0.8rem; text-align:center;">
                    Residência Multiprofissional
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown(
            "<div style='margin-bottom: 5px;'></div>",
            unsafe_allow_html=True,
        )

        if st.button(
            "🚪 Sair",
            type="secondary",
            use_container_width=True,
            key="btn_logout_header",
        ):
            fazer_logout()
