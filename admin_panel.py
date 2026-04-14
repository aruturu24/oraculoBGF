import os
from urllib.parse import quote_plus

import streamlit as st
from langchain_community.utilities import SQLDatabase

from auth import create_user, list_users, delete_user, update_password, is_admin

MYSQL_TABLES = ["tbl_customer"]


def _get_mysql_db():
    host = os.getenv("MYSQL_HOST")
    user = os.getenv("MYSQL_USER")
    password = os.getenv("MYSQL_PASSWORD")
    database = os.getenv("MYSQL_DATABASE", "")
    if not all([host, user, password]):
        return None
    uri = f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}@{host}/{database}"
    return SQLDatabase.from_uri(uri, include_tables=MYSQL_TABLES)


@st.cache_data(ttl=300)
def _fetch_administrator_options() -> list[str]:
    import ast
    db = _get_mysql_db()
    if not db:
        return []
    rows = db.run("SELECT DISTINCT administrator FROM tbl_customer ORDER BY administrator")
    if not rows:
        return []
    parsed = ast.literal_eval(rows)
    return [str(r[0]) for r in parsed if r[0]]


@st.cache_data(ttl=300)
def _fetch_customers_by_admin(administrator: str) -> list[dict]:
    import ast
    db = _get_mysql_db()
    if not db:
        return []
    rows = db.run(
        f"SELECT id, cust_name AS name FROM tbl_customer WHERE administrator = '{administrator}' ORDER BY name"
    )
    if not rows:
        return []
    parsed = ast.literal_eval(rows)
    return [{"id": str(r[0]), "name": str(r[1])} for r in parsed]


def admin_page():
    """Full-page admin panel for user management."""
    user = st.session_state.get("user")
    if not user or not is_admin(user):
        st.warning("Acesso negado.")
        return

    st.markdown(
        """
        <div class="page-header">
            <h1>Gerenciar Usuarios</h1>
            <p>Cadastre e gerencie os usuarios do sistema</p>
            <div class="gold-bar"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_reg, tab_users = st.tabs(["Registrar Usuario", "Usuarios Cadastrados"])

    with tab_reg:
        _render_registration_form()

    with tab_users:
        _render_users_list(user)


def _render_registration_form():
    admin_options = _fetch_administrator_options()
    new_admin = st.selectbox(
        "Administrador",
        options=admin_options,
        key="reg_admin",
        help="Valor de tbl_customer.administrator.",
    )

    customers_data = _fetch_customers_by_admin(new_admin) if new_admin else []
    id_to_name = {c["id"]: c["name"] for c in customers_data}
    customer_ids = [c["id"] for c in customers_data]

    with st.form("register_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            new_user = st.text_input("Nome de usuario")
        with c2:
            new_pass = st.text_input("Senha", type="password")

        select_opts = ["all"] + customer_ids
        selected_customers = st.multiselect(
            "Clientes permitidos",
            options=select_opts,
            default=["all"],
            format_func=lambda v: "Todos" if v == "all" else id_to_name.get(v, v),
            help="Selecione 'Todos' para acesso a todos os clientes do administrador.",
        )

        reg_submit = st.form_submit_button(
            "Registrar Usuario", use_container_width=True
        )

    if reg_submit:
        if not new_user or not new_pass or not new_admin:
            st.error("Preencha todos os campos.")
        else:
            if "all" in selected_customers or not selected_customers:
                allowed = "all"
            else:
                allowed = ",".join(selected_customers)
            if create_user(new_user, new_pass, new_admin, allowed):
                st.success(f"Usuario '{new_user}' criado com sucesso.")
            else:
                st.error(f"Usuario '{new_user}' ja existe.")


def _render_users_list(current_user: dict):
    users = list_users()
    if not users:
        st.info("Nenhum usuario cadastrado.")
        return

    hdr = st.columns([2.5, 2, 2.5, 2])
    hdr[0].markdown("**Usuario**")
    hdr[1].markdown("**Administrador**")
    hdr[2].markdown("**Criado em**")
    hdr[3].markdown("**Acoes**")
    st.divider()

    for u in users:
        cols = st.columns([2.5, 2, 2.5, 2])
        cols[0].write(u["username"])
        cols[1].write(u["administrator"])
        created = u.get("created_at", "")
        cols[2].write(str(created)[:16] if created else "---")

        if u["id"] != current_user["id"]:
            with cols[3]:
                bc1, bc2 = st.columns(2)
                if bc1.button("Senha", key=f"rst_{u['id']}"):
                    st.session_state[f"reset_target_{u['id']}"] = True
                if bc2.button("Excluir", key=f"del_{u['id']}"):
                    delete_user(u["id"])
                    st.rerun()
        else:
            cols[3].write("---")

        if st.session_state.get(f"reset_target_{u['id']}"):
            with st.form(f"reset_form_{u['id']}"):
                np = st.text_input(
                    "Nova senha", type="password", key=f"np_{u['id']}"
                )
                if st.form_submit_button("Salvar"):
                    if np:
                        update_password(u["id"], np)
                        st.session_state.pop(f"reset_target_{u['id']}", None)
                        st.success(f"Senha de '{u['username']}' atualizada.")
                        st.rerun()
                    else:
                        st.error("A senha nao pode ser vazia.")
            if st.button("Cancelar", key=f"cancel_{u['id']}"):
                st.session_state.pop(f"reset_target_{u['id']}", None)
                st.rerun()
