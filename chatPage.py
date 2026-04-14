import os
import re
from urllib.parse import quote_plus

import pymysql
from dotenv import load_dotenv

import streamlit as st

load_dotenv()
from langchain_classic.memory import ConversationBufferMemory
from langchain_groq import ChatGroq
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.agent_toolkits.sql.prompt import SQL_PREFIX
from langchain_core.messages import HumanMessage

from login import login_page
from auth import is_admin
from admin_panel import admin_page

MAX_HISTORY_MESSAGES = 10
MAX_HISTORY_EXCHANGES_AGENT = 2

# Increment when SQL schema / agent rules change to force agent re-init in session.
AGENT_SCHEMA_VERSION = 4

DEFAULT_MODEL = "llama-3.3-70b-versatile"
BGF_LOGO = "https://www.bgfconsultoria.com.br/template/imagens/logo.png"

memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

MYSQL_TABLES = ["tbl_audit", "tbl_customer", "tbl_attachment_audit"]

ASSISTANT_PERSONA = """
PERSONA E ESTILO (OBRIGATORIO):
- Voce representa a BGF Consultoria em Engenharia no chat. Fale como um colega de trabalho em um app de mensagens entre dois profissionais: cordial, direto, natural, em primeira pessoa quando fizer sentido.
- Tom de assistente pessoal da equipe BGF: prestativo, profissional e leve (sem ser informal demais nem robotizado).
- Idioma: use SOMENTE portugues brasileiro. NUNCA responda em ingles, espanhol ou outro idioma, nem trechos em outro idioma.
"""

OUTPUT_SAFETY = """
CONFIDENCIALIDADE NA RESPOSTA AO USUARIO (OBRIGATORIO):
- Nas mensagens ao usuario, NUNCA exponha dados tecnicos de banco: IDs numericos (de tabelas, clientes e anexos), nomes de tabelas ou colunas, caminhos completos de servidor (file_Path), chaves internas ou estrutura do schema.
- Fale apenas com informacoes que fariam sentido para alguem sem acesso ao banco: nomes de clientes, titulos ou descricoes de auditoria, nomes de arquivos/anexos (file_Name) quando for util, datas, textos descritivos.
- EXCECAO OBRIGATORIA PARA AUDITORIAS/FICHAS: sempre que o usuario perguntar algo sobre auditorias/fichas (lista, detalhes, status, datas, pendencias, anexos da auditoria etc.), inclua explicitamente o ID da auditoria em cada item citado na resposta.
- Se precisar referir-se a um registro sem ID, use descricao (nome do cliente, periodo, titulo da auditoria, nome do arquivo).
"""

ATTACHMENT_TABLE_RULES = """
- tbl_attachment_audit: anexos/fotos ligados a auditorias. Colunas: id_audit (FK para tbl_audit), file_Name, file_Path.
- SEMPRE que consultar tbl_attachment_audit, faca JOIN com tbl_audit e tbl_customer, aplicando filtros de acesso.
- Para buscar anexo por nome de arquivo: use file_Name com LIKE.
- Quando mostrar imagens, inclua file_Path e file_Name no SELECT.
"""

SQL_EXTRA_INSTRUCTIONS = """
REGRAS OBRIGATORIAS:
""" + ASSISTANT_PERSONA + OUTPUT_SAFETY + """
- Tabelas disponiveis: tbl_audit, tbl_customer, tbl_attachment_audit.
- O usuario atual e o administrador com o valor informado abaixo. Em TODAS as consultas que envolvam tbl_customer (ou customer), voce DEVE incluir a condicao: customer.administrator = '<VALOR_ADMIN>' (use o nome exato da coluna do schema). Assim o usuario so acessa os clientes que ele administra.
- tbl_audit: qualquer resultado de tbl_audit DEVE ter customer_id que exista em tbl_customer. Ao consultar tbl_audit, faca JOIN com tbl_customer (audit.customer_id = customer.id ou equivalente) e aplique o filtro customer.administrator = valor do administrador atual, para retornar apenas auditorias dos clientes que o usuario administra.
""" + ATTACHMENT_TABLE_RULES + """
- Valor do administrador atual: {administrator}
"""

