import os
import uuid
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

TEST_DB = "it_ai_profile_pbi030_test"

original_url = os.environ.get("DATABASE_URL")
if not original_url:
    raise SystemExit("DATABASE_URL missing")

url = make_url(original_url).set(database=TEST_DB)
engine = create_engine(url)

def assert_rejected(conn, sql, params, expected):
    try:
        with conn.begin_nested():
            conn.execute(text(sql), params)
    except DBAPIError as exc:
        code = getattr(exc.orig, "sqlstate", None)
        assert code == expected, (
            f"Expected SQLSTATE {expected}, got {code}"
        )
        print(f"PASS: rejected with SQLSTATE {code}")
    else:
        raise AssertionError("Operation should have been rejected")

with engine.connect() as conn:
    db = conn.execute(
        text("SELECT current_database()")
    ).scalar_one()

    if db != TEST_DB:
        raise SystemExit("SAFETY ERROR: Wrong database")

    print("Verified test database:", db)

# Kết thúc transaction được tạo tự động bởi SELECT.
    conn.rollback()

# Bắt đầu transaction riêng cho dữ liệu kiểm thử.
    tx = conn.begin()
    try:
        owner_id = -int(uuid.uuid4().int % 1000000000) - 1
        conn.execute(text("""
            INSERT INTO ita.users (id, email, full_name)
            VALUES (:id, :email, 'PBI030 Test User')
        """), {
            "id": owner_id,
            "email": f"pbi030-{uuid.uuid4().hex}@example.invalid"
        })

        ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        jobs = [str(uuid.uuid4()), str(uuid.uuid4())]

        insert_snapshot = text("""
            INSERT INTO ita.historical_snapshots (
                id, owner_id, source_job_id,
                visibility, scope, rubric_version,
                window_start, window_end, score,
                skills, evidence_summary,
                source_fingerprint, created_at
            )
            VALUES (
                :id, :owner_id, :job_id,
                'public', CAST(:scope AS jsonb), 'v1',
                '2026-01-01T00:00:00Z',
                '2026-06-01T00:00:00Z',
                :score, CAST(:skills AS jsonb),
                CAST('{}' AS jsonb), :fingerprint, now()
            )
        """)

        for i, score in enumerate([65, 82]):
            conn.execute(insert_snapshot, {
                "id": ids[i],
                "owner_id": owner_id,
                "job_id": jobs[i],
                "scope": '{"repositories":["demo-repo"]}',
                "score": score,
                "skills": (
                    '{"Python":70,"FastAPI":60}'
                    if i == 0 else
                    '{"Python":85,"FastAPI":80,"PostgreSQL":75}'
                ),
                "fingerprint": f"pbi030-test-{uuid.uuid4().hex}"
            })

        print("PASS: Created 2 snapshots")

        scores = conn.execute(text("""
            SELECT score
            FROM ita.historical_snapshots
            WHERE id IN (:a, :b)
            ORDER BY score
        """), {"a": ids[0], "b": ids[1]}).scalars().all()

        assert scores == [65, 82]
        assert scores[1] - scores[0] == 17
        print("PASS: Delta = +17")

        assert_rejected(
            conn,
            "UPDATE ita.historical_snapshots SET score=99 WHERE id=:id",
            {"id": ids[0]},
            "P0001"
        )
        print("PASS: UPDATE blocked")

        assert_rejected(
            conn,
            "DELETE FROM ita.historical_snapshots WHERE id=:id",
            {"id": ids[0]},
            "P0001"
        )
        print("PASS: DELETE blocked")

        assert_rejected(
            conn,
            """
            INSERT INTO ita.historical_snapshots
            SELECT :new_id, owner_id, :new_job,
                   visibility, scope, rubric_version,
                   window_start, window_end, 101,
                   skills, evidence_summary,
                   :fingerprint, now()
            FROM ita.historical_snapshots WHERE id=:id
            """,
            {
                "new_id": str(uuid.uuid4()),
                "new_job": str(uuid.uuid4()),
                "fingerprint": uuid.uuid4().hex,
                "id": ids[0]
            },
            "23514"
        )
        print("PASS: Score constraint")

        assert_rejected(
            conn,
            """
            INSERT INTO ita.historical_snapshots
            SELECT :new_id, owner_id, source_job_id,
                   visibility, scope, rubric_version,
                   window_start, window_end, score,
                   skills, evidence_summary,
                   :fingerprint, now()
            FROM ita.historical_snapshots WHERE id=:id
            """,
            {
                "new_id": str(uuid.uuid4()),
                "fingerprint": uuid.uuid4().hex,
                "id": ids[0]
            },
            "23505"
        )
        print("PASS: Duplicate source job blocked")

        final_score = conn.execute(text("""
            SELECT score FROM ita.historical_snapshots WHERE id=:id
        """), {"id": ids[0]}).scalar_one()

        assert final_score == 65
        print("PASS: Original snapshot unchanged")

    finally:
        tx.rollback()
        print("ROLLBACK: Test data removed")

print("ALL IMMUTABILITY TESTS PASSED")
