"""Loopback-first API and packaged frontend for the local web product."""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from community_intelligence import __version__
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


class DemoRequest(BaseModel):
    seed: int = 20260901
    message_count: int = Field(default=1200, ge=MIN_MESSAGE_COUNT, le=100_000)


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

    static_dir = Path(__file__).resolve().parent / "static"
    if not (static_dir / "index.html").is_file():
        raise RuntimeError("packaged frontend is missing; run the frontend production build")
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")
    return app
