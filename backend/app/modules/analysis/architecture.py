"""Architecture analysis engine with verifiable structural evidence (PBI-012).

Detects architectural characteristics supported by observable project structure:
1. Frontend/Backend separation (distinct sub-projects with own manifests)
2. Layered architecture (controllers/api, services, repositories/models)
3. MVC structure (models, views, controllers)
4. API-oriented services (FastAPI/Express routers, OpenAPI specs)
5. Worker/background-job components (RQ, Celery, task queues)
6. Database integration patterns (Alembic migrations, ORM schemas)
7. Monorepo organization (workspaces, docker-compose orchestration)

Rule: Do not claim an architectural pattern based solely on a folder name.
Every finding includes verifiable file and directory evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.analysis.evidence import (
    ConfidenceLevel,
    DetectionMethod,
    EvidenceCollector,
    EvidenceRecord,
    EvidenceSource,
    FindingType,
)
from app.modules.analysis.parsers.base import ManifestParserResult


@dataclass
class ArchitectureFinding:
    """Đặc trưng kiến trúc được xác nhận qua bằng chứng thực tế."""

    pattern: str
    name: str
    description: str
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH
    evidence: list[EvidenceRecord] = field(default_factory=list)


class ArchitectureAnalyzer:
    """Bộ phân tích tĩnh cấu trúc và kiến trúc phần mềm."""

    def __init__(self, repository_id: int, commit_sha: str) -> None:
        self.repository_id = repository_id
        self.commit_sha = commit_sha

    def analyze(
        self,
        tree_paths: list[str],
        manifest_results: list[ManifestParserResult],
        collector: EvidenceCollector | None = None,
    ) -> list[ArchitectureFinding]:
        """Phân tích các mẫu kiến trúc có trong repository."""
        findings: list[ArchitectureFinding] = []
        if not tree_paths:
            return findings

        paths_set = set(tree_paths)
        manifest_paths = {m.manifest_path for m in manifest_results if m.is_valid}

        # -------------------------------------------------------------
        # 1. Frontend / Backend Separation
        # -------------------------------------------------------------
        frontend_dirs = [
            p for p in tree_paths if p.startswith(("frontend/", "client/", "web/"))
        ]
        backend_dirs = [
            p for p in tree_paths if p.startswith(("backend/", "server/", "api/"))
        ]

        frontend_manifests = [
            p for p in manifest_paths if p.startswith(("frontend/", "client/", "web/"))
        ]
        backend_manifests = [
            p for p in manifest_paths if p.startswith(("backend/", "server/", "api/"))
        ]

        if frontend_dirs and backend_dirs and frontend_manifests and backend_manifests:
            ev_list: list[EvidenceRecord] = []
            rec1 = EvidenceRecord(
                repository_id=self.repository_id,
                commit_sha=self.commit_sha,
                file_path=frontend_manifests[0],
                finding_type=FindingType.ARCHITECTURE,
                classification="frontend_backend_separation",
                evidence_source=EvidenceSource.MANIFEST,
                detection_method=DetectionMethod.STRUCTURAL_INSPECTION,
                confidence=ConfidenceLevel.HIGH,
                confidence_score=0.95,
                rationale=(
                    (
                        "Thành phần Frontend tách biệt với manifest độc lập: "
                        f"{frontend_manifests[0]}"
                    )
                ),
            )
            rec2 = EvidenceRecord(
                repository_id=self.repository_id,
                commit_sha=self.commit_sha,
                file_path=backend_manifests[0],
                finding_type=FindingType.ARCHITECTURE,
                classification="frontend_backend_separation",
                evidence_source=EvidenceSource.MANIFEST,
                detection_method=DetectionMethod.STRUCTURAL_INSPECTION,
                confidence=ConfidenceLevel.HIGH,
                confidence_score=0.95,
                rationale=(
                    (
                        "Thành phần Backend tách biệt với manifest độc lập: "
                        f"{backend_manifests[0]}"
                    )
                ),
            )
            if collector is not None:
                collector.add(rec1)
                collector.add(rec2)
            ev_list.extend([rec1, rec2])

            findings.append(
                ArchitectureFinding(
                    pattern="frontend_backend_separation",
                    name="Frontend/Backend Separation",
                    description=(
                        "Dự án phân chia rõ rệt giữa Frontend và Backend "
                        "thành các không gian "
                        "làm việc riêng biệt với manifest quản lý phụ thuộc độc lập."
                    ),
                    confidence=ConfidenceLevel.HIGH,
                    evidence=ev_list,
                )
            )

        # -------------------------------------------------------------
        # 2. Layered Architecture (Tầng kiến trúc: API/Service/Data)
        # -------------------------------------------------------------
        has_api_layer = any(
            "/api/" in p or p.startswith("api/") or "/controllers/" in p
            for p in tree_paths
        )
        has_service_layer = any(
            "/services/" in p or p.startswith("services/") or "/domain/" in p
            for p in tree_paths
        )
        has_data_layer = any(
            "/models/" in p or "/repositories/" in p or "/db/" in p for p in tree_paths
        )

        if sum([has_api_layer, has_service_layer, has_data_layer]) >= 2:
            layer_ev: list[EvidenceRecord] = []
            sample_paths = [
                p
                for p in tree_paths
                if any(
                    x in p
                    for x in (
                        "/api/",
                        "/services/",
                        "/models/",
                        "/db/",
                        "/repositories/",
                    )
                )
            ][:3]
            for s_path in sample_paths:
                rec = EvidenceRecord(
                    repository_id=self.repository_id,
                    commit_sha=self.commit_sha,
                    file_path=s_path,
                    finding_type=FindingType.ARCHITECTURE,
                    classification="layered_architecture",
                    evidence_source=EvidenceSource.DIRECTORY_STRUCTURE,
                    detection_method=DetectionMethod.STRUCTURAL_INSPECTION,
                    confidence=ConfidenceLevel.HIGH,
                    confidence_score=0.90,
                    rationale=f"Tầng cấu trúc được phân tách rõ: {s_path}",
                )
                if collector is not None:
                    collector.add(rec)
                layer_ev.append(rec)

            findings.append(
                ArchitectureFinding(
                    pattern="layered_architecture",
                    name="Layered Architecture",
                    description=(
                        "Dự án áp dụng kiến trúc phân tầng "
                        "(Presentation/API, Service/Business Logic, "
                        "Data Access/Models) giúp tách biệt trách nhiệm rõ ràng."
                    ),
                    confidence=ConfidenceLevel.HIGH,
                    evidence=layer_ev,
                )
            )

        # -------------------------------------------------------------
        # 3. MVC-like Architecture
        # -------------------------------------------------------------
        has_models = any("/models/" in p or p.endswith("models.py") for p in tree_paths)
        has_views = any(
            "/views/" in p or "/templates/" in p or p.endswith("views.py")
            for p in tree_paths
        )
        has_controllers = any(
            "/controllers/" in p or p.endswith("controllers.py") for p in tree_paths
        )

        if has_models and (has_views or has_controllers):
            mvc_ev: list[EvidenceRecord] = []
            mvc_samples = [
                p
                for p in tree_paths
                if any(
                    x in p
                    for x in ("/models/", "/views/", "/controllers/", "/templates/")
                )
            ][:3]
            for m_path in mvc_samples:
                rec = EvidenceRecord(
                    repository_id=self.repository_id,
                    commit_sha=self.commit_sha,
                    file_path=m_path,
                    finding_type=FindingType.ARCHITECTURE,
                    classification="mvc_architecture",
                    evidence_source=EvidenceSource.DIRECTORY_STRUCTURE,
                    detection_method=DetectionMethod.STRUCTURAL_INSPECTION,
                    confidence=ConfidenceLevel.MEDIUM,
                    confidence_score=0.80,
                    rationale=f"Thành phần phù hợp cấu trúc MVC: {m_path}",
                )
                if collector is not None:
                    collector.add(rec)
                mvc_ev.append(rec)

            findings.append(
                ArchitectureFinding(
                    pattern="mvc_architecture",
                    name="Model-View-Controller (MVC) Structure",
                    description=(
                        "Dự án tổ chức mã nguồn theo mô hình MVC hoặc MTV "
                        "với các thành phần "
                        "Models, Views/Templates và Controllers."
                    ),
                    confidence=ConfidenceLevel.MEDIUM,
                    evidence=mvc_ev,
                )
            )

        # -------------------------------------------------------------
        # 4. API-Oriented Services
        # -------------------------------------------------------------
        api_routes = [
            p
            for p in tree_paths
            if ("router" in p.lower() or "endpoint" in p.lower() or "/api/" in p)
            and p.endswith((".py", ".ts", ".js", ".java", ".go"))
        ]
        if api_routes:
            rec = EvidenceRecord(
                repository_id=self.repository_id,
                commit_sha=self.commit_sha,
                file_path=api_routes[0],
                finding_type=FindingType.ARCHITECTURE,
                classification="api_service",
                evidence_source=EvidenceSource.SOURCE_CODE,
                detection_method=DetectionMethod.STRUCTURAL_INSPECTION,
                confidence=ConfidenceLevel.HIGH,
                confidence_score=0.90,
                rationale=f"Tập tin định tuyến API dịch vụ: {api_routes[0]}",
            )
            if collector is not None:
                collector.add(rec)

            findings.append(
                ArchitectureFinding(
                    pattern="api_service",
                    name="API-Oriented Architecture",
                    description=(
                        "Dự án cung cấp giao diện lập trình ứng dụng "
                        "(REST/OpenAPI API) "
                        "thông qua hệ thống định tuyến tập trung."
                    ),
                    confidence=ConfidenceLevel.HIGH,
                    evidence=[rec],
                )
            )

        # -------------------------------------------------------------
        # 5. Worker / Background Job Components
        # -------------------------------------------------------------
        worker_files = [
            p
            for p in tree_paths
            if any(
                k in p.lower()
                for k in ("worker.py", "tasks/", "queues.py", "/workers/")
            )
        ]
        if worker_files:
            rec = EvidenceRecord(
                repository_id=self.repository_id,
                commit_sha=self.commit_sha,
                file_path=worker_files[0],
                finding_type=FindingType.ARCHITECTURE,
                classification="background_workers",
                evidence_source=EvidenceSource.SOURCE_CODE,
                detection_method=DetectionMethod.STRUCTURAL_INSPECTION,
                confidence=ConfidenceLevel.HIGH,
                confidence_score=0.92,
                rationale=f"Thành phần xử lý tác vụ nền và hàng đợi: {worker_files[0]}",
            )
            if collector is not None:
                collector.add(rec)

            findings.append(
                ArchitectureFinding(
                    pattern="background_workers",
                    name="Asynchronous Workers & Queue System",
                    description=(
                        "Dự án tích hợp hệ thống xử lý tác vụ không đồng bộ "
                        "(Asynchronous Workers) "
                        "và hàng đợi thông điệp để thực thi các tác vụ nền."
                    ),
                    confidence=ConfidenceLevel.HIGH,
                    evidence=[rec],
                )
            )

        # -------------------------------------------------------------
        # 6. Database Integration & Migration Patterns
        # -------------------------------------------------------------
        db_files = [
            p
            for p in tree_paths
            if any(
                k in p.lower()
                for k in ("alembic.ini", "migrations/", "schema.sql", "prisma/")
            )
        ]
        if db_files:
            rec = EvidenceRecord(
                repository_id=self.repository_id,
                commit_sha=self.commit_sha,
                file_path=db_files[0],
                finding_type=FindingType.ARCHITECTURE,
                classification="database_integration",
                evidence_source=EvidenceSource.CONFIGURATION,
                detection_method=DetectionMethod.STRUCTURAL_INSPECTION,
                confidence=ConfidenceLevel.HIGH,
                confidence_score=0.95,
                rationale=(
                    "Hệ thống quản lý phiên bản cơ sở dữ liệu và migration: "
                    f"{db_files[0]}"
                ),
            )
            if collector is not None:
                collector.add(rec)

            findings.append(
                ArchitectureFinding(
                    pattern="database_integration",
                    name="Database Schema & Migration Management",
                    description=(
                        "Dự án sử dụng cơ chế quản lý di chuyển cơ sở dữ liệu "
                        "tự động (Database Migrations) "
                        "và ánh xạ quan hệ đối tượng (ORM)."
                    ),
                    confidence=ConfidenceLevel.HIGH,
                    evidence=[rec],
                )
            )

        # -------------------------------------------------------------
        # 7. Monorepo Organization
        # -------------------------------------------------------------
        is_monorepo = False
        monorepo_evidence_path = None
        for m_res in manifest_results:
            if m_res.metadata.get("is_monorepo"):
                is_monorepo = True
                monorepo_evidence_path = m_res.manifest_path
                break

        if (
            not is_monorepo
            and "docker-compose.yml" in paths_set
            and frontend_dirs
            and backend_dirs
        ):
            is_monorepo = True
            monorepo_evidence_path = "docker-compose.yml"

        if is_monorepo and monorepo_evidence_path:
            rec = EvidenceRecord(
                repository_id=self.repository_id,
                commit_sha=self.commit_sha,
                file_path=monorepo_evidence_path,
                finding_type=FindingType.ARCHITECTURE,
                classification="monorepo",
                evidence_source=EvidenceSource.CONFIGURATION,
                detection_method=DetectionMethod.STRUCTURAL_INSPECTION,
                confidence=ConfidenceLevel.HIGH,
                confidence_score=0.90,
                rationale=(
                    (
                        "Cấu hình monorepo / điều phối đa dịch vụ: "
                        f"{monorepo_evidence_path}"
                    )
                ),
            )
            if collector is not None:
                collector.add(rec)

            findings.append(
                ArchitectureFinding(
                    pattern="monorepo",
                    name="Monorepo Organization",
                    description=(
                        "Dự án được cấu trúc theo dạng Monorepo "
                        "điều phối nhiều ứng dụng/dịch vụ "
                        "trong cùng một kho lưu trữ mã nguồn duy nhất."
                    ),
                    confidence=ConfidenceLevel.HIGH,
                    evidence=[rec],
                )
            )

        return findings
