# Supabase/Neon e Segurança de Banco

O runtime atual usa Postgres via `DATABASE_URL`; Neon é a opção recomendada para produção neste momento.

Os arquivos em `supabase/` ficam como referência caso o projeto volte a usar Supabase Auth/RLS no futuro.

## Regras atuais no runtime Flask

- Toda query operacional filtra por `business_id`.
- O `business_id` vem da sessão do usuário autenticado.
- Conta nova nasce como `Sem assinatura`.
- Acesso interno exige assinatura `active` ou `trialing`.

## Tabelas usadas em produção

- `vf_users`
- `vf_businesses`
- `vf_business_members`
- `vf_business_settings`
- `vf_transactions`
- `vf_items`
- `vf_closings`
- `vf_month_closings`
- `vf_subscriptions`
- `vf_stripe_events`
