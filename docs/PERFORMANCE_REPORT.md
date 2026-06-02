# Performance Report

## Testes realizados localmente

Smoke funcional com Flask test client. Teste de carga externo não foi executado neste ambiente porque não há servidor persistente de produção com credenciais Stripe/Neon acessíveis no sandbox.

## Comandos sugeridos para staging

```bash
npx autocannon -c 25 -d 30 https://valora-finance.onrender.com/
npx autocannon -c 25 -d 30 https://valora-finance.onrender.com/precos
npx autocannon -c 25 -d 30 https://valora-finance.onrender.com/login
```

Não executar carga contra Stripe Checkout ou webhook em modo live.

## Medidas já aplicadas

- Cache bloqueado em rotas internas.
- Static assets servidos por Flask/Render.
- Query de dados sempre filtrada por `business_id`.
- Tabelas principais indexadas por `business_id` em Postgres.
- Rate limit simples em login, cadastro e checkout.

## Limites atuais

- Rate limit em memória não é global entre múltiplos workers/instâncias.
- Para escala maior, migrar rate limit para Redis ou serviço gerenciado.
