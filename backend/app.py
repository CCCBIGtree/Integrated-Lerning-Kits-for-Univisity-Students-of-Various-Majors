"""Flask 后端：提供分类 / 专业 / 网站数据接口，并托管前端页面。

启动：
    python -m backend.app                 # 默认 http://127.0.0.1:5000
    python -m backend.app --no-crawl      # 只启动网站，不运行定时爬虫
"""

from __future__ import annotations

import argparse
import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, abort, jsonify, request, send_from_directory

from . import crawler

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
CRAWL_INTERVAL_HOURS = 24
CRAWL_JITTER_SECONDS = 30 * 60  # 每次在 24 小时基础上随机浮动 ±30 分钟，避免固定时刻访问

app = Flask(__name__, static_folder=None)
scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
log = logging.getLogger("app")


def load_seed() -> dict:
    return json.loads(crawler.SEED_FILE.read_text(encoding="utf-8"))


def find_category(seed: dict, cid: str) -> dict:
    for cat in seed["categories"]:
        if cat["id"] == cid:
            return cat
    abort(404, description="分类不存在")


def enrich(site: dict, crawled: dict) -> dict:
    info = crawled["sites"].get(site["url"], {})
    return {
        **site,
        "status": info.get("status", "unknown"),
        "last_checked": info.get("last_checked"),
        "response_ms": info.get("response_ms"),
        "site_title": info.get("title", ""),
        "site_description": info.get("description", ""),
        "notices": info.get("notices", []),
    }


def site_count(cat: dict) -> int:
    return sum(len(m["sites"]) for m in cat["majors"])


@app.get("/api/categories")
def categories():
    seed = load_seed()
    return jsonify([
        {
            "id": c["id"],
            "name": c["name"],
            "icon": c.get("icon", ""),
            "description": c.get("description", ""),
            "major_count": len(c["majors"]),
            "site_count": site_count(c),
        }
        for c in seed["categories"]
    ])


@app.get("/api/categories/<cid>")
def category(cid: str):
    cat = find_category(load_seed(), cid)
    return jsonify({
        "id": cat["id"],
        "name": cat["name"],
        "icon": cat.get("icon", ""),
        "description": cat.get("description", ""),
        "majors": [
            {"id": m["id"], "name": m["name"], "site_count": len(m["sites"]),
             "preview": [s["name"] for s in m["sites"][:3]]}
            for m in cat["majors"]
        ],
    })


@app.get("/api/categories/<cid>/majors/<mid>")
def major(cid: str, mid: str):
    cat = find_category(load_seed(), cid)
    crawled = crawler.load_crawled()
    for m in cat["majors"]:
        if m["id"] == mid:
            return jsonify({
                "id": m["id"],
                "name": m["name"],
                "category": {"id": cat["id"], "name": cat["name"]},
                "sites": [enrich(s, crawled) for s in m["sites"]],
            })
    abort(404, description="专业不存在")


@app.get("/api/search")
def search():
    q = request.args.get("q", "").strip().lower()
    if not q:
        return jsonify([])
    seed, crawled = load_seed(), crawler.load_crawled()
    results, seen = [], set()
    for cat in seed["categories"]:
        for m in cat["majors"]:
            for s in m["sites"]:
                haystack = " ".join([s["name"], s["intro"], " ".join(s.get("tags", [])), m["name"]]).lower()
                key = (s["url"], m["id"])
                if q in haystack and key not in seen:
                    seen.add(key)
                    results.append({**enrich(s, crawled),
                                    "category": {"id": cat["id"], "name": cat["name"]},
                                    "major": {"id": m["id"], "name": m["name"]}})
    return jsonify(results[:50])


@app.get("/api/status")
def status():
    job = scheduler.get_job("daily-crawl") if scheduler.running else None
    return jsonify({
        "updated_at": crawler.load_crawled().get("updated_at"),
        "next_run": job.next_run_time.isoformat() if job and job.next_run_time else None,
        "interval_hours": CRAWL_INTERVAL_HOURS,
    })


@app.errorhandler(404)
def not_found(err):
    if request.path.startswith("/api/"):
        return jsonify({"error": getattr(err, "description", "Not Found")}), 404
    return err


@app.get("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/<path:path>")
def static_files(path: str):
    return send_from_directory(FRONTEND_DIR, path)


def _safe_crawl() -> None:
    try:
        crawler.run_once()
    except Exception:  # noqa: BLE001 - 定时任务失败不能拖垮网站
        log.exception("定时抓取失败")


def start_scheduler() -> None:
    updated = crawler.load_crawled().get("updated_at")
    stale = not updated or (
        datetime.now(timezone.utc) - datetime.fromisoformat(updated) > timedelta(hours=CRAWL_INTERVAL_HOURS)
    )
    scheduler.add_job(
        _safe_crawl, "interval", hours=CRAWL_INTERVAL_HOURS, jitter=CRAWL_JITTER_SECONDS,
        id="daily-crawl", max_instances=1, coalesce=True,
    )
    scheduler.start()
    if stale:
        # 数据缺失或已过期：后台立即补抓一轮，不阻塞网站启动
        threading.Thread(target=_safe_crawl, daemon=True).start()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--no-crawl", action="store_true", help="不启动定时爬虫")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if not args.no_crawl:
        start_scheduler()
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
