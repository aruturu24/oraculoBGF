import streamlit as st
from auth import authenticate, init_db

BGF_LOGO = "https://www.bgfconsultoria.com.br/template/imagens/logo.png"

LOGIN_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    @keyframes fadeInUp {
        from { opacity: 0; transform: translateY(14px); }
        to   { opacity: 1; transform: translateY(0); }
    }

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    [data-testid="stAppViewContainer"] {
        background: #002c97 !important;
    }
    [data-testid="stSidebar"] {
        display: none !important;
    }
    [data-testid="stHeader"] {
        background: transparent !important;
    }

    /* Form styled as floating white card */
    [data-testid="stForm"] {
        background: #FFFFFF !important;
        border: none !important;
        border-radius: 14px !important;
        padding: 2.2rem 2rem 1.8rem 2rem !important;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.18) !important;
        animation: fadeInUp 0.5s ease both;
    }

    /* Gold focus rings */
    [data-testid="stForm"] input {
        transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
    }
    [data-testid="stForm"] input:focus {
        border-color: #D4A017 !important;
        box-shadow: 0 0 0 2px rgba(212, 160, 23, 0.18) !important;
    }

    /* Submit button hover lift */
    .stFormSubmitButton > button {
        background: #002c97 !important;
        color: #FFFFFF !important;
        border: 1px solid #002c97 !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        transition: all 0.2s ease !important;
    }
    .stFormSubmitButton > button:hover {
        background: #001f6b !important;
        border-color: #001f6b !important;
        transform: translateY(-1px);
        box-shadow: 0 4px 14px rgba(212, 160, 23, 0.35) !important;
    }
    .stFormSubmitButton > button:active {
        transform: translateY(0);
    }

    .login-header {
        text-align: center;
        padding-bottom: 0.6rem;
    }
    .login-header img {
        height: 54px;
        margin-bottom: 0.6rem;
    }
    .login-header h2 {
        color: #002c97;
        font-size: 1.4rem;
        font-weight: 700;
        margin: 0;
    }
    .login-header p {
        color: #5A6175;
        font-size: 0.85rem;
        margin-top: 0.25rem;
    }
    .gold-bar {
        width: 48px;
        height: 3px;
        background: #D4A017;
        border-radius: 2px;
        margin: 0.7rem auto 0 auto;
    }
    .login-footer {
        text-align: center;
        color: rgba(255, 255, 255, 0.30);
        font-size: 0.75rem;
        margin-top: 1.6rem;
        animation: fadeInUp 0.65s ease both;
    }
</style>
"""


def login_page():
    """Renders login form. Returns True if user is authenticated."""
    if st.session_state.get("authenticated"):
        return True

    init_db()
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
