# PBI-017 — Role Scoring: lớp tích hợp

Điều phối: skill snapshot (PBI-016, qua adapter) + architecture evidence (PBI-012) → `app.ai.scoring.RoleScoringEngine`.
Không chứa logic chấm điểm; không ghi DB.

## API (prefix `/api/v1`)
- `GET /role-scoring/roles`
- `GET /role-scoring/roles/{role_key}/score?repository_id=&snapshot_ref=&rubric_version=`

## Nối PBI-016
Sửa duy nhất `dependencies.get_skill_snapshot_source`: trả về đối tượng thoả `skill_adapter.SkillSnapshotSource`
(`fetch(user_id, *, snapshot_ref=None) -> RawSkillSnapshot | None`, phải lọc theo user_id). Nếu payload 016
khác `SkillSnapshotInput`, truyền `mapper` vào `SkillSnapshotAdapter`. Engine/service không đổi.

## Chính sách evidence (`ArchitectureEvidencePolicy`)
- Loại evidence nguồn `directory_structure` (suy ra từ tên thư mục).
- Chỉ `verified` khi PBI-013 có `verification_status == "verified"` (tắt bằng `require_verified_contribution=False`).
- Chỉ đọc id/repo/commit/file_path/loại/nguồn/confidence; không đọc `matched_content`, `line_number`, `rationale`.
- Repo private: bắt buộc qua `verify_repository_access` + `verify_private_repo_consent`.

## Test
`cd backend && pytest tests/ai/scoring tests/modules/role_scoring`
