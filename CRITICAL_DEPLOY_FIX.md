# Correção crítica de produção

Esta versão impede o app de cair silenciosamente em SQLite no Render.

## Render Environment obrigatório

- DATABASE_URL = connection string do Neon/Postgres
- FLASK_SECRET_KEY = chave longa aleatória
- PYTHON_VERSION = 3.11.9
- VALORA_APP_URL = https://valora-finance.onrender.com
- VALORA_SITE_URL = https://valora-finance.onrender.com
- SITE_URL = https://valora-finance.onrender.com

## Não usar demo em produção

A conta demo não é mais criada automaticamente em Postgres.
Para habilitar manualmente, use:

ENABLE_DEMO_ACCOUNT=1

Recomendado para venda: não configurar ENABLE_DEMO_ACCOUNT.

## Validação

Acesse:

/healthz

Precisa retornar:

- database: postgres
- users_count aumentando quando uma conta é criada
