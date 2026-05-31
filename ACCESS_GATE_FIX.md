# Correção crítica — fluxo de assinatura

Esta versão muda a regra de acesso:

- Conta sem assinatura ativa/trial não entra em `/dashboard`, `/financas`, `/estoque`, `/vendas` ou `/relatorios`.
- Cadastro sem plano selecionado vai para `/precos`.
- Login sem assinatura vai para `/precos`.
- Plano escolhido antes do login/cadastro é preservado e redireciona para `/assinar/<plano>`.
- Após Stripe Checkout, o retorno usa `/billing/complete?session_id=...` para confirmar a assinatura no banco antes de liberar o dashboard.

Arquivos principais alterados:

- `app.py`

Validação obrigatória em produção:

1. `/healthz` deve mostrar `database: postgres`.
2. Conta nova deve cair em `/precos`, não em `/dashboard`.
3. Conta sem assinatura tentando `/dashboard` deve voltar para `/precos`.
4. Após pagamento teste no Stripe, deve voltar para `/billing/complete` e depois liberar `/dashboard`.
