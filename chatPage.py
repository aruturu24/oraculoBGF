import os
from urllib.parse import quote_plus

from dotenv import load_dotenv

import streamlit as st

load_dotenv()
from langchain_classic.memory import ConversationBufferMemory
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.agent_toolkits.sql.prompt import SQL_PREFIX
from langchain_core.messages import HumanMessage

# Últimas N mensagens para contexto
MAX_HISTORY_MESSAGES = 10  # 5 trocas usuário/assistente
MAX_HISTORY_EXCHANGES_AGENT = 3  # trocas no input do agente

config_models = {"Groq": {'Modelos': ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'mixtral-8x7b-32768'],
                            'chat': ChatGroq,},
                 "OpenAI": {'Modelos': ['gpt-4o-mini', 'gpt-3.5-turbo', 'gpt-4'],
                            'chat': ChatOpenAI,}
                }


memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

MYSQL_TABLES = ["tbl_audit", "tbl_customer"]

# Instruções para a IA
SQL_EXTRA_INSTRUCTIONS = """
REGRAS OBRIGATÓRIAS:
- Responda SEMPRE apenas em português brasileiro.
- Tabelas disponíveis: tbl_audit, tbl_customer. A tabela de clientes tem a coluna administrator.
- O usuário atual é o administrador com o valor informado abaixo. Em TODAS as consultas que envolvam tbl_customer (ou customer), você DEVE incluir a condição: customer.administrator = '<VALOR_ADMIN>' (use o nome exato da coluna do schema). Assim o usuário só acessa os clientes que ele administra.
- tbl_audit: qualquer resultado de tbl_audit DEVE ter customer_id que exista em tbl_customer. Ao consultar tbl_audit, faça JOIN com tbl_customer (audit.customer_id = customer.id ou equivalente) e aplique o filtro customer.administrator = valor do administrador atual, para retornar apenas auditorias dos clientes que o usuário administra.
- Valor do administrador atual: {administrator}
"""


def get_sql_prefix(administrador: str) -> str:
    admin_val = (administrador or "").strip()
    if not admin_val:
        admin_val = "(não definido — defina na sidebar para filtrar por administrador)"
    return SQL_PREFIX + SQL_EXTRA_INSTRUCTIONS.format(administrator=admin_val)


def _input_with_history(memoria, input_user: str) -> str:
    """Inclui as últimas trocas no input para o agente SQL."""
    msgs = memoria.buffer_as_messages
    n = 2 * MAX_HISTORY_EXCHANGES_AGENT
    recent = msgs[-n:] if len(msgs) > n else msgs
    if not recent:
        return input_user
    parts = ["Contexto da conversa anterior:"]
    for m in recent:
        role = "Usuário" if m.type == "human" else "Assistente"
        parts.append(f"{role}: {m.content}")
    parts.append(f"\nPergunta atual: {input_user}")
    return "\n".join(parts)


def _messages_with_history(memoria, input_user: str):
    """Lista de mensagens com histórico para o chat (sem agente)."""
    msgs = memoria.buffer_as_messages
    recent = msgs[-MAX_HISTORY_MESSAGES:] if len(msgs) > MAX_HISTORY_MESSAGES else list(msgs)
    return recent + [HumanMessage(content=input_user)]


def get_mysql_db():
    host = os.getenv("MYSQL_HOST")
    user = os.getenv("MYSQL_USER")
    password = os.getenv("MYSQL_PASSWORD")
    database = os.getenv("MYSQL_DATABASE", "")
    if not all([host, user, password]):
        return None
    uri = f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}@{host}/{database}"
    return SQLDatabase.from_uri(uri, include_tables=MYSQL_TABLES, sample_rows_in_table_info=2)


