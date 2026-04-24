import streamlit as st
from auth import authenticate, init_db
from oraculo.constants import BGF_LOGO

LOGIN_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    @keyframes fadeInUp {
        from { opacity: 0; transform: translateY(12px); }
        to   { opacity: 1; transform: translateY(0); }
    }

    @keyframes scaleIn {
        from { opacity: 0; transform: scale(0.92); }
        to   { opacity: 1; transform: scale(1); }
    }

    @keyframes goldShimmer {
        0%   { box-shadow: 0 0 0 0 rgba(212,160,23,0); }
        50%  { box-shadow: 0 0 8px 2px rgba(212,160,23,0.45); }
        100% { box-shadow: 0 0 0 0 rgba(212,160,23,0); }
    }

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    [data-testid="stAppViewContainer"] {
        background: linear-gradient(145deg, #001f6b 0%, #002c97 55%, #003bbf 100%) !important;
    }
    [data-testid="stSidebar"] {
        display: none !important;
    }
    [data-testid="stHeader"] {
        background: transparent !important;
    }

    [data-testid="stForm"] {
        background: #FFFFFF !important;
        border: none !important;
        border-radius: 16px !important;
        padding: 2.4rem 2.2rem 2rem 2.2rem !important;
        box-shadow: 0 16px 48px rgba(0, 0, 0, 0.22) !important;
        animation: scaleIn 0.45s cubic-bezier(0.34,1.3,0.64,1) both;
    }

    [data-testid="stForm"] input {
        border-radius: 8px !important;
        transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
    }
    [data-testid="stForm"] input:focus {
        border-color: #D4A017 !important;
        box-shadow: 0 0 0 3px rgba(212, 160, 23, 0.14) !important;
    }

    .stFormSubmitButton > button {
        background: #002c97 !important;
        color: #FFFFFF !important;
        border: 1px solid #002c97 !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        transition: all 0.2s ease !important;
    }
    .stFormSubmitButton > button:hover {
        background: #001f6b !important;
        border-color: #001f6b !important;
        transform: translateY(-1px);
        box-shadow: 0 6px 18px rgba(0, 44, 151, 0.35) !important;
    }
    .stFormSubmitButton > button:active {
        transform: translateY(0);
    }

    .login-header {
        text-align: center;
        padding-bottom: 0.75rem;
    }
    .login-header img {
        height: 56px;
        margin-bottom: 0.7rem;
        animation: scaleIn 0.5s cubic-bezier(0.34,1.56,0.64,1) both;
        animation-delay: 0.15s;
    }
    .login-header h2 {
        color: #002c97;
        font-size: 1.45rem;
        font-weight: 700;
        margin: 0;
        letter-spacing: -0.01em;
    }
    .login-header p {
        color: #8A93A8;
        font-size: 0.85rem;
        margin-top: 0.28rem;
    }
    .gold-bar {
        width: 44px;
        height: 3px;
        background: #D4A017;
        border-radius: 2px;
        margin: 0.75rem auto 0 auto;
        animation: goldShimmer 3s ease-in-out 0.5s infinite;
    }
    .login-footer {
        text-align: center;
        color: rgba(255, 255, 255, 0.28);
        font-size: 0.75rem;
        margin-top: 1.8rem;
        animation: fadeInUp 0.65s ease both;
    }
</style>
"""


def login_page():
    """Renders login form. Returns True if user is authenticated."""
    if st.session_state.get("authenticated"):
        return True

    if not st.session_state.get("_auth_db_ready"):
        init_db()
        st.session_state["_auth_db_ready"] = True
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)

    _, col, _ = st.columns([1.3, 1, 1.3])
    with col:
        st.markdown("")

        with st.form("login_form"):
            st.markdown(
                f"""
                <div class="login-header">
                    <img src="{BGF_LOGO}" alt="BGF Consultoria">
                    <h2>Oraculo</h2>
                    <p>Acesse sua conta para continuar</p>
                    <div class="gold-bar"></div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            username = st.text_input("Usuario", placeholder="Digite seu usuario")
            password = st.text_input(
                "Senha", type="password", placeholder="Digite sua senha"
            )
            submitted = st.form_submit_button("Entrar", use_container_width=True)

        if submitted:
            if not username or not password:
                st.error("Preencha todos os campos.")
                return False
            user = authenticate(username, password)
            if user:
                st.session_state["authenticated"] = True
                st.session_state["user"] = user
                st.session_state["administrador"] = user["administrator"]
                st.rerun()
            else:
                st.error("Usuario ou senha invalidos.")

        st.markdown(
            '<div class="login-footer">BGF Consultoria em Engenharia &copy; 2026</div>',
            unsafe_allow_html=True,
        )

    return False