SQL_EXTRA_INSTRUCTIONS_ADMIN = """
REGRAS OBRIGATORIAS:
""" + ASSISTANT_PERSONA + OUTPUT_SAFETY + """
- Tabelas disponiveis: tbl_audit, tbl_customer, tbl_attachment_audit.
- O usuario atual e um ADMINISTRADOR GERAL. Ele tem acesso a TODOS os clientes e auditorias, sem qualquer filtro por administrator. NAO aplique filtro de administrator nas consultas.
- tbl_audit: ao consultar tbl_audit, pode fazer JOIN com tbl_customer (audit.customer_id = customer.id ou equivalente) quando necessario, mas sem filtrar por administrator.
""" + ATTACHMENT_TABLE_RULES + """
"""

SQL_EXTRA_INSTRUCTIONS_FILTERED = """
REGRAS OBRIGATORIAS:
""" + ASSISTANT_PERSONA + OUTPUT_SAFETY + """
- Tabelas disponiveis: tbl_audit, tbl_customer, tbl_attachment_audit.
- O usuario atual tem acesso SOMENTE aos clientes com os seguintes IDs: {customer_ids}. Em TODAS as consultas que envolvam tbl_customer, voce DEVE incluir a condicao: customer.id IN ({customer_ids}).
- tbl_audit: qualquer resultado de tbl_audit DEVE ter customer_id que exista nos IDs permitidos. Ao consultar tbl_audit, faca JOIN com tbl_customer (audit.customer_id = customer.id ou equivalente) e aplique o filtro customer.id IN ({customer_ids}).
""" + ATTACHMENT_TABLE_RULES + """
"""


CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    @keyframes fadeInUp {
        from { opacity: 0; transform: translateY(10px); }
        to   { opacity: 1; transform: translateY(0); }
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50%      { opacity: 0.35; }
    }

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* ── Sidebar ────────────────────────────────────────── */
    [data-testid="stSidebar"] {
        background: #002c97;
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] *,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color: #FFFFFF !important;
    }
    [data-testid="stSidebar"] hr {
        border-color: rgba(255,255,255,0.12) !important;
    }
    [data-testid="stSidebar"] .stButton button {
        transition: all 0.2s ease;
    }
    [data-testid="stSidebar"] .stButton button:hover {
        transform: translateY(-1px);
    }
    [data-testid="stSidebar"] .stButton button:active {
        transform: translateY(0);
    }
    [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {
        background: rgba(255,255,255,0.06) !important;
        color: rgba(255,255,255,0.85) !important;
        border-color: rgba(255,255,255,0.15) !important;
    }
    [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover {
        background: rgba(255,255,255,0.12) !important;
        color: #FFFFFF !important;
    }
    [data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {
        color: #FFFFFF !important;
    }

    /* ── Chat header ────────────────────────────────────── */
    .bgf-header {
        background: #FFFFFF;
        padding: 0.85rem 1.4rem;
        border-radius: 10px;
        margin-bottom: 1.2rem;
        display: flex;
        align-items: center;
        gap: 0.9rem;
        border-bottom: 3px solid #D4A017;
        box-shadow: 0 1px 5px rgba(0,0,0,0.05);
        animation: fadeInUp 0.3s ease both;
    }
    .bgf-header img {
        height: 38px;
    }
    .bgf-header-text h1 {
        color: #002c97 !important;
        margin: 0;
        font-size: 1.2rem;
        font-weight: 700;
    }
    .bgf-header-text p {
        color: #5A6175 !important;
        margin: 0.1rem 0 0 0;
        font-size: 0.78rem;
    }

    /* ── Chat messages ──────────────────────────────────── */
    [data-testid="stChatMessage"] {
        background: #FFFFFF;
        border: 1px solid #DDE1E9;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.4rem;
        animation: fadeInUp 0.3s ease both;
        transition: box-shadow 0.2s ease;
    }
    [data-testid="stChatMessage"]:hover {
        box-shadow: 0 2px 10px rgba(0,0,0,0.04);
    }

    /* ── Chat input ─────────────────────────────────────── */
    [data-testid="stChatInput"] textarea {
        border-radius: 10px !important;
        border: 2px solid #D0D5DE !important;
        background: #FFFFFF !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 0.92rem !important;
        padding: 0.75rem 1rem !important;
        transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
    }
    [data-testid="stChatInput"] textarea:focus {
        border-color: #D4A017 !important;
        box-shadow: 0 0 0 3px rgba(212,160,23,0.12) !important;
    }
    [data-testid="stChatInput"] button {
        transition: transform 0.15s ease !important;
    }
    [data-testid="stChatInput"] button:hover {
        transform: scale(1.08);
    }

    /* Chat bar: + (anexo) alinhado ao stChatInput, sem textos */
    [data-testid="stHorizontalBlock"]:has([data-testid="stChatInput"]) {
        align-items: flex-end !important;
        gap: 0.35rem !important;
        width: 100% !important;
        margin-top: 0.25rem !important;
    }
    [data-testid="stHorizontalBlock"]:has([data-testid="stChatInput"]) > [data-testid="column"]:first-child {
        flex: 0 0 2.85rem !important;
        width: 2.85rem !important;
        min-width: 2.85rem !important;
        max-width: 2.85rem !important;
        padding: 0 0 0.2rem 0 !important;
    }
    [data-testid="stHorizontalBlock"]:has([data-testid="stChatInput"]) > [data-testid="column"]:nth-child(2) {
        flex: 1 1 auto !important;
        min-width: 0 !important;
    }
    [data-testid="stHorizontalBlock"]:has([data-testid="stChatInput"]) [data-testid="column"]:first-child [data-testid="stWidgetLabel"] {
        display: none !important;
        height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
        overflow: hidden !important;
    }
    [data-testid="stHorizontalBlock"]:has([data-testid="stChatInput"]) [data-testid="column"]:first-child [data-testid="stFileUploader"] {
        margin-bottom: 0 !important;
    }
    [data-testid="stHorizontalBlock"]:has([data-testid="stChatInput"]) [data-testid="column"]:first-child [data-testid="stFileUploader"] > section {
        padding: 0 !important;
        border: none !important;
        background: transparent !important;
    }
    [data-testid="stHorizontalBlock"]:has([data-testid="stChatInput"]) [data-testid="column"]:first-child [data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"],
    [data-testid="stHorizontalBlock"]:has([data-testid="stChatInput"]) [data-testid="column"]:first-child [data-testid="stFileUploader"] > section:first-of-type {
        border: 2px solid #D0D5DE !important;
        border-radius: 50% !important;
        width: 2.75rem !important;
        height: 2.75rem !important;
        min-height: 2.75rem !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 0 !important;
        margin: 0 auto !important;
        background: #FFFFFF !important;
        transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
    }
    [data-testid="stHorizontalBlock"]:has([data-testid="stChatInput"]) [data-testid="column"]:first-child [data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"]:hover,
    [data-testid="stHorizontalBlock"]:has([data-testid="stChatInput"]) [data-testid="column"]:first-child [data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"]:focus-within {
        border-color: #D4A017 !important;
        box-shadow: 0 0 0 2px rgba(212,160,23,0.12) !important;
    }
    [data-testid="stHorizontalBlock"]:has([data-testid="stChatInput"]) [data-testid="column"]:first-child [data-testid="stFileUploader"] p,
    [data-testid="stHorizontalBlock"]:has([data-testid="stChatInput"]) [data-testid="column"]:first-child [data-testid="stFileUploader"] span,
    [data-testid="stHorizontalBlock"]:has([data-testid="stChatInput"]) [data-testid="column"]:first-child [data-testid="stFileUploader"] small,
    [data-testid="stHorizontalBlock"]:has([data-testid="stChatInput"]) [data-testid="column"]:first-child [data-testid="stFileUploader"] [data-testid="stCaption"],
    [data-testid="stHorizontalBlock"]:has([data-testid="stChatInput"]) [data-testid="column"]:first-child [data-testid="stFileUploader"] [data-testid="stMarkdownContainer"],
    [data-testid="stHorizontalBlock"]:has([data-testid="stChatInput"]) [data-testid="column"]:first-child [data-testid="stFileUploader"] .uploadedFileData,
    [data-testid="stHorizontalBlock"]:has([data-testid="stChatInput"]) [data-testid="column"]:first-child [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzoneInstructions"] {
        display: none !important;
    }
    [data-testid="stHorizontalBlock"]:has([data-testid="stChatInput"]) [data-testid="column"]:first-child [data-testid="stFileUploader"] button {
        font-size: 0 !important;
        width: 100% !important;
        height: 2.75rem !important;
        min-height: 2.75rem !important;
        border-radius: 50% !important;
        border: none !important;
        background: transparent !important;
        padding: 0 !important;
        margin: 0 !important;
        color: transparent !important;
    }
    [data-testid="stHorizontalBlock"]:has([data-testid="stChatInput"]) [data-testid="column"]:first-child [data-testid="stFileUploader"] button::after {
        content: "+" !important;
        font-size: 1.45rem !important;
        font-weight: 400 !important;
        color: #002c97 !important;
        line-height: 1 !important;
        display: block !important;
    }
    [data-testid="stHorizontalBlock"]:has([data-testid="stChatInput"]) [data-testid="column"]:first-child [data-testid="stFileUploader"] .uploadedFile {
        display: none !important;
    }
    [data-testid="stHorizontalBlock"]:has([data-testid="stChatInput"]) [data-testid="column"]:first-child [data-testid="stFileUploader"]:has(.uploadedFile) section[data-testid="stFileUploaderDropzone"],
    [data-testid="stHorizontalBlock"]:has([data-testid="stChatInput"]) [data-testid="column"]:first-child [data-testid="stFileUploader"]:has(.uploadedFile) > section:first-of-type {
        border-color: #D4A017 !important;
        background: rgba(212,160,23,0.08) !important;
    }
    [data-testid="stHorizontalBlock"]:has([data-testid="stChatInput"]) [data-testid="column"]:first-child [data-testid="stFileUploader"]:has(.uploadedFile) button::after {
        content: "✓" !important;
        font-size: 1.05rem !important;
        color: #D4A017 !important;
    }

    /* ── Sidebar logo ───────────────────────────────────── */
    .sidebar-logo {
        text-align: center;
        padding: 0.4rem 0 0.5rem 0;
    }
    .sidebar-logo-bg {
        display: inline-block;
        background: #FFFFFF;
        border-radius: 10px;
        padding: 0.55rem 1.1rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    }
    .sidebar-logo-bg img {
        height: 34px;
        display: block;
    }

    /* ── Sidebar user card ──────────────────────────────── */
    .sidebar-user-card {
        background: rgba(255,255,255,0.06);
        border-radius: 10px;
        padding: 0.8rem 1rem;
        margin-bottom: 0.5rem;
        border: 1px solid rgba(255,255,255,0.08);
        transition: background 0.2s ease;
    }
    .sidebar-user-card:hover {
        background: rgba(255,255,255,0.10);
    }
    .sidebar-user-card .user-name {
        font-size: 0.92rem;
        font-weight: 600;
        color: #FFFFFF;
        margin-bottom: 0.15rem;
    }
    .sidebar-user-card .user-role {
        font-size: 0.76rem;
        color: rgba(255,255,255,0.55);
    }
    .sidebar-user-card .user-status {
        margin-top: 0.35rem;
        font-size: 0.76rem;
        color: rgba(255,255,255,0.55);
    }
    .status-dot {
        display: inline-block;
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: #34D399;
        margin-right: 5px;
        vertical-align: middle;
        animation: pulse 2s ease-in-out infinite;
    }

    /* ── Empty state ────────────────────────────────────── */
    .empty-state {
        text-align: center;
        padding: 4rem 2rem 2rem 2rem;
        color: #5A6175;
        animation: fadeInUp 0.4s ease both;
    }
    .empty-state h3 {
        color: #002c97;
        font-weight: 700;
        font-size: 1.15rem;
        margin-bottom: 0.4rem;
    }
    .empty-state p {
        font-size: 0.88rem;
        max-width: 380px;
        margin: 0 auto;
        line-height: 1.6;
    }

    /* ── Page header (admin) ─────────────────────────────── */
    .page-header {
        padding: 0.3rem 0 0.8rem 0;
        animation: fadeInUp 0.3s ease both;
    }
    .page-header h1 {
        color: #002c97 !important;
        font-size: 1.5rem;
        font-weight: 700;
        margin: 0;
    }
    .page-header p {
        color: #5A6175;
        font-size: 0.88rem;
        margin-top: 0.2rem;
    }
    .gold-bar {
        width: 48px;
        height: 3px;
        background: #D4A017;
        border-radius: 2px;
        margin-top: 0.55rem;
    }

    /* ── Global micro-interactions ────────────────────────── */
    .stButton > button,
    .stFormSubmitButton > button {
        transition: all 0.2s ease !important;
    }
    .stButton > button:hover,
    .stFormSubmitButton > button:hover {
        transform: translateY(-1px);
    }
    .stButton > button:active,
    .stFormSubmitButton > button:active {
        transform: translateY(0);
    }
    .stFormSubmitButton > button {
        color: #FFFFFF !important;
    }

    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] textarea {
        transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
    }
    [data-testid="stTextInput"] input:focus,
    [data-testid="stTextArea"] textarea:focus {
        border-color: #D4A017 !important;
        box-shadow: 0 0 0 2px rgba(212,160,23,0.12) !important;
    }

    /* ── Tabs ────────────────────────────────────────────── */
    .stTabs [data-baseweb="tab"] {
        transition: color 0.2s ease;
    }

    /* ── Nav label ───────────────────────────────────────── */
    .nav-label {
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: rgba(255,255,255,0.35);
        margin-bottom: 0.4rem;
        font-weight: 600;
    }
</style>
"""


def get_sql_prefix(administrador: str, allowed_customers: str = "all") -> str:
    admin_val = (administrador or "").strip()
    if admin_val.lower() == "admin":
        return SQL_PREFIX + SQL_EXTRA_INSTRUCTIONS_ADMIN
    if not admin_val:
        admin_val = "(nao definido)"

    if allowed_customers and allowed_customers != "all":
        ids_str = allowed_customers
        return SQL_PREFIX + SQL_EXTRA_INSTRUCTIONS_FILTERED.format(customer_ids=ids_str)

    return SQL_PREFIX + SQL_EXTRA_INSTRUCTIONS.format(administrator=admin_val)


_IMG_PATH_RE = re.compile(
    r"[\w/\\:\.\-~%]{3,400}\.(?:jpg|jpeg|png|gif|webp|bmp)",
    re.IGNORECASE,
)


def _extract_image_paths_from_text(text: str) -> list[str]:
    found = _IMG_PATH_RE.findall(text or "")
    out: list[str] = []
    for raw in found:
        p = raw.strip("'\",()[]{}|;").rstrip(",")
        if p and p not in out:
            out.append(p)
    return out


def _extract_paths_from_agent_steps(intermediate_steps) -> list[str]:
    if not intermediate_steps:
        return []
    chunks: list[str] = []
    for step in intermediate_steps:
        if not isinstance(step, (list, tuple)) or len(step) < 2:
            continue
        action, observation = step[0], step[1]
        tool = getattr(action, "tool", None) or ""
        if tool != "sql_db_query" or not isinstance(observation, str):
            continue
        chunks.append(observation)
    return _extract_image_paths_from_text("\n".join(chunks))


def _verify_attachment_paths_for_user(paths: list[str], user: dict) -> list[tuple[str, str | None]]:
    paths = [p.strip() for p in paths if p and str(p).strip()]
    if not paths:
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            ordered.append(p)
    paths = ordered[:30]

    host = os.getenv("MYSQL_HOST")
    user_mysql = os.getenv("MYSQL_USER")
    password = os.getenv("MYSQL_PASSWORD")
    database = os.getenv("MYSQL_DATABASE", "")
    if not all([host, user_mysql, password]):
        return []

    administrador = (user or {}).get("administrator", "") or ""
    allowed = (user or {}).get("allowed_customers", "all")

    placeholders = ",".join(["%s"] * len(paths))

    try:
        conn = pymysql.connect(
            host=host,
            user=user_mysql,
            password=password,
            database=database,
        )
    except pymysql.Error:
        return []

    try:
        cur = conn.cursor()
        if administrador.strip().lower() == "admin":
            sql = f"""
                SELECT DISTINCT att.`file_Path`, att.`file_Name`
                FROM `tbl_attachment_audit` att
                INNER JOIN `tbl_audit` au ON att.`id_audit` = au.`id`
                INNER JOIN `tbl_customer` c ON au.`customer_id` = c.`id`
                WHERE att.`file_Path` IN ({placeholders})
            """
            cur.execute(sql, paths)
        elif allowed and allowed != "all":
            ids = [x.strip() for x in allowed.split(",") if x.strip()]
            if not ids:
                return []
            id_ph = ",".join(["%s"] * len(ids))
            sql = f"""
                SELECT DISTINCT att.`file_Path`, att.`file_Name`
                FROM `tbl_attachment_audit` att
                INNER JOIN `tbl_audit` au ON att.`id_audit` = au.`id`
                INNER JOIN `tbl_customer` c ON au.`customer_id` = c.`id`
                WHERE att.`file_Path` IN ({placeholders})
                  AND c.`id` IN ({id_ph})
            """
            cur.execute(sql, paths + ids)
        else:
            sql = f"""
                SELECT DISTINCT att.`file_Path`, att.`file_Name`
                FROM `tbl_attachment_audit` att
                INNER JOIN `tbl_audit` au ON att.`id_audit` = au.`id`
                INNER JOIN `tbl_customer` c ON au.`customer_id` = c.`id`
                WHERE att.`file_Path` IN ({placeholders})
                  AND c.`administrator` = %s
            """
            cur.execute(sql, paths + [administrador])
        rows = cur.fetchall()
        ok = {r[0]: (r[1] if len(r) > 1 else None) for r in rows if r and r[0]}
        return [(p, ok.get(p)) for p in paths if p in ok]
    except pymysql.Error:
        return []
    finally:
        conn.close()


def _resolve_attachment_fs_path(db_path: str) -> str | None:
    db_path = (db_path or "").strip()
    if not db_path:
        return None
    root = (os.getenv("ATTACHMENT_FILES_ROOT") or "").strip()
    if os.path.isabs(db_path) and os.path.isfile(db_path):
        return db_path
    if root:
        joined = os.path.normpath(os.path.join(root, db_path.lstrip("/\\")))
        if os.path.isfile(joined):
            return joined
    if os.path.isfile(db_path):
        return db_path
    return None


def _resolved_attachments_for_display(
    verified: list[tuple[str, str | None]],
) -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    seen_fs: set[str] = set()
    for db_path, fname in verified:
        rp = _resolve_attachment_fs_path(db_path)
        if not rp or rp in seen_fs:
            continue
        seen_fs.add(rp)
        cap = fname or os.path.basename(db_path)
        out.append((rp, cap))
    return out


def _user_wants_audit_images(message: str) -> bool:
    m = (message or "").lower()
    triggers = (
        "imagem",
        "imagens",
        "foto",
        "fotos",
        "fotografia",
        "anexo",
        "anexos",
        "mostrar",
        "mostre",
        "exibir",
        "exiba",
        "ver a foto",
        "ver as fotos",
        "ver foto",
        "ver imagem",
        "manda a",
        "manda as",
        "envia a",
        "anexa",
    )
    return any(t in m for t in triggers)


def _should_show_images(user_message: str, has_upload_filename_hint: bool) -> bool:
    return _user_wants_audit_images(user_message) or has_upload_filename_hint


def _input_with_history(memoria, input_user: str) -> str:
    msgs = memoria.buffer_as_messages
    n = 2 * MAX_HISTORY_EXCHANGES_AGENT
    recent = msgs[-n:] if len(msgs) > n else msgs
    if not recent:
        return input_user
    parts = ["Contexto da conversa anterior:"]
    for m in recent:
        role = "Usuario" if m.type == "human" else "Assistente"
        parts.append(f"{role}: {m.content}")
    parts.append(f"\nPergunta atual: {input_user}")
    return "\n".join(parts)


def _messages_with_history(memoria, input_user: str):
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


def _ensure_model_initialized():
    if st.session_state.get("agent_schema_version") != AGENT_SCHEMA_VERSION:
        st.session_state.pop("chat", None)
        st.session_state.pop("agent", None)
        st.session_state["agent_schema_version"] = AGENT_SCHEMA_VERSION

    if st.session_state.get("chat") is not None:
        return

    apikey = os.getenv("GROQ_API_KEY", "")
    if not apikey:
        st.error("Chave GROQ_API_KEY nao encontrada. Configure o arquivo .env.")
        st.stop()

    user = st.session_state.get("user", {})
    administrador = user.get("administrator", "")
    allowed_customers = user.get("allowed_customers", "all")

    chat = ChatGroq(groq_api_key=apikey, model=DEFAULT_MODEL, max_tokens=4096)
    st.session_state["chat"] = chat

    db = get_mysql_db()
    if db:
        prefix = get_sql_prefix(administrador, allowed_customers)
        st.session_state["agent"] = create_sql_agent(
            chat,
            db=db,
            agent_type="tool-calling",
            prefix=prefix,
            max_iterations=6,
            agent_executor_kwargs={"return_intermediate_steps": True},
        )
    else:
        st.session_state["agent"] = None


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

    memoria = st.session_state.get("memoria", memory)
    chat_model = st.session_state.get("chat")

    total_mensagens = len(memoria.buffer_as_messages)
    if "mensagens_exibidas" not in st.session_state:
        st.session_state["mensagens_exibidas"] = total_mensagens

    mensagens_antigas = memoria.buffer_as_messages[:st.session_state["mensagens_exibidas"]]

    if not mensagens_antigas:
        st.markdown(
            """
            <div class="empty-state">
                <h3>Como posso ajudar?</h3>
                <p>Faca uma pergunta sobre seus dados, clientes ou auditorias.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    for mensagem in mensagens_antigas:
        with st.chat_message(mensagem.type):
            st.markdown(mensagem.content)

    _att_nonce = st.session_state.get("_attachment_uploader_nonce", 0)
    _col_attach, _col_chat = st.columns([0.07, 0.93], gap="small")
    with _col_attach:
        uf = st.file_uploader(
            "",
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
        if chat_model is None:
            st.error("O modelo nao foi inicializado. Verifique a configuracao.")
        else:
            with st.chat_message("human"):
                st.markdown(input_user)

            memoria.chat_memory.add_user_message(input_user)
            st.session_state["mensagens_exibidas"] += 1

            with st.chat_message("ai"):
                mensagem_placeholder = st.empty()
                agent = st.session_state.get("agent")
                upload_hint = st.session_state.pop("attachment_search_filename", None)
                if upload_hint:
                    st.session_state["_attachment_uploader_nonce"] = (
                        st.session_state.get("_attachment_uploader_nonce", 0) + 1
                    )
                verified_attachments: list[tuple[str, str | None]] = []
                show_imgs = False
                if agent:
                    input_with_ctx = _input_with_history(memoria, input_user)
                    if upload_hint:
                        safe_hint = re.sub(r'[^\w.\-]', '_', upload_hint)
                        input_with_ctx += f"\n\nBuscar imagem: {safe_hint}"
                    try:
                        result = agent.invoke({"input": input_with_ctx})
                        raw_output = result.get("output", "")
                        if not raw_output or raw_output.startswith("<function") or "tool_input" in raw_output:
                            resposta_completa = "Desculpe, nao consegui processar sua solicitacao. Por favor, tente reformular a pergunta."
                        else:
                            resposta_completa = raw_output
                        steps = result.get("intermediate_steps") or []
                    except Exception as e:
                        resposta_completa = "Ocorreu um erro ao processar. Tente novamente."
                        steps = []
                    raw_paths = _extract_paths_from_agent_steps(steps)
                    user_obj = st.session_state.get("user", {})
                    verified_attachments = _verify_attachment_paths_for_user(
                        raw_paths, user_obj
                    )
                    show_imgs = _should_show_images(input_user, bool(upload_hint))
                else:
                    resposta_completa = ""
                    messages = _messages_with_history(memoria, input_user)
                    for chunk in chat_model.stream(messages):
                        resposta_completa += chunk.content
                        mensagem_placeholder.markdown(resposta_completa)
                if agent:
                    mensagem_placeholder.markdown(resposta_completa)
                    if show_imgs and verified_attachments:
                        for fs_path, caption in _resolved_attachments_for_display(
                            verified_attachments
                        ):
                            st.image(fs_path, caption=caption)

            memoria.chat_memory.add_ai_message(resposta_completa)
            st.session_state["mensagens_exibidas"] += 1

        st.session_state["memoria"] = memoria
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

    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    sidebar()

    page = st.session_state.get("page", "chat")
    user = st.session_state.get("user", {})

    if page == "admin" and is_admin(user):
        admin_page()
    else:
        chat_page()


if __name__ == "__main__":
    main()
