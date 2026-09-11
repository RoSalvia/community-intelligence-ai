"""Loopback-first API and packaged frontend for the local web product."""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from community_intelligence import __version__
from community_intelligence.application.data_foundation import DataFoundationService
from community_intelligence.application.knowledge import KnowledgeService, SourceInput
from community_intelligence.importers.telegram import import_telegram_export
from community_intelligence.io import (
    cleanup_private_directory,
    publish_directory_no_replace,
    write_dataset,
)
from community_intelligence.pipeline import run_pipeline
from community_intelligence.synthetic import MIN_MESSAGE_COUNT, generate_dataset

DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_ANALYSIS_ID = re.compile(r"[0-9a-f]{32}")


class ApiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DemoRequest(ApiRequest):
    seed: int = 20260901
    message_count: int = Field(default=1200, ge=MIN_MESSAGE_COUNT, le=100_000)


class WorkspaceRequest(ApiRequest):
    project_name: str


class CommunityRequest(ApiRequest):
    name: str
    language: str
    timezone: str
    platform: str = "telegram"


class RoleAssignmentRequest(ApiRequest):
    user_id_hash: str
    role: str
    valid_from: datetime
    valid_to: datetime | None = None


class AnalysisRunRequest(ApiRequest):
    window: str = "since_last_check"
    start: datetime | None = None
    end: datetime | None = None


class CheckWatermarkRequest(ApiRequest):
    checked_through: datetime


class KnowledgeSourceRequest(ApiRequest):
    title: str
    source_type: str
    source_channel: str
    content: str
    published_at: datetime | None = None
    effective_from: datetime | None = None
    source_timezone: str = "UTC"
    published_on: date | None = None
    temporal_precision: Literal["day", "second"] | None = None
    canonical_url: str | None = None
    platform: str | None = None
    platform_content_id: str | None = None
    author: str | None = None
    language: str = "en"
    project_scope: str = "project"
    authority_level: str = "official"
    official_status: str = "verified_official"
    source_owner: str | None = None
    verification_method: str = "human-confirmed"
    updated_at: datetime | None = None
    effective_until: datetime | None = None
    observed_at: datetime | None = None
    superseded_at: datetime | None = None
    status: str = "current"
    supersedes_source_id: str | None = None
    supersedes_revision_id: str | None = None
    metadata_provenance: dict[str, str]
    semantic_tags: dict[str, str] = Field(default_factory=dict)


class KnowledgeFileMetadata(KnowledgeSourceRequest):
    content: str = ""


class KnowledgeQueryRequest(ApiRequest):
    query: str
    as_of_time: datetime | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    neighbor_count: int = Field(default=1, ge=0, le=2)
    max_context_chars: int = Field(default=4000, ge=200, le=20_000)


class ActorIdentityResponse(ApiRequest):
    community_id: str
    user_id_hash: str
    display_name: str | None
    platform_handle: str | None
    pseudonym: str
    operator_label: str
    identity_scope: Literal["local_only"]
    message_count: int
    first_seen_at: str
    last_seen_at: str


class ActorListResponse(ApiRequest):
    count: int
    items: list[ActorIdentityResponse]