def chat_page():
    st.title("Chat Page")
    st.header("bem vindo ao Oraculo",divider=True)
    memoria = st.session_state.get("memoria", memory)
    chat_model = st.session_state.get("chat")

    # Inicializa contador de mensagens exibidas
    total_mensagens = len(memoria.buffer_as_messages)
    if "mensagens_exibidas" not in st.session_state:
        st.session_state["mensagens_exibidas"] = total_mensagens

    # Exibe apenas as mensagens antigas
    mensagens_antigas = memoria.buffer_as_messages[:st.session_state["mensagens_exibidas"]]

    for mensagem in mensagens_antigas:
       with st.chat_message(mensagem.type):
           st.markdown(mensagem.content)

    # Processa entrada do usuário
    input_user = st.chat_input("Digite sua mensagem")
    if input_user:
        # Verifica se o modelo foi inicializado
        if chat_model is None:
            st.error("Por favor, inicie o Oráculo primeiro na sidebar!")
        else:
            # Exibe a mensagem do usuário
            with st.chat_message('human'):
                st.markdown(input_user)

            # Adiciona a mensagem do usuário na memória
            memoria.chat_memory.add_user_message(input_user)
            st.session_state["mensagens_exibidas"] += 1

            # Processa a resposta da IA
            with st.chat_message('ai'):
                mensagem_placeholder = st.empty()
                agent = st.session_state.get("agent")
                if agent:
                    input_with_ctx = _input_with_history(memoria, input_user)
                    result = agent.invoke({"input": input_with_ctx})
                    resposta_completa = result.get("output", str(result))
                else:
                    resposta_completa = ""
                    messages = _messages_with_history(memoria, input_user)
                    for chunk in chat_model.stream(messages):
                        resposta_completa += chunk.content
                        mensagem_placeholder.markdown(resposta_completa)
                if agent:
                    mensagem_placeholder.markdown(resposta_completa)

            # Salva a resposta na memória
            memoria.chat_memory.add_ai_message(resposta_completa)
            st.session_state["mensagens_exibidas"] += 1

        # Salva a memória e reinicia a página
        st.session_state["memoria"] = memoria
        st.rerun()




def sidebar():
    with st.sidebar:
        administrador = st.text_input(
            "Administrador",
            value=st.session_state.get("administrador", ""),
            placeholder="Administrador da tabela Customer",
            help="Usado para filtrar clientes: só verá dados onde customer.administrator = este valor.",
        )
        st.session_state["administrador"] = administrador

        provedor = st.selectbox("Selecione o provedor", list(config_models.keys()))
        modelo = st.selectbox("Selecione o modelo", config_models[provedor]["Modelos"])

        # Para Groq, usa a API key do .env
        if provedor == "Groq":
            apikey = os.getenv("GROQ_API_KEY", "")
            if not apikey:
                st.warning("GROQ_API_KEY não encontrada no arquivo .env")
        else:
            apikey = st.text_input(f"Digite sua API Key do {provedor}", value=st.session_state.get(f"api_key_{provedor}", ""), type="password")
            if st.button("Salvar Configurações"):
                st.session_state[f"api_key_{provedor}"] = apikey
                st.success("Configurações salvas com sucesso!")

        if st.button("iniciar Oraculo", use_container_width=True):
            if provedor == "Groq":
                apikey_to_use = os.getenv("GROQ_API_KEY", "")
            else:
                apikey_to_use = st.session_state.get(f"api_key_{provedor}", apikey)
            loading_models(provedor, modelo, apikey_to_use, administrador=administrador)




def loading_models(provedor, modelo, apikey, administrador: str = ""):
    # Verifica se a API key foi fornecida
    if not apikey:
        st.error(f"Por favor, insira e salve sua API Key do {provedor} antes de iniciar.")
        return None

    # Define os parâmetros corretos para cada provedor
    if provedor == "Groq":
        chat = config_models[provedor]["chat"](groq_api_key=apikey, model=modelo, max_tokens=4096)
    else:
        chat = config_models[provedor]["chat"](openai_api_key=apikey, model=modelo)

    st.session_state["chat"] = chat
    db = get_mysql_db()
    if db:
        prefix = get_sql_prefix(administrador)
        st.session_state["agent"] = create_sql_agent(
            chat, db=db, agent_type="tool-calling", prefix=prefix, max_iterations=6
        )
        st.success("Oráculo iniciado com MySQL (tbl_audit, tbl_customer)!")
    else:
        st.session_state["agent"] = None
        st.success("Oráculo iniciado com sucesso!")
    return chat

def main():
    chat_page()
    sidebar()


if __name__ == "__main__":
    main()
