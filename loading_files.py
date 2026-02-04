import os
from dotenv import load_dotenv

load_dotenv()
if "USER_AGENT" not in os.environ:
    os.environ["USER_AGENT"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"

from langchain_community.document_loaders import (WebBaseLoader, YoutubeLoader, PyPDFLoader, Docx2txtLoader, CSVLoader, TextLoader)
from youtube_transcript_api import YouTubeTranscriptApi


url = "https://www.google.com"


def loading_web(url):
    user_agent = os.environ.get("USER_AGENT", "oraculo/1.0 (contato: seu-email@exemplo.com)")
    loader = WebBaseLoader(
        url,
        requests_kwargs={
            "headers": {
                "User-Agent": user_agent,
            }
        },
    )
    documents_list = loader.load()
    documento = '\n\n'.join([doc.page_content for doc in documents_list])
    return documento
    


urlvideo = "y15070biffg"

def loading_youtube(urlvideo):

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(urlvideo)
        # Prioriza português: primeiro pt-BR, depois pt
        idiomas_preferidos = ['pt-BR', 'pt']
        documento_encontrado = False
        
        for idioma in idiomas_preferidos:
            for transcript in transcript_list:
                if transcript.language_code == idioma:
                    transcript_data = transcript.fetch()
                    documento = '\n\n'.join([item.text for item in transcript_data])
                    print(documento)
                    return documento
                    documento_encontrado = True
                    break
            if documento_encontrado:
                break
    except Exception as e:
        print(f"Erro ao carregar transcrição do YouTube: {e}")
        print(f"Video ID: {urlvideo}")
        print("Possíveis causas: vídeo sem transcrição disponível, transcrição bloqueada ou erro na API.")


def loading_csv(file_path):
    loader = CSVLoader(file_path=file_path)
    documents_list = loader.load()
    documento = '\n\n'.join([doc.page_content for doc in documents_list])
    return documento

def loading_txt(file_path):
    loader = TextLoader(file_path)
    documents_list = loader.load()
    documento = '\n\n'.join([doc.page_content for doc in documents_list])
    return documento

def loading_pdf(file_path):
    loader = PyPDFLoader(file_path)
    documents_list = loader.load()
    documento = '\n\n'.join([doc.page_content for doc in documents_list])
    return documento

# def loading_docx(file_path):
#     loader = Docx2txtLoader(file_path)
#     documents_list = loader.load()
#     documento = '\n\n'.join([doc.page_content for doc in documents_list])
#     return documento

# def loading_xlsx(file_path):
#     loader = Xlsx2txtLoader(file_path)
#     documents_list = loader.load()
#     documento = '\n\n'.join([doc.page_content for doc in documents_list])
#     return documento



# Exemplo de uso:
# file_path = r"C:\Users\arysson.silva\Documents\projetinhos\python\oraculo\files\xls\Plano Estratégico - 29.07.25.xlsx - Dados do plano de marketing.csv"
# documento = loading_xlsx(file_path)
# print(documento)