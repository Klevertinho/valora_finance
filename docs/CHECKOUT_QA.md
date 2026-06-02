# QA de Checkout Stripe

## Fluxo esperado

1. Usuário abre `/precos`.
2. Clica em `Assinar agora`.
3. Se deslogado, vai para login/cadastro preservando intenção de assinatura.
4. Após login/cadastro, vai para Stripe Checkout.
5. Stripe retorna para `/billing/complete?session_id=...`.
6. Backend consulta Stripe, grava assinatura e libera dashboard.

## Testes obrigatórios

- Usuário sem assinatura não acessa `/dashboard`.
- Usuário sem assinatura é redirecionado para `/precos`.
- Plano inválido retorna erro/redirect seguro.
- `STRIPE_PRICE_PROFISSIONAL_MONTHLY` ausente não quebra o site público, apenas bloqueia checkout com mensagem.
- Webhook sem assinatura Stripe retorna 400.
- Webhook duplicado retorna 200 com `duplicate=true`.
- Portal sem assinatura redireciona para `/precos`.
- Portal com `stripe_customer_id` abre Stripe Billing Portal.

## Cartão de teste Stripe

Use apenas modo teste:

- Cartão: `4242 4242 4242 4242`
- Validade: qualquer data futura
- CVC: qualquer 3 dígitos

## Verificação no banco

Consultar tabela:

- `vf_subscriptions` em Postgres
- `vf_stripe_events` para eventos processados

O status que libera acesso é somente:

- `active`
- `trialing`
