"""Subscription status helpers used by the Flask runtime and future repository layer."""

ACTIVE_STATUSES = {"active", "trialing"}

STATUS_LABELS = {
    "active": "Ativo",
    "trialing": "Em teste",
    "past_due": "Pagamento pendente",
    "canceled": "Cancelado",
    "incomplete": "Incompleto",
    "unpaid": "Não pago",
}


def has_access(status: str | None) -> bool:
    return status in ACTIVE_STATUSES
