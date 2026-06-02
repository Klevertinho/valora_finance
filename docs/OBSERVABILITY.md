# Observabilidade

## Onde ver logs

- Render > Web Service > Logs
- Stripe > Developers > Webhooks > Attempts
- Neon > Monitoring / Query insights

## Eventos importantes

- `checkout.session.completed`
- `customer.subscription.updated`
- `invoice.payment_failed`

## Logs seguros

Não logar:

- senha
- token
- secret Stripe
- webhook secret
- connection string
- payload completo de pagamento

Logar apenas:

- tipo do evento
- event id
- status resumido
- erro genérico
