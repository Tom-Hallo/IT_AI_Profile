import os
import subprocess
from sqlalchemy.engine import make_url

TEST_DB = "it_ai_profile_pbi030_test"

original_url = os.environ.get("DATABASE_URL")
if not original_url:
    raise SystemExit("DATABASE_URL is missing")

parsed = make_url(original_url)
test_url = parsed.set(database=TEST_DB)

os.environ["DATABASE_URL"] = test_url.render_as_string(
    hide_password=False
)

from app.core.config import settings
from app.db.session import engine
from sqlalchemy import text

if engine.url.database != TEST_DB:
    raise SystemExit("SAFETY ERROR: Wrong database")

with engine.connect() as conn:
    actual = conn.execute(text("SELECT current_database()")).scalar_one()

if actual != TEST_DB:
    raise SystemExit("SAFETY ERROR: Connected to wrong database")

print("Verified database:", actual)

subprocess.run(["alembic", "current"], check=True)
subprocess.run(["alembic", "upgrade", "head"], check=True)
subprocess.run(["alembic", "current"], check=True)

print("PBI-030 migration test completed")
