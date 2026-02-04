import streamlit as st

mensagens_exemplo = [
    {"role": "user", "content": "Olá, Oráculo!"},       
    {"role": "assistant", "content": "Olá! Como posso ajudar você hoje?"},  
    {"role": "user", "content": "Qual é a previsão do tempo para hoje?"},
    {"role": "assistant", "content": "Hoje o tempo estará ensolarado com temperaturas em torno de 25°C."}
]

def sidebar():
    st.sidebar.title("Configurações")
    st.sidebar.markdown("Aqui você pode adicionar configurações para o chat.")
    
def main():
    sidebar()
    
    
 if __name__ == "__main__":
    main()