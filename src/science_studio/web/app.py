"""Mobile-friendly web UI. Simple: new project, progress, inspect, download, resume."""
from __future__ import annotations
import threading, json
from pathlib import Path
from flask import Flask, request, render_template, redirect, url_for, send_file, jsonify

from .. import storage
from ..pipeline import run_project

app = Flask(__name__, template_folder="templates")
_jobs: dict[str, dict] = {}


def _run_bg(pid: str, **kw):
    _jobs[pid] = {"status": "running"}
    try:
        res = run_project(pid, **kw)
        _jobs[pid] = {"status": "done", "result": res}
    except Exception as e:
        _jobs[pid] = {"status": "error", "error": str(e)}


@app.route("/")
def index():
    return render_template("index.html", projects=storage.list_projects())


@app.route("/new", methods=["POST"])
def new():
    idea = request.form.get("idea", "").strip()
    if not idea:
        return redirect(url_for("index"))
    pid, _ = storage.create_project(
        idea, request.form.get("instructions", ""),
        request.form.get("duration", "12-15"), request.form.get("mode", "autonomous"))
    threading.Thread(target=_run_bg, args=(pid,), daemon=True).start()
    return redirect(url_for("project", pid=pid))


@app.route("/p/<pid>")
def project(pid):
    root = storage.project_dir(pid)
    doc = storage.read_json(root / "idea.json", {})
    plan = storage.read_json(root / "research" / "research_plan.json", {})
    sources = storage.read_json(root / "research" / "sources.json", [])
    claims = storage.read_json(root / "research" / "claims.json", [])
    outline = storage.read_json(root / "script" / "outline.json", {})
    fact = storage.read_json(root / "script" / "factcheck.json", {})
    board = storage.read_json(root / "production" / "storyboard.json", [])
    assets = storage.read_json(root / "production" / "assets.json", [])
    narr = storage.read_json(root / "production" / "narration.json", [])
    qa = storage.read_json(root / "production" / "final" / "qa-report.json", {})
    meta = storage.read_json(root / "production" / "final" / "metadata.json", {})
    script_md = (root / "script" / "script.md").read_text(encoding="utf-8") if (root / "script" / "script.md").exists() else ""
    log = (root / "pipeline.log").read_text(encoding="utf-8")[-6000:] if (root / "pipeline.log").exists() else ""
    job = _jobs.get(pid, {})
    final = root / "production" / "final" / "final.mp4"
    return render_template("project.html", pid=pid, doc=doc, plan=plan, sources=sources,
                           claims=claims, outline=outline, fact=fact, board=board,
                           assets=assets, narr=narr, qa=qa, meta=meta, script=script_md,
                           log=log, job=job, has_video=final.exists())


@app.route("/p/<pid>/resume")
def resume(pid):
    threading.Thread(target=_run_bg, args=(pid,), daemon=True).start()
    return redirect(url_for("project", pid=pid))


@app.route("/p/<pid>/video")
def video(pid):
    return send_file(storage.project_dir(pid) / "production" / "final" / "final.mp4",
                     mimetype="video/mp4", as_attachment=False)


@app.route("/p/<pid>/download/<path:name>")
def download(pid, name):
    # allowlisted production package files
    root = storage.project_dir(pid)
    safe = (root / name)
    try:
        safe.resolve().relative_to(root.resolve())
    except ValueError:
        return "forbidden", 403
    if not safe.exists() or not safe.is_file():
        return "not found", 404
    return send_file(safe, as_attachment=True)


@app.route("/p/<pid>/package")
def package(pid):
    import zipfile, io
    root = storage.project_dir(pid)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for ext in (".json", ".md", ".srt", ".vtt", ".txt", ".svg"):
            for f in root.rglob(f"*{ext}"):
                z.write(f, f.relative_to(root))
        for f in [root / "production" / "final" / "final.mp4",
                  root / "production" / "final" / "thumbnail.png"]:
            if f.exists():
                z.write(f, f.relative_to(root))
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True,
                     download_name=f"{pid}.zip")


@app.route("/api/providers")
def api_providers():
    from ..providers.registry import build_providers
    return jsonify(build_providers().status_report())


@app.route("/api/projects")
def api_projects():
    return jsonify(storage.list_projects())


def main():
    app.run(host="0.0.0.0", port=5000, debug=False)


if __name__ == "__main__":
    main()
