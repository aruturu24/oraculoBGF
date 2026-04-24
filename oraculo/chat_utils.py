import re
import unicodedata
from typing import Any

from oraculo.constants import DEFAULT_MODEL

IMG_PATH_RE = re.compile(
    r"[\w/\\:\.\-~%]{3,400}\.(?:jpg|jpeg|png|gif|webp|bmp)",
    re.IGNORECASE,
)

AUDIT_IMAGE_TRIGGERS = (
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

DB_KEYWORDS = (
    "auditoria",
    "auditorias",
    "ficha",
    "fichas",
    "resumo",
    "visao geral",
    "panorama",
    "status geral",
    "cliente",
    "clientes",
    "anexo",
    "anexos",
    "foto",
    "fotos",
    "imagem",
    "imagens",
    "tbl_",
    "banco",
    "mysql",
    "sql",
    "consulta",
    "consultar",
    "listar",
    "liste",
    "dados",
    "status",
    "risco",
    "risc",
    "categoria",
    "categorias",
    "nivel",
    "pendencia",
    "pendencias",
)

AUDIT_SUMMARY_TRIGGERS = (
    "resumo",
    "visao geral",
    "panorama",
    "status geral",
    "resuma",
    "resumir",
)

AUDIT_SUMMARY_CONTEXT_KEYWORDS = (
    "auditoria",
    "auditorias",
    "ficha",
    "fichas",
    "cliente",
    "clientes",
    "categoria",
    "categorias",
    "risco",
)

MODEL_IDENTITY_TRIGGERS = (
    "qual modelo",
    "que modelo",
    "modelo de ia",
    "modelo voce",
    "quem e voce",
    "quem e vc",
    "quem voce e",
    "quem e a ia",
    "quem e a inteligencia artificial",
)

UNCERTAIN_REPLIES = {
    "i don't know",
    "i dont know",
    "i do not know",
    "nao sei",
}

INTERNAL_PLANNING_PREFIXES = (
    "finally i will",
    "first i will",
    "next i will",
    "agora vou",
    "primeiro vou",
    "depois vou",
    "finalmente vou",
)

INTERNAL_PLANNING_KEYWORDS = (
    "construct my query",
    "build my query",
    "run my query",
    "execute my query",
    "consulta sql",
    "montar a consulta",
    "construir a consulta",
    "executar a consulta",
)

INTERMEDIATE_PROGRESS_PHRASES = (
    "vou buscar",
    "vou verificar",
    "vou checar",
    "vou confirmar",
    "vou consultar",
    "vou levantar",
    "vou olhar",
    "preciso confirmar",
    "preciso verificar",
    "deixe eu verificar",
    "ja te retorno",
    "retorno com",
    "buscar o esquema",
    "confirmar os nomes das colunas",
)

REPLY_TERM_REPLACEMENTS = (
    (re.compile(r"\blst_category\b", re.IGNORECASE), "categorias"),
    (re.compile(r"\btbl_audit\b", re.IGNORECASE), "fichas"),
    (re.compile(r"\btbl_customer\b", re.IGNORECASE), "clientes"),
    (re.compile(r"\btbl_attachment_audit\b", re.IGNORECASE), "anexos"),
    (re.compile(r"\bcode_category\b", re.IGNORECASE), "codigo da categoria"),
    (re.compile(r"\brisc\b", re.IGNORECASE), "risco"),
)


def extract_image_paths_from_text(text: str) -> list[str]:
    found = IMG_PATH_RE.findall(text or "")
    out: list[str] = []
    for raw in found:
        path = raw.strip("'\",()[]{}|;").rstrip(",")
        if path and path not in out:
            out.append(path)
    return out


def extract_paths_from_agent_messages(messages: Any) -> list[str]:
    if not messages:
        return []

    sql_chunks: list[str] = []
    for message in reversed(messages):
        msg_type = getattr(message, "type", "")
        if msg_type == "human":
            break
        if msg_type != "tool":
            continue
        tool = getattr(message, "name", "") or ""
        if tool and tool != "sql_db_query":
            continue
        content = coerce_text_content(getattr(message, "content", ""))
        if content:
            sql_chunks.append(content)

    if not sql_chunks:
        return []

    sql_chunks.reverse()
    return extract_image_paths_from_text("\n".join(sql_chunks))


def coerce_text_content(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        maybe_text = value.get("text")
        return maybe_text if isinstance(maybe_text, str) else str(value)
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            text = coerce_text_content(item).strip()
            if text:
                parts.append(text)
        return "\n".join(parts).strip()
    return str(value)


def normalize_user_text(text: str) -> str:
    lowered = (text or "").strip().lower()
    decomposed = unicodedata.normalize("NFD", lowered)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def is_model_identity_question(message: str) -> bool:
    normalized = normalize_user_text(message)
    return any(trigger in normalized for trigger in MODEL_IDENTITY_TRIGGERS)


def should_use_sql_agent(message: str, has_upload_filename_hint: bool) -> bool:
    if has_upload_filename_hint:
        return True

    normalized = normalize_user_text(message)
    if not normalized:
        return False
    if is_model_identity_question(normalized):
        return False
    return any(keyword in normalized for keyword in DB_KEYWORDS)


def should_show_images(user_message: str, has_upload_filename_hint: bool) -> bool:
    normalized = (user_message or "").lower()
    wants_images = any(trigger in normalized for trigger in AUDIT_IMAGE_TRIGGERS)
    return wants_images or has_upload_filename_hint


def is_audit_summary_request(message: str) -> bool:
    normalized = normalize_user_text(message)
    if not normalized:
        return False
    has_summary_intent = any(trigger in normalized for trigger in AUDIT_SUMMARY_TRIGGERS)
    has_audit_context = any(
        keyword in normalized for keyword in AUDIT_SUMMARY_CONTEXT_KEYWORDS
    )
    return has_summary_intent and has_audit_context


def is_intermediate_agent_reply(reply: str) -> bool:
    normalized = normalize_user_text(reply)
    if not normalized:
        return False
    return any(phrase in normalized for phrase in INTERMEDIATE_PROGRESS_PHRASES)


def sanitize_assistant_reply_terms(reply: str) -> str:
    text = reply or ""
    for pattern, replacement in REPLY_TERM_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    return text


def normalize_assistant_reply(reply: str, user_message: str) -> str:
    text = (reply or "").strip()
    if not text:
        return "Desculpe, nao consegui gerar uma resposta agora. Tente novamente em instantes."

    normalized = (
        normalize_user_text(text)
        .replace("`", "")
        .replace(".", "")
        .replace(",", "")
        .replace("!", "")
        .replace("?", "")
        .replace(":", "")
        .replace(";", "")
        .replace('"', "")
        .replace("'", "")
        .strip()
    )

    if is_model_identity_question(user_message) and (
        normalized in UNCERTAIN_REPLIES
        or "i don't know" in normalized
        or "i do not know" in normalized
    ):
        return f"Sou o Oraculo BGF e opero com o modelo {DEFAULT_MODEL} da Google Gemini."

    if normalized in UNCERTAIN_REPLIES:
        return "Nao tenho contexto suficiente para responder isso com precisao. Pode detalhar um pouco mais o que voce precisa?"

    is_planning_prefix = normalized.startswith(INTERNAL_PLANNING_PREFIXES)
    has_planning_keyword = any(keyword in normalized for keyword in INTERNAL_PLANNING_KEYWORDS)
    if (is_planning_prefix and has_planning_keyword) or normalized in INTERNAL_PLANNING_KEYWORDS:
        return (
            "Desculpe, tive uma falha ao montar a resposta final. "
            "Tente novamente com a mesma pergunta."
        )

    if is_intermediate_agent_reply(text):
        return (
            "Desculpe, tive uma falha ao concluir a consulta em uma unica resposta. "
            "Pode reenviar a mesma pergunta?"
        )

    return sanitize_assistant_reply_terms(text)