class AnalysisStore:
    """Own private, server-generated analysis workspaces under one fixed root."""

    def __init__(self, root: Path) -> None:
        lexical_root = Path(os.path.abspath(root.expanduser()))
        if os.path.lexists(lexical_root) and lexical_root.is_symlink():
            raise ValueError("data root must not be a symbolic link")
        lexical_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        lexical_root.chmod(0o700)
        self.root = lexical_root.resolve(strict=True)

    def create_demo(self, *, seed: int, message_count: int) -> dict[str, Any]:
        analysis_id = uuid.uuid4().hex

        def build(staging: Path) -> None:
            dataset = generate_dataset(seed=seed, message_count=message_count)
            dataset_dir = write_dataset(dataset, staging / "dataset")
            run_pipeline(dataset_dir, staging / "report")

        self._publish_analysis(analysis_id, build)
        return self.response(analysis_id)

    def create_telegram(self, source: Path, *, language: str) -> dict[str, Any]:
        analysis_id = uuid.uuid4().hex

        def build(staging: Path) -> None:
            dataset = import_telegram_export(source, language=language)
            dataset_dir = write_dataset(dataset, staging / "dataset")
            run_pipeline(dataset_dir, staging / "report")

        self._publish_analysis(analysis_id, build)
        return self.response(analysis_id)

    def _publish_analysis(self, analysis_id: str, build: Any) -> None:
        destination = self.root / analysis_id
        staging = Path(tempfile.mkdtemp(dir=self.root, prefix=f".{analysis_id}.staging-"))
        staging_status = staging.lstat()
        try:
            build(staging)
            publish_directory_no_replace(staging, destination)
        finally:
            cleanup_private_directory(
                staging,
                expected_inode=staging_status.st_ino,
                expected_device=staging_status.st_dev,
            )

    def response(self, analysis_id: str) -> dict[str, Any]:
        report = self.report(analysis_id)
        evidence = self.evidence(analysis_id)
        return {
            "analysis_id": analysis_id,
            "summary": {
                "message_count": report["Overview"]["message_count"],
                "community_count": report["Overview"]["community_count"],
                "campaign_count": report["Overview"]["campaign_count"],
                "evidence_count": len(evidence),
                "data_status": report["data_status"],
                "source_format": report["Overview"]["source"]["format"],
            },
            "report": report,
        }

    def report(self, analysis_id: str) -> dict[str, Any]:
        report_path = self._analysis_dir(analysis_id) / "report" / "report.json"
        if not report_path.is_file() or report_path.is_symlink():
            raise KeyError(analysis_id)
        return json.loads(report_path.read_text(encoding="utf-8"))

    def evidence(self, analysis_id: str) -> list[dict[str, Any]]:
        evidence_path = self._analysis_dir(analysis_id) / "report" / "evidence.jsonl"
        if not evidence_path.is_file() or evidence_path.is_symlink():
            raise KeyError(analysis_id)
        return [
            json.loads(line)
            for line in evidence_path.read_text(encoding="utf-8").splitlines()
            if line
        ]

    def _analysis_dir(self, analysis_id: str) -> Path:
        if _ANALYSIS_ID.fullmatch(analysis_id) is None:
            raise KeyError(analysis_id)
        path = self.root / analysis_id
        if not path.is_dir() or path.is_symlink():
            raise KeyError(analysis_id)
        resolved = path.resolve(strict=True)
        if resolved.parent != self.root:
            raise KeyError(analysis_id)
        return resolved


def _default_data_root() -> Path:
    override = os.environ.get("COMMUNITY_INTELLIGENCE_DATA_DIR")
    if override:
        return Path(override)
    return Path.home() / ".community-intelligence" / "analyses"


