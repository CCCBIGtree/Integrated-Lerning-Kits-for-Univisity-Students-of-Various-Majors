"""礼貌型爬虫：定期访问 seed.json 中收录的网站，补充网站标题、简介、
可用状态以及首页上的最新通知（报名 / 公告 / 大赛等）。

模仿正常用户的做法：
- 随机使用常见浏览器 User-Agent，并携带正常的 Accept / Accept-Language 头
- 遵守 robots.txt
- 打乱访问顺序，每次请求之间随机等待若干秒
- 同一 URL 一轮只访问一次，失败指数退避重试，超时即放弃

用法：
    python -m backend.crawler            # 立即抓取一轮
    python -m backend.crawler --fast     # 调试用，缩短请求间隔
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).resolve().parent / "data"
SEED_FILE = DATA_DIR / "seed.json"
CRAWLED_FILE = DATA_DIR / "crawled.json"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.6 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36",
]

NOTICE_KEYWORDS = ("报名", "通知", "公告", "考试", "成绩", "大赛", "比赛", "竞赛", "准考证", "Contest", "News")

TIMEOUT = 15
MAX_RETRIES = 2
MIN_DELAY, MAX_DELAY = 3.0, 10.0

log = logging.getLogger("crawler")


def _headers() -> dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


class PoliteCrawler:
    def __init__(self, min_delay: float = MIN_DELAY, max_delay: float = MAX_DELAY):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.session = requests.Session()
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}

    def _sleep(self) -> None:
        time.sleep(random.uniform(self.min_delay, self.max_delay))

    def allowed(self, url: str) -> bool:
        parts = urlparse(url)
        root = f"{parts.scheme}://{parts.netloc}"
        if root not in self._robots:
            rp = robotparser.RobotFileParser()
            try:
                resp = self.session.get(urljoin(root, "/robots.txt"), headers=_headers(), timeout=TIMEOUT)
                if resp.status_code >= 400:
                    rp = None  # 没有 robots.txt 视为允许
                else:
                    rp.parse(resp.text.splitlines())
            except requests.RequestException:
                rp = None
            self._robots[root] = rp
        rp = self._robots[root]
        return rp is None or rp.can_fetch("*", url)

    def fetch(self, url: str) -> tuple[requests.Response | None, float, str | None]:
        """返回 (response, 耗时毫秒, 错误信息)。"""
        error = None
        for attempt in range(MAX_RETRIES + 1):
            start = time.monotonic()
            try:
                resp = self.session.get(url, headers=_headers(), timeout=TIMEOUT, allow_redirects=True)
                return resp, (time.monotonic() - start) * 1000, None
            except requests.RequestException as exc:
                error = type(exc).__name__
                if attempt < MAX_RETRIES:
                    time.sleep(2 ** (attempt + 1) + random.random())
        return None, 0.0, error

    def crawl_site(self, url: str) -> dict:
        result = {
            "url": url,
            "last_checked": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": "unknown",
        }
        if not self.allowed(url):
            result["status"] = "robots_disallowed"
            return result

        resp, elapsed, error = self.fetch(url)
        if resp is None:
            result.update(status="unreachable", error=error)
            return result

        result.update(http_status=resp.status_code, response_ms=round(elapsed), final_url=resp.url)
        if resp.status_code >= 400:
            result["status"] = "error"
            return result

        result["status"] = "ok"
        if "html" in resp.headers.get("Content-Type", "html"):
            if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
                resp.encoding = resp.apparent_encoding
            result.update(parse_page(resp.text, resp.url))
        return result


def parse_page(html: str, base_url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    def meta(*names: str) -> str:
        for name in names:
            tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
            if tag and tag.get("content"):
                return " ".join(tag["content"].split())[:300]
        return ""

    title = " ".join(soup.title.get_text().split())[:120] if soup.title else ""

    notices, seen = [], set()
    for a in soup.find_all("a", href=True):
        text = " ".join(a.get_text().split())
        if not (6 <= len(text) <= 60) or text in seen:
            continue
        if not any(k.lower() in text.lower() for k in NOTICE_KEYWORDS):
            continue
        href = urljoin(base_url, a["href"])
        if not href.startswith(("http://", "https://")):
            continue
        seen.add(text)
        notices.append({"title": text, "url": href})
        if len(notices) >= 5:
            break

    return {
        "title": title,
        "description": meta("description", "og:description", "Description"),
        "keywords": meta("keywords", "Keywords"),
        "notices": notices,
    }


def unique_urls(seed: dict) -> list[str]:
    urls = {
        site["url"]
        for cat in seed["categories"]
        for major in cat["majors"]
        for site in major["sites"]
    }
    return sorted(urls)


def load_crawled() -> dict:
    if CRAWLED_FILE.exists():
        try:
            return json.loads(CRAWLED_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("crawled.json 损坏，将重新生成")
    return {"updated_at": None, "sites": {}}


def run_once(min_delay: float = MIN_DELAY, max_delay: float = MAX_DELAY) -> dict:
    seed = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    urls = unique_urls(seed)
    random.shuffle(urls)  # 打乱顺序，避免固定的访问模式

    crawler = PoliteCrawler(min_delay, max_delay)
    data = load_crawled()
    log.info("开始抓取 %d 个网站", len(urls))

    for i, url in enumerate(urls, 1):
        info = crawler.crawl_site(url)
        old = data["sites"].get(url, {})
        # 抓取失败时保留上一次成功获得的标题 / 简介 / 通知
        if info["status"] != "ok":
            for key in ("title", "description", "keywords", "notices"):
                if key in old:
                    info[key] = old[key]
        data["sites"][url] = info
        log.info("[%d/%d] %s -> %s", i, len(urls), url, info["status"])
        if i < len(urls):
            crawler._sleep()

    data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tmp = CRAWLED_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CRAWLED_FILE)
    log.info("抓取完成，结果写入 %s", CRAWLED_FILE)
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取一轮学习网站信息")
    parser.add_argument("--fast", action="store_true", help="调试模式：请求间隔缩短为 0.5~1 秒")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.fast:
        run_once(0.5, 1.0)
    else:
        run_once()


if __name__ == "__main__":
    main()
