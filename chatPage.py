import os
import re
from uuid import uuid4

import logging
import streamlit as st
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import InMemorySaver

from admin_panel import admin_page
from auth import is_admin
from login import login_page
from oraculo.chat_utils import (
    coerce_text_content,
    extract_paths_from_agent_messages,
    is_audit_summary_request,
    is_intermediate_agent_reply,
    normalize_assistant_reply,
    should_show_images,
    should_use_sql_agent,
)
from oraculo.constants import AGENT_SCHEMA_VERSION, BGF_LOGO, CHAT_MYSQL_TABLES, DEFAULT_MODEL
from oraculo.mysql_utils import (
    get_sql_database,
    resolved_attachments_for_display,
    verify_attachment_paths_for_user,
)
from oraculo.prompts import GENERAL_ASSISTANT_PROMPT, build_sql_prefix
from oraculo.styles import load_app_css

load_dotenv()


NON_ESSENTIAL_SQL_TOOLS = {"sql_db_query_checker", "sql_db_list_tables"}
logger = logging.getLogger(__name__)


class LeanSQLDatabaseToolkit(SQLDatabaseToolkit):
    def get_tools(self):
        tools = super().get_tools()
        return [tool for tool in tools if tool.name not in NON_ESSENTIAL_SQL_TOOLS]


def _ensure_thread_id() -> str:
    thread_id = st.session_state.get("agent_thread_id")
    if not thread_id:
        thread_id = str(uuid4())
        st.session_state["agent_thread_id"] = thread_id
    return thread_id


def _agent_config() -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": _ensure_thread_id()}}


def _ensure_display_messages() -> list[dict[str, str]]:
    messages = st.session_state.get("display_messages")
    if messages is None:
        messages = []
        st.session_state["display_messages"] = messages
    return messages


def _extract_last_ai_reply(messages: list[object]) -> str:
    for message in reversed(messages):
        if getattr(message, "type", "") == "ai":
            return coerce_text_content(getattr(message, "content", ""))
    return ""


def _ensure_model_initialized() -> None:
    if st.session_state.get("agent_schema_version") != AGENT_SCHEMA_VERSION:
        st.session_state.pop("chat", None)
        st.session_state.pop("agent", None)
        st.session_state.pop("memoria", None)
        st.session_state.pop("mensagens_exibidas", None)
        st.session_state.pop("display_messages", None)
        st.session_state.pop("agent_checkpointer", None)
        st.session_state.pop("agent_thread_id", None)
        st.session_state.pop("agent_has_db", None)
        st.session_state["agent_schema_version"] = AGENT_SCHEMA_VERSION

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        st.error("Chave GEMINI_API_KEY nao encontrada. Configure o arquivo .env.")
        st.stop()

    chat = st.session_state.get("chat")
    if chat is None:
        chat = ChatGoogleGenerativeAI(
            google_api_key=api_key,
            model=DEFAULT_MODEL,
            max_output_tokens=4096,
            convert_system_message_to_human=True,
        )
        st.session_state["chat"] = chat

    if st.session_state.get("agent") is not None:
        return

    checkpointer = st.session_state.get("agent_checkpointer")
    if checkpointer is None:
        checkpointer = InMemorySaver()
        st.session_state["agent_checkpointer"] = checkpointer

    user = st.session_state.get("user", {})
    administrator = user.get("administrator", "")
    allowed_customers = user.get("allowed_customers", "all")

    db = get_sql_database(CHAT_MYSQL_TABLES, sample_rows_in_table_info=2)
    tools = []
    system_prompt = GENERAL_ASSISTANT_PROMPT

    if db:
        prefix = build_sql_prefix(administrator, allowed_customers)
        sql_system_prompt = prefix.format(dialect=db.dialect, top_k=10)
        sql_system_prompt = sql_system_prompt.replace(
            'If the question does not seem related to the database, just return "I don\'t know" as the answer.',
            "Se a pergunta nao estiver relacionada ao banco de dados, responda normalmente em portugues brasileiro sem usar ferramentas.",
        )
        toolkit = LeanSQLDatabaseToolkit(db=db, llm=chat)
        tools = toolkit.get_tools()
        system_prompt = (
            f"{GENERAL_ASSISTANT_PROMPT}\n\n"
            f"{sql_system_prompt}\n\n"
            "Use ferramentas SQL apenas quando a pergunta exigir dados do banco. "
            "Se for uma pergunta geral, responda diretamente sem chamar ferramentas."
        )
        st.session_state["agent_has_db"] = True
    else:
        st.session_state["agent_has_db"] = False

    st.session_state["agent"] = create_agent(
        model=chat,
        tools=tools,
        system_prompt=system_prompt,
        checkpointer=checkpointer,
        name="bgf_oraculo_agent",
    )
    _ensure_thread_id()


