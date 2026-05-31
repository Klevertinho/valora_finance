# Deploy da Valora Finance em produção

Stack atual: Flask + SQLite local + Jinja + CSS puro + Stripe server-side. Para produção real, use Render/Railway/Fly.io ou VPS. Vercel não é a melhor opção para este projeto porque a aplicação é Flask persistente, não Next.js.

## 1. Variáveis de ambiente obrigatórias

Configure no painel da plataforma:

```env
FLASK_SECRET_KEY=um_secret_forte
VALORA_APP_URL=https://sua-url-de-producao.com
VALORA_SITE_URL=https://sua-url-de-producao.com
SITE_URL=https://sua-url-de-producao.com

STRIPE_SECRET_KEY=sk_test_ou_sk_live
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_TRIAL_DAYS=7
STRIPE_PRICE_INICIAL_MONTHLY=price_...
STRIPE_PRICE_PROFISSIONAL_MONTHLY=price_...

SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
```

Nunca exponha `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` ou `SUPABASE_SERVICE_ROLE_KEY` no frontend.

## 2. Deploy recomendado no Render

1. Crie um novo Web Service.
2. Conecte o repositório ou envie este projeto.
3. Runtime: Python.
4. Build Command:

```bash
pip install -r requirements.txt
```

5. Start Command:

```bash
gunicorn 'app:create_app()' --bind 0.0.0.0:$PORT
```

6. Configure as variáveis de ambiente.
7. Faça deploy.
8. Copie a URL pública gerada.
9. Atualize `VALORA_APP_URL`, `VALORA_SITE_URL` e `SITE_URL` com a URL final.
10. Redeploy.

## 3. Supabase

1. Crie um projeto Supabase.
2. Rode `supabase/schema.sql`.
3. Rode `supabase/subscriptions.sql`.
4. Em Authentication > URL Configuration:
   - Site URL: `https://sua-url-de-producao.com`
   - Redirect URLs:
     - `https://sua-url-de-producao.com/*`
     - `https://sua-url-de-producao.com/login`
     - `https://sua-url-de-producao.com/cadastro`
     - `https://sua-url-de-producao.com/dashboard`
     - `https://sua-url-de-producao.com/recuperar-senha`

## 4. Stripe

No Stripe, crie:

### Produto 1
- Nome: Valora Finance Inicial
- Preço: R$ 39/mês
- Tipo: recorrente mensal
- Copie o `price_...` para `STRIPE_PRICE_INICIAL_MONTHLY`.

### Produto 2
- Nome: Valora Finance Profissional
- Preço: R$ 69/mês
- Tipo: recorrente mensal
- Copie o `price_...` para `STRIPE_PRICE_PROFISSIONAL_MONTHLY`.

## 5. Webhook Stripe

Crie webhook para:

```txt
https://sua-url-de-producao.com/api/stripe/webhook
```

Eventos:

- `checkout.session.completed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.payment_succeeded`
- `invoice.payment_failed`

Copie o signing secret `whsec_...` para `STRIPE_WEBHOOK_SECRET`.

## 6. Teste de checkout

1. Entre em `/cadastro` e crie uma conta.
2. Acesse `/precos`.
3. Clique em Inicial ou Profissional.
4. Confirme que abre Stripe Checkout.
5. Use cartão teste do Stripe.
6. Após pagar, deve voltar para `/dashboard?checkout=success`.
7. Confira em `/configuracoes` o status da assinatura.
8. Clique em “Gerenciar assinatura” para abrir o Stripe Customer Portal.

## 7. Observação importante sobre banco

O runtime atual ainda usa SQLite local como fallback funcional. Para SaaS com clientes reais, migre a camada de dados para Supabase/Postgres antes de escalar, usando os schemas já preparados.
