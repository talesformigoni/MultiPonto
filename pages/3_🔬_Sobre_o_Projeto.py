import streamlit as st

# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================
st.set_page_config(
    page_title="Sobre o Projeto | MultiPonto",
    page_icon="📍",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ============================================================
# ESTILOS
# ============================================================
st.markdown("""
<style>
    /* ---------- GERAL ---------- */
    .stApp { background: #f8fafc; }
    section[data-testid="stSidebar"] { display: none !important; }
    button[data-testid="collapsedControl"] { display: none !important; }
    .block-container { max-width: 900px; padding-top: 3rem; padding-bottom: 3rem; }

    /* ---------- HERO ---------- */
    .hero { text-align: center; padding: 20px 10px 35px 10px; }
    .hero-icon { font-size: 3.2rem; margin-bottom: 8px; }
    .hero-title { color: #0f172a; font-size: 3rem; font-weight: 900; letter-spacing: -1.5px; margin: 0; }
    .hero-subtitle { color: #64748b; font-size: 1.08rem; margin-top: 8px; line-height: 1.6; }
    .hero-line { width: 70px; height: 4px; background: #2563eb; border-radius: 10px; margin: 20px auto 0 auto; }

    /* ---------- CARDS ---------- */
    .info-card { background: white; border: 1px solid #e2e8f0; border-radius: 16px; padding: 25px 28px; margin: 18px 0; box-shadow: 0 4px 14px rgba(15, 23, 42, 0.04); }
    .section-header { display: flex; align-items: center; gap: 12px; margin-bottom: 15px; }
    .section-icon { width: 42px; height: 42px; background: #eff6ff; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 1.3rem; }
    .section-title { color: #0f172a; font-size: 1.35rem; font-weight: 800; margin: 0; }
    .text-body { color: #334155; font-size: 1rem; line-height: 1.75; text-align: justify; }
    .text-body b { color: #0f172a; }

    /* ---------- DESTAQUE ---------- */
    .highlight { background: linear-gradient(135deg, #eff6ff 0%, #f8fafc 100%); border-left: 4px solid #2563eb; border-radius: 0 12px 12px 0; padding: 18px 20px; margin-top: 18px; color: #1e3a8a; line-height: 1.65; }

    /* ---------- TECNOLOGIAS ---------- */
    .tech-container { margin-top: 12px; }
    .tech-badge { display: inline-block; background: #f1f5f9; color: #334155; border: 1px solid #e2e8f0; padding: 7px 13px; border-radius: 20px; font-size: 0.82rem; font-weight: 700; margin: 4px 3px; }

    /* ---------- AUTORIA ---------- */
    .author-box { background: #0f172a; color: white; border-radius: 16px; padding: 28px; margin-top: 18px; }
    .author-name { font-size: 1.2rem; font-weight: 800; margin-bottom: 6px; }
    .author-role { color: #94a3b8; font-size: 0.92rem; margin-bottom: 16px; }
    .author-text { color: #cbd5e1; line-height: 1.7; font-size: 0.96rem; text-align: justify; }

    /* ---------- RODAPÉ ---------- */
    .footer { text-align: center; color: #94a3b8; font-size: 0.82rem; margin-top: 25px; margin-bottom: 20px; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# HERO
# ============================================================
st.markdown("""
<div class="hero">
<div class="hero-icon">📍</div>
<div class="hero-title">MultiPonto</div>
<div class="hero-subtitle">
Gestão, ciência de dados e transparência<br>
aplicadas à Residência Multiprofissional em Saúde
</div>
<div class="hero-line"></div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# 1. O DESAFIO
# ============================================================
st.markdown("""
<div class="info-card">
<div class="section-header">
<div class="section-icon">🎯</div>
<div class="section-title">O desafio da gestão</div>
</div>
<div class="text-body">
A Residência Multiprofissional em Saúde é uma modalidade de pós-graduação <i>lato sensu</i> caracterizada pela formação em serviço, combinando atividades práticas, teóricas e teórico-práticas.
<br><br>
Em uma rotina marcada por diferentes cenários de atuação, atividades externas, capacitações, reuniões e mudanças de agenda, o acompanhamento da carga horária pode se tornar um desafio administrativo.
<br><br>
Processos baseados exclusivamente em registros manuais dificultam a consolidação das informações e aumentam a possibilidade de inconsistências no acompanhamento de presença, faltas, afastamentos e compensações.
</div>
<div class="highlight">
<b>O MultiPonto nasceu dessa necessidade:</b> transformar registros dispersos em informações organizadas, rastreáveis e úteis para a tomada de decisão.
</div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# 2. A SOLUÇÃO
# ============================================================
st.markdown("""
<div class="info-card">
<div class="section-header">
<div class="section-icon">⚡</div>
<div class="section-title">Uma solução orientada por dados</div>
</div>
<div class="text-body">
O <b>MultiPonto</b> é uma ferramenta desenvolvida para apoiar a gestão e o acompanhamento da jornada dos residentes.
<br><br>
O sistema centraliza registros, organiza informações e automatiza cálculos relacionados à carga horária, permitindo que a coordenação tenha uma visão mais clara do cumprimento da jornada ao longo do período.
<br><br>
A proposta não é substituir a análise da coordenação, mas <b>reduzir o trabalho operacional</b> e fornecer informações mais consistentes para apoiar decisões administrativas.
</div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# 3. INOVAÇÃO
# ============================================================
st.markdown("""
<div class="info-card">
<div class="section-header">
<div class="section-icon">🔬</div>
<div class="section-title">Propósito científico e inovação</div>
</div>
<div class="text-body">
O projeto representa uma iniciativa de <b>inovação tecnológica aplicada à gestão em saúde</b>, utilizando automação e análise de dados para enfrentar um problema concreto observado no cotidiano da Residência Multiprofissional.
<br><br>
A lógica do sistema considera diferentes elementos da jornada, permitindo relacionar registros de presença, calendário, períodos institucionais e demais informações necessárias ao acompanhamento da carga horária.
<br><br>
Dessa forma, dados que antes precisavam ser conferidos manualmente passam a ser processados de maneira estruturada, proporcionando maior agilidade, padronização e transparência.
</div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# 4. AUTORIA
# ============================================================
st.markdown("""
<div class="author-box">
<div class="author-name">Idealização e desenvolvimento</div>
<div class="author-role">Projeto MultiPonto</div>
<div class="author-text">
O MultiPonto foi idealizado e desenvolvido por <b>Benedito Tales Santos Sousa Formigoni</b>, Nutricionista e Residente em Atenção Básica e Saúde da Família, no município de Buritis, Rondônia.
<br><br>
A experiência simultânea nos campos assistencial e administrativo permitiu identificar uma necessidade concreta da gestão da residência e transformá-la em uma solução tecnológica.
<br><br>
O projeto nasce, portanto, de uma premissa simples: <b>quando um problema recorrente pode ser organizado por dados, a tecnologia pode transformar esforço manual em inteligência para a gestão.</b>
</div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# 5. TECNOLOGIA
# ============================================================
st.markdown("""
<div class="info-card">
<div class="section-header">
<div class="section-icon">⚙️</div>
<div class="section-title">Arquitetura e tecnologia</div>
</div>
<div class="text-body">
O sistema foi desenvolvido utilizando uma arquitetura baseada em serviços em nuvem, banco de dados NoSQL e ferramentas de análise de dados.
<br><br>
A estrutura foi pensada para permitir evolução progressiva da aplicação, mantendo separação entre interface, autenticação, armazenamento e processamento das informações.
</div>
<div class="tech-container">
<span class="tech-badge">Python 3</span>
<span class="tech-badge">Streamlit</span>
<span class="tech-badge">Firebase</span>
<span class="tech-badge">Cloud Firestore</span>
<span class="tech-badge">Firebase Authentication</span>
<span class="tech-badge">Pandas</span>
<span class="tech-badge">Plotly</span>
<span class="tech-badge">FPDF</span>
</div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# 6. PRINCÍPIO DO PROJETO
# ============================================================
st.markdown("""
<div class="info-card">
<div class="section-header">
<div class="section-icon">💡</div>
<div class="section-title">Mais que um sistema</div>
</div>
<div class="text-body">
O MultiPonto foi pensado a partir de uma ideia central: <b>gestão eficiente começa com informação organizada.</b>
<br><br>
Ao transformar registros cotidianos em dados estruturados, o sistema busca contribuir para uma gestão mais transparente, objetiva e orientada por evidências.
<br><br>
É tecnologia aplicada a um problema real — simples na origem, mas estratégico na gestão.
</div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# RODAPÉ
# ============================================================
st.markdown("""
<div class="footer">MultiPonto · Projeto de inovação tecnológica em gestão da saúde</div>
""", unsafe_allow_html=True)

# ============================================================
# BOTÃO DE RETORNO
# ============================================================
st.markdown("<br>", unsafe_allow_html=True)

col1, col2, col3 = st.columns([1, 1.5, 1])

with col2:
    if st.button("⬅️ Retornar ao Login", type="primary", use_container_width=True):
        st.switch_page("app.py")