def _process_pending_response(display_messages: list[dict]) -> None:
    """Run the agent for a pending user input and append the AI reply."""
    pending = st.session_state.pop("_pending_input", None)
    upload_hint = st.session_state.pop("_pending_upload_hint", None)
    if pending is None:
        return

    with st.chat_message("ai"):
        mensagem_placeholder = st.empty()
        mensagem_placeholder.markdown("_Pensando..._")

        agent = st.session_state.get("agent")
        verified_attachments: list[tuple[str, str | None]] = []
        show_imgs = should_show_images(pending, bool(upload_hint))
        needs_sql_agent = should_use_sql_agent(pending, bool(upload_hint))
        has_db = bool(st.session_state.get("agent_has_db"))

        if not agent:
            resposta_completa = "O modelo nao foi inicializado. Verifique a configuracao."
            result_messages: list[object] = []
        elif needs_sql_agent and not has_db:
            resposta_completa = (
                "Nao consegui acessar o banco de dados agora para responder essa pergunta. "
                "Verifique a conexao/configuracao do MySQL e tente novamente."
            )
            result_messages = []
        else:
            invoke_input = pending
            if needs_sql_agent and is_audit_summary_request(pending):
                invoke_input += (
                    "\n\nINSTRUCAO OBRIGATORIA PARA ESTA RESPOSTA: "
                    "faca resumo textual real dos problemas por categoria de nivel 2, "
                    "usando o mapeamento interno de categorias e agrupando fichas-filhas por prefixo do codigo. "
                    "Exemplo: categoria 72,2 deve considerar code_category = '72,2' e code_category LIKE '72,2,%'. "
                    "Mostre cada categoria com titulo em Markdown no formato '## Categoria <code> - <description>'. "
                    "Considere apenas fichas de risco alto com base no campo oficial de risco (risc >= 4), "
                    "ignorando risco < 4. "
                    "Nao retorne IDs nem quantidade de fichas, a menos que o usuario peca explicitamente. "
                    "Nao cite nomes de tabelas ou colunas na resposta final. "
                    "Em cada item, escreva um resumo mais longo (2 paragrafos curtos), "
                    "destacando problema principal, padroes recorrentes, impacto e acao sugerida."
                )
            if upload_hint:
                safe_hint = re.sub(r"[^\w.\-]", "_", upload_hint)
                invoke_input += f"\n\nBuscar imagem: {safe_hint}"

            try:
                result = agent.invoke(
                    {"messages": [{"role": "user", "content": invoke_input}]},
                    _agent_config(),
                )
                result_messages = result.get("messages", []) if isinstance(result, dict) else []
                raw_output = _extract_last_ai_reply(result_messages)
                if raw_output and needs_sql_agent and has_db and is_intermediate_agent_reply(raw_output):
                    result = agent.invoke(
                        {
                            "messages": [
                                {
                                    "role": "user",
                                    "content": (
                                        "Continue internamente e entregue agora apenas a resposta final "
                                        "da solicitacao original. Nao envie mensagem de andamento."
                                    ),
                                }
                            ]
                        },
                        _agent_config(),
                    )
                    result_messages = (
                        result.get("messages", []) if isinstance(result, dict) else []
                    )
                    raw_output = _extract_last_ai_reply(result_messages)
                if (
                    not raw_output
                    or raw_output.startswith("<function")
                    or "tool_input" in raw_output
                ):
                    resposta_completa = (
                        "Desculpe, nao consegui processar sua solicitacao. "
                        "Por favor, tente reformular a pergunta."
                    )
                else:
                    resposta_completa = raw_output
            except Exception as e:
                logger.exception("Agent invocation failed")
                err_msg = str(e).strip() or e.__class__.__name__
                resposta_completa = (
                    "Ocorreu um erro ao processar sua solicitacao.\n\n"
                    f"Detalhe tecnico: `{err_msg}`"
                )
                result_messages = []

        if show_imgs and result_messages:
            raw_paths = extract_paths_from_agent_messages(result_messages)
            if raw_paths:
                user_obj = st.session_state.get("user", {})
                verified_attachments = verify_attachment_paths_for_user(raw_paths, user_obj)

        resposta_completa = normalize_assistant_reply(resposta_completa, pending)
        mensagem_placeholder.markdown(resposta_completa)

        if show_imgs and verified_attachments:
            for fs_path, caption in resolved_attachments_for_display(verified_attachments):
                st.image(fs_path, caption=caption)

    display_messages.append({"role": "ai", "content": resposta_completa})
    st.session_state["display_messages"] = display_messages
    st.rerun()


