# PBI-017 — Role-based Scoring Engine

Lõi chấm điểm role, độc lập với PBI-016 (chỉ nhận DTO, không đọc DB/model của PBI-016).

```python
from app.ai.scoring import RoleScoringEngine, RoleScoringInput

result = RoleScoringEngine().score(
    RoleScoringInput(role_key="backend_developer", skill_snapshot=..., architecture=...)
)
```

- `schemas.py`: input (`RoleScoringInput`, `SkillSnapshotInput`, `ArchitectureEvidenceSet`,
  `EvidenceRef`) và output (`RoleScoreResult`, `CriterionResult`). `EvidenceRef.from_record()`
  chuyển từ `EvidenceRecord`/`AnalysisEvidence` của PBI-012.
- `rubrics/*.json`: rubric có version. Thêm role = thêm file JSON hoặc
  `RubricRegistry.register_data(...)`; không sửa engine. Trọng số/ngưỡng là **đề xuất ban đầu,
  chưa hiệu chỉnh** (`calibration_status = proposed_unvalidated`).
- `evidence_catalog.py`: chỉ các pattern kiến trúc mà `ArchitectureAnalyzer` thật sự phát ra
  (có test đối chiếu mã nguồn) và danh sách số liệu bị cấm (commit/LOC/repo/stars/forks).
- Trạng thái: `SCORED | UNKNOWN | INSUFFICIENT | CONFLICTING`. Thiếu dữ liệu → `score = None`,
  không bao giờ 0. Tổng điểm chỉ tính khi `coverage ≥ min_coverage` và mọi tiêu chí
  `required` đều SCORED. `confidence` mô tả độ đầy đủ/nhất quán của bằng chứng,
  không phải xác suất đúng.

Chờ PBI-016: danh mục `skill_key` thật (rubric đang dùng tên chuẩn hoá như `python`,
`fastapi`, `react`), thang điểm/confidence (giả định 0..100), cách đánh dấu evidence đã verify.

Test: `cd backend && pytest tests/ai/scoring`

## Chống tăng điểm giả (QA PBI-017)

- Evidence có `commit_sha` được định danh theo (SHA, file_path, finding_type,
  classification), **không** theo `repository_id`: fork/bản sao cùng commit và cùng file
  không tạo thêm bằng chứng (engine ghi nhận `DUPLICATE`, giữ confidence thấp nhất).
  Evidence không có SHA vẫn tách theo repository.
- commit/LOC/số repository/stars/forks không có đường vào DTO (`extra="forbid"`) và bị
  loại nếu xuất hiện như skill key hoặc finding type.
- Test: `tests/ai/scoring/test_anti_inflation.py`,
  `tests/modules/role_scoring/test_anti_inflation_integration.py`.
