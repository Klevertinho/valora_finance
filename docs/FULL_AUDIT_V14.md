# Valora Finance — Auditoria completa V14

Data: 2026-06-03
Stack: Flask + Jinja + CSS puro + Postgres/Neon via `DATABASE_URL` + Stripe server-side + ReportLab.

## Achados e correções desta rodada

### Segurança
- Removido `data.db` do pacote final para evitar upload acidental de banco local para GitHub.
- Criado `.env.example` completo. `.env`, `data.db`, caches e artefatos locais ficam ignorados pelo Git.
- `/healthz` passou a expor apenas dados mínimos em produção. Contadores internos só aparecem fora de produção ou com `HEALTH_TOKEN`.
- Link mutável `GET /load_demo_data` foi convertido para `POST` com CSRF.
- Portal de assinatura agora aceita apenas `POST`.
- CSP ajustada para permitir Google Fonts sem erro de console e Stripe sem quebrar checkout.
- Conta demo não é mais criada automaticamente nem mesmo no fallback SQLite; só com `ENABLE_DEMO_ACCOUNT=1`.
- Nota de login demo só aparece quando `ENABLE_DEMO_ACCOUNT=1`.
- Senha mínima de cadastro aumentada para 8 caracteres.

### Funcionalidades
- Fluxo de assinatura segue: `/precos` → `/assinar/profissional` → login/cadastro → Stripe Checkout → `/billing/complete` → dashboard liberado.
- Conta sem assinatura continua bloqueada nas rotas internas principais.
- `/configuracoes` continua acessível para usuário logado sem assinatura para logout, suporte e escolha de plano.
- Ação “Ver demonstração” agora usa formulário seguro em vez de link GET.

### Design e UX
- Botões de ação POST no topo e no cockpit mantêm o visual de botão, sem aparência de formulário.
- Header público passou a exibir “Valora Finance”, reduzindo ambiguidade de marca.
- Mensagens de plano continuam clicáveis e direcionam para `/precos`.

### Oferta e venda
- Mantido plano único Profissional por R$69/mês.
- Oferta permanece simples: financeiro + estoque + IA + fechamentos + PDF + portal de assinatura.
- Página de preços passou a usar linguagem singular: “plano único”.

## Comandos executados

```bash
python3 -m py_compile app.py
python3 tests/smoke_security.py
python3 -m compileall .
bandit -r . -x ./venv,./.venv,./node_modules
pip-audit -r requirements.txt
```

## Resultados

- `py_compile`: passou.
- `smoke_security`: passou.
- `compileall`: passou.
- `bandit`: sem issues identificadas.
- `pip-audit`: não concluiu por falha de DNS no sandbox ao acessar PyPI. Deve ser rodado novamente em ambiente com internet.

## Testes funcionais executados com Flask test client

- `/` retorna 200.
- `/precos` retorna 200.
- `/login` retorna 200.
- `/cadastro` retorna 200.
- `/dashboard` deslogado redireciona para `/login`.
- Conta criada sem assinatura redireciona para `/precos`.
- Conta sem assinatura não acessa `/dashboard`.
- `/configuracoes` é acessível para conta logada sem assinatura.
- `GET /load_demo_data` retorna 405.
- `POST /load_demo_data` sem assinatura redireciona para `/precos`.
- `/healthz` funciona.

## Pendências antes de Stripe live

1. Trocar qualquer senha exposta anteriormente no banco/Neon.
2. Confirmar `DATABASE_URL` do Neon no Render.
3. Confirmar `/healthz` em produção com `database = postgres`.
4. Confirmar webhook Stripe com evento real de teste.
5. Rodar `pip-audit` em ambiente com internet.
6. Testar assinatura real em modo teste antes de ativar modo live.
