"""CLI: python -m science_studio <cmd>"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    from science_studio import storage
    from science_studio.pipeline import run_project
    ap = argparse.ArgumentParser(prog="science-studio", description="Autonomous science YouTube production")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("new", help="create a project")
    p.add_argument("idea")
    p.add_argument("--instructions", default="")
    p.add_argument("--duration", default="12-15", choices=["8-10", "12-15", "15-20", "auto"])
    p.add_argument("--mode", default="autonomous", choices=["autonomous", "approval"])

    p = sub.add_parser("run", help="run/resume a project")
    p.add_argument("project_id")
    p.add_argument("--from-scratch", action="store_true")
    p.add_argument("--stop-after", default="")

    p = sub.add_parser("status", help="project status")
    p.add_argument("project_id", nargs="?")

    p = sub.add_parser("list", help="list projects")
    p = sub.add_parser("providers", help="provider status")

    p = sub.add_parser("upload", help="upload final video to YouTube (optional)")
    p.add_argument("project_id")
    p.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])

    a = ap.parse_args()
    if a.cmd == "new":
        pid, root = storage.create_project(a.idea, a.instructions, a.duration, a.mode)
        print(json.dumps({"project_id": pid, "path": str(root)}, indent=2))
    elif a.cmd == "run":
        print(json.dumps(run_project(a.project_id, resume=not a.from_scratch,
                                     stop_after=a.stop_after), indent=2))
    elif a.cmd == "status":
        if a.project_id:
            doc = storage.read_json(storage.project_dir(a.project_id) / "idea.json", {})
            print(json.dumps(doc, indent=2))
        else:
            print(json.dumps(storage.list_projects(), indent=2))
    elif a.cmd == "list":
        print(json.dumps(storage.list_projects(), indent=2))
    elif a.cmd == "providers":
        from science_studio.providers.registry import build_providers
        print(json.dumps(build_providers().status_report(), indent=2))
    elif a.cmd == "upload":
        from science_studio.metadata.upload import upload_video
        root = storage.project_dir(a.project_id)
        meta = storage.read_json(root / "production" / "final" / "metadata.json", {})
        print(json.dumps(upload_video(
            str(root / "production" / "final" / "final.mp4"),
            (meta.get("titles") or ["Science video"])[0],
            meta.get("description", ""), meta.get("tags", []), a.privacy), indent=2))


if __name__ == "__main__":
    main()