def chat_page():
    st.markdown(
        f"""
        <div class="bgf-header">
            <img src="{BGF_LOGO}" alt="BGF">
            <div class="bgf-header-text">
                <h1>BGF Oraculo</h1>
                <p>Assistente inteligente &middot; BGF Consultoria em Engenharia</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _ensure_model_initialized()

    display_messages = _ensure_display_messages()

    if not display_messages and "_pending_input" not in st.session_state:
        st.markdown(
            """
            <div class="empty-state">
                <h3>Como posso ajudar?</h3>
                <p>Faca uma pergunta sobre seus dados, clientes ou auditorias.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    for mensagem in display_messages:
        role = mensagem.get("role", "ai")
        content = mensagem.get("content", "")
        with st.chat_message(role):
            st.markdown(content)

    # Process any pending agent response (runs above the input widget)
    _process_pending_response(display_messages)

    _att_nonce = st.session_state.get("_attachment_uploader_nonce", 0)
    _col_attach, _col_chat = st.columns([0.07, 0.93], gap="small")
    with _col_attach:
        uf = st.file_uploader(
            "Anexar imagem",
            label_visibility="hidden",
            type=["png", "jpg", "jpeg", "gif", "webp", "bmp"],
            key=f"attachment_name_search_{_att_nonce}",
            help=None,
        )
        if uf is not None:
            st.session_state["attachment_search_filename"] = uf.name
    with _col_chat:
        input_user = st.chat_input("Digite sua pergunta...")

    if input_user:
        upload_hint = st.session_state.pop("attachment_search_filename", None)
        if upload_hint:
            st.session_state["_attachment_uploader_nonce"] = (
                st.session_state.get("_attachment_uploader_nonce", 0) + 1
            )
        display_messages.append({"role": "human", "content": input_user})
        st.session_state["display_messages"] = display_messages
        st.session_state["_pending_input"] = input_user
        if upload_hint:
            st.session_state["_pending_upload_hint"] = upload_hint
        st.rerun()


def sidebar():
    with st.sidebar:
        user = st.session_state.get("user", {})
        administrador = st.session_state.get("administrador", user.get("administrator", ""))
        st.session_state["administrador"] = administrador

        allowed_customers = user.get("allowed_customers", "all")
        st.session_state["allowed_customers"] = allowed_customers

        page = st.session_state.get("page", "chat")

        st.markdown(
            f"""
            <div class="sidebar-logo">
                <div class="sidebar-logo-bg">
                    <img src="{BGF_LOGO}" alt="BGF">
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown('<div class="nav-label">Navegacao</div>', unsafe_allow_html=True)

        if st.button(
            "Chat",
            type="primary" if page == "chat" else "secondary",
            use_container_width=True,
            key="nav_chat",
        ):
            if page != "chat":
                st.session_state["page"] = "chat"
                st.rerun()

        if is_admin(user):
            if st.button(
                "Gerenciar Usuarios",
                type="primary" if page == "admin" else "secondary",
                use_container_width=True,
                key="nav_admin",
            ):
                if page != "admin":
                    st.session_state["page"] = "admin"
                    st.rerun()

        st.markdown("---")

        st.markdown(
            f"""
            <div class="sidebar-user-card">
                <div class="user-name">{user.get('username', '')}</div>
                <div class="user-role">Administrador: {administrador}</div>
                <div class="user-status">
                    <span class="status-dot"></span>Conectado
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("Sair", type="secondary", use_container_width=True, key="nav_logout"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()


def main():
    st.set_page_config(page_title="BGF Oraculo", page_icon=BGF_LOGO, layout="wide")

    if not login_page():
        return

    st.markdown(load_app_css(), unsafe_allow_html=True)
    sidebar()

    page = st.session_state.get("page", "chat")
    user = st.session_state.get("user", {})

    if page == "admin" and is_admin(user):
        admin_page()
    else:
        chat_page()


if __name__ == "__main__":
    main()
