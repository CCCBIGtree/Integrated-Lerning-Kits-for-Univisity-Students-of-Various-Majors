// 单页应用：基于 hash 的三级路由
//   #/                      首页：一级分类（通用 / 理 / 工 / 农 / 医 / 商 / 管 / 教育）
//   #/c/<分类>              二级：专业方向（如 工科 -> 电气 / 机械 / 计算机）
//   #/c/<分类>/m/<专业>     三级：网站介绍卡片，可点击跳转
//   #/search/<关键词>       搜索结果

const view = document.getElementById("view");
const breadcrumb = document.getElementById("breadcrumb");
const searchInput = document.getElementById("search-input");

const STATUS_TEXT = {
  ok: "可访问",
  error: "访问异常",
  unreachable: "暂时无法访问",
  robots_disallowed: "未抓取",
  unknown: "待检测",
};

function esc(str) {
  return String(str ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

function safeUrl(url) {
  return /^https?:\/\//i.test(url) ? url : "#";
}

async function api(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || res.statusText);
  return res.json();
}

function setCrumbs(items) {
  breadcrumb.innerHTML = items
    .map((it, i) => (i < items.length - 1 && it.href
      ? `<a href="${it.href}">${esc(it.label)}</a>`
      : `<span>${esc(it.label)}</span>`))
    .join('<span class="sep">›</span>');
}

function siteCard(site, showWhere = false) {
  const status = site.status || "unknown";
  const checked = site.last_checked ? `，检测于 ${new Date(site.last_checked).toLocaleString("zh-CN")}` : "";
  const crawled = site.site_description && site.site_description !== site.intro
    ? `<p class="crawled" title="由爬虫从网站首页获取">${esc(site.site_description)}</p>` : "";
  const notices = site.notices?.length
    ? `<details class="notices"><summary>官网最新动态（${site.notices.length}）</summary><ul>${
      site.notices.map((n) => `<li><a href="${esc(safeUrl(n.url))}" target="_blank" rel="noopener noreferrer">${esc(n.title)}</a></li>`).join("")
    }</ul></details>` : "";
  const where = showWhere && site.category
    ? `<a class="where" href="#/c/${esc(site.category.id)}/m/${esc(site.major.id)}">${esc(site.category.name)} › ${esc(site.major.name)}</a>` : "";

  return `
    <article class="card site">
      <div class="site-head">
        <h3>${esc(site.name)}</h3>
        <span class="status ${esc(status)}" title="${esc(STATUS_TEXT[status] || status)}${esc(checked)}">${esc(STATUS_TEXT[status] || status)}</span>
      </div>
      ${where}
      <div class="tags">${(site.tags || []).map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</div>
      <p class="intro">${esc(site.intro)}</p>
      ${crawled}
      ${notices}
      <a class="visit" href="${esc(safeUrl(site.url))}" target="_blank" rel="noopener noreferrer">访问官网 ↗</a>
    </article>`;
}

async function renderHome() {
  setCrumbs([{ label: "首页" }]);
  const cats = await api("/api/categories");
  view.innerHTML = `
    <h1>选择你的学科门类</h1>
    <p class="lead">按门类 → 专业逐级查找考试、考证、竞赛与学习网站</p>
    <div class="list">${cats.map((c) => `
      <a class="card row" href="#/c/${esc(c.id)}">
        <span class="icon">${esc(c.icon)}</span>
        <div class="row-body">
          <h2>${esc(c.name)}</h2>
          <p>${esc(c.description)}</p>
        </div>
        <span class="meta">${c.major_count} 个方向 · ${c.site_count} 个网站 →</span>
      </a>`).join("")}
    </div>`;
}

async function renderCategory(cid) {
  const cat = await api(`/api/categories/${encodeURIComponent(cid)}`);
  setCrumbs([{ label: "首页", href: "#/" }, { label: cat.name }]);
  view.innerHTML = `
    <h1>${esc(cat.icon)} ${esc(cat.name)}</h1>
    <p class="lead">${esc(cat.description)}</p>
    <div class="list">${cat.majors.map((m) => `
      <a class="card row" href="#/c/${esc(cat.id)}/m/${esc(m.id)}">
        <div class="row-body">
          <h2>${esc(m.name)}</h2>
          <p>${m.preview.map(esc).join("、")}${m.site_count > 3 ? " 等" : ""}</p>
        </div>
        <span class="meta">${m.site_count} 个网站 →</span>
      </a>`).join("")}
    </div>`;
}

async function renderMajor(cid, mid) {
  const major = await api(`/api/categories/${encodeURIComponent(cid)}/majors/${encodeURIComponent(mid)}`);
  setCrumbs([
    { label: "首页", href: "#/" },
    { label: major.category.name, href: `#/c/${major.category.id}` },
    { label: major.name },
  ]);
  view.innerHTML = `
    <h1>${esc(major.name)}</h1>
    <p class="lead">${major.sites.length} 个相关网站，点击“访问官网”跳转</p>
    <div class="site-list">${major.sites.map((s) => siteCard(s)).join("")}</div>`;
}

async function renderSearch(q) {
  setCrumbs([{ label: "首页", href: "#/" }, { label: `搜索：${q}` }]);
  searchInput.value = q;
  const results = await api(`/api/search?q=${encodeURIComponent(q)}`);
  view.innerHTML = results.length
    ? `<h1>搜索“${esc(q)}”</h1><p class="lead">找到 ${results.length} 条结果</p>
       <div class="site-list">${results.map((s) => siteCard(s, true)).join("")}</div>`
    : `<div class="empty">没有找到与“${esc(q)}”相关的网站</div>`;
}

async function router() {
  const parts = location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  try {
    if (parts[0] === "c" && parts[1] && parts[2] === "m" && parts[3]) await renderMajor(parts[1], parts[3]);
    else if (parts[0] === "c" && parts[1]) await renderCategory(parts[1]);
    else if (parts[0] === "search" && parts[1]) await renderSearch(parts[1]);
    else await renderHome();
  } catch (err) {
    view.innerHTML = `<div class="error-box">加载失败：${esc(err.message)}　<a href="#/">返回首页</a></div>`;
  }
  window.scrollTo(0, 0);
}

document.getElementById("search-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = searchInput.value.trim();
  location.hash = q ? `#/search/${encodeURIComponent(q)}` : "#/";
});

async function loadStatus() {
  const el = document.getElementById("crawl-status");
  try {
    const s = await api("/api/status");
    el.textContent = s.updated_at
      ? `网站信息每 ${s.interval_hours} 小时自动更新 · 上次更新 ${new Date(s.updated_at).toLocaleString("zh-CN")}`
      : "网站信息尚未抓取，首次抓取进行中…";
  } catch {
    el.textContent = "";
  }
}

window.addEventListener("hashchange", router);
router();
loadStatus();
