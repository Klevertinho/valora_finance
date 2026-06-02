# Deploy de Produção — Valora Finance

## Plataforma recomendada

Render Web Service com Python + Gunicorn.

## Build Command

```bash
pip install --upgrade pip && pip install -r requirements.txt
```

## Start Command

```bash
gunicorn "app:create_app()" --workers 2 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT
```

## Variáveis obrigatórias

```env
APP_ENV=production
PYTHON_VERSION=3.11.9
FLASK_SECRET_KEY=
DATABASE_URL=
VALORA_APP_URL=https://valora-finance.onrender.com
VALORA_SITE_URL=https://valora-finance.onrender.com
SITE_URL=https://valora-finance.onrender.com
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_PROFISSIONAL_MONTHLY=
STRIPE_TRIAL_DAYS=0
ENABLE_DEMO_ACCOUNT=0
```

## Neon/Postgres

Use a connection string do Neon no formato:

```txt
postgresql://user:password@host/db?sslmode=require
```

Não use SQLite em produção.

## Stripe

Webhook de produção/teste:

```txt
https://valora-finance.onrender.com/api/stripe/webhook
```

Eventos:

- `checkout.session.completed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.payment_succeeded`
- `invoice.payment_failed`

## Checklist antes de live

- `/healthz` mostra `database=postgres`.
- Conta nova aumenta `users_count`.
- Redeploy não reduz `users_count`.
- Checkout abre no Stripe.
- Webhook grava assinatura.
- Dashboard só libera após assinatura ativa/trial.
- Portal de assinatura abre para cliente pagante.
