"""Collaboration, Pull Request, Review, CI & Problem-Solving Analysis Service
(PBI-014).

Strict compliance with Epic-03, FR-010:
- Collect accessible PRs, reviews, check runs (Checks API) & commit statuses.
- Preserve exact status and timestamps for merged, closed unmerged and open PRs.
- Associate evidence accurately with repo, PR number, commit SHA & check name.
- NEVER penalize or infer low competency from rejected/closed PRs, changes, or
  failed CI.
- Detect evidence-grounded problem-solving sequences and iterative review loops.
- Enforce strict server-side authorization, private repo consent & atomic
  persistence.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, desc, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.types import JSON

from app.core.time_range import resolve_range
from app.modules.analysis.models import (
    CollaborationAnalysis,
    CollaborationEvidence,
)
from app.modules.analysis.schemas import (
    CollaborationAnalysisRequest,
    CollaborationAnalysisResponse,
    CollaborationEvidenceItem,
    CollaborationEvidenceListResponse,
    CollaborationObservation,
    ProblemSolvingSequence,
)
from app.modules.analysis.verification_service import (
    verify_private_repo_consent,
    verify_repository_access,
)
from app.modules.auth.models import OAuthAccount
from app.modules.auth.service import get_user_github_token
from app.modules.github.client import (
    GitHubApiClient,
    GitHubApiError,
    GitHubEmptyRepositoryError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubServerError,
    GitHubTokenRevokedError,
)
from app.modules.github.models import Repository
from app.modules.users.models import User

logger = logging.getLogger(__name__)

MAX_PRS_LIMIT = 200
MAX_REVIEWS_PER_PR = 50
MAX_CHECKS_PER_COMMIT = 50


def _parse_timestamp(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    try:
        val = value.replace("Z", "+00:00") if value.endswith("Z") else value
        dt = datetime.fromisoformat(val)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return None


async def analyze_repository_collaboration(
    db: Session,
    repository_id: int,
    user: User,
    request: CollaborationAnalysisRequest,
    job_id: str | None = None,
    report_id: int | None = None,
    persist: bool = True,
    custom_client: GitHubApiClient | None = None,
) -> CollaborationAnalysisResponse:
    """Thực hiện thu thập và phân tích Pull Request, Review, CI & xử lý lỗi."""

    repo = verify_repository_access(db, repository_id, user)
    owner = repo.owner_login or (repo.full_name.split("/")[0] if repo.full_name else "")
    repo_name = repo.name

    # Hàm này trả về tuple: (token, OAuth scopes).
    token, scopes = get_user_github_token(db, user.id)

    if not token and custom_client is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tài khoản chưa liên kết GitHub hoặc token không khả dụng.",
        )

    # Private repo phải được kiểm tra bằng scope thật, không phải None.
    verify_private_repo_consent(repo, scopes, db, user.id)

    # 2. Khởi tạo GitHub Client và xác thực người dùng
    oauth_acc = db.scalar(
        select(OAuthAccount).where(
            OAuthAccount.user_id == user.id,
            OAuthAccount.provider == "github",
        )
    )

    auth_github_user_id: str | None = (
        str(oauth_acc.provider_user_id)
        if oauth_acc and oauth_acc.provider_user_id is not None
        else None
    )
    auth_github_login: str | None = None

    client = custom_client if custom_client is not None else GitHubApiClient(token)

    try:
        gh_user = await client.get_authenticated_user()
        auth_github_login = gh_user.get("login")
        if not auth_github_user_id and gh_user.get("id"):
            auth_github_user_id = str(gh_user["id"])
    except GitHubTokenRevokedError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="GitHub token không hợp lệ hoặc đã bị thu hồi.",
        ) from exc
    except GitHubRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="GitHub API rate limit đã đạt giới hạn.",
        ) from exc
    except (GitHubApiError, GitHubServerError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Lỗi khi kết nối GitHub API: {type(exc).__name__}",
        ) from exc

    # 3. Phân giải khoảng thời gian
    time_range_info = None
    since_dt: datetime | None = None
    until_dt: datetime | None = None

    if request.mode or request.preset or request.start_date:
        try:
            resolved = resolve_range(
                mode=request.mode or "preset",
                preset=request.preset,
                month=request.month,
                year=int(request.year) if request.year else None,
                start=request.start_date,
                end=request.end_date,
                tz_name=request.timezone,
            )
            since_dt = resolved.start
            until_dt = resolved.end
            time_range_info = {
                "start": since_dt.isoformat(),
                "end": until_dt.isoformat(),
                "timezone": request.timezone,
                "label": getattr(resolved, "label", request.mode),
            }
        except HTTPException:
            raise
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Khoảng thời gian phân tích không hợp lệ.",
            ) from exc

    coverage_status = "complete"
    confidence = "high"
    limitations: list[str] = []
    collection_truncated = False

    def mark_truncated() -> None:
        nonlocal collection_truncated
        collection_truncated = True

    # 4. Thu thập Pull Requests
    raw_prs: list[dict[str, Any]] = []
    try:
        raw_prs = await client.list_pull_requests(
            owner=owner,
            repo=repo_name,
            state="all",
            sort="created",
            direction="desc",
            per_page=100,
            max_pages=2,
            on_truncated=mark_truncated,
        )
    except GitHubRateLimitError:
        coverage_status = "partial"
        confidence = "uncertain"
        limitations.append(
            "Đạt giới hạn GitHub API rate-limit trong quá trình thu thập PRs."
        )
    except (GitHubEmptyRepositoryError, GitHubNotFoundError):
        raw_prs = []
    except (GitHubApiError, GitHubServerError) as exc:
        coverage_status = "partial"
        confidence = "uncertain"
        limitations.append(f"Lỗi khi thu thập Pull Requests: {type(exc).__name__}.")

    evidence_list: list[CollaborationEvidenceItem] = []
    total_prs_analyzed = 0
    merged_prs_count = 0
    closed_unmerged_prs_count = 0
    open_prs_count = 0
    user_prs_count = 0
    external_prs_count = 0

    total_reviews_analyzed = 0
    approved_reviews_count = 0
    changes_requested_count = 0
    commented_reviews_count = 0
    dismissed_reviews_count = 0
    user_reviews_conducted_count = 0
    user_reviews_received_count = 0

    total_checks_analyzed = 0
    successful_checks_count = 0
    failed_checks_count = 0
    pending_checks_count = 0
    other_checks_count = 0

    prs_with_context: list[dict[str, Any]] = []

    for pr in raw_prs:
        pr_num = pr.get("number")
        if not pr_num:
            continue

        # Lọc theo nhánh đích (base branch) của Pull Request.
        if request.branch:
            base_info = pr.get("base") or {}
            if base_info.get("ref") != request.branch:
                continue

        created_at_dt = _parse_timestamp(pr.get("created_at"))
        updated_at_dt = _parse_timestamp(pr.get("updated_at"))
        closed_at_dt = _parse_timestamp(pr.get("closed_at"))
        merged_at_dt = _parse_timestamp(pr.get("merged_at"))

        if since_dt and created_at_dt and created_at_dt < since_dt:
            if not updated_at_dt or updated_at_dt < since_dt:
                continue
        if until_dt and created_at_dt and created_at_dt > until_dt:
            continue

        total_prs_analyzed += 1

        pr_user = pr.get("user") or {}
        pr_user_id = str(pr_user.get("id")) if pr_user.get("id") else None
        pr_user_login = pr_user.get("login")

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
            user_prs_count += 1
        else:
            external_prs_count += 1

        is_merged = bool(merged_at_dt or pr.get("merged"))
        raw_state = pr.get("state", "open")

        if is_merged:
            normalized_state = "merged"
            merged_prs_count += 1
            rationale = (
                f"Pull Request #{pr_num} đã được merge vào nhánh "
                f"'{pr.get('base', {}).get('ref', 'main')}'. "
                "Ghi nhận đóng góp cộng tác được tích hợp."
            )
        elif raw_state == "closed":
            normalized_state = "closed_unmerged"
            closed_unmerged_prs_count += 1
            rationale = (
                f"Pull Request #{pr_num} đã đóng mà không merge. "
                "Đóng PR chưa merge là hoạt động dự án bình thường "
                "(đổi hướng kỹ thuật, tái cấu trúc hoặc giải pháp thay thế), "
                "không phản ánh năng lực kém."
            )
        else:
            normalized_state = "open"
            open_prs_count += 1
            rationale = f"Pull Request #{pr_num} đang mở (open)."

        head_info = pr.get("head") or {}
        head_sha = head_info.get("sha")

        pr_evidence = CollaborationEvidenceItem(
            evidence_type="pull_request",
            target_identifier=f"PR #{pr_num}",
            pr_number=pr_num,
            commit_sha=head_sha,
            state=normalized_state,
            actor_login=pr_user_login,
            actor_id=pr_user_id,
            actor_type=pr_user.get("type", "User"),
            is_profile_owner=is_pr_author,
            html_url=pr.get("html_url"),
            title_or_message=pr.get("title", ""),
            recorded_at=pr.get("created_at"),
            rationale=rationale,
            metadata={
                "number": pr_num,
                "state": normalized_state,
                "raw_state": raw_state,
                "is_merged": is_merged,
                "merged_at": pr.get("merged_at"),
                "closed_at": pr.get("closed_at"),
                "head_ref": head_info.get("ref"),
                "base_ref": pr.get("base", {}).get("ref"),
            },
        )
        evidence_list.append(pr_evidence)

        prs_with_context.append(
            {
                "pr_num": pr_num,
                "head_sha": head_sha,
                "is_pr_author": is_pr_author,
                "author_login": pr_user_login,
                "state": normalized_state,
                "created_at": created_at_dt,
                "closed_at": closed_at_dt,
                "merged_at": merged_at_dt,
                "reviews": [],
                "checks": [],
                "statuses": [],
            }
        )

    # 5. Thu thập Reviews và CI Checks cho các PR
    prs_to_inspect = prs_with_context[:MAX_PRS_LIMIT]

    for pr_ctx in prs_to_inspect:
        pr_num = pr_ctx["pr_num"]
        head_sha = pr_ctx["head_sha"]
        is_pr_author = pr_ctx["is_pr_author"]

        # A. Thu thập Reviews
        try:
            reviews = await client.list_pull_request_reviews(
                owner=owner,
                repo=repo_name,
                pull_number=pr_num,
                per_page=50,
                max_pages=1,
                on_truncated=mark_truncated,
            )
            for rev in reviews:
                rev_id = rev.get("id")
                rev_user = rev.get("user") or {}
                rev_login = rev_user.get("login")
                rev_id_str = str(rev_user.get("id")) if rev_user.get("id") else None
                rev_state = (rev.get("state") or "COMMENTED").upper()
                rev_submitted_at = rev.get("submitted_at")

                is_rev_owner = bool(
                    auth_github_login
                    and rev_login
                    and rev_login.lower() == auth_github_login.lower()
                )

                total_reviews_analyzed += 1
                if rev_state == "APPROVED":
                    approved_reviews_count += 1
                    rev_rationale = (
                        f"Review #{rev_id} trên PR #{pr_num} đã phê duyệt (APPROVED) "
                        "mã nguồn."
                    )
                elif rev_state == "CHANGES_REQUESTED":
                    changes_requested_count += 1
                    rev_rationale = (
                        f"Review #{rev_id} trên PR #{pr_num} yêu cầu điều chỉnh "
                        "(CHANGES_REQUESTED). Yêu cầu thay đổi là phần chuẩn mực "
                        "của quy trình phản biện chuyên nghiệp, không phản ánh "
                        "năng lực kém."
                    )
                elif rev_state == "COMMENTED":
                    commented_reviews_count += 1
                    rev_rationale = (
                        f"Review #{rev_id} trên PR #{pr_num} đóng góp nhận xét "
                        "thảo luận."
                    )
                elif rev_state == "DISMISSED":
                    dismissed_reviews_count += 1
                    rev_rationale = (
                        f"Review #{rev_id} trên PR #{pr_num} đã được bãi miễn "
                        "(DISMISSED)."
                    )
                else:
                    rev_rationale = (
                        f"Review #{rev_id} trên PR #{pr_num} ở trạng thái {rev_state}."
                    )

                if is_rev_owner:
                    user_reviews_conducted_count += 1
                elif is_pr_author:
                    user_reviews_received_count += 1

                evidence_list.append(
                    CollaborationEvidenceItem(
                        evidence_type="review",
                        target_identifier=f"Review #{rev_id} (PR #{pr_num})",
                        pr_number=pr_num,
                        commit_sha=rev.get("commit_id") or head_sha,
                        state=rev_state,
                        actor_login=rev_login,
                        actor_id=rev_id_str,
                        actor_type=rev_user.get("type", "User"),
                        is_profile_owner=is_rev_owner,
                        html_url=rev.get("html_url"),
                        title_or_message=(rev.get("body") or "")[:200],
                        recorded_at=rev_submitted_at,
                        rationale=rev_rationale,
                        metadata={
                            "review_id": rev_id,
                            "pr_number": pr_num,
                            "state": rev_state,
                            "commit_id": rev.get("commit_id"),
                        },
                    )
                )

                pr_ctx["reviews"].append(
                    {
                        "id": rev_id,
                        "state": rev_state,
                        "reviewer": rev_login,
                        "is_reviewer_owner": is_rev_owner,
                        "submitted_at": _parse_timestamp(rev_submitted_at),
                    }
                )
        except GitHubRateLimitError:
            coverage_status = "partial"
            confidence = "uncertain"
            limitations.append(
                f"Đạt giới hạn rate-limit khi lấy review của PR #{pr_num}."
            )
        except (GitHubEmptyRepositoryError, GitHubNotFoundError):
            coverage_status = "partial"
            confidence = "uncertain"
            limitations.append(f"Không thể xác minh đầy đủ reviews của PR #{pr_num}.")
        except (GitHubApiError, GitHubServerError) as exc:
            coverage_status = "partial"
            confidence = "uncertain"
            limitations.append(
                f"Lỗi khi lấy review của PR #{pr_num}: {type(exc).__name__}."
            )

        # B. Thu thập CI Checks và Statuses cho commit SHA của PR
        if head_sha:
            # 1. Checks API (Check Runs)
            try:
                check_runs = await client.list_check_runs_for_ref(
                    owner=owner,
                    repo=repo_name,
                    ref=head_sha,
                    per_page=50,
                    max_pages=1,
                    on_truncated=mark_truncated,
                )
                for run in check_runs:
                    run_id = run.get("id")
                    run_name = run.get("name", "check")
                    run_status = run.get("status", "completed")
                    run_conclusion = run.get("conclusion")
                    run_completed_at = run.get("completed_at") or run.get("started_at")

                    total_checks_analyzed += 1
                    if run_conclusion == "success":
                        successful_checks_count += 1
                        check_rationale = (
                            f"Kiểm tra CI '{run_name}' cho commit {head_sha[:7]} "
                            "thành công."
                        )
                    elif run_conclusion in ("failure", "timed_out", "action_required"):
                        failed_checks_count += 1
                        check_rationale = (
                            f"Kiểm tra CI '{run_name}' cho commit {head_sha[:7]} "
                            f"thất bại ({run_conclusion}). Thất bại trong CI là "
                            "cơ chế phát hiện lỗi sớm (fail-fast) chuẩn mực, "
                            "không phản ánh năng lực kém."
                        )
                    elif run_status in ("queued", "in_progress", "waiting"):
                        pending_checks_count += 1
                        check_rationale = (
                            f"Kiểm tra CI '{run_name}' đang thực thi ({run_status})."
                        )
                    else:
                        other_checks_count += 1
                        check_rationale = (
                            f"Kiểm tra CI '{run_name}' có kết quả "
                            f"'{run_conclusion or run_status}'."
                        )

                    evidence_list.append(
                        CollaborationEvidenceItem(
                            evidence_type="check_run",
                            target_identifier=f"CheckRun #{run_id} ({run_name})",
                            pr_number=pr_num,
                            commit_sha=head_sha,
                            check_name=run_name,
                            state=run_status,
                            conclusion=run_conclusion,
                            is_profile_owner=is_pr_author,
                            html_url=run.get("html_url"),
                            title_or_message=run.get("output", {}).get("title")
                            if isinstance(run.get("output"), dict)
                            else None,
                            recorded_at=run_completed_at,
                            rationale=check_rationale,
                            metadata={
                                "check_run_id": run_id,
                                "source_api": "checks_api",
                                "name": run_name,
                                "status": run_status,
                                "conclusion": run_conclusion,
                                "started_at": run.get("started_at"),
                                "completed_at": run.get("completed_at"),
                            },
                        )
                    )

                    pr_ctx["checks"].append(
                        {
                            "id": run_id,
                            "name": run_name,
                            "status": run_status,
                            "conclusion": run_conclusion,
                            "completed_at": _parse_timestamp(run_completed_at),
                        }
                    )
            except GitHubRateLimitError:
                coverage_status = "partial"
                confidence = "uncertain"
                limitations.append(
                    "Đạt giới hạn rate-limit khi lấy check runs của commit "
                    f"{head_sha[:7]}."
                )
            except (GitHubEmptyRepositoryError, GitHubNotFoundError):
                coverage_status = "partial"
                confidence = "uncertain"
                limitations.append(
                    f"Không thể xác minh check runs của commit {head_sha[:7]}."
                )
            except (GitHubApiError, GitHubServerError) as exc:
                coverage_status = "partial"
                confidence = "uncertain"
                limitations.append(
                    f"Lỗi khi lấy check runs của commit {head_sha[:7]}: "
                    f"{type(exc).__name__}."
                )

            # 2. Status API (Commit Statuses)
            try:
                statuses = await client.list_commit_statuses_for_ref(
                    owner=owner,
                    repo=repo_name,
                    ref=head_sha,
                    per_page=50,
                    max_pages=1,
                    on_truncated=mark_truncated,
                )
                for st in statuses:
                    st_id = st.get("id")
                    st_context = st.get("context", "ci")
                    st_state = st.get("state", "pending")
                    st_created_at = st.get("created_at")

                    total_checks_analyzed += 1
                    if st_state == "success":
                        successful_checks_count += 1
                        st_rationale = (
                            f"Commit status '{st_context}' cho commit {head_sha[:7]} "
                            "thành công."
                        )
                    elif st_state in ("failure", "error"):
                        failed_checks_count += 1
                        st_rationale = (
                            f"Commit status '{st_context}' cho commit {head_sha[:7]} "
                            f"báo lỗi ({st_state}). Cảnh báo kiểm thử commit giúp "
                            "ngăn ngừa lỗi, không phản ánh năng lực kém."
                        )
                    elif st_state == "pending":
                        pending_checks_count += 1
                        st_rationale = f"Commit status '{st_context}' đang chờ xử lý."
                    else:
                        other_checks_count += 1
                        st_rationale = (
                            f"Commit status '{st_context}' ở trạng thái {st_state}."
                        )

                    evidence_list.append(
                        CollaborationEvidenceItem(
                            evidence_type="commit_status",
                            target_identifier=f"Status #{st_id} ({st_context})",
                            pr_number=pr_num,
                            commit_sha=head_sha,
                            check_name=st_context,
                            state=st_state,
                            conclusion=st_state,
                            is_profile_owner=is_pr_author,
                            html_url=st.get("target_url"),
                            title_or_message=st.get("description"),
                            recorded_at=st_created_at,
                            rationale=st_rationale,
                            metadata={
                                "status_id": st_id,
                                "source_api": "status_api",
                                "context": st_context,
                                "state": st_state,
                            },
                        )
                    )

                    pr_ctx["statuses"].append(
                        {
                            "id": st_id,
                            "context": st_context,
                            "state": st_state,
                            "created_at": _parse_timestamp(st_created_at),
                        }
                    )
            except GitHubRateLimitError:
                coverage_status = "partial"
                confidence = "uncertain"
                limitations.append(
                    f"Đạt giới hạn rate-limit khi lấy statuses của commit "
                    f"{head_sha[:7]}."
                )
            except (GitHubEmptyRepositoryError, GitHubNotFoundError):
                coverage_status = "partial"
                confidence = "uncertain"
                limitations.append(
                    f"Không thể xác minh commit statuses của {head_sha[:7]}."
                )
            except (GitHubApiError, GitHubServerError) as exc:
                coverage_status = "partial"
                confidence = "uncertain"
                limitations.append(
                    f"Lỗi khi lấy statuses của commit {head_sha[:7]}: "
                    f"{type(exc).__name__}."
                )

    # 6. Phát hiện chuỗi xử lý lỗi & chu kỳ lặp phản biện
    problem_solving_sequences: list[ProblemSolvingSequence] = []
    seq_counter = 0

    for pr_ctx in prs_to_inspect:
        pr_num = pr_ctx["pr_num"]
        reviews = pr_ctx["reviews"]
        checks = pr_ctx["checks"]

        # A. Chu kỳ phản biện & điều chỉnh (Review Feedback Loop)
        cr_reviews = [r for r in reviews if r["state"] == "CHANGES_REQUESTED"]
        for cr in cr_reviews:
            cr_time = cr["submitted_at"]
            later_approved = [
                r
                for r in reviews
                if r["state"] == "APPROVED"
                and r["submitted_at"]
                and cr_time
                and r["submitted_at"] > cr_time
            ]
            if later_approved or pr_ctx["state"] == "merged":
                seq_counter += 1
                seq_id = f"SEQ-REV-{pr_num}-{seq_counter}"
                appr_event = (
                    {
                        "type": "review_approved",
                        "reviewer": later_approved[0]["reviewer"],
                        "time": later_approved[0]["submitted_at"].isoformat()
                        if later_approved[0]["submitted_at"]
                        else None,
                    }
                    if later_approved
                    else {
                        "type": "pr_merged",
                        "time": pr_ctx["merged_at"].isoformat()
                        if pr_ctx["merged_at"]
                        else None,
                    }
                )
                seq = ProblemSolvingSequence(
                    sequence_id=seq_id,
                    pr_number=pr_num,
                    trigger_event={
                        "type": "review_changes_requested",
                        "reviewer": cr["reviewer"],
                        "time": cr_time.isoformat() if cr_time else None,
                        "description": "Yêu cầu thay đổi từ reviewer",
                    },
                    iteration_events=[],
                    resolution_or_outcome=appr_event,
                    explanation=(
                        f"PR #{pr_num} ghi nhận yêu cầu thay đổi từ reviewer, "
                        "sau đó có sự kiện phê duyệt hoặc merge. "
                        "Chưa đủ bằng chứng để kết luận developer đã sửa mã nguồn "
                        "hoặc giải quyết chính xác yêu cầu review."
                    ),
                    limitations=[
                        "Quan sát dựa trên chuỗi thời gian của review và trạng thái; "
                        "không khẳng định nguyên nhân chủ quan tuyệt đối."
                    ],
                )
                problem_solving_sequences.append(seq)

                evidence_list.append(
                    CollaborationEvidenceItem(
                        evidence_type="problem_solving_sequence",
                        target_identifier=f"Sequence {seq_id} (PR #{pr_num})",
                        pr_number=pr_num,
                        state="review_followup_observed",
                        is_profile_owner=pr_ctx["is_pr_author"],
                        recorded_at=cr_time,
                        rationale=seq.explanation,
                        metadata={
                            "sequence_id": seq_id,
                            "type": "review_feedback_loop",
                            "trigger": cr["state"],
                        },
                    )
                )

        # B. Chu kỳ xử lý lỗi CI (CI Fail-Fast & Resolution Loop)
        failed_checks = [
            c
            for c in checks
            if c.get("conclusion") in ("failure", "timed_out", "action_required")
        ]
        successful_checks = [c for c in checks if c.get("conclusion") == "success"]
        if failed_checks and successful_checks:
            f_time = failed_checks[0].get("completed_at")
            s_time = successful_checks[-1].get("completed_at")
            if f_time and s_time and s_time >= f_time:
                seq_counter += 1
                seq_id = f"SEQ-CI-{pr_num}-{seq_counter}"
                seq = ProblemSolvingSequence(
                    sequence_id=seq_id,
                    pr_number=pr_num,
                    trigger_event={
                        "type": "ci_check_failure",
                        "check_name": failed_checks[0].get("name"),
                        "time": f_time.isoformat(),
                        "conclusion": failed_checks[0].get("conclusion"),
                    },
                    iteration_events=[],
                    resolution_or_outcome={
                        "type": "ci_check_success",
                        "check_name": successful_checks[-1].get("name"),
                        "time": s_time.isoformat(),
                        "conclusion": "success",
                    },
                    explanation=(
                        f"PR #{pr_num} có một check thất bại và một check thành công "
                        "được ghi nhận sau đó. Đây là hai sự kiện CI quan sát được. "
                        "Chưa có bằng chứng commit sửa đổi hoặc nguyên nhân cụ thể "
                        "để khẳng định lỗi trước đó đã được khắc phục."
                    ),
                    limitations=[
                        "Kiểm tra thành công tiếp sau là bằng chứng của kết quả CI; "
                        "không tự động suy diễn toàn bộ nguyên nhân do một cá nhân."
                    ],
                )
                problem_solving_sequences.append(seq)

                evidence_list.append(
                    CollaborationEvidenceItem(
                        evidence_type="problem_solving_sequence",
                        target_identifier=f"Sequence {seq_id} (PR #{pr_num})",
                        pr_number=pr_num,
                        state="ci_outcomes_observed",
                        is_profile_owner=pr_ctx["is_pr_author"],
                        recorded_at=f_time,
                        rationale=seq.explanation,
                        metadata={
                            "sequence_id": seq_id,
                            "type": "ci_failure_resolution_loop",
                        },
                    )
                )

    # 7. Xây dựng Quan sát Hợp tác & Phản biện (Collaboration Observations)
    collaboration_observations: list[CollaborationObservation] = []

    if total_prs_analyzed == 0:
        collaboration_observations.append(
            CollaborationObservation(
                category="pull_request",
                title="Không có Pull Request trong phạm vi phân tích",
                description=(
                    "Không quan sát thấy Pull Request nào trong phạm vi dữ liệu "
                    "đã kiểm tra. Không được suy diễn điều này đại diện cho kỹ năng "
                    "cộng tác kém."
                ),
                evidence_level="observed_event",
                confidence="high",
            )
        )
    else:
        collaboration_observations.append(
            CollaborationObservation(
                category="pull_request",
                title=f"Đã phân tích {total_prs_analyzed} Pull Requests",
                description=(
                    f"Ghi nhận {merged_prs_count} PR đã merge, "
                    f"{closed_unmerged_prs_count} PR đóng chưa merge, "
                    f"và {open_prs_count} PR đang mở ({user_prs_count} PR "
                    f"của lập trình viên, {external_prs_count} PR của cộng sự). "
                    "PR đóng chưa merge là trạng thái kỹ thuật bình thường, "
                    "không bị tính điểm trừ năng lực."
                ),
                evidence_level="observed_event",
                confidence="high",
            )
        )

    if user_reviews_conducted_count > 0:
        collaboration_observations.append(
            CollaborationObservation(
                category="review",
                title="Tích cực tham gia đánh giá mã nguồn",
                description=(
                    f"Lập trình viên đã thực hiện {user_reviews_conducted_count} lượt "
                    "code review cho đồng nghiệp. Minh chứng cho vai trò hỗ trợ "
                    "nâng cao chất lượng mã nguồn chung."
                ),
                evidence_level="evidence_backed_relationship",
                confidence="high",
            )
        )

    if changes_requested_count > 0:
        collaboration_observations.append(
            CollaborationObservation(
                category="review",
                title="Quy trình phản biện chuyên nghiệp với yêu cầu điều chỉnh",
                description=(
                    f"Ghi nhận {changes_requested_count} lượt yêu cầu thay đổi "
                    "(CHANGES_REQUESTED). Yêu cầu thay đổi là phần không thể thiếu "
                    "trong chu trình thẩm định chất lượng, tuyệt đối không bị "
                    "đánh giá tiêu cực."
                ),
                evidence_level="contextual_explanation",
                confidence="high",
            )
        )

    if failed_checks_count > 0:
        collaboration_observations.append(
            CollaborationObservation(
                category="ci_check",
                title="Cơ chế Fail-Fast qua CI/CD được kích hoạt",
                description=(
                    f"Ghi nhận {failed_checks_count} lượt kiểm tra CI thất bại "
                    "trên các commit thử nghiệm. Thất bại trong CI chứng minh pipeline "
                    "kiểm thử hoạt động hiệu quả để chặn lỗi sớm trước khi merge, "
                    "không thể hiện năng lực kém của lập trình viên."
                ),
                evidence_level="contextual_explanation",
                confidence="high",
            )
        )

    if problem_solving_sequences:
        collaboration_observations.append(
            CollaborationObservation(
                category="problem_solving",
                title=f"Ghi nhận {len(problem_solving_sequences)} chuỗi sự kiện",
                description=(
                    f"Đã ghi nhận {len(problem_solving_sequences)} chuỗi sự kiện "
                    "review hoặc CI có diễn biến tiếp theo. "
                    "Chưa xác minh được hành động sửa code hoặc quan hệ nhân quả."
                ),
                evidence_level="contextual_explanation",
                confidence="uncertain",
                related_identifiers=[s.sequence_id for s in problem_solving_sequences],
            )
        )

    if collection_truncated:
        coverage_status = "partial"
        confidence = "uncertain"
        limitations.append(
            "Dữ liệu GitHub đạt giới hạn phân trang; một số PR hoặc review cũ hơn "
            "có thể chưa được hiển thị đầy đủ."
        )

    analyzed_at = datetime.now(UTC)
    summary_data = {
        "branch_filter": request.branch,
        "branch_filter_type": "base",
        "total_prs_analyzed": total_prs_analyzed,
        "merged_prs_count": merged_prs_count,
        "closed_unmerged_prs_count": closed_unmerged_prs_count,
        "open_prs_count": open_prs_count,
        "user_prs_count": user_prs_count,
        "external_prs_count": external_prs_count,
        "total_reviews_analyzed": total_reviews_analyzed,
        "approved_reviews_count": approved_reviews_count,
        "changes_requested_count": changes_requested_count,
        "commented_reviews_count": commented_reviews_count,
        "dismissed_reviews_count": dismissed_reviews_count,
        "user_reviews_conducted_count": user_reviews_conducted_count,
        "user_reviews_received_count": user_reviews_received_count,
        "total_checks_analyzed": total_checks_analyzed,
        "successful_checks_count": successful_checks_count,
        "failed_checks_count": failed_checks_count,
        "pending_checks_count": pending_checks_count,
        "other_checks_count": other_checks_count,
        "problem_solving_sequences_count": len(problem_solving_sequences),
    }

    response = CollaborationAnalysisResponse(
        id=None,
        repository_id=repo.id,
        repository_name=repo.name,
        repository_full_name=repo.full_name or repo.name,
        user_id=user.id,
        job_id=job_id,
        report_id=report_id,
        total_prs_analyzed=total_prs_analyzed,
        merged_prs_count=merged_prs_count,
        closed_unmerged_prs_count=closed_unmerged_prs_count,
        open_prs_count=open_prs_count,
        user_prs_count=user_prs_count,
        external_prs_count=external_prs_count,
        total_reviews_analyzed=total_reviews_analyzed,
        approved_reviews_count=approved_reviews_count,
        changes_requested_count=changes_requested_count,
        commented_reviews_count=commented_reviews_count,
        dismissed_reviews_count=dismissed_reviews_count,
        user_reviews_conducted_count=user_reviews_conducted_count,
        user_reviews_received_count=user_reviews_received_count,
        total_checks_analyzed=total_checks_analyzed,
        successful_checks_count=successful_checks_count,
        failed_checks_count=failed_checks_count,
        pending_checks_count=pending_checks_count,
        other_checks_count=other_checks_count,
        problem_solving_sequences_count=len(problem_solving_sequences),
        coverage_status=coverage_status,
        confidence=confidence,
        time_range=time_range_info,
        limitations=limitations,
        collaboration_observations=collaboration_observations,
        problem_solving_sequences=problem_solving_sequences,
        summary_data=summary_data,
        analyzed_at=analyzed_at.isoformat(),
        evidence=evidence_list,
    )

    if persist:
        # Kiểm tra lại quyền truy cập trước khi lưu dữ liệu.
        current_repo = verify_repository_access(db, repository_id, user)

        if current_repo.private:
            _, current_scopes = get_user_github_token(db, user.id)
            verify_private_repo_consent(
                current_repo,
                current_scopes,
                db,
                user.id,
            )

        persist_collaboration_result(db, response, commit=True)

    return response


def get_stored_collaboration(
    db: Session,
    repository_id: int,
    user: User,
    *,
    only_unfiltered: bool = False,
) -> CollaborationAnalysisResponse | None:
    """Truy xuất bản ghi phân tích cộng tác gần nhất đã lưu trong cơ sở dữ liệu."""

    repo = verify_repository_access(db, repository_id, user)

    if repo.private:
        _, scopes = get_user_github_token(db, user.id)
        verify_private_repo_consent(repo, scopes, db, user.id)

    stmt = select(CollaborationAnalysis).where(
        CollaborationAnalysis.repository_id == repository_id,
        CollaborationAnalysis.user_id == user.id,
    )

    if only_unfiltered:
        stmt = stmt.where(
            or_(
                CollaborationAnalysis.time_range.is_(None),
                CollaborationAnalysis.time_range == JSON.NULL,
            )
        )

    collab = db.scalar(
        stmt.order_by(
            desc(CollaborationAnalysis.analyzed_at),
            desc(CollaborationAnalysis.id),
        )
    )

    if not collab:
        return None

    repo = db.scalar(select(Repository).where(Repository.id == repository_id))
    repo_name = repo.name if repo else "unknown"
    repo_full_name = repo.full_name or repo_name if repo else "unknown"

    ev_rows = db.scalars(
        select(CollaborationEvidence)
        .where(CollaborationEvidence.analysis_id == collab.id)
        .order_by(CollaborationEvidence.id.asc())
    ).all()

    evidence_items = [
        CollaborationEvidenceItem(
            id=e.id,
            evidence_type=e.evidence_type,
            target_identifier=e.target_identifier,
            pr_number=e.pr_number,
            commit_sha=e.commit_sha,
            check_name=e.check_name,
            state=e.state,
            conclusion=e.conclusion,
            actor_login=e.actor_login,
            actor_id=e.actor_id,
            actor_type=e.actor_type,
            is_profile_owner=e.is_profile_owner,
            html_url=e.html_url,
            title_or_message=e.title_or_message,
            recorded_at=e.recorded_at.isoformat() if e.recorded_at else None,
            rationale=e.rationale,
            metadata=e.metadata_,
        )
        for e in ev_rows
    ]

    observations = [
        CollaborationObservation(**obs)
        for obs in (collab.collaboration_observations or [])
        if isinstance(obs, dict)
    ]
    sequences = [
        ProblemSolvingSequence(**seq)
        for seq in (collab.problem_solving_observations or [])
        if isinstance(seq, dict)
    ]

    return CollaborationAnalysisResponse(
        id=collab.id,
        repository_id=collab.repository_id,
        repository_name=repo_name,
        repository_full_name=repo_full_name,
        user_id=collab.user_id,
        job_id=str(collab.job_id) if collab.job_id else None,
        report_id=collab.report_id,
        total_prs_analyzed=collab.total_prs_analyzed,
        merged_prs_count=collab.merged_prs_count,
        closed_unmerged_prs_count=collab.closed_unmerged_prs_count,
        open_prs_count=collab.open_prs_count,
        user_prs_count=collab.user_prs_count,
        external_prs_count=collab.external_prs_count,
        total_reviews_analyzed=collab.total_reviews_analyzed,
        approved_reviews_count=collab.approved_reviews_count,
        changes_requested_count=collab.changes_requested_count,
        commented_reviews_count=collab.commented_reviews_count,
        dismissed_reviews_count=collab.dismissed_reviews_count,
        user_reviews_conducted_count=collab.user_reviews_conducted_count,
        user_reviews_received_count=collab.user_reviews_received_count,
        total_checks_analyzed=collab.total_checks_analyzed,
        successful_checks_count=collab.successful_checks_count,
        failed_checks_count=collab.failed_checks_count,
        pending_checks_count=collab.pending_checks_count,
        other_checks_count=collab.other_checks_count,
        problem_solving_sequences_count=collab.problem_solving_sequences_count,
        coverage_status=collab.coverage_status,
        confidence=collab.confidence,
        time_range=collab.time_range,
        limitations=collab.limitations,
        collaboration_observations=observations,
        problem_solving_sequences=sequences,
        summary_data=collab.summary_data,
        analyzed_at=collab.analyzed_at.isoformat() if collab.analyzed_at else "",
        evidence=evidence_items,
    )


def persist_collaboration_result(
    db: Session,
    result: CollaborationAnalysisResponse,
    *,
    commit: bool = True,
) -> CollaborationAnalysis:
    """Lưu kết quả phân tích cộng tác vào cơ sở dữ liệu một cách an toàn."""

    # Mỗi lần phân tích tạo một bản ghi độc lập.
    # Không ghi đè kết quả và evidence của các lần phân tích trước.
    collab = CollaborationAnalysis(
        repository_id=result.repository_id,
        user_id=result.user_id,
    )
    db.add(collab)

    analyzed_at_val = (
        datetime.fromisoformat(result.analyzed_at)
        if isinstance(result.analyzed_at, str)
        else result.analyzed_at
    )

    collab.job_id = uuid.UUID(result.job_id) if result.job_id else None
    collab.report_id = result.report_id
    collab.total_prs_analyzed = result.total_prs_analyzed
    collab.merged_prs_count = result.merged_prs_count
    collab.closed_unmerged_prs_count = result.closed_unmerged_prs_count
    collab.open_prs_count = result.open_prs_count
    collab.user_prs_count = result.user_prs_count
    collab.external_prs_count = result.external_prs_count
    collab.total_reviews_analyzed = result.total_reviews_analyzed
    collab.approved_reviews_count = result.approved_reviews_count
    collab.changes_requested_count = result.changes_requested_count
    collab.commented_reviews_count = result.commented_reviews_count
    collab.dismissed_reviews_count = result.dismissed_reviews_count
    collab.user_reviews_conducted_count = result.user_reviews_conducted_count
    collab.user_reviews_received_count = result.user_reviews_received_count
    collab.total_checks_analyzed = result.total_checks_analyzed
    collab.successful_checks_count = result.successful_checks_count
    collab.failed_checks_count = result.failed_checks_count
    collab.pending_checks_count = result.pending_checks_count
    collab.other_checks_count = result.other_checks_count
    collab.problem_solving_sequences_count = result.problem_solving_sequences_count
    collab.coverage_status = result.coverage_status
    collab.confidence = result.confidence
    collab.time_range = result.time_range
    collab.limitations = result.limitations
    collab.collaboration_observations = [
        obs.model_dump() if hasattr(obs, "model_dump") else obs
        for obs in result.collaboration_observations
    ]
    collab.problem_solving_observations = [
        seq.model_dump() if hasattr(seq, "model_dump") else seq
        for seq in result.problem_solving_sequences
    ]
    collab.summary_data = result.summary_data
    collab.analyzed_at = analyzed_at_val
    collab.updated_at = analyzed_at_val

    db.flush()

    db.execute(
        delete(CollaborationEvidence).where(
            CollaborationEvidence.analysis_id == collab.id
        )
    )

    for item in result.evidence:
        db.add(
            CollaborationEvidence(
                analysis_id=collab.id,
                repository_id=result.repository_id,
                user_id=result.user_id,
                evidence_type=item.evidence_type,
                target_identifier=item.target_identifier,
                pr_number=item.pr_number,
                commit_sha=item.commit_sha,
                check_name=item.check_name,
                state=item.state,
                conclusion=item.conclusion,
                actor_login=item.actor_login,
                actor_id=item.actor_id,
                actor_type=item.actor_type,
                is_profile_owner=item.is_profile_owner,
                html_url=item.html_url,
                title_or_message=item.title_or_message,
                recorded_at=_parse_timestamp(item.recorded_at),
                rationale=item.rationale,
                metadata_=item.metadata,
            )
        )

    db.flush()

    if commit:
        db.commit()

    result.id = collab.id
    return collab


def get_collaboration_evidence_list(
    db: Session,
    repository_id: int,
    user: User,
    evidence_type: str = "all",
    state: str = "all",
    pr_number: int | None = None,
    page: int = 1,
    per_page: int = 50,
) -> CollaborationEvidenceListResponse:
    """Truy xuất danh sách bằng chứng cộng tác phân trang và lọc (PBI-014)."""

    repo = verify_repository_access(db, repository_id, user)

    if repo.private:
        _, scopes = get_user_github_token(db, user.id)
        verify_private_repo_consent(repo, scopes, db, user.id)

    latest_analysis = db.scalar(
        select(CollaborationAnalysis.id)
        .where(
            CollaborationAnalysis.repository_id == repository_id,
            CollaborationAnalysis.user_id == user.id,
        )
        .order_by(
            desc(CollaborationAnalysis.analyzed_at),
            desc(CollaborationAnalysis.id),
        )
        .limit(1)
    )

    if latest_analysis is None:
        return CollaborationEvidenceListResponse(
            repository_id=repository_id,
            total=0,
            page=page,
            per_page=per_page,
            items=[],
        )

    stmt = select(CollaborationEvidence).where(
        CollaborationEvidence.repository_id == repository_id,
        CollaborationEvidence.user_id == user.id,
        CollaborationEvidence.analysis_id == latest_analysis,
    )

    if evidence_type and evidence_type != "all":
        stmt = stmt.where(CollaborationEvidence.evidence_type == evidence_type)
    if state and state != "all":
        stmt = stmt.where(CollaborationEvidence.state == state)
    if pr_number is not None:
        stmt = stmt.where(CollaborationEvidence.pr_number == pr_number)

    all_rows = db.scalars(stmt.order_by(CollaborationEvidence.id.asc())).all()
    total = len(all_rows)

    start = (page - 1) * per_page
    end = start + per_page
    paginated = all_rows[start:end]

    items = [
        CollaborationEvidenceItem(
            id=e.id,
            evidence_type=e.evidence_type,
            target_identifier=e.target_identifier,
            pr_number=e.pr_number,
            commit_sha=e.commit_sha,
            check_name=e.check_name,
            state=e.state,
            conclusion=e.conclusion,
            actor_login=e.actor_login,
            actor_id=e.actor_id,
            actor_type=e.actor_type,
            is_profile_owner=e.is_profile_owner,
            html_url=e.html_url,
            title_or_message=e.title_or_message,
            recorded_at=e.recorded_at.isoformat() if e.recorded_at else None,
            rationale=e.rationale,
            metadata=e.metadata_,
        )
        for e in paginated
    ]

    return CollaborationEvidenceListResponse(
        repository_id=repository_id,
        total=total,
        page=page,
        per_page=per_page,
        items=items,
    )
