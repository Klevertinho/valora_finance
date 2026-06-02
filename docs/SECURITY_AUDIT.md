# Auditoria de Segurança — Valora Finance

Data: 2026-06-02  
Stack: Flask + Jinja + CSS puro + Postgres/Neon via `DATABASE_URL` + Stripe server-side + ReportLab.

## Comandos executados

- `python --version`
- `node --version`
- `npm --version`
- `grep -RInE` para secrets, Stripe, Supabase, localhost, cookies, CSRF, DEBUG e padrões inseguros
- `python3 -m py_compile app.py`
- `python3 -m compileall .`
- smoke tests com Flask test client em `tests/smoke_security.py`

## Achados e correções

### Alta severidade

1. **Produção podia cair em banco local se `DATABASE_URL` estivesse ausente**  
   Correção: em produção/Render, o app falha explicitamente se `DATABASE_URL` não existir. Isso evita conta sumir por fallback silencioso em SQLite.

2. **Webhook Stripe sem idempotência explícita**  
   Correção: criação da tabela `stripe_events`/`vf_stripe_events` e bloqueio de reprocessamento por `event.id`.

3. **Fluxo de assinatura não podia liberar acesso apenas por `checkout=success`**  
   Correção preservada: retorno do Stripe passa por `/billing/complete`, consulta o Stripe, grava assinatura e só então libera dashboard.

### Média severidade

1. **Headers de segurança incompletos**  
   Correção: CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy, COOP, HSTS em HTTPS/produção.

2. **Rate limit só existia em login/cadastro**  
   Correção: rate limit simples também aplicado ao fluxo de checkout.

3. **Mensagens de erro do webhook podiam devolver detalhe interno**  
   Correção: webhook responde erro genérico após falha de assinatura/handler, sem vazar payload ou stack.

4. **`FLASK_SECRET_KEY` podia usar fallback em produção**  
   Correção: produção exige `FLASK_SECRET_KEY`.

### Baixa severidade

1. **Arquivos de cache Python dentro do ZIP**  
   Correção: `__pycache__` removido e `.gitignore` atualizado.

2. **Documentação de resposta a incidente insuficiente**  
   Correção: criada documentação operacional em `docs/INCIDENT_RUNBOOK.md`.

## Pendências críticas fora do código

- Trocar/rotacionar qualquer senha ou chave que tenha sido colada em chat, print ou log.
- Garantir que `DATABASE_URL` no Render aponta para Neon/Postgres, não Supabase antigo nem SQLite.
- Confirmar `STRIPE_WEBHOOK_SECRET` real do endpoint de produção.
- Testar pagamento com cartão Stripe de teste antes de ativar modo live.

## Não encontrados no código atual

- `STRIPE_SECRET_KEY` hardcoded no frontend.
- `SUPABASE_SERVICE_ROLE_KEY` hardcoded no frontend.
- uso de `eval`, `pickle`, `yaml.load`, `os.system` ou `subprocess`.
- CORS aberto com `*`.

## Resultado das ferramentas defensivas

- `bandit -r .`: sem issues após correção, apenas `# nosec` justificado para servidor dev local (`app.run`) e credencial fictícia de teste.
- `pip-audit -r requirements.txt`: ferramenta instalada, mas a consulta falhou por falha de DNS no sandbox (`Failed to resolve pypi.org`). Deve ser rodada novamente em ambiente com internet antes do live.
- `python3 -m py_compile app.py`: passou.
- `python3 -m compileall .`: passou.
- `python3 tests/smoke_security.py`: passou.

## Observação sobre senha exposta

Durante o processo operacional, uma senha de banco foi enviada no chat. Ela deve ser rotacionada no provedor de banco antes de qualquer uso real com clientes.
