import os

MAX_HISTORY_MESSAGES = 20
MAX_HISTORY_EXCHANGES_AGENT = 2

# Increment when SQL schema / agent rules change to force agent re-init in session.
AGENT_SCHEMA_VERSION = 22

DEFAULT_MODEL = (os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash")
BGF_LOGO = "https://www.bgfconsultoria.com.br/template/imagens/logo.png"

CHAT_MYSQL_TABLES = ("tbl_audit", "tbl_customer", "tbl_attachment_audit", "lst_category")
MAX_ATTACHMENT_PATHS = 30
