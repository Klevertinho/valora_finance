# Valora Finance

Base Flask/SQLite da Valora Finance com estrutura de SaaS: landing pública, autenticação local, rotas protegidas, isolamento por empresa, persistência em banco local e schema Supabase pronto para produção.

## Stack identificada

- Python + Flask
- SQLite local como fallback de desenvolvimento
- CSS puro (`static/style.css`)
- Jinja templates
- ReportLab para PDFs
- Sem Next.js, Vite, React Router ou Tailwind neste pacote
- Supabase ainda não está conectado em runtime, mas `supabase/schema.sql` e `.env.example` foram preparados para a migração

## Como rodar

```bash
pip install -r requirements.txt
python app.py
```

Acesse:

```text
http://localhost:8000
```

## Conta demo local

```text
Email: demo@valora.local
Senha: demo1234
```

Você também pode criar uma nova conta em `/cadastro`.

## Rotas públicas

- `/`
- `/login`
- `/cadastro`
- `/recuperar-senha`
- `/precos`
- `/termos`
- `/privacidade`

## Rotas protegidas

- `/dashboard`
- `/financas`
- `/estoque`
- `/vendas`
- `/relatorios`
- `/configuracoes`
- `/onboarding`

## Persistência

Os dados ficam em `data.db`, isolados por `business_id`. Ao fechar e abrir o sistema, fazer login novamente preserva transações, produtos, vendas, fechamentos e configurações.

## Supabase

O arquivo `supabase/schema.sql` contém schema Postgres com RLS para produção. Use `.env.example` como referência de variáveis.

## SEO público implementado

A landing pública (`/`) possui title, description, canonical, Open Graph, Twitter Card, JSON-LD `SoftwareApplication`, JSON-LD `FAQPage`, heading semântico com um único H1 e seções otimizadas para pequenos negócios.

Rotas SEO adicionadas:

- `/robots.txt`
- `/sitemap.xml`
- `/precos`
- `/termos`
- `/privacidade`

Configure `SITE_URL` ou `VALORA_SITE_URL` no ambiente de produção para canonical, sitemap e Open Graph apontarem para o domínio definitivo.

## Produção e assinatura

Este pacote inclui base de produção para assinatura com Stripe:

- `/assinar/<plano>`: entrada pública dos CTAs de preço;
- `/api/stripe/create-checkout-session`: criação server-side de checkout;
- `/api/stripe/webhook`: webhook Stripe com verificação de assinatura;
- `/billing/portal`: portal de assinatura;
- `/configuracoes`: exibe status de plano e acesso ao portal.

Leia `DEPLOY.md` antes de colocar em produção.

## Variáveis críticas

Copie `.env.example`, configure valores reais e nunca exponha chaves secretas no frontend.

```env
VALORA_APP_URL=https://sua-url-publica.com
VALORA_SITE_URL=https://sua-url-publica.com
STRIPE_SECRET_KEY=sk_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_INICIAL_MONTHLY=price_...
STRIPE_PRICE_PROFISSIONAL_MONTHLY=price_...
```

## Start command em produção

```bash
gunicorn 'app:create_app()' --bind 0.0.0.0:$PORT
```
