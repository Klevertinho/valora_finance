# Correção de login, acesso e assinatura

Esta versão corrige dois problemas críticos:

1. O botão normal **Entrar** não deve herdar plano antigo salvo na sessão.
2. Usuário que já pagou não deve ficar preso em `/precos` caso o webhook do Stripe tenha atrasado ou falhado.

## Comportamento novo

- `/login` normal limpa intenção antiga de assinatura.
- `/assinar/inicial` e `/assinar/profissional` continuam preservando o plano escolhido.
- Depois do login, se houver assinatura ativa/trialing registrada no banco, entra no dashboard.
- Se o webhook não registrou a assinatura, o sistema busca no Stripe pelo email do usuário, salva a assinatura e libera o acesso.
- Conta sem assinatura continua bloqueada e vai para `/precos`.

## Variáveis necessárias

- `STRIPE_SECRET_KEY`
- `STRIPE_PRICE_INICIAL_MONTHLY`
- `STRIPE_PRICE_PROFISSIONAL_MONTHLY`
- `STRIPE_WEBHOOK_SECRET`
- `DATABASE_URL`

## Teste

1. Faça login pelo botão Entrar do header.
2. Se o usuário não tiver assinatura, deve ir para `/precos`.
3. Se o usuário tiver assinatura ativa/trialing no Stripe com o mesmo email, deve entrar no dashboard.
4. Clique em Assinar Profissional deslogado: deve ir para login/cadastro e depois checkout.
