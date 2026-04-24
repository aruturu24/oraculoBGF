from pathlib import Path

CSS_PATH = Path(__file__).resolve().parent / "app.css"


def load_app_css() -> str:
    try:
        css = CSS_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""
    return f"<style>\n{css}\n</style>"
