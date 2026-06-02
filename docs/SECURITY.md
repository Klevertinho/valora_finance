# Segurança do Projeto

## Secrets

Nunca commitar:

- `.env`
- `DATABASE_URL`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- chaves Supabase service role
- tokens ou senhas de banco

Use apenas `.env.example` como referência.

## Produção

No Render, obrigatórios:

- `APP_ENV=production`
- `FLASK_SECRET_KEY`
- `DATABASE_URL`
- `VALORA_APP_URL`
- `VALORA_SITE_URL`
- `SITE_URL`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_PROFISSIONAL_MONTHLY`

## Banco

Produção deve usar Neon/Postgres. O app falha em produção se `DATABASE_URL` não existir.

## Stripe

- Checkout é criado somente no backend.
- Frontend não define preço.
- `plan` é validado server-side.
- O webhook valida assinatura Stripe.
- Eventos são idempotentes via tabela `stripe_events`.
- `checkout=success` sozinho não libera o sistema.

## Rotação de chaves

Rotacione imediatamente se uma chave/senha foi exposta em chat, print, GitHub ou log.
