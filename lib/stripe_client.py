"""Stripe server-side helper reference. Secrets must stay server-only."""
import os
import stripe


def get_stripe_client():
    secret_key = os.environ["STRIPE_SECRET_KEY"]
    stripe.api_key = secret_key
    return stripe
