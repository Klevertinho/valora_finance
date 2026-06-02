# Incident Runbook

## Checkout fora do ar

1. Verificar Render Logs.
2. Confirmar `STRIPE_SECRET_KEY`.
3. Confirmar `STRIPE_PRICE_PROFISSIONAL_MONTHLY`.
4. Testar `/precos` e `/assinar/profissional`.
5. Se necessário, pausar tráfego pago.

## Pagamento aprovado, mas dashboard não liberou

1. Verificar Stripe > Developers > Webhooks.
2. Verificar se evento `checkout.session.completed` teve status 2xx.
3. Conferir `vf_subscriptions` pelo email/customer.
4. Cliente pode fazer login novamente; o sistema tenta sincronizar assinatura pelo email Stripe.

## Banco fora do ar

1. Verificar Neon status.
2. Confirmar `DATABASE_URL` no Render.
3. Abrir `/healthz`.
4. Se app não iniciar, rollback do último deploy no Render.

## Conta sumindo

1. Abrir `/healthz`.
2. Confirmar `database=postgres` e `database_url_present=true`.
3. Confirmar que não existe `ENABLE_DEMO_ACCOUNT=1` em produção.
4. Confirmar que o Render não está sem `DATABASE_URL`.

## Rotação de secrets

Rotacionar no provedor, atualizar Render Environment e fazer redeploy.
