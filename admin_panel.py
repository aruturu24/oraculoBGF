import streamlit as st

from auth import create_user, delete_user, is_admin, list_users, update_password
from oraculo.mysql_utils import fetch_administrator_options, fetch_customers_by_admin


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


def _normalize_allowed_customers(selected_customers: list[str]) -> str:
    selected = [str(item).strip() for item in selected_customers if str(item).strip()]
    if not selected or "all" in selected:
        return "all"

    unique: list[str] = []
    seen: set[str] = set()
    for customer_id in selected:
        if customer_id in seen:
            continue
        seen.add(customer_id)
        unique.append(customer_id)
    return ",".join(unique) if unique else "all"


def _format_allowed_customers(value: str) -> str:
    allowed = (value or "all").strip()
    if not allowed or allowed == "all":
        return "Todos"
    ids = [item.strip() for item in allowed.split(",") if item.strip()]
    return ", ".join(ids) if ids else "Todos"


def _render_registration_form():
    admin_options = fetch_administrator_options()
    if admin_options:
        new_admin = st.selectbox(
            "Administrador",
            options=admin_options,
            key="reg_admin",
            help="Valor de tbl_customer.administrator.",
        )
    else:
        st.info(
            "Nao foi possivel listar administradores do MySQL. Digite manualmente o valor."
        )
        new_admin = st.text_input(
            "Administrador",
            key="reg_admin_manual",
            help="Valor de tbl_customer.administrator.",
        )

    customers_data = fetch_customers_by_admin(new_admin) if new_admin else []
    id_to_name = {c["id"]: c["name"] for c in customers_data}
    customer_ids = [c["id"] for c in customers_data]

    with st.form("register_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            new_user = st.text_input("Nome de usuario")
        with c2:
            new_pass = st.text_input("Senha", type="password")

        select_opts = ["all"] + customer_ids if customer_ids else ["all"]
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
            allowed = _normalize_allowed_customers(selected_customers)
            if create_user(new_user, new_pass, new_admin, allowed):
                st.success(f"Usuario '{new_user}' criado com sucesso.")
            else:
                st.error(f"Usuario '{new_user}' ja existe.")


def _render_users_list(current_user: dict):
    users = list_users()
    if not users:
        st.info("Nenhum usuario cadastrado.")
        return

    hdr = st.columns([2.2, 1.8, 2.2, 2.2, 2.0])
    hdr[0].markdown("**Usuario**")
    hdr[1].markdown("**Administrador**")
    hdr[2].markdown("**Clientes**")
    hdr[3].markdown("**Criado em**")
    hdr[4].markdown("**Acoes**")
    st.divider()

    for u in users:
        cols = st.columns([2.2, 1.8, 2.2, 2.2, 2.0])
        cols[0].write(u["username"])
        cols[1].write(u["administrator"])
        cols[2].write(_format_allowed_customers(u.get("allowed_customers", "all")))
        created = u.get("created_at", "")
        cols[3].write(str(created)[:16] if created else "---")

        if u["id"] != current_user["id"]:
            with cols[4]:
                bc1, bc2 = st.columns(2)
                if bc1.button("Senha", key=f"rst_{u['id']}"):
                    st.session_state[f"reset_target_{u['id']}"] = True
                if bc2.button("Excluir", key=f"del_{u['id']}"):
                    delete_user(u["id"])
                    st.rerun()
        else:
            cols[4].write("---")

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
