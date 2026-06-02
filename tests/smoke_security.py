"""Smoke checks defensivos para Valora Finance.
Executar localmente: python tests/smoke_security.py
"""
import os
import re
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-key-with-more-than-40-chars")
os.environ.setdefault("VALORA_FORCE_HTTPS", "0")
os.environ.setdefault("APP_ENV", "test")
# precisa ser setado antes de importar app.py porque app = create_app() roda no import
fd, path = tempfile.mkstemp(prefix="valora_test_", suffix=".db")
os.close(fd)
os.environ["VALORA_DATABASE_PATH"] = path
os.environ.pop("DATABASE_URL", None)

from app import create_app  # noqa: E402


def csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return match.group(1) if match else ""


def check(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main():
    app = create_app()
    app.config.update(TESTING=True)
    client = app.test_client()

    r = client.get("/")
    check(r.status_code == 200, "landing deveria retornar 200")
    check(r.headers.get("X-Content-Type-Options") == "nosniff", "header nosniff ausente")
    check("Content-Security-Policy" in r.headers, "CSP ausente")

    r = client.get("/dashboard")
    check(r.status_code in {302, 303}, "redirect esperado")
    check("/login" in r.headers.get("Location", ""), "dashboard deslogado deve ir para login")

    r = client.get("/cadastro")
    token = csrf(r.get_data(as_text=True))
    check(bool(token), "csrf ausente")
    r = client.post("/cadastro", data={
        "csrf_token": token,
        "full_name": "Teste Seguro",
        "email": "teste-seguro@example.com",
        "password": "senha_teste_segura_123",  # nosec B105 - credencial fictícia de teste
        "business_name": "Empresa Teste",
        "business_type": "Loja",
        "load_demo": "0",
    })
    check(r.status_code in {302, 303}, "redirect esperado")
    check("/precos" in r.headers.get("Location", ""), "redirect para preços esperado")

    r = client.get("/dashboard")
    check(r.status_code in {302, 303}, "redirect esperado")
    check("/precos" in r.headers.get("Location", ""), "redirect para preços esperado")

    r = client.get("/assinar/plano-invalido")
    check(r.status_code in {302, 303}, "redirect esperado")
    check("/precos" in r.headers.get("Location", ""), "redirect para preços esperado")

    r = client.post("/api/stripe/webhook", data=b"{}")
    check(r.status_code in {400, 401}, "webhook inválido deve ser rejeitado")

    r = client.get("/healthz")
    check(r.status_code == 200, "landing deveria retornar 200")
    body = r.get_json()
    check(body["database"] == "sqlite", "teste local deve usar sqlite")
    check(body["users_count"] >= 1, "healthz deve retornar users_count")

    print("smoke_security: ok")


if __name__ == "__main__":
    main()
