# Valora Finance — Segurança e QA

## Segurança aplicada

- Sessão com `HttpOnly`, `SameSite=Lax` e `Secure` em produção.
- Headers de segurança: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy` e HSTS quando HTTPS estiver ativo.
- CSRF em formulários POST internos, exceto webhook Stripe, que usa assinatura própria.
- Rate limit simples para login e cadastro por IP.
- Redirecionamento interno validado para evitar open redirect.
- Rotas internas bloqueadas sem login.
- Rotas operacionais bloqueadas sem assinatura `active` ou `trialing`.
- Produção no Render exige `DATABASE_URL`; sem banco persistente, o app falha ao iniciar.
- Stripe Secret e Webhook Secret ficam somente no servidor.
- Conta nova nasce como `Sem assinatura` e só libera acesso após assinatura real.

## Testes obrigatórios após deploy

1. Abrir `/healthz` e confirmar `database: postgres`.
2. Criar conta nova e confirmar aumento de `users_count` em `/healthz`.
3. Fazer redeploy e confirmar que `users_count` não caiu.
4. Tentar `/dashboard` sem assinatura: deve redirecionar para `/precos`.
5. Clicar em `Assinar agora`: deve abrir Stripe Checkout.
6. Pagar com cartão de teste Stripe.
7. Voltar para `/billing/complete` e depois dashboard.
8. Abrir `/configuracoes` e confirmar plano/status.
9. Clicar em `Gerenciar assinatura` e abrir portal Stripe.
10. Fazer logout e login novamente; conta deve continuar existindo.

## Observação

Depois de validar tudo, troque qualquer senha exposta em chat, print ou ambiente inseguro.
