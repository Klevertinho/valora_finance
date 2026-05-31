"""Repository placeholder for Supabase migration.

The Flask app currently uses SQLite as a local authenticated fallback.
Production migration should map these operations to Supabase tables using
business_id and Row Level Security from supabase/schema.sql.
"""

class RepositoryNotConfigured(RuntimeError):
    pass


def using_local_fallback() -> bool:
    return True