def create_app(
    *,
    data_root: Path | None = None,
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
    internal_review: bool | None = None,
) -> FastAPI:
    if max_upload_bytes < 1:
        raise ValueError("max_upload_bytes must be positive")
    store = AnalysisStore(data_root or _default_data_root())
    app = FastAPI(
        title="Community Intelligence",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.analysis_store = store

    review_enabled = (
        os.environ.get("COMMUNITY_INTELLIGENCE_INTERNAL_REVIEW") == "1"
        if internal_review is None
        else internal_review
    )

    def data_foundation() -> DataFoundationService:
        service = getattr(app.state, "data_foundation_service", None)
        if service is None:
            service = DataFoundationService(
                database_path=store.root / "workspace.sqlite3",
                artifact_root=store.root / "workspace-runs",
            )
            app.state.data_foundation_service = service
        return service

    def knowledge() -> KnowledgeService:
        service = getattr(app.state, "knowledge_service", None)
        if service is None:
            foundation = data_foundation()
            service = KnowledgeService(
                database=foundation.database,
                artifact_root=store.root / "knowledge",
            )
            app.state.knowledge_service = service
        return service

    def source_input(
        request: KnowledgeSourceRequest, *, content: str | bytes, filename: str | None = None
    ) -> SourceInput:
        values = request.model_dump(exclude={"content"})
        return SourceInput(content=content, filename=filename, **values)

    def execute_analysis_in_background(analysis_run_id: str) -> None:
        try:
            data_foundation().execute_analysis_run(analysis_run_id)
        except Exception:
            # The service persists the failed state for the polling endpoint.
            return

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.post("/api/analyses/demo", status_code=status.HTTP_201_CREATED)
    def create_demo(request: DemoRequest) -> dict[str, Any]:
        return store.create_demo(seed=request.seed, message_count=request.message_count)

    @app.post("/api/analyses/telegram", status_code=status.HTTP_201_CREATED)
    async def create_telegram(
        file: Annotated[UploadFile, File()],
        language: Annotated[str, Form()] = "und",
    ) -> JSONResponse:
        if not file.filename or Path(file.filename).suffix.casefold() != ".json":
            await file.close()
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Upload a Telegram Desktop JSON export.",
            )
        content = await file.read(max_upload_bytes + 1)
        await file.close()
        if len(content) > max_upload_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Upload exceeds the {max_upload_bytes}-byte local limit.",
            )
        descriptor, temporary_name = tempfile.mkstemp(
            dir=store.root,
            prefix=".telegram-upload-",
            suffix=".json",
        )
        source = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                result = await run_in_threadpool(
                    store.create_telegram,
                    source,
                    language=language,
                )
            except (OSError, ValueError) as error:
                detail = str(error).splitlines()[0]
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=detail,
                ) from None
            return JSONResponse(result, status_code=status.HTTP_201_CREATED)
        finally:
            source.unlink(missing_ok=True)

    @app.get("/api/analyses/{analysis_id}")
    def get_analysis(analysis_id: str) -> dict[str, Any]:
        try:
            return store.report(analysis_id)
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found.",
            ) from None

    @app.get("/api/analyses/{analysis_id}/evidence")
    def get_evidence(analysis_id: str) -> dict[str, Any]:
        try:
            items = store.evidence(analysis_id)
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found.",
            ) from None
        return {"count": len(items), "items": items}

    @app.post("/api/v1/workspaces", status_code=status.HTTP_201_CREATED)
    def create_workspace(request: WorkspaceRequest) -> dict[str, Any]:
        try:
            return data_foundation().create_workspace(request.project_name)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    @app.get("/api/v1/workspaces")
    def list_workspaces() -> dict[str, Any]:
        items = data_foundation().list_workspaces()
        return {"count": len(items), "items": items}

    @app.get("/api/v1/workspaces/{workspace_id}")
    def get_workspace(workspace_id: str) -> dict[str, Any]:
        try:
            return data_foundation().get_workspace(workspace_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Workspace not found.") from None

    @app.patch("/api/v1/workspaces/{workspace_id}")
    def update_workspace(workspace_id: str, request: WorkspaceRequest) -> dict[str, Any]:
        try:
            return data_foundation().update_workspace(workspace_id, request.project_name)
        except KeyError:
            raise HTTPException(status_code=404, detail="Workspace not found.") from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    @app.post(
        "/api/v1/workspaces/{workspace_id}/communities",
        status_code=status.HTTP_201_CREATED,
    )
    def create_community(workspace_id: str, request: CommunityRequest) -> dict[str, Any]:
        try:
            return data_foundation().create_community(
                workspace_id,
                request.name,
                request.language,
                request.timezone,
                platform=request.platform,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="Workspace not found.") from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    @app.post("/api/v1/communities/{community_id}/imports/telegram")
    async def import_workspace_telegram(
        community_id: str,
        file: Annotated[UploadFile, File()],
    ) -> JSONResponse:
        if not file.filename or Path(file.filename).suffix.casefold() != ".json":
            await file.close()
            raise HTTPException(status_code=415, detail="Upload a Telegram Desktop JSON export.")
        content = await file.read(max_upload_bytes + 1)
        await file.close()
        if len(content) > max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Upload exceeds the {max_upload_bytes}-byte local limit.",
            )
        descriptor, temporary_name = tempfile.mkstemp(
            dir=store.root,
            prefix=".workspace-import-",
            suffix=".json",
        )
        source = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
            try:
                result = await run_in_threadpool(
                    data_foundation().import_telegram,
                    community_id,
                    source,
                )
            except KeyError:
                raise HTTPException(status_code=404, detail="Community not found.") from None
            except (OSError, ValueError) as error:
                raise HTTPException(status_code=400, detail=str(error).splitlines()[0]) from None
            return JSONResponse(result, status_code=200 if result["duplicate"] else 201)
        finally:
            source.unlink(missing_ok=True)

    @app.get("/api/v1/workspaces/{workspace_id}/actors")
    def list_actors(workspace_id: str) -> ActorListResponse:
        try:
            items = data_foundation().list_actors(workspace_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Workspace not found.") from None
        return ActorListResponse(count=len(items), items=items)

    @app.put("/api/v1/workspaces/{workspace_id}/role-assignments")
    def set_role_assignment(
        workspace_id: str,
        request: RoleAssignmentRequest,
    ) -> dict[str, Any]:
        try:
            return data_foundation().set_role_assignment(
                workspace_id,
                request.user_id_hash,
                request.role,
                valid_from=request.valid_from,
                valid_to=request.valid_to,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="Workspace not found.") from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    @app.get("/api/v1/workspaces/{workspace_id}/freshness")
    def get_freshness(workspace_id: str) -> dict[str, Any]:
        try:
            items = data_foundation().get_freshness(workspace_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Workspace not found.") from None
        return {"count": len(items), "items": items}

    @app.post(
        "/api/v1/workspaces/{workspace_id}/analysis-runs",
        status_code=status.HTTP_202_ACCEPTED,
    )
    def create_analysis_run(
        workspace_id: str,
        request: AnalysisRunRequest,
        background_tasks: BackgroundTasks,
    ) -> dict[str, Any]:
        try:
            run = data_foundation().create_analysis_run(
                workspace_id,
                request.window,
                start=request.start,
                end=request.end,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="Workspace not found.") from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        background_tasks.add_task(execute_analysis_in_background, run["analysis_run_id"])
        return run

    @app.get("/api/v1/analysis-runs/{analysis_run_id}")
    def get_analysis_run(analysis_run_id: str) -> dict[str, Any]:
        try:
            return data_foundation().get_analysis_run(analysis_run_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Analysis run not found.") from None

    @app.put("/api/v1/workspaces/{workspace_id}/check-watermark")
    def mark_checked(workspace_id: str, request: CheckWatermarkRequest) -> dict[str, Any]:
        try:
            return data_foundation().mark_checked(workspace_id, request.checked_through)
        except KeyError:
            raise HTTPException(status_code=404, detail="Workspace not found.") from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    @app.post(
        "/api/v1/workspaces/{workspace_id}/knowledge-sources/manual",
        status_code=status.HTTP_201_CREATED,
    )
    def add_manual_knowledge_source(
        workspace_id: str, request: KnowledgeSourceRequest
    ) -> dict[str, Any]:
        try:
            return knowledge().add_source(
                workspace_id,
                source_input(request, content=request.content),
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="Workspace not found.") from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    @app.post(
        "/api/v1/workspaces/{workspace_id}/knowledge-sources/files",
        status_code=status.HTTP_201_CREATED,
    )
    async def add_knowledge_file(
        workspace_id: str,
        file: Annotated[UploadFile, File()],
        metadata_json: Annotated[str, Form()],
    ) -> dict[str, Any]:
        filename = file.filename or ""
        if Path(filename).suffix.casefold() not in {".md", ".txt", ".pdf"}:
            await file.close()
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="M2 supports .md, .txt, and text-based .pdf. OCR is unavailable.",
            )
        content = await file.read(max_upload_bytes + 1)
        await file.close()
        if len(content) > max_upload_bytes:
            raise HTTPException(status_code=413, detail="Knowledge file exceeds local limit.")
        try:
            request = KnowledgeFileMetadata.model_validate_json(metadata_json)
            return knowledge().add_source(
                workspace_id,
                source_input(request, content=content, filename=filename),
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="Workspace not found.") from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    @app.post(
        "/api/v1/knowledge-sources/{source_id}/revisions/manual",
        status_code=status.HTTP_201_CREATED,
    )
    def add_manual_knowledge_revision(
        source_id: str, request: KnowledgeSourceRequest
    ) -> dict[str, Any]:
        try:
            return knowledge().add_revision(
                source_id,
                source_input(request, content=request.content),
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="Knowledge source not found.") from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    @app.post(
        "/api/v1/knowledge-sources/{source_id}/revisions/files",
        status_code=status.HTTP_201_CREATED,
    )
    async def add_knowledge_file_revision(
        source_id: str,
        file: Annotated[UploadFile, File()],
        metadata_json: Annotated[str, Form()],
    ) -> dict[str, Any]:
        filename = file.filename or ""
        if Path(filename).suffix.casefold() not in {".md", ".txt", ".pdf"}:
            await file.close()
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="M2 supports .md, .txt, and text-based .pdf. OCR is unavailable.",
            )
        content = await file.read(max_upload_bytes + 1)
        await file.close()
        if len(content) > max_upload_bytes:
            raise HTTPException(status_code=413, detail="Knowledge file exceeds local limit.")
        try:
            request = KnowledgeFileMetadata.model_validate_json(metadata_json)
            return knowledge().add_revision(
                source_id,
                source_input(request, content=content, filename=filename),
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="Knowledge source not found.") from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    @app.get("/api/v1/workspaces/{workspace_id}/knowledge-sources")
    def list_knowledge_sources(workspace_id: str) -> dict[str, Any]:
        items = knowledge().list_sources(workspace_id)
        return {"count": len(items), "items": items}

    @app.get("/api/v1/knowledge-sources/{source_id}")
    def get_knowledge_source(source_id: str) -> dict[str, Any]:
        try:
            return knowledge().get_source(source_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Knowledge source not found.") from None

    @app.get("/api/v1/knowledge-revisions/{revision_id}")
    def get_knowledge_revision(revision_id: str) -> dict[str, Any]:
        try:
            return knowledge().get_revision(revision_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Knowledge revision not found.") from None

    @app.get("/api/v1/knowledge-chunks/{chunk_id}")
    def get_knowledge_chunk(chunk_id: str) -> dict[str, Any]:
        try:
            return knowledge().get_chunk(chunk_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Knowledge chunk not found.") from None

    @app.post("/api/v1/knowledge-revisions/{revision_id}/reindex")
    def reindex_knowledge_revision(revision_id: str) -> dict[str, Any]:
        try:
            return knowledge().reindex_revision(revision_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Knowledge revision not found.") from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    @app.post("/api/v1/workspaces/{workspace_id}/knowledge-query")
    def query_knowledge(workspace_id: str, request: KnowledgeQueryRequest) -> dict[str, Any]:
        try:
            return knowledge().query(
                workspace_id,
                request.query,
                as_of_time=request.as_of_time,
                top_k=request.top_k,
                neighbor_count=request.neighbor_count,
                max_context_chars=request.max_context_chars,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    if review_enabled:

        @app.get("/internal/m1-review", include_in_schema=False)
        def internal_m1_review() -> FileResponse:
            return FileResponse(Path(__file__).with_name("internal_m1_review.html"))

        @app.get("/internal/knowledge-review", include_in_schema=False)
        def internal_knowledge_review() -> FileResponse:
            return FileResponse(Path(__file__).with_name("internal_knowledge_review.html"))

    static_dir = Path(__file__).resolve().parent / "static"
    if not (static_dir / "index.html").is_file():
        raise RuntimeError("packaged frontend is missing; run the frontend production build")
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")
    return app
