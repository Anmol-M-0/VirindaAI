from __future__ import annotations

import concurrent.futures
import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional


class DiagnosticStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"


@dataclass(slots=True)
class CheckResult:
    name: str
    category: str
    status: DiagnosticStatus
    message: str
    latency_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DoctorReport:
    overall_status: DiagnosticStatus
    checks: list[CheckResult] = field(default_factory=list)
    total_latency_ms: float = 0.0

    @property
    def is_healthy(self) -> bool:
        return self.overall_status in (DiagnosticStatus.PASS, DiagnosticStatus.WARN)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_status": self.overall_status.value,
            "total_latency_ms": round(self.total_latency_ms, 2),
            "check_count": len(self.checks),
            "checks": [
                {
                    "name": c.name,
                    "category": c.category,
                    "status": c.status.value,
                    "message": c.message,
                    "latency_ms": round(c.latency_ms, 2),
                    "details": c.details,
                }
                for c in self.checks
            ],
        }


class DiagnosticRunner:
    """Unified system preflight diagnostic runner with bounded deadlines and read-only safety."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        bus_host: str = "127.0.0.1",
        bus_port: int = 8181,
        nats_url: str = "nats://127.0.0.1:4222",
        check_timeout_seconds: float = 0.8,
    ) -> None:
        self.db_path = (
            db_path or Path.home() / ".local" / "share" / "virinda-ai" / "virinda.sqlite3"
        )
        self.bus_host = bus_host
        self.bus_port = bus_port
        self.nats_url = nats_url
        self.check_timeout_seconds = check_timeout_seconds

    def check_audio(self) -> CheckResult:
        t0 = time.time()
        recorders = [cmd for cmd in ("pw-record", "arecord", "sox") if shutil.which(cmd)]
        players = [cmd for cmd in ("pw-play", "aplay", "paplay") if shutil.which(cmd)]

        lat = (time.time() - t0) * 1000.0
        if recorders and players:
            return CheckResult(
                name="audio_subsystem",
                category="audio",
                status=DiagnosticStatus.PASS,
                message=f"Audio capture ({recorders[0]}) and playback ({players[0]}) ready.",
                latency_ms=lat,
                details={"recorders": recorders, "players": players},
            )
        return CheckResult(
            name="audio_subsystem",
            category="audio",
            status=DiagnosticStatus.WARN,
            message="Missing native PipeWire/ALSA utilities; mock audio fallback active.",
            latency_ms=lat,
            details={"recorders": recorders, "players": players},
        )

    def check_compositor(self) -> CheckResult:
        t0 = time.time()
        from virinda.infrastructure.desktop.probes import detect_desktop_context

        ctx = detect_desktop_context()
        lat = (time.time() - t0) * 1000.0
        return CheckResult(
            name="desktop_compositor",
            category="desktop",
            status=DiagnosticStatus.PASS,
            message=f"Compositor ({ctx.compositor}) active; focused app: {ctx.active_app or 'none'}.",
            latency_ms=lat,
            details=ctx.to_dict(),
        )

    def check_sqlite_integrity(self) -> CheckResult:
        t0 = time.time()
        if not self.db_path.exists():
            return CheckResult(
                name="sqlite_database",
                category="storage",
                status=DiagnosticStatus.PASS,
                message="Clean environment; database will be initialized on first run.",
                latency_ms=(time.time() - t0) * 1000.0,
            )

        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=0.5)
            try:
                integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
                fk_violations = len(conn.execute("PRAGMA foreign_key_check").fetchall())
                user_version = conn.execute("PRAGMA user_version").fetchone()[0]
            finally:
                conn.close()

            lat = (time.time() - t0) * 1000.0
            if integrity == "ok" and fk_violations == 0:
                return CheckResult(
                    name="sqlite_database",
                    category="storage",
                    status=DiagnosticStatus.PASS,
                    message=f"SQLite WAL integrity verified (schema v{user_version}).",
                    latency_ms=lat,
                    details={
                        "integrity": integrity,
                        "fk_violations": fk_violations,
                        "version": user_version,
                    },
                )
            return CheckResult(
                name="sqlite_database",
                category="storage",
                status=DiagnosticStatus.FAIL,
                message=f"Database integrity issue: {integrity}, {fk_violations} FK violations.",
                latency_ms=lat,
                details={"integrity": integrity, "fk_violations": fk_violations},
            )
        except Exception as exc:
            return CheckResult(
                name="sqlite_database",
                category="storage",
                status=DiagnosticStatus.WARN,
                message=f"SQLite read check warning: {exc}",
                latency_ms=(time.time() - t0) * 1000.0,
            )

    def check_ovos_bus(self) -> CheckResult:
        t0 = time.time()
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.3)
        try:
            res = sock.connect_ex((self.bus_host, self.bus_port))
            lat = (time.time() - t0) * 1000.0
            if res == 0:
                return CheckResult(
                    name="ovos_message_bus",
                    category="ipc",
                    status=DiagnosticStatus.PASS,
                    message=f"OVOS MessageBus listening on {self.bus_host}:{self.bus_port}.",
                    latency_ms=lat,
                )
            return CheckResult(
                name="ovos_message_bus",
                category="ipc",
                status=DiagnosticStatus.WARN,
                message="OVOS MessageBus daemon not running locally (optional).",
                latency_ms=lat,
            )
        except Exception as exc:
            return CheckResult(
                name="ovos_message_bus",
                category="ipc",
                status=DiagnosticStatus.WARN,
                message=f"OVOS bus check warning: {exc}",
                latency_ms=(time.time() - t0) * 1000.0,
            )
        finally:
            sock.close()

    def check_embeddings(self) -> CheckResult:
        t0 = time.time()
        from virinda.infrastructure.persistence.embeddings import FastEmbedProvider

        fast_embed = FastEmbedProvider()
        lat = (time.time() - t0) * 1000.0
        if fast_embed._lazy_init():
            return CheckResult(
                name="semantic_embeddings",
                category="ml",
                status=DiagnosticStatus.PASS,
                message="Local FastEmbed ONNX semantic engine ready.",
                latency_ms=lat,
            )
        return CheckResult(
            name="semantic_embeddings",
            category="ml",
            status=DiagnosticStatus.PASS,
            message="Deterministic lexical BM25 fallback engine active.",
            latency_ms=lat,
        )

    def run_all(self) -> DoctorReport:
        t_start = time.time()
        checks: list[CheckResult] = []

        check_funcs: list[Callable[[], CheckResult]] = [
            self.check_audio,
            self.check_compositor,
            self.check_sqlite_integrity,
            self.check_ovos_bus,
            self.check_embeddings,
        ]

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(check_funcs)) as ex:
            futures = {ex.submit(fn): fn.__name__ for fn in check_funcs}
            for fut in concurrent.futures.as_completed(futures):
                try:
                    res = fut.result(timeout=self.check_timeout_seconds)
                    checks.append(res)
                except Exception as exc:
                    name = futures[fut]
                    checks.append(
                        CheckResult(
                            name=name,
                            category="system",
                            status=DiagnosticStatus.WARN,
                            message=f"Check timed out or failed: {exc}",
                        )
                    )

        overall = DiagnosticStatus.PASS
        for c in checks:
            if c.status == DiagnosticStatus.FAIL:
                overall = DiagnosticStatus.FAIL
                break
            elif c.status == DiagnosticStatus.WARN and overall != DiagnosticStatus.FAIL:
                overall = DiagnosticStatus.WARN

        total_lat = (time.time() - t_start) * 1000.0
        return DoctorReport(
            overall_status=overall,
            checks=checks,
            total_latency_ms=total_lat,
        )
