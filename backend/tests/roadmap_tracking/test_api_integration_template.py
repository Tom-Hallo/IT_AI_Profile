"""Integration contract scenarios for dedicated PostgreSQL test database.

Do not enable until the project-specific auth fixtures and isolated DB are wired.
This file is a contract template, NOT a passing integration test.

Required checks:
1. User A PATCH milestone -> history entry with old/new status, timestamp, note.
2. User B GET/PATCH/re-evaluate/apply/reject User A roadmap -> 404.
3. Same snapshot re-evaluate twice -> no duplicate suggestion.
4. Different rubric/scope/period -> 422, zero writes.
5. Apply suggestion -> one new history entry, all earlier entries unchanged.
6. Reject suggestion -> milestone and history unchanged.
7. Concurrent PATCH with stale expected_version -> 409.
8. Re-apply same suggestion -> 409.
9. Mock adapter disabled in production -> 404.
10. Re-evaluate snapshot owned by another user -> 404.
"""
