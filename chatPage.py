import streamlit as st
import tempfile
from langchain.memory import ConversationBufferMemory
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from loading_files import *

config_models = {"Groq": {'Modelos': ['lhama-70b', 'mixtral-8x7b'],
                            'chat': ChatGroq,},
                 "OpenAI": {'Modelos': ['gpt-4o-mini', 'gpt-3.5-turbo', 'gpt-4'],
                            'chat': ChatOpenAI,}
                }

filesType = ["pdf", "docx", "txt", "csv", 'Site', 'YouTube']

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
    tabs = st.sidebar.tabs(["Upload de Arquivos", "Seleção de Modelos"])
    with tabs[0]:
       tipoArquivo = st.selectbox("Selecione o tipo de arquivo", filesType)
    if tipoArquivo == "Site":
        url = st.text_input("Digite a URL do site")
    if tipoArquivo == "YouTube":
        youtube_url = st.text_input("Digite a URL do vídeo do YouTube") 
    if tipoArquivo == "pdf":
       pdf_file = st.file_uploader("Escolha um arquivo PDF", type=["pdf"])
    elif tipoArquivo == "docx":
        uploaded_file = st.file_uploader("Escolha um arquivo DOCX", type=["docx"])
    elif tipoArquivo == "txt":
        uploaded_file = st.file_uploader("Escolha um arquivo TXT", type=["txt"])
    elif tipoArquivo == "csv":
        uploaded_file = st.file_uploader("Escolha um arquivo CSV", type=["csv"])
        uploaded_file = st.file_uploader("Escolha um arquivo", type=filesType[:-2])
    
    with tabs[1]:
        provedor= st.selectbox("Selecione o provedor", list(config_models.keys()))
        modelo = st.selectbox("Selecione o modelo", config_models[provedor]["Modelos"])
        
        apikey = st.text_input(f"Digite sua API Key do {provedor}",value=st.session_state.get(f'api_key_{provedor}', ''), type="password")
        if st.button("Salvar Configurações"):
            st.success("Configurações salvas com sucesso!")
            
            st.session_state[f'api_key_{provedor}'] = apikey

    if st.button("iniciar Oraculo",use_container_width=True):
        # Usa a API key do session_state se disponível
        apikey_to_use = st.session_state.get(f'api_key_{provedor}', apikey)
        
        loading_models(provedor,modelo,apikey_to_use,tipoArquivo,pdf_file)
        
        
        
        
def loading_models(provedor,modelo,apikey,type_file,file_path):
    
    if type_file == "Site":
        file_path = loading_web(file_path)
    elif type_file == "YouTube":
        file_path = loading_youtube(file_path)
    elif type_file == "csv":
        file_path = loading_csv(file_path)
    elif type_file == "txt":
        file_path = loading_txt(file_path)
    elif type_file == "pdf":
        with tempfile.NamedTemporaryFile(suffix='.pdf',delete=False) as temp:
            temp.write(uploaded_file.read())
            file_name = temp.name
            file_path = loading_pdf(file_name)
        print(file_path)
    # Verifica se a API key foi fornecida
    if not apikey:
        st.error(f"Por favor, insira e salve sua API Key do {provedor} antes de iniciar.")
        return None
    
    # Define os parâmetros corretos para cada provedor
    if provedor == "OpenAI":
        chat = config_models[provedor]["chat"](openai_api_key=apikey, model=modelo)
    elif provedor == "Groq":
        chat = config_models[provedor]["chat"](groq_api_key=apikey, model=modelo)
    
    st.session_state["chat"] = chat
    st.success("Oráculo iniciado com sucesso!")
    return chat

def main():
    chat_page()
    with st.sidebar:
        sidebar()
   
    
if __name__ == "__main__":
    main()