"""Verification service for fork provenance, repository ownership & real contribution
(PBI-013).

Strict compliance with Epic-03, FR-008, FR-010, FR-013:
- Distinguish original repo, fork, and parent metadata.
- Distinguish repository ownership from code authorship.
- Verify commit authorship using authenticated GitHub actor ID/login.
- Verify pull requests created by developer and verifiable merge state.
- Prevent double counting and profile inflation (forks with 0 user commits).
- Mark unavailable or incomplete data as 'unknown' rather than speculating.
- Fail closed and enforce server-side privacy/consent boundaries.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.core.time_range import resolve_range
from app.modules.analysis.models import (
    RepositoryVerification,
    VerificationEvidence,
)
from app.modules.analysis.schemas import (
    RepositoryVerificationResponse,
    RepositoryVerificationSummary,
    VerificationEvidenceItem,
    VerificationRequest,
)
from app.modules.auth.models import OAuthAccount
from app.modules.auth.service import get_user_github_token, has_private_access
from app.modules.github.client import (
    GitHubApiClient,
    GitHubApiError,
    GitHubEmptyRepositoryError,
    GitHubNotFoundError,
    GitHubPermissionError,
    GitHubRateLimitError,
    GitHubServerError,
)
from app.modules.github.models import Repository, user_repository
from app.modules.users.models import User

logger = logging.getLogger(__name__)

MAX_COMMITS_LIMIT = 1000
MAX_PRS_LIMIT = 500


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        val = value.replace("Z", "+00:00") if value.endswith("Z") else value
        dt = datetime.fromisoformat(val)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return None


def verify_repository_access(db: Session, repository_id: int, user: User) -> Repository:
    """Xác thực người dùng có liên kết và quyền truy cập repository."""
    stmt = (
        select(Repository)
        .join(user_repository, Repository.id == user_repository.c.repository_id)
        .where(
            user_repository.c.user_id == user.id,
            user_repository.c.repository_id == repository_id,
        )
    )
    repo = db.scalar(stmt)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy repository hoặc bạn không có quyền truy cập.",
        )
    if repo.private and not has_private_access(db, user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy repository hoặc bạn không có quyền truy cập.",
        )
    return repo


def verify_private_repo_consent(
    repo: Repository,
    scope: str | None,
    db: Session,
    user_id: int,
) -> None:
    """Xác thực quyền OAuth 'repo' và sự đồng thuận đối với repository riêng tư."""
    if not repo.private:
        return
    if not has_private_access(db, user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Truy cập repository riêng tư yêu cầu quyền đã được cấp phép.",
        )
    has_private_scope = bool(scope and "repo" in scope)
    if not has_private_scope:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Phân tích repository riêng tư yêu cầu token có scope 'repo'.",
        )
    from app.modules.consent.guards import require_private_access_consent

    require_private_access_consent(db, user_id, repo.id)


async def verify_repository_contributions(
    db: Session,
    repository_id: int,
    user: User,
    request: VerificationRequest | None = None,
    client: GitHubApiClient | None = None,
    job_id: str | None = None,
    report_id: int | None = None,
) -> RepositoryVerificationResponse:
    """Xác minh fork, quyền sở hữu và đóng góp thực tế từ GitHub API."""
    if request is None:
        request = VerificationRequest()

    # 1. Kiểm tra quyền truy cập repository & consent
    repo = verify_repository_access(db, repository_id, user)
    token, scopes = get_user_github_token(db, user.id)
    verify_private_repo_consent(repo, scopes, db=db, user_id=user.id)

    # 2. Định danh nhà phát triển đã xác thực
    oauth_acc = db.scalar(
        select(OAuthAccount).where(
            OAuthAccount.user_id == user.id,
            OAuthAccount.provider == "github",
        )
    )
    p_uid = getattr(oauth_acc, "provider_user_id", None)
    auth_github_user_id = str(p_uid) if p_uid is not None else None
    auth_github_login: str | None = None

    # Khởi tạo client
    api_client = client or GitHubApiClient(access_token=token or "")

    try:
        if token or client:
            user_profile = await api_client.get_authenticated_user()
            if isinstance(user_profile, dict):
                auth_github_login = user_profile.get("login")
                if user_profile.get("id"):
                    auth_github_user_id = str(user_profile.get("id"))
    except GitHubApiError:
        pass

    # 3. Phân loại repository provenance và metadata parent
    if repo.full_name and "/" in repo.full_name:
        owner, repo_name = repo.full_name.split("/", 1)
    else:
        owner, repo_name = repo.name, repo.name

    parent_metadata_status = "none"
    parent_repo_name: str | None = None
    parent_repo_url: str | None = None
    is_fork = bool(repo.is_fork)

    limitations: list[str] = [
        "Xác minh tác giả commit dựa trên định danh actor ID / login.",
        "Tên hoặc email trong commit không liên kết GitHub được coi là unverified.",
    ]

    try:
        repo_details = await api_client.get_repository_details(owner, repo_name)
        if isinstance(repo_details, dict):
            is_fork = bool(repo_details.get("fork", is_fork))
            if is_fork:
                parent_data = repo_details.get("parent")
                if isinstance(parent_data, dict):
                    parent_repo_name = parent_data.get("full_name")
                    parent_repo_url = parent_data.get("html_url")
                    parent_metadata_status = "verified"
                elif repo.fork_source:
                    parent_repo_name = repo.fork_source
                    parent_metadata_status = "unknown"
                else:
                    parent_metadata_status = "unknown"
                    limitations.append(
                        "Không thể lấy metadata repository gốc từ GitHub API."
                    )
    except (GitHubNotFoundError, GitHubPermissionError, GitHubApiError) as exc:
        if is_fork:
            parent_repo_name = repo.fork_source
            parent_metadata_status = "unknown"
            limitations.append(
                f"Không thể lấy chi tiết repository gốc ({type(exc).__name__})."
            )

    # 4. Xác định quyền sở hữu repository
    is_user_owner = bool(
        (auth_github_login and owner.lower() == auth_github_login.lower())
        or (repo.owner_id == user.id and not repo.full_name)
    )

    if is_user_owner:
        ownership_status = "fork_owner" if is_fork else "owner"
        provenance_type = "fork" if is_fork else "original"
    else:
        ownership_status = "collaborator"
        provenance_type = "collaboration"

    # 5. Xử lý khoảng thời gian (PBI-010 integration)
    time_range_info = None
    start_utc: datetime | None = None
    end_utc: datetime | None = None

    if request.mode:
        start_utc, end_utc = resolve_range(
            mode=request.mode,
            preset=request.preset,
            month=request.month,
            year=request.year,
            start_date=request.start_date,
            end_date=request.end_date,
            timezone_name=request.timezone,
        )
        time_range_info = {
            "start_utc": start_utc.isoformat(),
            "end_utc": end_utc.isoformat(),
            "timezone": request.timezone,
        }

    # 6. Thu thập và xác minh Commits
    target_branch = request.branch or repo.default_branch or "main"
    evidence_list: list[VerificationEvidenceItem] = []
    seen_commit_shas: set[str] = set()

    verified_commits_count = 0
    unverified_commits_count = 0
    verified_additions = 0
    verified_deletions = 0
    coverage_status = "complete"
    confidence = "high"

    try:
        raw_commits = await api_client.list_commits(
            owner=owner,
            repo=repo_name,
            since=start_utc,
            until=end_utc,
            sha=target_branch,
            per_page=100,
            max_pages=20,
        )

        sem = asyncio.Semaphore(10)

        async def _inspect_commit(
            c: dict[str, Any],
        ) -> VerificationEvidenceItem | None:
            sha = c.get("sha", "")
            if not sha or sha in seen_commit_shas:
                return None
            seen_commit_shas.add(sha)

            commit_meta = c.get("commit") or {}
            msg = (commit_meta.get("message") or "").split("\n")[0]
            git_author = commit_meta.get("author") or {}
            committer_date = (commit_meta.get("committer") or {}).get("date")
            author_date = git_author.get("date")
            recorded_at_str = committer_date or author_date

            if start_utc or end_utc:
                parsed_dt = _parse_timestamp(recorded_at_str)
                if parsed_dt:
                    if start_utc and parsed_dt < start_utc:
                        return None
                    if end_utc and parsed_dt >= end_utc:
                        return None

            author_obj = c.get("author")
            author_id = (
                str(author_obj.get("id"))
                if isinstance(author_obj, dict) and author_obj.get("id")
                else None
            )
            author_login = (
                author_obj.get("login") if isinstance(author_obj, dict) else None
            )
            author_type = (
                author_obj.get("type", "User")
                if isinstance(author_obj, dict)
                else "User"
            )
            git_author_name = git_author.get("name", "")

            is_bot = (
                author_type.lower() == "bot"
                or (author_login and "[bot]" in author_login.lower())
                or "[bot]" in git_author_name.lower()
            )
            is_merge = len(c.get("parents", [])) > 1

            id_match = bool(
                auth_github_user_id
                and author_id
                and author_id == str(auth_github_user_id)
            )
            login_match = bool(
                auth_github_login
                and author_login
                and author_login.lower() == auth_github_login.lower()
            )
            is_author_verified = (id_match or login_match) and not is_bot

            additions = None
            deletions = None
            c_stats = c.get("stats")
            if isinstance(c_stats, dict) and "additions" in c_stats:
                additions = int(c_stats.get("additions", 0))
                deletions = int(c_stats.get("deletions", 0))
            else:
                try:
                    async with sem:
                        details = await api_client.get_commit_details(
                            owner, repo_name, sha
                        )
                        stats = details.get("stats") or {}
                        additions = int(stats.get("additions", 0))
                        deletions = int(stats.get("deletions", 0))
                except Exception:
                    pass

            is_fork_inherited = False
            if is_author_verified:
                v_status = "verified"
                rationale = f"Commit {sha[:7]} xác thực bởi GitHub @{author_login}."
            else:
                if author_obj is None:
                    v_status = "unverified"
                    rationale = f"Commit {sha[:7]} thiếu liên kết GitHub; unverified."
                else:
                    if is_fork:
                        is_fork_inherited = True
                        v_status = "unverified"
                        rationale = (
                            f"Commit {sha[:7]} kế thừa từ repo gốc bởi @{author_login}."
                        )
                    else:
                        v_status = "unverified"
                        rationale = (
                            f"Commit {sha[:7]} do lập trình viên khác thực hiện."
                        )

            return VerificationEvidenceItem(
                evidence_type="commit",
                target_identifier=sha,
                verification_status=v_status,
                actor_login=author_login,
                actor_id=author_id,
                actor_type=author_type,
                html_url=(
                    c.get("html_url")
                    or f"https://github.com/{repo.full_name}/commit/{sha}"
                ),
                title_or_message=msg,
                is_merge=is_merge,
                is_bot=is_bot,
                is_fork_inherited=is_fork_inherited,
                additions=additions,
                deletions=deletions,
                recorded_at=recorded_at_str,
                rationale=rationale,
                metadata={
                    "sha": sha,
                    "parents_count": len(c.get("parents", [])),
                },
            )

        if raw_commits:
            processed_commits = await asyncio.gather(
                *[_inspect_commit(c) for c in raw_commits]
            )
            for ev in processed_commits:
                if ev is not None:
                    evidence_list.append(ev)
                    if ev.verification_status == "verified":
                        verified_commits_count += 1
                        verified_additions += ev.additions or 0
                        verified_deletions += ev.deletions or 0
                    else:
                        unverified_commits_count += 1

    except GitHubRateLimitError:
        coverage_status = "partial"
        confidence = "uncertain"
        limitations.append(
            "Đạt giới hạn GitHub rate-limit khi lấy commits; kết quả partial."
        )
    except (GitHubEmptyRepositoryError, GitHubNotFoundError):
        pass
    except (GitHubApiError, GitHubServerError) as exc:
        coverage_status = "partial"
        confidence = "uncertain"
        limitations.append(f"Lỗi khi thu thập commits: {type(exc).__name__}.")

    # 7. Thu thập và xác minh Pull Requests
    verified_prs_count = 0
    unverified_prs_count = 0
    seen_pr_numbers: set[int] = set()

    try:
        raw_prs = await api_client.list_pull_requests(
            owner=owner,
            repo=repo_name,
            state="all",
            sort="created",
            direction="desc",
            per_page=100,
            max_pages=10,
        )

        for pr in raw_prs:
            pr_num = pr.get("number")
            if not pr_num or pr_num in seen_pr_numbers:
                continue
            seen_pr_numbers.add(pr_num)

            created_at_str = pr.get("created_at")
            if start_utc or end_utc:
                parsed_dt = _parse_timestamp(created_at_str)
                if parsed_dt:
                    if start_utc and parsed_dt < start_utc:
                        continue
                    if end_utc and parsed_dt >= end_utc:
                        continue

            pr_user = pr.get("user") or {}
            pr_user_id = str(pr_user.get("id")) if pr_user.get("id") else None
            pr_user_login = pr_user.get("login")
            pr_state = pr.get("state", "open")
            pr_merged = bool(pr.get("merged_at") or pr.get("merged"))

            head_data = pr.get("head") or {}
            base_data = pr.get("base") or {}
            head_repo = head_data.get("repo") or {}
            base_repo = base_data.get("repo") or {}

            id_match = bool(
                auth_github_user_id
                and pr_user_id
                and pr_user_id == str(auth_github_user_id)
            )
            login_match = bool(
                auth_github_login
                and pr_user_login
                and pr_user_login.lower() == auth_github_login.lower()
            )
            is_pr_author = id_match or login_match

            if is_pr_author:
                pr_v_status = "verified"
                merge_text = "đã merge" if pr_merged else "chưa merge"
                rationale = (
                    f"Pull Request #{pr_num} do người dùng tạo "
                    f"({pr_state}, {merge_text})."
                )
                verified_prs_count += 1
            else:
                pr_v_status = "unverified"
                rationale = f"Pull Request #{pr_num} do @{pr_user_login} tạo."
                unverified_prs_count += 1

            evidence_list.append(
                VerificationEvidenceItem(
                    evidence_type="pull_request",
                    target_identifier=str(pr_num),
                    verification_status=pr_v_status,
                    actor_login=pr_user_login,
                    actor_id=pr_user_id,
                    actor_type=pr_user.get("type", "User"),
                    html_url=pr.get("html_url"),
                    title_or_message=pr.get("title", ""),
                    pr_state=pr_state,
                    pr_merged=pr_merged,
                    source_repo=head_repo.get("full_name"),
                    target_repo=base_repo.get("full_name"),
                    recorded_at=created_at_str,
                    rationale=rationale,
                    metadata={
                        "number": pr_num,
                        "state": pr_state,
                        "merged": pr_merged,
                    },
                )
            )

    except GitHubRateLimitError:
        coverage_status = "partial"
        confidence = "uncertain"
        limitations.append(
            "Đạt giới hạn GitHub API rate-limit trong quá trình thu thập PRs."
        )
    except (GitHubEmptyRepositoryError, GitHubNotFoundError):
        pass
    except (GitHubApiError, GitHubServerError) as exc:
        coverage_status = "partial"
        confidence = "uncertain"
        limitations.append(f"Lỗi khi thu thập Pull Requests: {type(exc).__name__}.")

    # 8. Xác định Verification Status và Flag Anti-Inflation
    anti_inflation_flag = False

    if is_fork:
        if verified_commits_count > 0 or verified_prs_count > 0:
            verification_status = "verified"
            rationale_summary = (
                f"Fork đã xác minh có đóng góp thực tế "
                f"({verified_commits_count} commits, {verified_prs_count} PRs)."
            )
        else:
            verification_status = "no_contribution"
            anti_inflation_flag = True
            rationale_summary = (
                "Fork do lập trình viên sở hữu nhưng chưa có commit/PR "
                "được xác minh. Toàn bộ mã nguồn là kế thừa từ upstream."
            )
            limitations.append(
                "Fork không chứa commit được xác minh của lập trình viên. "
                "Không tính điểm đóng góp cá nhân."
            )
    else:
        if verified_commits_count > 0 or verified_prs_count > 0:
            verification_status = "verified"
            rationale_summary = (
                f"Đã xác minh {verified_commits_count} commits và "
                f"{verified_prs_count} PRs của lập trình viên."
            )
        elif unverified_commits_count == 0 and unverified_prs_count == 0:
            verification_status = "no_contribution"
            rationale_summary = (
                "Repository rỗng hoặc không có hoạt động trong khoảng thời gian."
            )
        else:
            verification_status = "unverified"
            rationale_summary = (
                "Repository có hoạt động nhưng không có commit/PR của lập trình viên."
            )

    if parent_metadata_status == "unknown" and is_fork:
        if verification_status != "verified":
            verification_status = "unknown"
        confidence = "medium"

    # Add provenance evidence record
    provenance_ev = VerificationEvidenceItem(
        evidence_type="provenance",
        target_identifier=repo.full_name or repo.name,
        verification_status=(
            "verified" if parent_metadata_status != "unknown" else "unknown"
        ),
        actor_login=owner,
        html_url=repo.html_url,
        title_or_message=(
            f"Provenance: {provenance_type}, Ownership: {ownership_status}"
        ),
        rationale=(
            f"Repository {repo.name} ({'Fork' if is_fork else 'Original'}), "
            f"nguồn gốc: {parent_repo_name or 'gốc'}."
        ),
        source_repo=parent_repo_name,
        target_repo=repo.full_name or repo.name,
        metadata={
            "is_fork": is_fork,
            "parent_repo_name": parent_repo_name,
            "parent_metadata_status": parent_metadata_status,
            "ownership_status": ownership_status,
        },
    )
    evidence_list.insert(0, provenance_ev)

    verified_at = datetime.now(UTC)
    summary_data = {
        "anti_inflation_flag": anti_inflation_flag,
        "rationale_summary": rationale_summary,
        "verified_commits_count": verified_commits_count,
        "unverified_commits_count": unverified_commits_count,
        "verified_prs_count": verified_prs_count,
        "unverified_prs_count": unverified_prs_count,
        "total_commits": verified_commits_count + unverified_commits_count,
        "total_prs": verified_prs_count + unverified_prs_count,
    }

    # 9. Lưu trữ nguyên tử (Idempotent Persistence)
    existing_verif = db.scalar(
        select(RepositoryVerification).where(
            RepositoryVerification.repository_id == repo.id,
            RepositoryVerification.user_id == user.id,
        )
    )

    if existing_verif is None:
        verif_obj = RepositoryVerification(
            repository_id=repo.id,
            user_id=user.id,
        )
        db.add(verif_obj)
    else:
        verif_obj = existing_verif

    verif_obj.job_id = None if not job_id else job_id
    verif_obj.report_id = report_id
    verif_obj.provenance_type = provenance_type
    verif_obj.ownership_status = ownership_status
    verif_obj.is_fork = is_fork
    verif_obj.parent_repo_name = parent_repo_name
    verif_obj.parent_repo_url = parent_repo_url
    verif_obj.parent_metadata_status = parent_metadata_status
    verif_obj.verification_status = verification_status
    verif_obj.coverage_status = coverage_status
    verif_obj.confidence = confidence
    verif_obj.verified_commits_count = verified_commits_count
    verif_obj.unverified_commits_count = unverified_commits_count
    verif_obj.verified_prs_count = verified_prs_count
    verif_obj.unverified_prs_count = unverified_prs_count
    verif_obj.verified_additions = verified_additions
    verif_obj.verified_deletions = verified_deletions
    verif_obj.time_range = time_range_info
    verif_obj.limitations = limitations
    verif_obj.summary_data = summary_data
    verif_obj.verified_at = verified_at
    verif_obj.updated_at = verified_at

    db.flush()

    db.execute(
        delete(VerificationEvidence).where(
            VerificationEvidence.verification_id == verif_obj.id
        )
    )

    for item in evidence_list:
        ev_row = VerificationEvidence(
            verification_id=verif_obj.id,
            repository_id=repo.id,
            user_id=user.id,
            evidence_type=item.evidence_type,
            target_identifier=item.target_identifier,
            verification_status=item.verification_status,
            actor_login=item.actor_login,
            actor_id=item.actor_id,
            actor_type=item.actor_type,
            html_url=item.html_url,
            title_or_message=item.title_or_message,
            is_merge=item.is_merge,
            is_bot=item.is_bot,
            is_fork_inherited=item.is_fork_inherited,
            additions=item.additions,
            deletions=item.deletions,
            pr_state=item.pr_state,
            pr_merged=item.pr_merged,
            source_repo=item.source_repo,
            target_repo=item.target_repo,
            recorded_at=_parse_timestamp(item.recorded_at),
            rationale=item.rationale,
            metadata_=item.metadata,
        )
        db.add(ev_row)

    db.commit()

    return RepositoryVerificationResponse(
        id=verif_obj.id,
        repository_id=repo.id,
        repository_name=repo.name,
        repository_full_name=repo.full_name or repo.name,
        user_id=user.id,
        job_id=job_id,
        report_id=report_id,
        provenance_type=provenance_type,
        ownership_status=ownership_status,
        is_fork=is_fork,
        parent_repo_name=parent_repo_name,
        parent_repo_url=parent_repo_url,
        parent_metadata_status=parent_metadata_status,
        verification_status=verification_status,
        coverage_status=coverage_status,
        confidence=confidence,
        verified_commits_count=verified_commits_count,
        unverified_commits_count=unverified_commits_count,
        verified_prs_count=verified_prs_count,
        unverified_prs_count=unverified_prs_count,
        verified_additions=verified_additions,
        verified_deletions=verified_deletions,
        anti_inflation_flag=anti_inflation_flag,
        time_range=time_range_info,
        limitations=limitations,
        summary_data=summary_data,
        verified_at=verified_at.isoformat(),
        evidence=evidence_list,
    )


def get_stored_verification(
    db: Session,
    repository_id: int,
    user: User,
) -> RepositoryVerificationResponse | None:
    """Truy xuất bản ghi xác minh gần nhất đã lưu trong cơ sở dữ liệu."""
    verify_repository_access(db, repository_id, user)

    verif = db.scalar(
        select(RepositoryVerification)
        .where(
            RepositoryVerification.repository_id == repository_id,
            RepositoryVerification.user_id == user.id,
        )
        .order_by(desc(RepositoryVerification.verified_at))
    )
    if not verif:
        return None

    repo = db.scalar(select(Repository).where(Repository.id == repository_id))
    repo_name = repo.name if repo else "unknown"
    repo_full_name = repo.full_name or repo_name if repo else "unknown"

    ev_rows = db.scalars(
        select(VerificationEvidence)
        .where(VerificationEvidence.verification_id == verif.id)
        .order_by(VerificationEvidence.id.asc())
    ).all()

    evidence_items = [
        VerificationEvidenceItem(
            id=e.id,
            evidence_type=e.evidence_type,
            target_identifier=e.target_identifier,
            verification_status=e.verification_status,  # type: ignore[arg-type]
            actor_login=e.actor_login,
            actor_id=e.actor_id,
            actor_type=e.actor_type,
            html_url=e.html_url,
            title_or_message=e.title_or_message,
            is_merge=e.is_merge,
            is_bot=e.is_bot,
            is_fork_inherited=e.is_fork_inherited,
            additions=e.additions,
            deletions=e.deletions,
            pr_state=e.pr_state,
            pr_merged=e.pr_merged,
            source_repo=e.source_repo,
            target_repo=e.target_repo,
            recorded_at=e.recorded_at.isoformat() if e.recorded_at else None,
            rationale=e.rationale,
            metadata=e.metadata_,
        )
        for e in ev_rows
    ]

    anti_inflation_flag = bool(
        verif.summary_data.get("anti_inflation_flag", False)
        if isinstance(verif.summary_data, dict)
        else False
    )

    return RepositoryVerificationResponse(
        id=verif.id,
        repository_id=verif.repository_id,
        repository_name=repo_name,
        repository_full_name=repo_full_name,
        user_id=verif.user_id,
        job_id=str(verif.job_id) if verif.job_id else None,
        report_id=verif.report_id,
        provenance_type=verif.provenance_type,
        ownership_status=verif.ownership_status,
        is_fork=verif.is_fork,
        parent_repo_name=verif.parent_repo_name,
        parent_repo_url=verif.parent_repo_url,
        parent_metadata_status=verif.parent_metadata_status,
        verification_status=verif.verification_status,
        coverage_status=verif.coverage_status,
        confidence=verif.confidence,
        verified_commits_count=verif.verified_commits_count,
        unverified_commits_count=verif.unverified_commits_count,
        verified_prs_count=verif.verified_prs_count,
        unverified_prs_count=verif.unverified_prs_count,
        verified_additions=verif.verified_additions,
        verified_deletions=verif.verified_deletions,
        anti_inflation_flag=anti_inflation_flag,
        time_range=verif.time_range,
        limitations=verif.limitations,
        summary_data=verif.summary_data,
        verified_at=verif.verified_at.isoformat() if verif.verified_at else "",
        evidence=evidence_items,
    )


def get_verification_summary(
    db: Session,
    repository_id: int,
    user: User,
) -> RepositoryVerificationSummary | None:
    """Lấy bản tóm tắt xác minh để nhúng vào báo cáo phân tích mã nguồn."""
    verif = db.scalar(
        select(RepositoryVerification)
        .where(
            RepositoryVerification.repository_id == repository_id,
            RepositoryVerification.user_id == user.id,
        )
        .order_by(desc(RepositoryVerification.verified_at))
    )
    if not verif:
        return None

    anti_inflation_flag = bool(
        verif.summary_data.get("anti_inflation_flag", False)
        if isinstance(verif.summary_data, dict)
        else False
    )
    rationale = (
        verif.summary_data.get("rationale_summary")
        if isinstance(verif.summary_data, dict)
        else None
    )

    return RepositoryVerificationSummary(
        provenance_type=verif.provenance_type,
        ownership_status=verif.ownership_status,
        is_fork=verif.is_fork,
        parent_repo_name=verif.parent_repo_name,
        parent_repo_url=verif.parent_repo_url,
        parent_metadata_status=verif.parent_metadata_status,
        verification_status=verif.verification_status,
        coverage_status=verif.coverage_status,
        confidence=verif.confidence,
        verified_commits_count=verif.verified_commits_count,
        unverified_commits_count=verif.unverified_commits_count,
        verified_prs_count=verif.verified_prs_count,
        unverified_prs_count=verif.unverified_prs_count,
        verified_additions=verif.verified_additions,
        verified_deletions=verif.verified_deletions,
        anti_inflation_flag=anti_inflation_flag,
        rationale=rationale,
    )
