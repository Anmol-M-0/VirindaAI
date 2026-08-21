from __future__ import annotations

import argparse
import json
from pathlib import Path

from virinda.application.runtime import build_service
from virinda.config.settings import Settings
from virinda.interfaces.ipc import LocalRPCClient, default_socket_path
from virinda.ovos.doctor import render_report, run_doctor


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="virinda", description="MarinaAI local-first assistant")
    parser.add_argument("--data-dir", type=Path, help="override local state directory")
    parser.add_argument(
        "--socket",
        type=Path,
        help="use a running marinad Unix socket instead of opening SQLite locally",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    doctor = sub.add_parser("doctor", help="check local OVOS integration and configuration")
    doctor.add_argument(
        "--json", action="store_true", dest="doctor_json", help="emit machine-readable JSON"
    )
    doctor.add_argument(
        "--services", action="store_true", help="also check Marina OVOS user services"
    )
    doctor.add_argument(
        "--audio", action="store_true", help="inspect PipeWire/WirePlumber and ALSA audio devices"
    )
    doctor.add_argument(
        "--nats",
        action="store_true",
        help="inspect the NATS JetStream job-backbone client configuration",
    )
    provider = sub.add_parser("provider", help="select the active provider/model")
    provider.add_argument("name")
    provider.add_argument("--model")
    sub.add_parser("providers")
    profile = sub.add_parser("profile", help="inspect or change the local user profile")
    profile.add_argument("action", choices=["show", "update", "clear"], nargs="?", default="show")
    profile.add_argument("--json", dest="profile_json", default="{}")
    sub.add_parser("capabilities", help="list Marina capability contracts")
    context = sub.add_parser("context", help="show or change interaction context mode")
    context.add_argument("mode", nargs="?", choices=["normal", "focus", "private", "quiet"])
    ask = sub.add_parser("ask", help="send a text prompt")
    ask.add_argument("prompt")
    ask.add_argument("--provider")
    ask.add_argument("--model")
    stream = sub.add_parser("ask-stream", help="stream provider events over the daemon socket")
    stream.add_argument("prompt")
    stream.add_argument("--provider")
    stream.add_argument("--model")
    sub.add_parser("history")
    events = sub.add_parser("events")
    events.add_argument("--limit", type=int, default=100)
    sub.add_parser("sessions")
    sub.add_parser("clear")
    backup = sub.add_parser("backup")
    backup.add_argument("destination", type=Path)
    cancel = sub.add_parser("cancel")
    cancel.add_argument("--reason", default="user")
    sub.add_parser("features")
    memory = sub.add_parser("memory", help="inspect or manage local memory")
    memory.add_argument("action", choices=["show", "search", "fact", "note", "clear"])
    memory.add_argument("args", nargs="*")
    alerts = sub.add_parser("alerts")
    alerts.add_argument("action", choices=["list", "add", "cancel"], default="list", nargs="?")
    alerts.add_argument("args", nargs="*")
    sub.add_parser("notifications")
    sub.add_parser("briefing")
    sub.add_parser("desktop-signals")
    routines = sub.add_parser("routines", help="inspect and schedule local routines")
    routines.add_argument(
        "action",
        choices=[
            "list",
            "schedule",
            "run-due",
            "runs",
            "event",
            "approve",
            "preview",
            "update",
            "disable",
            "delete",
            "health",
            "reconcile",
        ],
        default="list",
        nargs="?",
    )
    routines.add_argument("args", nargs="*")
    sub.add_parser("tools")
    tool = sub.add_parser("tool")
    tool.add_argument("name")
    tool.add_argument("--approve", action="store_true")
    tool.add_argument("--json-args", default="{}")
    overlay = sub.add_parser(
        "overlay",
        help="optional localhost developer diagnostics UI; production OVOS uses MessageBus/ovos-gui",
    )
    overlay.add_argument("--host", default="127.0.0.1")
    overlay.add_argument("--port", type=int, default=8765)
    sub.add_parser("features-json")
    return parser


def _rpc(args: argparse.Namespace, settings: Settings) -> None:
    client = LocalRPCClient(args.socket or default_socket_path(settings.data_dir))
    command = args.command
    if command == "status":
        print(json.dumps(client.call("status"), indent=2))
    elif command == "providers":
        print("\n".join(client.call("providers")))
    elif command == "profile":
        if args.action == "show":
            print(json.dumps(client.call("profile"), indent=2))
        elif args.action == "update":
            print(
                json.dumps(
                    client.call("profile_update", changes=json.loads(args.profile_json)), indent=2
                )
            )
        elif args.action == "clear":
            client.call("profile_clear")
    elif command == "provider":
        print(
            json.dumps(client.call("set_provider", provider=args.name, model=args.model), indent=2)
        )
    elif command == "capabilities":
        print(json.dumps(client.call("capabilities"), indent=2))
    elif command == "context":
        if args.mode:
            print(json.dumps(client.call("set_context", mode=args.mode), indent=2))
        else:
            print(json.dumps(client.call("context"), indent=2))
    elif command == "ask":
        result = client.call("ask", text=args.prompt, provider=args.provider, model=args.model)
        if result:
            print(result)
    elif command == "ask-stream":
        for event in client.stream(args.prompt, provider=args.provider, model=args.model):
            if event.get("type") == "ResponseDelta":
                print(event.get("text", ""), end="", flush=True)
        print()
    elif command == "history":
        for message in client.call("history"):
            print(f"[{message['role']}] {message['content']}")
    elif command == "events":
        for event in client.call("events", limit=args.limit):
            print(json.dumps(event, ensure_ascii=False))
    elif command == "sessions":
        print("\n".join(client.call("sessions")))
    elif command == "clear":
        client.call("clear")
    elif command == "backup":
        print(client.call("backup", destination=str(args.destination)))
    elif command == "cancel":
        client.call("cancel", reason=args.reason)
    elif command == "features":
        print(json.dumps(client.call("features"), indent=2))
    elif command == "memory":
        if args.action == "show":
            print(json.dumps(client.call("memory"), indent=2))
        elif args.action == "search":
            print(json.dumps(client.call("memory_search", query=args.args[0]), indent=2))
        elif args.action == "fact":
            print(
                json.dumps(
                    client.call("memory_fact", key=args.args[0], value=args.args[1]), indent=2
                )
            )
        elif args.action == "note":
            print(json.dumps(client.call("memory_note", text=" ".join(args.args)), indent=2))
        elif args.action == "clear":
            client.call("memory_clear")
    elif command == "alerts":
        if args.action == "list":
            print(json.dumps(client.call("alerts"), indent=2))
        elif args.action == "cancel":
            print(client.call("cancel_alert", id=args.args[0]))
    elif command == "notifications":
        print(json.dumps(client.call("notifications"), indent=2))
    elif command == "briefing":
        print(client.call("briefing"))
    elif command == "desktop-signals":
        print(json.dumps(client.call("desktop_signals"), indent=2))
    elif command == "routines":
        if args.action == "list":
            print(json.dumps(client.call("routines"), indent=2))
        elif args.action == "schedule":
            print(
                json.dumps(
                    client.call(
                        "routine_schedule",
                        name=args.args[0],
                        due_at=float(args.args[1]),
                        action=args.args[2],
                    ),
                    indent=2,
                )
            )
        elif args.action == "run-due":
            print(json.dumps(client.call("routine_run_due"), indent=2))
        elif args.action == "runs":
            print(
                json.dumps(
                    client.call("routine_runs", routine_id=(args.args[0] if args.args else None)),
                    indent=2,
                )
            )
        elif args.action == "preview":
            print(json.dumps(client.call("routine_preview", id=args.args[0]), indent=2))
        elif args.action == "event":
            print(
                json.dumps(
                    client.call(
                        "routine_event",
                        event=args.args[0],
                        payload=json.loads(args.args[1]) if len(args.args) > 1 else {},
                    ),
                    indent=2,
                )
            )
        elif args.action == "approve":
            print(json.dumps(client.call("routine_approve", run_id=args.args[0]), indent=2))
        elif args.action == "update":
            changes = json.loads(args.args[1])
            print(
                json.dumps(
                    client.call("routine_update", id=args.args[0], changes=changes), indent=2
                )
            )
        elif args.action == "disable":
            print(client.call("routine_disable", id=args.args[0]))
        elif args.action == "delete":
            print(client.call("routine_delete", id=args.args[0]))
        elif args.action == "health":
            print(json.dumps(client.call("automation_health"), indent=2))
        elif args.action == "reconcile":
            print(
                json.dumps(
                    client.call(
                        "automation_reconcile",
                        stale_after_seconds=float(args.args[0]) if args.args else 900.0,
                        requeue=(len(args.args) > 1 and args.args[1].lower() == "requeue"),
                    ),
                    indent=2,
                )
            )
    elif command == "tools":
        print(json.dumps(client.call("capabilities"), indent=2))
    elif command == "tool":
        print(
            json.dumps(
                client.call(
                    "tool_execute",
                    name=args.name,
                    approved=args.approve,
                    kwargs=json.loads(args.json_args),
                ),
                indent=2,
            )
        )


def main() -> None:
    args = _parser().parse_args()
    settings = Settings.from_env()
    if args.data_dir:
        settings = settings.with_data_dir(args.data_dir)
    if args.socket:
        _rpc(args, settings)
        return

    if args.command == "doctor":
        report = run_doctor(
            Path(__file__).parents[3],
            check_services=args.services,
            check_audio=args.audio,
            check_nats=args.nats,
        )
        if args.doctor_json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print(render_report(report))
        raise SystemExit(0 if report.ok else 1)

    service = build_service(settings)
    try:
        if args.command == "status":
            print(json.dumps(service.health(), indent=2))
        elif args.command == "providers":
            print("\n".join(service.router.available()))
        elif args.command == "profile":
            if args.action == "show":
                print(json.dumps(service.profile_snapshot(), indent=2))
            elif args.action == "update":
                print(json.dumps(service.update_profile(**json.loads(args.profile_json)), indent=2))
            elif args.action == "clear":
                service.clear_profile()
        elif args.command == "provider":
            print(json.dumps(service.select_provider(args.name, args.model), indent=2))
        elif args.command == "capabilities":
            print(json.dumps(service.capability_snapshot(), indent=2))
        elif args.command == "context":
            if args.mode:
                service.set_context_mode(args.mode)
            print(json.dumps(service.context(), indent=2))
        elif args.command == "ask":
            result = service.ask(args.prompt, provider=args.provider, model=args.model)
            if result:
                print(result)
        elif args.command == "ask-stream":
            raise SystemExit("ask-stream requires --socket and a running marinad")
        elif args.command == "history":
            for message in service.store.load_messages(service.snapshot().session_id):
                print(f"[{message.role}] {message.content}")
        elif args.command == "events":
            for event in service.store.load_events(service.snapshot().session_id, args.limit):
                print(
                    json.dumps(
                        {"type": type(event).__name__, **event.to_payload()}, ensure_ascii=False
                    )
                )
        elif args.command == "sessions":
            for session_id in service.store.list_sessions():
                print(session_id)
        elif args.command == "clear":
            service.clear()
        elif args.command == "backup":
            print(service.store.backup(args.destination))
        elif args.command == "cancel":
            service.cancel(args.reason)
        elif args.command == "features" or args.command == "features-json":
            print(json.dumps(service.feature_health(), indent=2))
        elif args.command == "memory":
            if args.action == "show":
                print(json.dumps(service.memory_snapshot(), indent=2))
            elif args.action == "search":
                print(json.dumps(service.memory_search(args.args[0]), indent=2))
            elif args.action == "fact":
                print(json.dumps(service.memory_fact(args.args[0], args.args[1]), indent=2))
            elif args.action == "note":
                print(json.dumps(service.memory_add_note(" ".join(args.args)), indent=2))
            elif args.action == "clear":
                service.memory_clear()
        elif args.command == "alerts":
            if args.action == "list":
                print(json.dumps(service.alerts_snapshot(), indent=2))
            elif args.action == "add":
                print(
                    json.dumps(
                        service.schedule_alert(args.args[0], args.args[1], float(args.args[2])),
                        indent=2,
                    )
                )
            elif args.action == "cancel":
                print(service.cancel_alert(args.args[0]))
        elif args.command == "notifications":
            print(json.dumps(service.notifications_snapshot(), indent=2))
        elif args.command == "briefing":
            print(service.briefing())
        elif args.command == "desktop-signals":
            print(json.dumps(service.desktop_signals(), indent=2))
        elif args.command == "routines":
            if args.action == "list":
                print(json.dumps(service.routines_snapshot(), indent=2))
            elif args.action == "schedule":
                print(
                    json.dumps(
                        service.schedule_routine(args.args[0], float(args.args[1]), args.args[2]),
                        indent=2,
                    )
                )
            elif args.action == "run-due":
                print(json.dumps(service.run_due_routines(), indent=2))
            elif args.action == "runs":
                print(
                    json.dumps(service.routine_runs(args.args[0] if args.args else None), indent=2)
                )
            elif args.action == "preview":
                print(json.dumps(service.routine_preview(args.args[0]), indent=2))
            elif args.action == "event":
                print(
                    json.dumps(
                        service.run_routine_event(
                            args.args[0], json.loads(args.args[1]) if len(args.args) > 1 else {}
                        ),
                        indent=2,
                    )
                )
            elif args.action == "approve":
                print(json.dumps(service.approve_routine_run(args.args[0]), indent=2))
            elif args.action == "update":
                print(
                    json.dumps(
                        service.update_routine(args.args[0], **json.loads(args.args[1])), indent=2
                    )
                )
            elif args.action == "disable":
                print(service.disable_routine(args.args[0]))
            elif args.action == "delete":
                print(service.delete_routine(args.args[0]))
            elif args.action == "health":
                print(json.dumps(service.automation_health(), indent=2))
            elif args.action == "reconcile":
                print(
                    json.dumps(
                        service.reconcile_automation(
                            stale_after_seconds=float(args.args[0]) if args.args else 900.0,
                            requeue=(len(args.args) > 1 and args.args[1].lower() == "requeue"),
                        ),
                        indent=2,
                    )
                )
        elif args.command == "tools":
            print(
                json.dumps(
                    [
                        {
                            "name": d.name,
                            "capability": d.capability,
                            "description": d.description,
                            "risk": d.risk.value,
                        }
                        for d in service.tools.describe()
                    ],
                    indent=2,
                )
            )
        elif args.command == "tool":
            print(
                json.dumps(
                    service.tool_execute(
                        args.name, approved=args.approve, **json.loads(args.json_args)
                    ),
                    indent=2,
                )
            )
        elif args.command == "overlay":
            from virinda.desktop import OverlayServer

            overlay_server = OverlayServer(service, args.host, args.port)
            host, port = overlay_server.start()
            print(f"Marina diagnostics overlay (localhost only): http://{host}:{port}/")
            try:
                import threading

                threading.Event().wait()
            except KeyboardInterrupt:
                pass
            finally:
                overlay_server.stop()
    finally:
        service.close()
