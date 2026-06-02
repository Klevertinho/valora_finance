import os
import sqlite3
import re
import json
from functools import wraps
from io import BytesIO
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session, Response, jsonify

from werkzeug.security import generate_password_hash, check_password_hash


BRAND_NAME = "Valora Finance"
BRAND_TAGLINE = "Gestão inteligente"


APP_TABLES = {
    "transactions": "vf_transactions",
    "items": "vf_items",
    "closings": "vf_closings",
    "month_closings": "vf_month_closings",
    "app_settings": "vf_app_settings",
    "users": "vf_users",
    "businesses": "vf_businesses",
    "business_members": "vf_business_members",
    "business_settings": "vf_business_settings",
    "subscriptions": "vf_subscriptions",
}


def is_postgres_dsn(value: str | None) -> bool:
    return bool(value and value.startswith(("postgres://", "postgresql://")))


def normalize_postgres_dsn(dsn: str) -> str:
    """Render/Supabase Transaction Pooler connection string helper."""
    dsn = dsn.strip()
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn[len("postgres://"):]
    if "sslmode=" not in dsn:
        separator = "&" if "?" in dsn else "?"
        dsn = f"{dsn}{separator}sslmode=require"
    return dsn


def _map_app_tables(sql: str) -> str:
    """Use isolated Valora tables in Postgres to avoid conflicts with Supabase Auth/public schema."""
    for old, new in APP_TABLES.items():
        sql = re.sub(rf"\b{old}\b", new, sql)
    return sql


def _adapt_postgres_sql(sql: str) -> str:
    sql = _map_app_tables(sql)
    return sql.replace("?", "%s")


class PostgresCursor:
    def __init__(self, cursor):
        self.cursor = cursor
        self._lastrowid = None

    @property
    def lastrowid(self):
        return self._lastrowid

    def execute(self, sql, params=None):
        params = params or ()
        query = _adapt_postgres_sql(sql.strip())
        query_l = query.lower()
        needs_id = (
            query_l.startswith("insert into vf_users ")
            or query_l.startswith("insert into vf_businesses ")
        ) and " returning " not in query_l
        if needs_id:
            query = query.rstrip().rstrip(";") + " RETURNING id"
        self.cursor.execute(query, params)
        if needs_id:
            row = self.cursor.fetchone()
            self._lastrowid = row["id"] if row else None
        return self

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()


class PostgresConnection:
    def __init__(self, dsn):
        import psycopg2
        import psycopg2.extras
        self.conn = psycopg2.connect(normalize_postgres_dsn(dsn), cursor_factory=psycopg2.extras.RealDictCursor)

    def cursor(self):
        return PostgresCursor(self.conn.cursor())

    def execute(self, sql, params=None):
        cur = self.cursor()
        return cur.execute(sql, params or ())

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()


