import os

import streamlit as st
from langchain_classic.memory import ConversationBufferMemory
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

config_models = {"Groq": {'Modelos': ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'mixtral-8x7b-32768'],
                            'chat': ChatGroq,},
                 "OpenAI": {'Modelos': ['gpt-4o-mini', 'gpt-3.5-turbo', 'gpt-4'],
                            'chat': ChatOpenAI,}
                }


memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)




def chat_page():
    st.title("Chat Page")
    st.header("bem vindo ao Oraculo",divider=True)
    memoria = st.session_state.get("memoria", memory)
    chat_model = st.session_state.get("chat")

    # Inicializa contador de mensagens exibidas
    total_mensagens = len(memoria.buffer_as_messages)
    if "mensagens_exibidas" not in st.session_state:
        st.session_state["mensagens_exibidas"] = total_mensagens

    # Exibe apenas as mensagens antigas (já salvas)
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

            # Processa a resposta da IA com stream
            with st.chat_message('ai'):
                mensagem_placeholder = st.empty()
                resposta_completa = ""
                # Itera sobre os chunks do stream e extrai o conteúdo
                for chunk in chat_model.stream(input_user):
                    resposta_completa += chunk.content
                    mensagem_placeholder.markdown(resposta_completa)

            # Salva a resposta na memória
            memoria.chat_memory.add_ai_message(resposta_completa)
            st.session_state["mensagens_exibidas"] += 1

        # Salva a memória e reinicia a página
        st.session_state["memoria"] = memoria
        st.rerun()




def sidebar():
    with st.sidebar:
        provedor = st.selectbox("Selecione o provedor", list(config_models.keys()))
        modelo = st.selectbox("Selecione o modelo", config_models[provedor]["Modelos"])

        # Para Groq, usa a API key do .env
        if provedor == "Groq":
            apikey = os.getenv("GROQ_API_KEY", "")
            if apikey:
                st.info("Usando API Key do arquivo .env")
            else:
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
            loading_models(provedor, modelo, apikey_to_use)




def loading_models(provedor, modelo, apikey):
    # Verifica se a API key foi fornecida
    if not apikey:
        st.error(f"Por favor, insira e salve sua API Key do {provedor} antes de iniciar.")
        return None

    # Define os parâmetros corretos para cada provedor
    if provedor == "Groq":
        chat = config_models[provedor]["chat"](groq_api_key=apikey, model=modelo)
    else:
        chat = config_models[provedor]["chat"](openai_api_key=apikey, model=modelo)

    st.session_state["chat"] = chat
    st.success("Oráculo iniciado com sucesso!")
    return chat

def main():
    chat_page()
    sidebar()


if __name__ == "__main__":
    main()
