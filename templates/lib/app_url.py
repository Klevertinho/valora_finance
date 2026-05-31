"""Production URL helper reference for future extraction from app.py."""
import os


def get_app_url(default_host: str = "https://valorafinance.com.br") -> str:
    return (
        os.getenv("VALORA_APP_URL")
        or os.getenv("APP_URL")
        or os.getenv("SITE_URL")
        or os.getenv("VALORA_SITE_URL")
        or os.getenv("NEXT_PUBLIC_APP_URL")
        or os.getenv("NEXT_PUBLIC_SITE_URL")
        or default_host
    ).rstrip("/")
