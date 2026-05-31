# Repositories

A versão atual é Flask + SQLite local com isolamento por `business_id`. Estes arquivos documentam a camada de dados equivalente para a futura migração para Supabase/Postgres. As rotas do Flask já centralizam leitura e escrita em funções internas (`fetch_transactions`, `fetch_items`, `fetch_closings`, `load_settings`, `save_settings`) e filtram por empresa autenticada.

Na migração, criar módulos Python ou TypeScript com as mesmas responsabilidades:

- transactions: listar, criar, atualizar, remover
- products: listar, criar, atualizar, remover, vender, repor
- sales: listar e criar vendas
- dailyClosings: listar e criar fechamentos
- settings: ler e atualizar configurações
