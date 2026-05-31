# Correção Render / Python / Postgres

Este projeto usa psycopg2-binary para conectar no Supabase/Postgres. No Render, se o serviço subir com Python 3.14, o psycopg2 pode falhar com erro de símbolo indefinido.

Correção obrigatória no Render:

1. Environment > Add Environment Variable

PYTHON_VERSION=3.11.9

2. Build Command

pip install --upgrade pip && pip install -r requirements.txt

3. Start Command

gunicorn "app:create_app()" --bind 0.0.0.0:$PORT

4. Manual Deploy > Clear build cache & deploy

Este pacote também inclui `.python-version` com 3.11.9 para ajudar o Render a selecionar a versão correta.