def init_postgres_db(dsn: str) -> None:
    """Create the production Postgres schema used by the Flask app.

    Tables are prefixed with vf_ to avoid collisions with Supabase's auth/users
    and any public tables created by earlier experiments.
    """
    conn = PostgresConnection(dsn)
    cur = conn.cursor()

    ddl_statements = [
        """
        CREATE TABLE IF NOT EXISTS vf_users (
            id SERIAL PRIMARY KEY,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS vf_businesses (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            owner_user_id INTEGER NOT NULL REFERENCES vf_users(id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS vf_business_members (
            id SERIAL PRIMARY KEY,
            business_id INTEGER NOT NULL REFERENCES vf_businesses(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES vf_users(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'owner',
            created_at TEXT NOT NULL,
            UNIQUE(business_id, user_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS vf_business_settings (
            id SERIAL PRIMARY KEY,
            business_id INTEGER NOT NULL UNIQUE REFERENCES vf_businesses(id) ON DELETE CASCADE,
            company_name TEXT NOT NULL,
            business_type TEXT NOT NULL,
            plan TEXT NOT NULL DEFAULT 'Sem assinatura',
            visual_preference TEXT NOT NULL DEFAULT 'Graphite Premium',
            demo_loaded INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS vf_transactions (
            id SERIAL PRIMARY KEY,
            description TEXT NOT NULL,
            amount DOUBLE PRECISION NOT NULL,
            date TEXT NOT NULL,
            category TEXT NOT NULL,
            business_category TEXT DEFAULT 'Geral',
            created_at TEXT,
            business_id INTEGER DEFAULT 1 REFERENCES vf_businesses(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS vf_items (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price DOUBLE PRECISION DEFAULT 0,
            category TEXT DEFAULT 'Geral',
            min_stock INTEGER DEFAULT 1,
            cost_price DOUBLE PRECISION DEFAULT 0,
            sale_price DOUBLE PRECISION DEFAULT 0,
            business_id INTEGER DEFAULT 1 REFERENCES vf_businesses(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS vf_closings (
            id SERIAL PRIMARY KEY,
            date TEXT NOT NULL,
            revenue DOUBLE PRECISION NOT NULL,
            expenses DOUBLE PRECISION NOT NULL,
            net DOUBLE PRECISION NOT NULL,
            products_sold TEXT,
            critical_products TEXT,
            recommendations TEXT,
            created_at TEXT,
            business_id INTEGER DEFAULT 1 REFERENCES vf_businesses(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS vf_month_closings (
            id SERIAL PRIMARY KEY,
            month TEXT NOT NULL,
            revenue DOUBLE PRECISION NOT NULL,
            expenses DOUBLE PRECISION NOT NULL,
            net DOUBLE PRECISION NOT NULL,
            expense_ratio DOUBLE PRECISION NOT NULL,
            sales_count INTEGER NOT NULL,
            products_sold TEXT,
            top_expense TEXT,
            critical_products TEXT,
            insights TEXT,
            recommendations TEXT,
            created_at TEXT,
            business_id INTEGER DEFAULT 1 REFERENCES vf_businesses(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS vf_app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS vf_subscriptions (
            id SERIAL PRIMARY KEY,
            business_id INTEGER NOT NULL REFERENCES vf_businesses(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES vf_users(id) ON DELETE CASCADE,
            stripe_customer_id TEXT,
            stripe_subscription_id TEXT UNIQUE,
            stripe_price_id TEXT,
            plan TEXT,
            status TEXT,
            current_period_start TEXT,
            current_period_end TEXT,
            trial_start TEXT,
            trial_end TEXT,
            cancel_at_period_end INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_vf_transactions_business ON vf_transactions(business_id)",
        "CREATE INDEX IF NOT EXISTS idx_vf_items_business ON vf_items(business_id)",
        "CREATE INDEX IF NOT EXISTS idx_vf_subscriptions_business ON vf_subscriptions(business_id)",
    ]
    for ddl in ddl_statements:
        cur.execute(ddl)

    now = datetime.now().isoformat(timespec="minutes")
    cur.execute(
        """
        UPDATE vf_business_settings
        SET plan = 'Sem assinatura'
        WHERE plan = 'Profissional'
          AND business_id NOT IN (
            SELECT business_id FROM vf_subscriptions WHERE status IN ('active', 'trialing')
          )
        """
    )

    if os.environ.get("ENABLE_DEMO_ACCOUNT", "0") == "1":
        demo = cur.execute("SELECT id FROM vf_users WHERE email = %s", ("demo@valora.local",)).fetchone()
        if not demo:
            cur.execute(
                "INSERT INTO vf_users (full_name, email, password_hash, created_at, updated_at) VALUES (%s, %s, %s, %s, %s)",
                ("Usuário Demo", "demo@valora.local", generate_password_hash("demo1234"), now, now),
            )
            user_id = cur.lastrowid
            cur.execute(
                "INSERT INTO vf_businesses (name, type, owner_user_id, created_at, updated_at) VALUES (%s, %s, %s, %s, %s)",
                ("Empresa demo", "Salão de beleza", user_id, now, now),
            )
            business_id = cur.lastrowid
            cur.execute(
                "INSERT INTO vf_business_members (business_id, user_id, role, created_at) VALUES (%s, %s, %s, %s)",
                (business_id, user_id, "owner", now),
            )
            cur.execute(
                "INSERT INTO vf_business_settings (business_id, company_name, business_type, plan, visual_preference, demo_loaded, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (business_id, "Empresa demo", "Salão de beleza", "Sem assinatura", "Graphite Premium", 0, now, now),
            )

    conn.commit()
    conn.close()


def init_db(db_path: str) -> None:
    """Create and migrate SQLite locally or Postgres in production when DATABASE_URL is set."""
    if is_postgres_dsn(db_path):
        init_postgres_db(db_path)
        return
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            date TEXT NOT NULL,
            category TEXT NOT NULL
        )
        """
    )
    cur.execute("PRAGMA table_info(transactions)")
    tx_cols = {row[1] for row in cur.fetchall()}
    if "business_category" not in tx_cols:
        cur.execute('ALTER TABLE transactions ADD COLUMN business_category TEXT DEFAULT "Geral"')
    if "created_at" not in tx_cols:
        cur.execute('ALTER TABLE transactions ADD COLUMN created_at TEXT')
        cur.execute("UPDATE transactions SET created_at = date WHERE created_at IS NULL")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL
        )
        """
    )
    cur.execute("PRAGMA table_info(items)")
    item_cols = {row[1] for row in cur.fetchall()}
    if "category" not in item_cols:
        cur.execute('ALTER TABLE items ADD COLUMN category TEXT DEFAULT "Geral"')
    if "min_stock" not in item_cols:
        cur.execute("ALTER TABLE items ADD COLUMN min_stock INTEGER DEFAULT 1")
    if "cost_price" not in item_cols:
        cur.execute("ALTER TABLE items ADD COLUMN cost_price REAL DEFAULT 0")
    if "sale_price" not in item_cols:
        cur.execute("ALTER TABLE items ADD COLUMN sale_price REAL")
        cur.execute("UPDATE items SET sale_price = price")

    cur.execute("UPDATE items SET sale_price = price WHERE sale_price IS NULL")
    cur.execute("UPDATE items SET cost_price = sale_price * 0.55 WHERE cost_price IS NULL OR cost_price = 0")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS closings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            revenue REAL NOT NULL,
            expenses REAL NOT NULL,
            net REAL NOT NULL,
            products_sold TEXT,
            critical_products TEXT,
            recommendations TEXT,
            created_at TEXT
        )
        """
    )
    cur.execute("PRAGMA table_info(closings)")
    closing_cols = {row[1] for row in cur.fetchall()}
    if "created_at" not in closing_cols:
        cur.execute("ALTER TABLE closings ADD COLUMN created_at TEXT")
        cur.execute("UPDATE closings SET created_at = date WHERE created_at IS NULL")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS month_closings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month TEXT NOT NULL,
            revenue REAL NOT NULL,
            expenses REAL NOT NULL,
            net REAL NOT NULL,
            expense_ratio REAL NOT NULL,
            sales_count INTEGER NOT NULL,
            products_sold TEXT,
            top_expense TEXT,
            critical_products TEXT,
            insights TEXT,
            recommendations TEXT,
            created_at TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )

    # SaaS/auth local fallback schema. This mirrors the Supabase-ready model and
    # keeps data isolated by user/business in local development.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS businesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            owner_user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(owner_user_id) REFERENCES users(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS business_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT 'owner',
            created_at TEXT NOT NULL,
            UNIQUE(business_id, user_id),
            FOREIGN KEY(business_id) REFERENCES businesses(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS business_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL UNIQUE,
            company_name TEXT NOT NULL,
            business_type TEXT NOT NULL,
            plan TEXT NOT NULL DEFAULT 'Sem assinatura',
            visual_preference TEXT NOT NULL DEFAULT 'Graphite Premium',
            demo_loaded INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(business_id) REFERENCES businesses(id) ON DELETE CASCADE
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            stripe_customer_id TEXT,
            stripe_subscription_id TEXT UNIQUE,
            stripe_price_id TEXT,
            plan TEXT,
            status TEXT,
            current_period_start TEXT,
            current_period_end TEXT,
            trial_start TEXT,
            trial_end TEXT,
            cancel_at_period_end INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(business_id) REFERENCES businesses(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # Corrige contas antigas que nasceram como "Profissional" sem assinatura real.
    # Plano comercial passa a ser derivado da tabela subscriptions/webhook Stripe.
    cur.execute("""
        UPDATE business_settings
        SET plan = 'Sem assinatura'
        WHERE plan = 'Profissional'
          AND business_id NOT IN (
            SELECT business_id FROM subscriptions WHERE status IN ('active', 'trialing')
          )
    """)

    def ensure_column(table, column, definition):
        cur.execute(f"PRAGMA table_info({table})")
        cols = {row[1] for row in cur.fetchall()}
        if column not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    for table in ["transactions", "items", "closings", "month_closings"]:
        ensure_column(table, "business_id", "INTEGER DEFAULT 1")

    # Create a local demo account so the product can be tested immediately.
    now = datetime.now().isoformat(timespec="minutes")
    demo = cur.execute("SELECT id FROM users WHERE email = ?", ("demo@valora.local",)).fetchone()
    if not demo:
        cur.execute(
            "INSERT INTO users (full_name, email, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("Usuário Demo", "demo@valora.local", generate_password_hash("demo1234"), now, now),
        )
        user_id = cur.lastrowid
        cur.execute(
            "INSERT INTO businesses (name, type, owner_user_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("Empresa demo", "Salão de beleza", user_id, now, now),
        )
        business_id = cur.lastrowid
        cur.execute(
            "INSERT INTO business_members (business_id, user_id, role, created_at) VALUES (?, ?, ?, ?)",
            (business_id, user_id, "owner", now),
        )
        cur.execute(
            "INSERT INTO business_settings (business_id, company_name, business_type, plan, visual_preference, demo_loaded, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (business_id, "Empresa demo", "Salão de beleza", "Sem assinatura", "Graphite Premium", 0, now, now),
        )

    conn.commit()
    conn.close()


def get_db_connection(db_path: str):
    if is_postgres_dsn(db_path):
        return PostgresConnection(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "valora-finance-local-dev-secret")
    database_url = os.environ.get("DATABASE_URL")
    running_on_render = bool(os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID") or os.environ.get("PORT"))
    if running_on_render and not database_url:
        raise RuntimeError("DATABASE_URL ausente em produção. Configure a connection string do Neon/Postgres no Render para evitar perda de contas.")
    db_path = database_url or os.environ.get("VALORA_DATABASE_PATH") or os.path.join(os.path.dirname(__file__), "data.db")
    init_db(db_path)

    default_settings = {
        "company_name": "Empresa demo",
        "business_type": "Salão de beleza",
        "plan": "Sem assinatura",
        "visual_preference": "Graphite Premium",
    }

    def current_user():
        user_id = session.get("user_id")
        if not user_id:
            return None
        conn = get_db_connection(db_path)
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        conn.close()
        return row

    def current_business_id():
        business_id = session.get("business_id")
        if business_id:
            return business_id
        user_id = session.get("user_id")
        if not user_id:
            return None
        conn = get_db_connection(db_path)
        row = conn.execute("SELECT business_id FROM business_members WHERE user_id = ? ORDER BY id LIMIT 1", (user_id,)).fetchone()
        conn.close()
        if row:
            session["business_id"] = row["business_id"]
            return row["business_id"]
        return None

    def load_settings():
        data = dict(default_settings)
        business_id = current_business_id()
        if not business_id:
            return data
        conn = get_db_connection(db_path)
        row = conn.execute("SELECT * FROM business_settings WHERE business_id = ?", (business_id,)).fetchone()
        conn.close()
        if row:
            data["company_name"] = row["company_name"]
            data["business_type"] = row["business_type"]
            data["plan"] = row["plan"]
            data["visual_preference"] = row["visual_preference"]
            data["demo_loaded"] = bool(row["demo_loaded"])
        return data

    def save_settings(data):
        business_id = current_business_id()
        if not business_id:
            return
        now = datetime.now().isoformat(timespec="minutes")
        conn = get_db_connection(db_path)
        conn.execute(
            """
            INSERT INTO business_settings (business_id, company_name, business_type, plan, visual_preference, demo_loaded, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(business_id) DO UPDATE SET
                company_name = excluded.company_name,
                business_type = excluded.business_type,
                plan = excluded.plan,
                visual_preference = excluded.visual_preference,
                demo_loaded = excluded.demo_loaded,
                updated_at = excluded.updated_at
            """,
            (
                business_id,
                data.get("company_name", "Empresa demo"),
                data.get("business_type", "Outro"),
                data.get("plan", "Sem assinatura"),
                data.get("visual_preference", "Graphite Premium"),
                1 if data.get("demo_loaded") else 0,
                now,
                now,
            ),
        )
        conn.commit()
        conn.close()

    public_endpoints = {
        "landing", "login", "cadastro", "recuperar_senha", "precos", "termos", "privacidade",
        "robots_txt", "sitemap_xml", "healthz", "stripe_webhook", "assinar_plano", "static"
    }
    auth_endpoints = {"login", "cadastro"}
    subscription_required_endpoints = {
        "dashboard", "financas", "estoque", "vendas", "relatorios",
        "load_demo_data", "close_day", "close_month", "daily_pdf", "month_pdf",
        "delete_transaction", "delete_item"
    }

    def _safe_next_url(value):
        """Allow only internal redirects."""
        if value and isinstance(value, str) and value.startswith("/") and not value.startswith("//"):
            return value
        return None

    def _valid_plan(value):
        plan = (value or "").lower()
        return plan if plan in {"inicial", "profissional"} else ""

    def _has_paid_or_trial_access():
        """Only Stripe/webhook-created active or trialing subscriptions unlock the app.

        If the webhook failed or arrived late, we try one Stripe sync per session by
        customer email before blocking the user. This prevents a paying customer
        from being trapped on the pricing page.
        """
        if not session.get("user_id") or not session.get("business_id"):
            return False
        try:
            if bool(subscription_access(get_subscription_for_business()).get("has_access")):
                return True
            if not session.get("stripe_subscription_sync_attempted"):
                session["stripe_subscription_sync_attempted"] = True
                if sync_subscription_from_stripe_for_current_user():
                    return bool(subscription_access(get_subscription_for_business()).get("has_access"))
            return False
        except Exception:
            return False

    def _safe_post_auth_destination(next_url=None):
        """After login/cadastro, never drop unpaid users inside the app."""
        next_url = _safe_next_url(next_url)
        if _has_paid_or_trial_access():
            return next_url or url_for("dashboard")
        # Conta criada/logada sem assinatura: sempre vai para planos.
        return url_for("precos", required="subscription")

    @app.before_request
    def protect_routes():
        endpoint = request.endpoint
        if not endpoint:
            return None
        logged = bool(session.get("user_id"))
        if endpoint not in public_endpoints and not logged:
            next_url = request.full_path if request.query_string else request.path
            return redirect(url_for("login", next=next_url))
        if endpoint in auth_endpoints and logged:
            plan = _valid_plan(request.args.get("plan"))
            next_url = _safe_next_url(request.args.get("next"))
            if plan:
                session["pending_plan"] = plan
                return redirect(url_for("assinar_plano", plan=plan))
            session.pop("pending_plan", None)
            return redirect(_safe_post_auth_destination(next_url))
        if logged and endpoint in subscription_required_endpoints and not _has_paid_or_trial_access():
            session["blocked_after_login"] = endpoint
            flash("Escolha um plano para ativar o sistema.", "info")
            return redirect(url_for("precos", required="subscription"))
        return None

    @app.template_filter("currency")
    def currency(value):
        """Brazilian currency formatting with no line-breaking surprises."""
        try:
            amount = float(value)
            formatted = f"R$ {abs(amount):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            return f"-{formatted}" if amount < 0 else formatted
        except (TypeError, ValueError):
            return "R$ 0,00"

    @app.template_filter("date_br")
    def date_br(value):
        try:
            return datetime.fromisoformat(value).strftime("%d/%m/%Y")
        except Exception:
            return value

    @app.context_processor
    def inject_globals():
        settings_payload = load_settings()
        subscription = None
        subscription_view = {
            "plan": None,
            "status": None,
            "status_label": "Sem assinatura",
            "is_active": False,
            "is_trialing": False,
            "has_access": False,
            "trial_ends_at": None,
            "current_period_end": None,
        }
        try:
            if current_user():
                subscription = get_subscription_for_business()
                subscription_view = subscription_access(subscription)
                if subscription_view.get("has_access") and subscription_view.get("plan"):
                    settings_payload["plan"] = plan_label(subscription_view.get("plan"))
                else:
                    settings_payload["plan"] = "Sem assinatura"
        except Exception:
            settings_payload["plan"] = settings_payload.get("plan") or "Sem assinatura"
        return {
            "settings": settings_payload,
            "current_user": current_user(),
            "subscription_global": subscription,
            "subscription_view_global": subscription_view,
            "brand_name": BRAND_NAME,
            "brand_tagline": BRAND_TAGLINE,
            "today_iso": datetime.today().date().isoformat(),
        }

    def fetch_transactions():
        business_id = current_business_id()
        if not business_id:
            return []
        conn = get_db_connection(db_path)
        rows = conn.execute("SELECT * FROM transactions WHERE business_id = ? ORDER BY date DESC, id DESC", (business_id,)).fetchall()
        conn.close()
        return rows

    def fetch_items():
        business_id = current_business_id()
        if not business_id:
            return []
        conn = get_db_connection(db_path)
        rows = conn.execute("SELECT * FROM items WHERE business_id = ? ORDER BY name ASC", (business_id,)).fetchall()
        conn.close()
        return rows

    def fetch_closings():
        business_id = current_business_id()
        if not business_id:
            return []
        conn = get_db_connection(db_path)
        rows = conn.execute("SELECT * FROM closings WHERE business_id = ? ORDER BY date DESC, id DESC", (business_id,)).fetchall()
        conn.close()
        return rows

    def fetch_month_closings():
        business_id = current_business_id()
        if not business_id:
            return []
        conn = get_db_connection(db_path)
        rows = conn.execute("SELECT * FROM month_closings WHERE business_id = ? ORDER BY month DESC, id DESC", (business_id,)).fetchall()
        conn.close()
        return rows

    def has_data():
        return bool(fetch_transactions() or fetch_items())

    def financial_totals(transactions):
        revenue = sum(tx["amount"] for tx in transactions if tx["amount"] > 0)
        expenses = -sum(tx["amount"] for tx in transactions if tx["amount"] < 0)
        return revenue, expenses, revenue - expenses

    def monthly_totals(transactions):
        prefix = datetime.today().strftime("%Y-%m")
        return financial_totals([tx for tx in transactions if tx["date"].startswith(prefix)])

    def today_totals(transactions):
        today = datetime.today().date().isoformat()
        rows = [tx for tx in transactions if tx["date"] == today]
        revenue, expenses, net = financial_totals(rows)
        products_sold = len([tx for tx in rows if tx["amount"] > 0 and "venda" in tx["description"].lower()])
        return {"revenue": revenue, "expenses": expenses, "net": net, "movements": len(rows), "products_sold": products_sold}

    def product_margin(item):
        sale = item["sale_price"] if "sale_price" in item.keys() and item["sale_price"] is not None else item["price"]
        cost = item["cost_price"] if "cost_price" in item.keys() and item["cost_price"] is not None else sale * 0.55
        if sale <= 0:
            return 0
        return ((sale - cost) / sale) * 100

    def product_status(item):
        min_stock = item["min_stock"] if "min_stock" in item.keys() else 1
        if item["quantity"] <= 0:
            return "critico"
        if item["quantity"] <= min_stock:
            return "atencao"
        return "saudavel"

    def stock_stats(items):
        critical = [item for item in items if product_status(item) != "saudavel"]
        units = sum(item["quantity"] for item in items)
        value = sum((item["cost_price"] if "cost_price" in item.keys() else item["price"] * 0.55) * item["quantity"] for item in items)
        margins = [product_margin(item) for item in items]
        avg_margin = sum(margins) / len(margins) if margins else 0
        return {"critical": critical, "critical_count": len(critical), "units": units, "value": value, "avg_margin": avg_margin}

    def calculate_business_health(revenue, expenses, net, critical_count):
        """Return coherent health status, score and short executive message."""
        if revenue <= 0 and expenses <= 0:
            return {"label": "Demo", "class": "primary", "score": 68, "message": "Carregue uma demonstração."}

        ratio = expenses / revenue if revenue else 1
        if net < 0 or ratio > 0.75 or critical_count > 5:
            label = "Crítico"
            css = "danger"
        elif ratio > 0.55 or critical_count >= 3:
            label = "Atenção"
            css = "warning"
        else:
            label = "Saudável"
            css = "success"

        score = 90
        if net < 0:
            score -= 32
        if ratio > 0.75:
            score -= 28
        elif ratio > 0.55:
            score -= round((ratio - 0.55) * 100 * 0.95)
        elif ratio < 0.40 and revenue > 0:
            score += 4
        if critical_count > 2:
            score -= (critical_count - 2) * 5
        score = int(max(24, min(96, round(score))))

        if css == "success":
            message = "Caixa positivo e custos controlados."
        elif css == "warning":
            message = "Margem positiva, mas despesas elevadas."
        elif css == "primary":
            message = "Use a demo para visualizar o cockpit."
        else:
            message = "Resultado exige ação imediata."
        return {"label": label, "class": css, "score": score, "message": message}

    def health_score(revenue, expenses, critical_count):
        net = revenue - expenses
        return calculate_business_health(revenue, expenses, net, critical_count)["score"]

    def health_label(score):
        if score >= 78:
            return {"label": "Saudável", "class": "success"}
        if score >= 52:
            return {"label": "Atenção", "class": "warning"}
        return {"label": "Crítico", "class": "danger"}

    def weekly_summary(transactions):
        today = datetime.today().date()
        rows = []
        for offset in range(6, -1, -1):
            day = today - timedelta(days=offset)
            date_str = day.isoformat()
            revenue = sum(tx["amount"] for tx in transactions if tx["amount"] > 0 and tx["date"] == date_str)
            expenses = -sum(tx["amount"] for tx in transactions if tx["amount"] < 0 and tx["date"] == date_str)
            rows.append({"date": date_str, "label": day.strftime("%d/%m"), "revenue": revenue, "expenses": expenses})
        max_value = max([row["revenue"] for row in rows] + [row["expenses"] for row in rows] + [1])
        for row in rows:
            row["revenue_height"] = max(5, round((row["revenue"] / max_value) * 100)) if row["revenue"] else 3
            row["expenses_height"] = max(5, round((row["expenses"] / max_value) * 100)) if row["expenses"] else 3
        return rows

    def expenses_by_category(transactions):
        totals = {}
        for tx in transactions:
            if tx["amount"] < 0:
                key = tx["business_category"] if "business_category" in tx.keys() and tx["business_category"] else tx["description"]
                totals[key] = totals.get(key, 0) + (-tx["amount"])
        total = sum(totals.values())
        rows = []
        for name, value in sorted(totals.items(), key=lambda item: item[1], reverse=True)[:5]:
            percent = (value / total * 100) if total else 0
            rows.append({"name": name, "value": value, "percent": percent, "width": max(8, min(100, round(percent)))})
        return rows

    def recent_transactions(transactions, n=6):
        return transactions[:n]

    def generate_insights(transactions, items):
        revenue, expenses, net = monthly_totals(transactions)
        stock = stock_stats(items)
        insights = []
        if revenue:
            ratio = round((expenses / revenue) * 100)
            insights.append({"title": f"Despesas em {ratio}%", "text": "Sob controle" if ratio <= 55 else "Revisar despesas", "class": "success" if ratio < 65 else "warning"})
        else:
            insights.append({"title": "Sem receita", "text": "Registre vendas", "class": "warning"})
        insights.append({"title": f"{stock['critical_count']} itens críticos", "text": "Repor estoque" if stock["critical_count"] else "Estoque ok", "class": "warning" if stock["critical_count"] else "success"})
        insights.append({"title": "Saldo positivo" if net >= 0 else "Saldo negativo", "text": "Reserve capital de giro" if net >= 0 else "Revisar caixa", "class": "success" if net >= 0 else "danger"})
        closings_today = any(tx["date"] == datetime.today().date().isoformat() for tx in transactions)
        insights.append({"title": "Fechamento", "text": "Atualizado" if closings_today else "Pendente", "class": "primary" if closings_today else "warning"})
        return insights

    def generate_actions(transactions, items):
        actions = []
        stock = stock_stats(items)
        today = datetime.today().date().isoformat()
        has_sale_today = any(tx["date"] == today and tx["amount"] > 0 for tx in transactions)
        if not has_sale_today:
            actions.append("Registrar vendas")
        if stock["critical_count"]:
            actions.append("Repor estoque")
        actions.append("Fechar dia")
        actions.append("Ver relatório")
        return actions[:4]

    def close_day_summary():
        transactions = fetch_transactions()
        items = fetch_items()
        today = datetime.today().date().isoformat()
        today_txs = [tx for tx in transactions if tx["date"] == today]
        revenue, expenses, net = financial_totals(today_txs)
        sold = [tx["description"].replace("Venda de ", "") for tx in today_txs if tx["amount"] > 0 and "venda" in tx["description"].lower()]
        critical = [item["name"] for item in items if product_status(item) != "saudavel"]
        recs = []
        if net >= 0:
            recs.append("Reservar caixa para reposição")
        else:
            recs.append("Revisar despesas do dia")
        if critical:
            recs.append("Repor itens críticos")
        return {
            "date": today,
            "revenue": revenue,
            "expenses": expenses,
            "net": net,
            "products_sold": ", ".join(sorted(set(sold))) or "-",
            "critical_products": ", ".join(sorted(set(critical))) or "-",
            "recommendations": "; ".join(recs),
        }

    def close_month_summary(month=None):
        transactions = fetch_transactions()
        items = fetch_items()
        target_month = month or datetime.today().date().isoformat()[:7]
        month_txs = [tx for tx in transactions if tx["date"].startswith(target_month)]
        revenue, expenses, net = financial_totals(month_txs)
        ratio = (expenses / revenue * 100) if revenue else 0

        sales = [tx for tx in month_txs if tx["amount"] > 0]
        sold = {}
        for tx in sales:
            if "venda" in tx["description"].lower():
                product = tx["description"].replace("Venda de ", "")
                sold[product] = sold.get(product, 0) + 1
        products_sold = ", ".join(f"{name} ({qty})" for name, qty in sorted(sold.items(), key=lambda item: item[1], reverse=True)) or "-"

        expense_rows = expenses_by_category(month_txs)
        top_expense = f"{expense_rows[0]['name']} ({currency(expense_rows[0]['value'])})" if expense_rows else "-"
        critical = [item["name"] for item in items if product_status(item) != "saudavel"]

        insights = []
        if revenue == 0:
            insights.append("Mês sem receita registrada; cadastre vendas para medir desempenho.")
        elif ratio > 75:
            insights.append(f"Despesas consumiram {ratio:.0f}% da receita; margem mensal está pressionada.")
        elif ratio > 55:
            insights.append(f"Despesas em {ratio:.0f}% da receita; mês positivo, mas pede controle de custos.")
        else:
            insights.append(f"Despesas em {ratio:.0f}% da receita; operação financeira saudável.")

        insights.append("Resultado mensal positivo; separar capital de giro e reposição." if net >= 0 else "Resultado mensal negativo; revisar gastos e mix de vendas imediatamente.")
        if critical:
            insights.append(f"{len(critical)} itens precisam de atenção no estoque antes do próximo ciclo.")
        if expense_rows:
            insights.append(f"Maior gasto do mês: {expense_rows[0]['name']}.")

        recommendations = []
        if ratio > 55:
            recommendations.append("Revisar despesas fixas e compras de fornecedor")
        if critical:
            recommendations.append("Planejar reposição dos itens críticos")
        if net > 0:
            recommendations.append("Reservar parte do saldo como capital de giro")
        else:
            recommendations.append("Criar ação de venda para recuperar caixa")

        return {
            "month": target_month,
            "revenue": revenue,
            "expenses": expenses,
            "net": net,
            "expense_ratio": ratio,
            "sales_count": len(sales),
            "products_sold": products_sold,
            "top_expense": top_expense,
            "critical_products": ", ".join(sorted(set(critical))) or "-",
            "insights": "; ".join(insights),
            "insight_list": insights,
            "recommendations": "; ".join(recommendations),
        }

    def seed_demo_data():
        business_id = current_business_id()
        if not business_id:
            flash("Entre na conta para carregar a demonstração.", "error")
            return False
        if has_data():
            flash("Dados existentes preservados.", "info")
            return False
        today = datetime.today().date()
        revenue_rows = [
            ("Venda balcão", 890.00, "Vendas", 0),
            ("Serviço realizado", 1200.00, "Serviços", 1),
            ("Pacote mensal", 2500.00, "Serviços", 2),
            ("Venda de Shampoo Profissional", 690.00, "Vendas", 3),
            ("Recebimento cliente", 4800.00, "Recebimentos", 5),
            ("Venda recorrente", 3200.00, "Recorrência", 6),
        ]
        expense_rows = [
            ("Fornecedor", -1800.00, "Fornecedor", 0),
            ("Aluguel", -2900.00, "Aluguel", 2),
            ("Marketing", -850.00, "Marketing", 3),
            ("Reposição de estoque", -2200.00, "Estoque", 4),
            ("Operacional", -950.00, "Operação", 6),
        ]
        products = [
            ("Shampoo Profissional", "Cabelo", 3, 5, 32.00, 59.90),
            ("Máscara Capilar", "Cabelo", 8, 4, 28.00, 69.90),
            ("Creme Finalizador", "Finalização", 0, 3, 18.00, 39.90),
            ("Tinta 7.1", "Coloração", 2, 4, 22.00, 49.90),
            ("Escova Térmica", "Acessórios", 6, 2, 45.00, 89.90),
            ("Óleo Reparador", "Finalização", 4, 3, 16.00, 42.90),
            ("Gel Modelador", "Finalização", 1, 4, 12.00, 29.90),
            ("Condicionador Premium", "Cabelo", 10, 5, 26.00, 58.90),
        ]
        conn = get_db_connection(db_path)
        cur = conn.cursor()
        for desc, amount, category, days_ago in revenue_rows:
            date = (today - timedelta(days=days_ago)).isoformat()
            cur.execute(
                "INSERT INTO transactions (description, amount, date, category, business_category, created_at, business_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (desc, amount, date, "receita", category, date, business_id),
            )
        for desc, amount, category, days_ago in expense_rows:
            date = (today - timedelta(days=days_ago)).isoformat()
            cur.execute(
                "INSERT INTO transactions (description, amount, date, category, business_category, created_at, business_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (desc, amount, date, "despesa", category, date, business_id),
            )
        for name, category, quantity, min_stock, cost, sale in products:
            cur.execute(
                "INSERT INTO items (name, quantity, price, category, min_stock, cost_price, sale_price, business_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (name, quantity, sale, category, min_stock, cost, sale, business_id),
            )
        conn.commit()
        conn.close()
        settings_payload = load_settings()
        settings_payload["demo_loaded"] = True
        save_settings(settings_payload)
        flash("Demo carregada.", "success")
        return True

    def dashboard_context():
        transactions = fetch_transactions()
        items = fetch_items()
        revenue, expenses, net = monthly_totals(transactions)
        stock = stock_stats(items)
        ratio = (expenses / revenue * 100) if revenue else 0
        health = calculate_business_health(revenue, expenses, net, stock["critical_count"])
        score = health["score"]
        metric_cards = [
            {"title": "Receita", "value": currency(revenue), "trend": "+12,5%", "kind": "success", "icon": "↑"},
            {"title": "Despesas", "value": currency(expenses), "trend": f"{ratio:.0f}%", "kind": "danger", "icon": "↓"},
            {"title": "Saldo", "value": currency(net), "trend": "Positivo" if net >= 0 else "Negativo", "kind": "primary", "icon": "R$"},
            {"title": "Produtos críticos", "value": str(stock["critical_count"]), "trend": "Repor estoque" if stock["critical_count"] else "OK", "kind": "warning", "icon": "!"},
        ]
        actions = [
            {"label": "Nova venda", "url": "#nova-venda", "class": "primary"},
            {"label": "Novo produto", "url": "#novo-produto", "class": "ghost"},
        ]
        if not transactions and not items:
            actions = [{"label": "Ver demonstração", "url": url_for("load_demo_data"), "class": "gold"}]
        return {
            "transactions": transactions,
            "items": items,
            "month_revenue": revenue,
            "month_expenses": expenses,
            "month_net": net,
            "expense_ratio": ratio,
            "stock": stock,
            "score": score,
            "health": health,
            "metric_cards": metric_cards,
            "weekly_data": weekly_summary(transactions),
            "expenses_categories": expenses_by_category(transactions),
            "recent_transactions": recent_transactions(transactions),
            "insights": generate_insights(transactions, items),
            "actions": generate_actions(transactions, items),
            "today_summary": today_totals(transactions),
            "critical_items": stock["critical"],
            "no_data": not transactions and not items,
            "page_actions": actions,
        }

    def public_site_url() -> str:
        # URL canônica pública. Não usar localhost como canonical de produção.
        return (
            os.getenv("SITE_URL")
            or os.getenv("VALORA_SITE_URL")
            or os.getenv("NEXT_PUBLIC_SITE_URL")
            or "https://valorafinance.com.br"
        ).rstrip("/")

    def get_app_url() -> str:
        """Return the production application URL used in Stripe redirects and SEO."""
        return (
            os.getenv("VALORA_APP_URL")
            or os.getenv("APP_URL")
            or os.getenv("SITE_URL")
            or os.getenv("VALORA_SITE_URL")
            or os.getenv("NEXT_PUBLIC_APP_URL")
            or os.getenv("NEXT_PUBLIC_SITE_URL")
            or request.host_url.rstrip("/")
        ).rstrip("/")

    def stripe_price_map():
        return {
            "inicial": os.getenv("STRIPE_PRICE_INICIAL_MONTHLY"),
            "profissional": os.getenv("STRIPE_PRICE_PROFISSIONAL_MONTHLY"),
        }

    def plan_label(plan):
        return {"inicial": "Inicial", "profissional": "Profissional"}.get(plan, "Sem assinatura")

    def get_stripe_client():
        secret_key = os.getenv("STRIPE_SECRET_KEY")
        if not secret_key:
            return None
        try:
            import stripe
            stripe.api_key = secret_key
            return stripe
        except Exception:
            return None

    def timestamp_to_iso(value):
        if not value:
            return None
        try:
            return datetime.fromtimestamp(int(value)).isoformat(timespec="seconds")
        except Exception:
            return None

    def upsert_subscription(payload):
        now = datetime.now().isoformat(timespec="minutes")
        conn = get_db_connection(db_path)
        existing = None
        if payload.get("stripe_subscription_id"):
            existing = conn.execute(
                "SELECT id FROM subscriptions WHERE stripe_subscription_id = ?",
                (payload.get("stripe_subscription_id"),),
            ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE subscriptions
                SET stripe_customer_id = ?, stripe_price_id = ?, plan = ?, status = ?,
                    current_period_start = ?, current_period_end = ?, trial_start = ?, trial_end = ?,
                    cancel_at_period_end = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    payload.get("stripe_customer_id"), payload.get("stripe_price_id"), payload.get("plan"),
                    payload.get("status"), payload.get("current_period_start"), payload.get("current_period_end"),
                    payload.get("trial_start"), payload.get("trial_end"), 1 if payload.get("cancel_at_period_end") else 0,
                    now, existing["id"],
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO subscriptions (
                    business_id, user_id, stripe_customer_id, stripe_subscription_id, stripe_price_id,
                    plan, status, current_period_start, current_period_end, trial_start, trial_end,
                    cancel_at_period_end, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("business_id"), payload.get("user_id"), payload.get("stripe_customer_id"),
                    payload.get("stripe_subscription_id"), payload.get("stripe_price_id"), payload.get("plan"),
                    payload.get("status"), payload.get("current_period_start"), payload.get("current_period_end"),
                    payload.get("trial_start"), payload.get("trial_end"), 1 if payload.get("cancel_at_period_end") else 0,
                    now, now,
                ),
            )
        if payload.get("business_id") and payload.get("plan"):
            conn.execute(
                "UPDATE business_settings SET plan = ?, updated_at = ? WHERE business_id = ?",
                (plan_label(payload.get("plan")), now, payload.get("business_id")),
            )
        conn.commit()
        conn.close()

    def get_subscription_for_business(business_id=None):
        business_id = business_id or current_business_id()
        if not business_id:
            return None
        conn = get_db_connection(db_path)
        row = conn.execute(
            "SELECT * FROM subscriptions WHERE business_id = ? ORDER BY updated_at DESC, id DESC LIMIT 1",
            (business_id,),
        ).fetchone()
        conn.close()
        return row

    def subscription_status_label(status):
        return {
            "active": "Ativo",
            "trialing": "Em teste",
            "past_due": "Pagamento pendente",
            "canceled": "Cancelado",
            "incomplete": "Incompleto",
            "unpaid": "Não pago",
        }.get(status or "", "Sem assinatura")

    def subscription_access(subscription):
        status = subscription["status"] if subscription else None
        return {
            "plan": subscription["plan"] if subscription else None,
            "status": status,
            "status_label": subscription_status_label(status),
            "is_active": status == "active",
            "is_trialing": status == "trialing",
            "has_access": status in {"active", "trialing"},
            "trial_ends_at": subscription["trial_end"] if subscription else None,
            "current_period_end": subscription["current_period_end"] if subscription else None,
        }

    def _stripe_obj_get(obj, key, default=None):
        try:
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)
        except Exception:
            return default

    def _first_subscription_price_id(subscription):
        try:
            items = _stripe_obj_get(subscription, "items", {})
            data = _stripe_obj_get(items, "data", []) or []
            if not data:
                return None
            first = data[0]
            price = _stripe_obj_get(first, "price", {})
            return _stripe_obj_get(price, "id")
        except Exception:
            return None

    def sync_subscription_from_stripe_for_current_user():
        """Recover access for users who paid but whose webhook was not saved.

        This searches Stripe customers by the logged-in email, finds an active/trialing
        subscription, maps its price ID back to our plan, and writes it to the local DB.
        """
        user = current_user()
        business_id = current_business_id()
        if not user or not business_id:
            return False
        stripe = get_stripe_client()
        if not stripe:
            return False
        price_to_plan = {v: k for k, v in stripe_price_map().items() if v}
        try:
            customers = stripe.Customer.list(email=user["email"], limit=10)
            for customer in (_stripe_obj_get(customers, "data", []) or []):
                customer_id = _stripe_obj_get(customer, "id")
                if not customer_id:
                    continue
                subscriptions = stripe.Subscription.list(customer=customer_id, status="all", limit=10)
                for sub in (_stripe_obj_get(subscriptions, "data", []) or []):
                    status = _stripe_obj_get(sub, "status")
                    if status not in {"active", "trialing"}:
                        continue
                    price_id = _first_subscription_price_id(sub)
                    metadata = _stripe_obj_get(sub, "metadata", {}) or {}
                    plan = _stripe_obj_get(metadata, "plan") or price_to_plan.get(price_id)
                    if plan not in {"inicial", "profissional"}:
                        continue
                    upsert_subscription({
                        "business_id": int(business_id),
                        "user_id": int(user["id"]),
                        "stripe_customer_id": customer_id,
                        "stripe_subscription_id": _stripe_obj_get(sub, "id"),
                        "stripe_price_id": price_id,
                        "plan": plan,
                        "status": status,
                        "current_period_start": timestamp_to_iso(_stripe_obj_get(sub, "current_period_start")),
                        "current_period_end": timestamp_to_iso(_stripe_obj_get(sub, "current_period_end")),
                        "trial_start": timestamp_to_iso(_stripe_obj_get(sub, "trial_start")),
                        "trial_end": timestamp_to_iso(_stripe_obj_get(sub, "trial_end")),
                        "cancel_at_period_end": _stripe_obj_get(sub, "cancel_at_period_end"),
                    })
                    return True
        except Exception as exc:
            print("Stripe subscription sync failed:", exc)
            return False
        return False

    def create_checkout_session_for_plan(plan):
        plan = (plan or "").lower()
        price_id = stripe_price_map().get(plan)
        if plan not in {"inicial", "profissional"} or not price_id:
            raise ValueError("Plano inválido ou STRIPE_PRICE do plano ausente.")
        stripe = get_stripe_client()
        if not stripe:
            raise RuntimeError("Stripe não configurado. Verifique STRIPE_SECRET_KEY e a dependência stripe.")
        user = current_user()
        business_id = current_business_id()
        if not user or not business_id:
            raise PermissionError("Usuário não autenticado.")
        app_url = get_app_url()
        session_obj = stripe.checkout.Session.create(
            mode="subscription",
            customer_email=user["email"],
            line_items=[{"price": price_id, "quantity": 1}],
            subscription_data={
                "trial_period_days": int(os.getenv("STRIPE_TRIAL_DAYS", "7")),
                "metadata": {"user_id": str(user["id"]), "business_id": str(business_id), "plan": plan},
            },
            metadata={"user_id": str(user["id"]), "business_id": str(business_id), "plan": plan},
            success_url=f"{app_url}/billing/complete?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{app_url}/precos?checkout=cancelled",
        )
        return session_obj

    @app.context_processor
    def inject_public_site_url():
        return {"site_url": public_site_url()}

    @app.route("/")
    def landing():
        return render_template(
            "landing.html",
            title="Valora Finance | Controle financeiro para pequenos negócios",
            description="Sistema financeiro com IA para controlar caixa, vendas, estoque, despesas e fechamento diário em pequenos negócios.",
            canonical_url=public_site_url() + "/",
        )

    @app.route("/precos")
    def precos():
        if request.args.get("checkout") == "cancelled":
            flash("Checkout cancelado. Você pode escolher um plano quando quiser.", "info")
        if request.args.get("required") == "subscription":
            flash("A conta foi criada, mas o sistema só libera após escolher um plano.", "info")
        return render_template(
            "precos.html",
            title="Preços | Valora Finance",
            description="Conheça os planos da Valora Finance para controlar financeiro, vendas, estoque e fechamento diário em pequenos negócios.",
            canonical_url=public_site_url() + "/precos",
        )

    @app.route("/termos")
    def termos():
        return render_template(
            "termos.html",
            title="Termos de Uso | Valora Finance",
            description="Conheça os termos de uso da Valora Finance, sistema financeiro e operacional para pequenos negócios.",
            canonical_url=public_site_url() + "/termos",
        )

    @app.route("/privacidade")
    def privacidade():
        return render_template(
            "privacidade.html",
            title="Política de Privacidade | Valora Finance",
            description="Entenda como a Valora Finance trata dados de conta, empresa, financeiro, estoque e vendas no sistema.",
            canonical_url=public_site_url() + "/privacidade",
        )

    @app.route("/robots.txt")
    def robots_txt():
        body = f"""User-agent: *
Allow: /
Disallow: /dashboard
Disallow: /financas
Disallow: /estoque
Disallow: /vendas
Disallow: /relatorios
Disallow: /configuracoes
Disallow: /login
Disallow: /cadastro
Disallow: /recuperar-senha

Sitemap: {public_site_url()}/sitemap.xml
"""
        return Response(body, mimetype="text/plain")

    @app.route("/sitemap.xml")
    def sitemap_xml():
        today = datetime.today().date().isoformat()
        urls = [
            ("/", "weekly", "1.0"),
            ("/precos", "monthly", "0.8"),
            ("/termos", "yearly", "0.3"),
            ("/privacidade", "yearly", "0.3"),
        ]
        items = "".join(
            f"<url><loc>{public_site_url()}{path}</loc><lastmod>{today}</lastmod><changefreq>{freq}</changefreq><priority>{priority}</priority></url>"
            for path, freq, priority in urls
        )
        xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>'
        return Response(xml, mimetype="application/xml")

    @app.route("/healthz")
    def healthz():
        conn = get_db_connection(db_path)
        try:
            users_count = conn.execute("SELECT COUNT(*) AS total FROM users").fetchone()["total"]
            subscriptions_count = conn.execute("SELECT COUNT(*) AS total FROM subscriptions").fetchone()["total"]
        finally:
            conn.close()
        return jsonify({
            "ok": True,
            "database": "postgres" if is_postgres_dsn(db_path) else "sqlite",
            "users_count": users_count,
            "subscriptions_count": subscriptions_count,
            "stripe_configured": bool(os.getenv("STRIPE_SECRET_KEY")),
            "app_url": get_app_url(),
        })

    @app.route("/login", methods=["GET", "POST"])
    def login():
        arg_plan = _valid_plan(request.args.get("plan"))
        if request.method == "GET" and not arg_plan:
            # Clicking the normal header/login button must not inherit an old pricing intent.
            session.pop("pending_plan", None)
        selected_plan = _valid_plan(request.form.get("plan") or arg_plan or session.get("pending_plan"))
        next_url = _safe_next_url(request.args.get("next"))
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            conn = get_db_connection(db_path)
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if not user or not check_password_hash(user["password_hash"], password):
                conn.close()
                flash("Email ou senha inválidos.", "error")
                return render_template("login.html", title="Entrar | Valora Finance", email=email, selected_plan=selected_plan, next_url=next_url)
            membership = conn.execute("SELECT business_id FROM business_members WHERE user_id = ? ORDER BY id LIMIT 1", (user["id"],)).fetchone()
            pending_plan = selected_plan or _valid_plan(session.get("pending_plan"))
            session.clear()
            session["user_id"] = user["id"]
            if membership:
                session["business_id"] = membership["business_id"]
            flash("Login realizado.", "success")
            # If the customer already paid but the webhook was missed, recover access now.
            session.pop("stripe_subscription_sync_attempted", None)
            sync_subscription_from_stripe_for_current_user()
            if pending_plan:
                session["pending_plan"] = pending_plan
                return redirect(url_for("assinar_plano", plan=pending_plan))
            return redirect(_safe_post_auth_destination(next_url))
        return render_template("login.html", title="Entrar | Valora Finance", email="", selected_plan=selected_plan, next_url=next_url)

    @app.route("/cadastro", methods=["GET", "POST"])
    def cadastro():
        business_types = ["Salão de beleza", "Barbearia", "Loja", "Restaurante", "Açaíteria", "Pizzaria", "Mercado", "Outro"]
        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            business_name = request.form.get("business_name", "").strip()
            business_type = request.form.get("business_type", "")
            load_demo = request.form.get("load_demo") == "1"
            selected_plan = (request.form.get("plan") or "").lower()
            if selected_plan not in {"", "inicial", "profissional"}:
                selected_plan = ""
            if not full_name or not business_name or business_type not in business_types:
                flash("Preencha nome, empresa e tipo de negócio.", "error")
                return render_template("cadastro.html", title="Criar conta | Valora Finance", business_types=business_types, form=request.form, selected_plan=selected_plan)
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
                flash("Informe um email válido.", "error")
                return render_template("cadastro.html", title="Criar conta | Valora Finance", business_types=business_types, form=request.form, selected_plan=selected_plan)
            if len(password) < 6:
                flash("A senha precisa ter pelo menos 6 caracteres.", "error")
                return render_template("cadastro.html", title="Criar conta | Valora Finance", business_types=business_types, form=request.form, selected_plan=selected_plan)
            conn = get_db_connection(db_path)
            exists = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if exists:
                conn.close()
                flash("Este email já está cadastrado.", "error")
                return render_template("cadastro.html", title="Criar conta | Valora Finance", business_types=business_types, form=request.form, selected_plan=selected_plan)
            now = datetime.now().isoformat(timespec="minutes")
            cur = conn.cursor()
            cur.execute("INSERT INTO users (full_name, email, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?)", (full_name, email, generate_password_hash(password), now, now))
            user_id = cur.lastrowid
            cur.execute("INSERT INTO businesses (name, type, owner_user_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)", (business_name, business_type, user_id, now, now))
            business_id = cur.lastrowid
            cur.execute("INSERT INTO business_members (business_id, user_id, role, created_at) VALUES (?, ?, ?, ?)", (business_id, user_id, "owner", now))
            cur.execute("INSERT INTO business_settings (business_id, company_name, business_type, plan, visual_preference, demo_loaded, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (business_id, business_name, business_type, "Sem assinatura", "Graphite Premium", 0, now, now))
            conn.commit()
            conn.close()
            session.clear()
            session["user_id"] = user_id
            session["business_id"] = business_id
            if load_demo:
                seed_demo_data()
            flash("Conta criada. Escolha um plano para ativar o sistema.", "success")
            if selected_plan:
                session["pending_plan"] = selected_plan
                return redirect(url_for("assinar_plano", plan=selected_plan))
            return redirect(url_for("precos", required="subscription"))
        selected_plan = (request.args.get("plan") or "").lower()
        if selected_plan not in {"inicial", "profissional"}:
            selected_plan = ""
        return render_template("cadastro.html", title="Criar conta | Valora Finance", business_types=business_types, form={}, load_demo=request.args.get("demo") == "true", selected_plan=selected_plan)

    @app.route("/recuperar-senha", methods=["GET", "POST"])
    def recuperar_senha():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            flash("Se o email existir, enviaremos as instruções de recuperação.", "success")
            return render_template("recuperar_senha.html", title="Recuperar senha | Valora Finance", sent=True, email=email)
        return render_template("recuperar_senha.html", title="Recuperar senha | Valora Finance", sent=False)

    @app.route("/assinar/<plan>")
    def assinar_plano(plan):
        """Public-safe entrypoint for pricing CTAs."""
        plan = (plan or "").lower()
        if plan not in {"inicial", "profissional"}:
            flash("Plano inválido.", "error")
            return redirect(url_for("precos"))
        if not session.get("user_id"):
            session["pending_plan"] = plan
            flash("Entre ou crie sua conta para concluir a assinatura.", "info")
            return redirect(url_for("login", plan=plan, next=url_for("assinar_plano", plan=plan)))
        try:
            checkout_session = create_checkout_session_for_plan(plan)
            return redirect(checkout_session.url)
        except Exception as exc:
            flash(f"Checkout indisponível: {exc}", "error")
            return redirect(url_for("precos"))

    @app.route("/api/stripe/create-checkout-session", methods=["POST"])
    def create_checkout_session_api():
        payload = request.get_json(silent=True) or {}
        plan = (payload.get("plan") or request.form.get("plan") or "").lower()
        try:
            checkout_session = create_checkout_session_for_plan(plan)
            return jsonify({"url": checkout_session.url})
        except PermissionError:
            return jsonify({"error": "Faça login para assinar."}), 401
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    @app.route("/billing/complete")
    def billing_complete():
        """Finalize checkout synchronously so the dashboard is not opened before access exists."""
        session_id = request.args.get("session_id")
        if not session_id:
            flash("Checkout não confirmado. Escolha um plano novamente.", "error")
            return redirect(url_for("precos"))
        if not session.get("user_id") or not session.get("business_id"):
            flash("Entre novamente para concluir a assinatura.", "info")
            return redirect(url_for("login", next=request.full_path))
        stripe = get_stripe_client()
        if not stripe:
            flash("Stripe não configurado no servidor.", "error")
            return redirect(url_for("precos"))
        try:
            checkout = stripe.checkout.Session.retrieve(session_id)
            metadata = checkout.get("metadata") or {}
            subscription_id = checkout.get("subscription")
            if str(metadata.get("user_id")) != str(session.get("user_id")) or str(metadata.get("business_id")) != str(session.get("business_id")):
                flash("Checkout não pertence a esta conta.", "error")
                return redirect(url_for("precos"))
            if not subscription_id:
                flash("Assinatura ainda não encontrada no checkout.", "error")
                return redirect(url_for("precos"))
            sub = stripe.Subscription.retrieve(subscription_id)
            item = sub["items"]["data"][0] if sub["items"]["data"] else {}
            price = item.get("price") or {}
            upsert_subscription({
                "business_id": int(metadata.get("business_id")),
                "user_id": int(metadata.get("user_id")),
                "stripe_customer_id": checkout.get("customer"),
                "stripe_subscription_id": sub.get("id"),
                "stripe_price_id": price.get("id"),
                "plan": metadata.get("plan"),
                "status": sub.get("status"),
                "current_period_start": timestamp_to_iso(sub.get("current_period_start")),
                "current_period_end": timestamp_to_iso(sub.get("current_period_end")),
                "trial_start": timestamp_to_iso(sub.get("trial_start")),
                "trial_end": timestamp_to_iso(sub.get("trial_end")),
                "cancel_at_period_end": sub.get("cancel_at_period_end"),
            })
            session.pop("pending_plan", None)
            flash("Assinatura ativada. Sistema liberado.", "success")
            return redirect(url_for("dashboard"))
        except Exception as exc:
            flash(f"Não foi possível confirmar o checkout: {exc}", "error")
            return redirect(url_for("precos"))

    @app.route("/billing/portal", methods=["POST", "GET"])
    def billing_portal():
        subscription = get_subscription_for_business()
        if not subscription or not subscription["stripe_customer_id"]:
            flash("Nenhuma assinatura ativa encontrada. Escolha um plano para começar.", "info")
            return redirect(url_for("precos"))
        stripe = get_stripe_client()
        if not stripe:
            flash("Portal de assinatura indisponível. Configure STRIPE_SECRET_KEY.", "error")
            return redirect(url_for("configuracoes"))
        portal = stripe.billing_portal.Session.create(
            customer=subscription["stripe_customer_id"],
            return_url=f"{get_app_url()}/configuracoes?billing=return",
        )
        return redirect(portal.url)

    @app.route("/api/stripe/webhook", methods=["POST"])
    def stripe_webhook():
        stripe = get_stripe_client()
        webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
        if not stripe or not webhook_secret:
            return jsonify({"error": "Stripe webhook não configurado."}), 400
        payload = request.get_data(as_text=False)
        signature = request.headers.get("stripe-signature")
        if not signature:
            return jsonify({"error": "Missing Stripe signature."}), 400
        try:
            event = stripe.Webhook.construct_event(payload, signature, webhook_secret)
        except Exception as exc:
            return jsonify({"error": f"Invalid signature: {exc}"}), 400

        try:
            if event["type"] == "checkout.session.completed":
                checkout = event["data"]["object"]
                metadata = checkout.get("metadata") or {}
                subscription_id = checkout.get("subscription")
                if subscription_id:
                    sub = stripe.Subscription.retrieve(subscription_id)
                    item = sub["items"]["data"][0] if sub["items"]["data"] else {}
                    price = item.get("price") or {}
                    upsert_subscription({
                        "business_id": int(metadata.get("business_id")),
                        "user_id": int(metadata.get("user_id")),
                        "stripe_customer_id": checkout.get("customer"),
                        "stripe_subscription_id": sub.get("id"),
                        "stripe_price_id": price.get("id"),
                        "plan": metadata.get("plan"),
                        "status": sub.get("status"),
                        "current_period_start": timestamp_to_iso(sub.get("current_period_start")),
                        "current_period_end": timestamp_to_iso(sub.get("current_period_end")),
                        "trial_start": timestamp_to_iso(sub.get("trial_start")),
                        "trial_end": timestamp_to_iso(sub.get("trial_end")),
                        "cancel_at_period_end": sub.get("cancel_at_period_end"),
                    })
            elif event["type"] in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
                sub = event["data"]["object"]
                metadata = sub.get("metadata") or {}
                item = sub["items"]["data"][0] if sub.get("items") and sub["items"]["data"] else {}
                price = item.get("price") or {}
                if metadata.get("user_id") and metadata.get("business_id"):
                    upsert_subscription({
                        "business_id": int(metadata.get("business_id")),
                        "user_id": int(metadata.get("user_id")),
                        "stripe_customer_id": sub.get("customer"),
                        "stripe_subscription_id": sub.get("id"),
                        "stripe_price_id": price.get("id"),
                        "plan": metadata.get("plan"),
                        "status": sub.get("status"),
                        "current_period_start": timestamp_to_iso(sub.get("current_period_start")),
                        "current_period_end": timestamp_to_iso(sub.get("current_period_end")),
                        "trial_start": timestamp_to_iso(sub.get("trial_start")),
                        "trial_end": timestamp_to_iso(sub.get("trial_end")),
                        "cancel_at_period_end": sub.get("cancel_at_period_end"),
                    })
            return jsonify({"received": True})
        except Exception as exc:
            return jsonify({"error": f"Webhook handler failed: {exc}"}), 500

    @app.route("/logout")
    def logout():
        session.clear()
        flash("Sessão encerrada.", "success")
        return redirect(url_for("login"))

    @app.route("/onboarding")
    def onboarding():
        return redirect(url_for("configuracoes"))

    @app.route("/dashboard")
    def dashboard():
        if request.args.get("checkout") == "success":
            flash("Assinatura iniciada. O status será atualizado após confirmação do Stripe.", "success")
        ctx = dashboard_context()
        dashboard_actions = [
            {"label": "Nova venda", "url": "#nova-venda", "class": "primary"},
            {"label": "Nova despesa", "url": "#nova-movimentacao", "class": "secondary"},
            {"label": "Novo produto", "url": "#novo-produto", "class": "ghost"},
            {"label": "Fechar dia", "url": url_for("relatorios") + "#fechamento", "class": "ghost"},
        ]
        if ctx["no_data"]:
            dashboard_actions = [
                {"label": "Ver demonstração", "url": url_for("load_demo_data"), "class": "gold"},
                {"label": "Nova movimentação", "url": "#nova-movimentacao", "class": "ghost"},
            ]
        ctx.update({
            "page_title": "Visão geral",
            "page_subtitle": "Caixa, estoque e prioridades do dia.",
            "page_actions": dashboard_actions,
        })
        return render_template("dashboard.html", **ctx)

    @app.route("/financas", methods=["GET", "POST"])
    def financas():
        if request.method == "POST":
            category = request.form.get("category", "receita")
            amount = float(request.form.get("amount", 0) or 0)
            if category == "despesa" and amount > 0:
                amount = -amount
            if category == "receita" and amount < 0:
                amount = abs(amount)
            date = request.form.get("date") or datetime.today().date().isoformat()
            business_id = current_business_id()
            conn = get_db_connection(db_path)
            conn.execute(
                "INSERT INTO transactions (description, amount, date, category, business_category, created_at, business_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    request.form.get("description", "Movimentação").strip() or "Movimentação",
                    amount,
                    date,
                    category,
                    request.form.get("business_category", "Geral").strip() or "Geral",
                    datetime.now().isoformat(timespec="minutes"),
                    business_id,
                ),
            )
            conn.commit()
            conn.close()
            flash("Movimentação salva.", "success")
            return redirect(url_for("financas"))
        ctx = dashboard_context()
        transactions = ctx["transactions"]
        revenue, expenses, net = monthly_totals(transactions)
        cats = expenses_by_category(transactions)
        ctx.update({
            "page_title": "Financeiro",
            "page_subtitle": "Fluxo de caixa e movimentações.",
            "revenue": revenue,
            "expenses": expenses,
            "net": net,
            "major_expense_cat": cats[0]["name"] if cats else "—",
            "page_actions": [
                {"label": "Nova movimentação", "url": "#nova-movimentacao", "class": "primary"},
            ],
        })
        if not ctx["transactions"] and not ctx["items"]:
            ctx["page_actions"].append({"label": "Ver demonstração", "url": url_for("load_demo_data"), "class": "gold"})
        return render_template("finance.html", **ctx)

    @app.route("/estoque", methods=["GET", "POST"])
    def estoque():
        if request.method == "POST":
            action = request.form.get("action", "add")
            business_id = current_business_id()
            conn = get_db_connection(db_path)
            if action == "add":
                name = request.form.get("name", "Produto").strip() or "Produto"
                category = request.form.get("category", "Geral").strip() or "Geral"
                quantity = int(request.form.get("quantity", 0) or 0)
                min_stock = int(request.form.get("min_stock", 1) or 1)
                cost = float(request.form.get("cost_price", 0) or 0)
                sale = float(request.form.get("sale_price", 0) or 0)
                conn.execute(
                    "INSERT INTO items (name, quantity, price, category, min_stock, cost_price, sale_price, business_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (name, quantity, sale, category, min_stock, cost, sale, business_id),
                )
                flash("Produto salvo.", "success")
            elif action == "sell":
                item_id = int(request.form.get("item_id", 0) or 0)
                quantity = int(request.form.get("sell_quantity", 1) or 1)
                item = conn.execute("SELECT * FROM items WHERE id = ? AND business_id = ?", (item_id, business_id)).fetchone()
                if item and quantity > 0 and item["quantity"] >= quantity:
                    sale_price = item["sale_price"] or item["price"]
                    conn.execute("UPDATE items SET quantity = quantity - ? WHERE id = ? AND business_id = ?", (quantity, item_id, business_id))
                    conn.execute(
                        "INSERT INTO transactions (description, amount, date, category, business_category, created_at, business_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (f"Venda de {item['name']}", sale_price * quantity, datetime.today().date().isoformat(), "receita", "Vendas", datetime.now().isoformat(timespec="minutes"), business_id),
                    )
                    flash("Venda registrada.", "success")
                else:
                    flash("Estoque insuficiente.", "error")
            elif action == "restock":
                item_id = int(request.form.get("item_id", 0) or 0)
                quantity = int(request.form.get("restock_quantity", 1) or 1)
                cost = float(request.form.get("restock_cost", 0) or 0)
                item = conn.execute("SELECT * FROM items WHERE id = ? AND business_id = ?", (item_id, business_id)).fetchone()
                if item and quantity > 0:
                    current_qty = item["quantity"]
                    current_cost = item["cost_price"] or item["price"] * 0.55
                    new_cost = ((current_cost * current_qty) + cost) / max(1, current_qty + quantity)
                    conn.execute("UPDATE items SET quantity = quantity + ?, cost_price = ? WHERE id = ? AND business_id = ?", (quantity, new_cost, item_id, business_id))
                    if cost:
                        conn.execute(
                            "INSERT INTO transactions (description, amount, date, category, business_category, created_at, business_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (f"Reposição de {item['name']}", -abs(cost), datetime.today().date().isoformat(), "despesa", "Estoque", datetime.now().isoformat(timespec="minutes"), business_id),
                        )
                    flash("Reposição salva.", "success")
            conn.commit()
            conn.close()
            return redirect(url_for("estoque"))
        ctx = dashboard_context()
        item_rows = []
        for item in ctx["items"]:
            data = dict(item)
            data["margin"] = product_margin(item)
            data["status"] = product_status(item)
            item_rows.append(data)
        ctx.update({
            "page_title": "Estoque",
            "page_subtitle": "Produtos, margem e reposição.",
            "items": item_rows,
            "page_actions": [
                {"label": "Novo produto", "url": "#novo-produto", "class": "primary"},
                {"label": "Nova venda", "url": "#nova-venda", "class": "ghost"},
            ],
        })
        return render_template("inventory.html", **ctx)

    @app.route("/vendas", methods=["GET", "POST"])
    def vendas():
        if request.method == "POST":
            return redirect(url_for("estoque"))
        ctx = dashboard_context()
        sale_txs = [tx for tx in ctx["transactions"] if tx["amount"] > 0]
        sales_total = sum(tx["amount"] for tx in sale_txs)
        ticket_average = sales_total / len(sale_txs) if sale_txs else 0
        products_sold = len([tx for tx in sale_txs if "venda" in tx["description"].lower()])
        ctx.update({
            "page_title": "Vendas",
            "page_subtitle": "Vendas, ticket médio e produtos vendidos.",
            "sale_transactions": sale_txs,
            "sales_total": sales_total,
            "ticket_average": ticket_average,
            "products_sold_count": products_sold,
            "page_actions": [{"label": "Nova venda", "url": "#nova-venda", "class": "primary"}],
        })
        return render_template("sales.html", **ctx)

    @app.route("/relatorios")
    def relatorios():
        ctx = dashboard_context()
        transactions = ctx["transactions"]
        daily = {}
        monthly = {}
        products_sold = {}
        for tx in transactions:
            daily[tx["date"]] = daily.get(tx["date"], 0) + tx["amount"]
            month = tx["date"][:7]
            monthly[month] = monthly.get(month, 0) + tx["amount"]
            if tx["amount"] > 0 and "venda" in tx["description"].lower():
                product = tx["description"].replace("Venda de ", "")
                products_sold[product] = products_sold.get(product, 0) + 1
        ctx.update({
            "page_title": "Relatórios",
            "page_subtitle": "Fechamentos e decisões do período.",
            "daily_summary": daily,
            "monthly_summary": monthly,
            "products_sold": products_sold,
            "closings": fetch_closings(),
            "month_closings": fetch_month_closings(),
            "month_summary": close_month_summary(),
            "page_actions": [
                {"label": "Fechar dia", "url": "#fechamento", "class": "secondary"},
                {"label": "Fechar mês", "url": "#fechamento-mensal", "class": "primary"},
            ],
        })
        return render_template("reports.html", **ctx)



    def make_closing_pdf(summary):
        """Create a branded PDF report for a daily closing."""
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader

        buffer = BytesIO()
        page_w, page_h = A4
        c = canvas.Canvas(buffer, pagesize=A4)
        margin = 18 * mm
        y = page_h - margin

        # Background
        c.setFillColor(colors.HexColor("#0B1120"))
        c.rect(0, 0, page_w, page_h, stroke=0, fill=1)

        # Card helper
        def card(x, y_top, w, h, title, value, subtitle=None, accent="#2563EB"):
            c.setFillColor(colors.HexColor("#111827"))
            c.roundRect(x, y_top - h, w, h, 12, stroke=0, fill=1)
            c.setStrokeColor(colors.HexColor("#243247"))
            c.roundRect(x, y_top - h, w, h, 12, stroke=1, fill=0)
            c.setFillColor(colors.HexColor(accent))
            c.setFont("Helvetica-Bold", 9)
            c.drawString(x + 12, y_top - 20, title)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 18)
            c.drawString(x + 12, y_top - 45, value)
            if subtitle:
                c.setFillColor(colors.HexColor("#94A3B8"))
                c.setFont("Helvetica", 8)
                c.drawString(x + 12, y_top - 62, subtitle)

        # Logo and header
        logo_path = os.path.join(os.path.dirname(__file__), "static", "valora-logo-gold.png")
        if os.path.exists(logo_path):
            c.drawImage(ImageReader(logo_path), margin, y - 18, width=20 * mm, height=14 * mm, mask="auto", preserveAspectRatio=True)
        c.setFillColor(colors.HexColor("#F8FAFC"))
        c.setFont("Helvetica-Bold", 18)
        c.drawString(margin + 28 * mm, y - 4, "Valora Finance")
        c.setFillColor(colors.HexColor("#94A3B8"))
        c.setFont("Helvetica", 10)
        c.drawString(margin + 28 * mm, y - 18, "Fechamento diário personalizado")

        c.setFillColor(colors.HexColor("#D4A72C"))
        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(page_w - margin, y - 6, date_br(summary["date"]))
        y -= 42 * mm

        # Title
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 22)
        c.drawString(margin, y, "Resumo do dia")
        c.setFillColor(colors.HexColor("#94A3B8"))
        c.setFont("Helvetica", 10)
        c.drawString(margin, y - 16, f"Empresa: {load_settings().get('company_name', 'Empresa demo')} | Plano: {load_settings().get('plan', 'Profissional')}")
        y -= 32 * mm

        # KPI cards
        gap = 8 * mm
        card_w = (page_w - 2 * margin - gap) / 2
        card_h = 34 * mm
        card(margin, y, card_w, card_h, "RECEITAS", currency(summary["revenue"]), "Entradas do dia", "#86EFAC")
        card(margin + card_w + gap, y, card_w, card_h, "DESPESAS", currency(summary["expenses"]), "Saídas do dia", "#FCA5A5")
        y -= card_h + 9 * mm
        card(margin, y, card_w, card_h, "SALDO", currency(summary["net"]), "Resultado operacional", "#FCD34D" if summary["net"] >= 0 else "#FCA5A5")
        card(margin + card_w + gap, y, card_w, card_h, "ITENS VENDIDOS", str(summary.get("products_sold", "-") or "-"), "Produtos movimentados", "#93C5FD")
        y -= card_h + 15 * mm

        # Text blocks
        def text_block(title, body):
            nonlocal y
            c.setFillColor(colors.HexColor("#111827"))
            h = 34 * mm
            c.roundRect(margin, y - h, page_w - 2 * margin, h, 12, stroke=0, fill=1)
            c.setStrokeColor(colors.HexColor("#243247"))
            c.roundRect(margin, y - h, page_w - 2 * margin, h, 12, stroke=1, fill=0)
            c.setFillColor(colors.HexColor("#D4A72C"))
            c.setFont("Helvetica-Bold", 10)
            c.drawString(margin + 12, y - 16, title)
            c.setFillColor(colors.white)
            c.setFont("Helvetica", 10)
            text = c.beginText(margin + 12, y - 32)
            for line in str(body).split("; "):
                text.textLine(line[:105])
            c.drawText(text)
            y -= h + 8 * mm

        text_block("Produtos críticos", summary.get("critical_products") or "Nenhum item crítico no fechamento.")
        text_block("Recomendações", summary.get("recommendations") or "Sem recomendações adicionais.")

        # Footer
        c.setFillColor(colors.HexColor("#64748B"))
        c.setFont("Helvetica", 8)
        c.drawCentredString(page_w / 2, 14 * mm, "Gerado automaticamente pela Valora Finance")
        c.showPage()
        c.save()
        buffer.seek(0)
        return buffer

    @app.route("/close_day", methods=["POST"])
    def close_day():
        summary = close_day_summary()
        conn = get_db_connection(db_path)
        conn.execute(
            "INSERT INTO closings (date, revenue, expenses, net, products_sold, critical_products, recommendations, created_at, business_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (summary["date"], summary["revenue"], summary["expenses"], summary["net"], summary["products_sold"], summary["critical_products"], summary["recommendations"], datetime.now().isoformat(timespec="minutes"), current_business_id()),
        )
        conn.commit()
        conn.close()
        flash("Dia fechado. PDF disponível para download.", "success")
        return redirect(url_for("relatorios"))

    @app.route("/relatorios/pdf")
    def download_report_pdf():
        closings = fetch_closings()
        if closings:
            latest = closings[0]
            summary = {
                "date": latest["date"],
                "revenue": latest["revenue"],
                "expenses": latest["expenses"],
                "net": latest["net"],
                "products_sold": latest["products_sold"],
                "critical_products": latest["critical_products"],
                "recommendations": latest["recommendations"],
            }
        else:
            summary = close_day_summary()
        pdf = make_closing_pdf(summary)
        filename = f"valora-fechamento-{summary['date']}.pdf"
        return send_file(pdf, as_attachment=True, download_name=filename, mimetype="application/pdf")

    def make_month_closing_pdf(summary):
        """Create a branded PDF report for a monthly closing."""
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader

        buffer = BytesIO()
        page_w, page_h = A4
        c = canvas.Canvas(buffer, pagesize=A4)
        margin = 18 * mm
        y = page_h - margin

        c.setFillColor(colors.HexColor("#0B1120"))
        c.rect(0, 0, page_w, page_h, stroke=0, fill=1)

        def card(x, y_top, w, h, title, value, subtitle=None, accent="#2563EB"):
            c.setFillColor(colors.HexColor("#111827"))
            c.roundRect(x, y_top - h, w, h, 12, stroke=0, fill=1)
            c.setStrokeColor(colors.HexColor("#243247"))
            c.roundRect(x, y_top - h, w, h, 12, stroke=1, fill=0)
            c.setFillColor(colors.HexColor(accent))
            c.setFont("Helvetica-Bold", 9)
            c.drawString(x + 12, y_top - 20, title)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 17)
            c.drawString(x + 12, y_top - 45, value)
            if subtitle:
                c.setFillColor(colors.HexColor("#94A3B8"))
                c.setFont("Helvetica", 8)
                c.drawString(x + 12, y_top - 62, subtitle)

        logo_path = os.path.join(os.path.dirname(__file__), "static", "valora-logo-gold.png")
        if os.path.exists(logo_path):
            c.drawImage(ImageReader(logo_path), margin, y - 18, width=20 * mm, height=14 * mm, mask="auto", preserveAspectRatio=True)
        c.setFillColor(colors.HexColor("#F8FAFC"))
        c.setFont("Helvetica-Bold", 18)
        c.drawString(margin + 28 * mm, y - 4, "Valora Finance")
        c.setFillColor(colors.HexColor("#94A3B8"))
        c.setFont("Helvetica", 10)
        c.drawString(margin + 28 * mm, y - 18, "Fechamento mensal personalizado")
        c.setFillColor(colors.HexColor("#D4A72C"))
        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(page_w - margin, y - 6, summary["month"])
        y -= 42 * mm

        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 22)
        c.drawString(margin, y, "Resumo do mês")
        c.setFillColor(colors.HexColor("#94A3B8"))
        c.setFont("Helvetica", 10)
        c.drawString(margin, y - 16, f"Empresa: {load_settings().get('company_name', 'Empresa demo')} | Plano: {load_settings().get('plan', 'Profissional')}")
        y -= 32 * mm

        gap = 8 * mm
        card_w = (page_w - 2 * margin - gap) / 2
        card_h = 34 * mm
        card(margin, y, card_w, card_h, "RECEITAS", currency(summary["revenue"]), "Entradas do mês", "#86EFAC")
        card(margin + card_w + gap, y, card_w, card_h, "DESPESAS", currency(summary["expenses"]), f"{summary['expense_ratio']:.0f}% da receita", "#FCA5A5")
        y -= card_h + 9 * mm
        card(margin, y, card_w, card_h, "SALDO", currency(summary["net"]), "Resultado mensal", "#FCD34D" if summary["net"] >= 0 else "#FCA5A5")
        card(margin + card_w + gap, y, card_w, card_h, "VENDAS", str(summary.get("sales_count", 0)), "Transações de entrada", "#93C5FD")
        y -= card_h + 14 * mm

        def text_block(title, body, height=40 * mm):
            nonlocal y
            c.setFillColor(colors.HexColor("#111827"))
            c.roundRect(margin, y - height, page_w - 2 * margin, height, 12, stroke=0, fill=1)
            c.setStrokeColor(colors.HexColor("#243247"))
            c.roundRect(margin, y - height, page_w - 2 * margin, height, 12, stroke=1, fill=0)
            c.setFillColor(colors.HexColor("#D4A72C"))
            c.setFont("Helvetica-Bold", 10)
            c.drawString(margin + 12, y - 16, title)
            c.setFillColor(colors.white)
            c.setFont("Helvetica", 9)
            text = c.beginText(margin + 12, y - 32)
            for line in str(body).split("; "):
                text.textLine(line[:112])
            c.drawText(text)
            y -= height + 8 * mm

        text_block("Insights do mês", summary.get("insights") or "Sem insights disponíveis.", 45 * mm)
        text_block("Produtos vendidos", summary.get("products_sold") or "-", 30 * mm)
        text_block("Recomendações", summary.get("recommendations") or "Sem recomendações adicionais.", 34 * mm)

        c.setFillColor(colors.HexColor("#64748B"))
        c.setFont("Helvetica", 8)
        c.drawCentredString(page_w / 2, 14 * mm, "Gerado automaticamente pela Valora Finance")
        c.showPage()
        c.save()
        buffer.seek(0)
        return buffer

    @app.route("/close_month", methods=["POST"])
    def close_month():
        summary = close_month_summary()
        conn = get_db_connection(db_path)
        conn.execute(
            "INSERT INTO month_closings (month, revenue, expenses, net, expense_ratio, sales_count, products_sold, top_expense, critical_products, insights, recommendations, created_at, business_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (summary["month"], summary["revenue"], summary["expenses"], summary["net"], summary["expense_ratio"], summary["sales_count"], summary["products_sold"], summary["top_expense"], summary["critical_products"], summary["insights"], summary["recommendations"], datetime.now().isoformat(timespec="minutes"), current_business_id()),
        )
        conn.commit()
        conn.close()
        flash("Mês fechado. PDF mensal disponível para download.", "success")
        return redirect(url_for("relatorios"))

    @app.route("/relatorios/month_pdf")
    def download_month_report_pdf():
        month_closings = fetch_month_closings()
        if month_closings:
            latest = month_closings[0]
            summary = {
                "month": latest["month"],
                "revenue": latest["revenue"],
                "expenses": latest["expenses"],
                "net": latest["net"],
                "expense_ratio": latest["expense_ratio"],
                "sales_count": latest["sales_count"],
                "products_sold": latest["products_sold"],
                "top_expense": latest["top_expense"],
                "critical_products": latest["critical_products"],
                "insights": latest["insights"],
                "recommendations": latest["recommendations"],
            }
        else:
            summary = close_month_summary()
        pdf = make_month_closing_pdf(summary)
        filename = f"valora-fechamento-mensal-{summary['month']}.pdf"
        return send_file(pdf, as_attachment=True, download_name=filename, mimetype="application/pdf")

    @app.route("/configuracoes", methods=["GET", "POST"])
    def configuracoes():
        if request.method == "POST":
            action = request.form.get("action")
            if action == "save_settings":
                settings_payload = load_settings()
                settings_payload["company_name"] = request.form.get("company_name", "Empresa demo").strip() or "Empresa demo"
                settings_payload["business_type"] = request.form.get("business_type", "Outro")
                # Plano não é mais editável manualmente. Ele vem da assinatura Stripe.
                settings_payload["plan"] = load_settings().get("plan", "Sem assinatura")
                settings_payload["visual_preference"] = request.form.get("visual_preference", "Graphite Premium")
                save_settings(settings_payload)
                flash("Configurações salvas.", "success")
            elif action == "clear_data":
                conn = get_db_connection(db_path)
                business_id = current_business_id()
                conn.execute("DELETE FROM transactions WHERE business_id = ?", (business_id,))
                conn.execute("DELETE FROM items WHERE business_id = ?", (business_id,))
                conn.execute("DELETE FROM closings WHERE business_id = ?", (business_id,))
                conn.execute("DELETE FROM month_closings WHERE business_id = ?", (business_id,))
                conn.commit()
                conn.close()
                flash("Dados limpos.", "success")
            elif action == "load_demo":
                seed_demo_data()
            return redirect(url_for("configuracoes"))
        ctx = dashboard_context()
        subscription = get_subscription_for_business()
        ctx.update({
            "page_title": "Configurações",
            "page_subtitle": "Empresa, plano e assinatura.",
            "page_actions": [],
            "subscription": subscription,
            "subscription_view": subscription_access(subscription),
        })
        return render_template("settings.html", **ctx)

    @app.route("/load_demo_data")
    def load_demo_data():
        seed_demo_data()
        return redirect(url_for("dashboard"))

    @app.route("/financas/delete/<int:item_id>", methods=["POST"])
    def delete_transaction(item_id):
        conn = get_db_connection(db_path)
        conn.execute("DELETE FROM transactions WHERE id = ? AND business_id = ?", (item_id, current_business_id()))
        conn.commit()
        conn.close()
        flash("Movimentação removida.", "success")
        return redirect(url_for("financas"))

    @app.route("/estoque/delete/<int:item_id>", methods=["POST"])
    def delete_item(item_id):
        conn = get_db_connection(db_path)
        conn.execute("DELETE FROM items WHERE id = ? AND business_id = ?", (item_id, current_business_id()))
        conn.commit()
        conn.close()
        flash("Produto removido.", "success")
        return redirect(url_for("estoque"))

    return app


# Compatível com `gunicorn app:app` e também com `gunicorn "app:create_app()"`.
app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="0.0.0.0", port=port)
