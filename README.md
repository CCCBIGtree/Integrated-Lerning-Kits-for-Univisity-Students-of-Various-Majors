# 大学生学习导航（Integrated Learning Kits）

按 **学科门类 → 专业方向 → 网站** 三级整理的大学生考试、考证、竞赛与学习网站导航。
后端用 Python 爬虫每 24 小时自动检测一次各网站，补充网站简介、可用状态和官网最新通知。

```
首页：通用 / 理科 / 工科 / 农科 / 医科 / 商科 / 管理 / 教育
  └─ 工科：电气 / 机械 / 计算机 / 土木
        └─ 计算机：蓝桥杯 / ICPC(ACM) / CCPC / LeetCode / Codeforces / 洛谷 …
              └─ 网站介绍 + 「访问官网」跳转
```

## 快速开始

```bash
pip install -r requirements.txt
python run.py                    # 打开 http://127.0.0.1:5000
```

在 PyCharm / VS Code 中直接右键 **`run.py` → 运行** 即可（不要直接运行 `backend/app.py`）。

- 启动时如果没有抓取数据（或数据超过 24 小时），会在后台立即抓取一轮，不影响网站访问。
- 之后每 24 小时（±30 分钟随机浮动）自动抓取一次。
- `python -m backend.app --no-crawl` 只启动网站；`python -m backend.crawler` 手动抓取一轮。

## 项目结构

```
backend/
  app.py            Flask 接口 + 托管前端 + APScheduler 定时任务
  crawler.py        礼貌型爬虫
  data/seed.json    收录的分类 / 专业 / 网站（手工维护）
  data/crawled.json 爬虫结果（自动生成，不提交）
frontend/
  index.html  style.css  app.js   原生 JS 单页应用（hash 路由，无需构建）
```

## 爬虫如何“模仿正常用户”

- 随机使用常见浏览器 User-Agent，携带正常的 `Accept` / `Accept-Language` 请求头
- 遵守各网站 `robots.txt`，禁止抓取的网站不访问
- 每轮打乱访问顺序，请求之间随机等待 3~10 秒；同一网址每轮只访问一次
- 只访问首页，失败最多重试 2 次（指数退避），超时 15 秒
- 抓取失败时保留上一次成功的数据

爬虫从每个网站首页提取：网页标题、`meta description`，以及包含“报名 / 通知 / 公告 / 成绩 / 大赛”等关键词的最新链接（最多 5 条），在前端卡片的「官网最新动态」中展示。

## 添加网站

编辑 `backend/data/seed.json`，在对应专业的 `sites` 里加一项即可，无需改代码：

```json
{"name": "网站名", "url": "https://example.com/", "tags": ["竞赛"], "intro": "一句话介绍"}
```

新增门类或专业同理（`categories` → `majors` → `sites`），`id` 用英文，会出现在网址中。

## 接口

| 接口 | 说明 |
| --- | --- |
| `GET /api/categories` | 一级门类列表 |
| `GET /api/categories/<分类id>` | 门类下的专业方向 |
| `GET /api/categories/<分类id>/majors/<专业id>` | 专业下的网站（含爬虫数据） |
| `GET /api/search?q=关键词` | 搜索网站 |
| `GET /api/status` | 上次抓取时间、下次抓取时间 |
