(function () {
  var root = document.body.dataset.root || "";
  var de = document.documentElement;
  function store(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) {} }

  // theme
  document.getElementById("theme-toggle").addEventListener("click", function () {
    var cur = de.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    var nx = cur === "dark" ? "light" : "dark";
    de.dataset.theme = nx; store("hm-theme", nx);
  });

  // reading mode
  var modeBtns = document.querySelectorAll(".modes button");
  function setMode(m) {
    de.dataset.mode = m; store("hm-mode", m);
    modeBtns.forEach(function (b) { b.classList.toggle("on", b.dataset.mode === m); });
  }
  setMode(de.dataset.mode || "zh");
  modeBtns.forEach(function (b) { b.addEventListener("click", function () { setMode(b.dataset.mode); }); });

  // ¶ toggles original
  document.querySelectorAll(".para .pnum").forEach(function (a) {
    a.addEventListener("click", function (ev) {
      if ((de.dataset.mode || "zh") !== "zh") return;
      ev.preventDefault();
      a.parentElement.classList.toggle("open");
      history.replaceState(null, "", a.getAttribute("href"));
    });
  });

  // nav toggle (mobile)
  document.getElementById("nav-toggle").addEventListener("click", function () { document.body.classList.toggle("nav-open"); });
  document.querySelector(".main").addEventListener("click", function () { document.body.classList.remove("nav-open"); });
  var on = document.querySelector(".sidebar .on");
  if (on && on.scrollIntoView) on.scrollIntoView({ block: "center" });

  // tooltips: glossary terms and footnotes
  var tip = document.getElementById("tip");
  function showTip(el, htmlStr) {
    tip.innerHTML = htmlStr; tip.hidden = false;
    var r = el.getBoundingClientRect();
    var left = Math.min(window.scrollX + r.left, window.scrollX + document.documentElement.clientWidth - tip.offsetWidth - 12);
    tip.style.left = Math.max(8, left) + "px";
    tip.style.top = (window.scrollY + r.bottom + 6) + "px";
  }
  function hideTip() { tip.hidden = true; }
  document.addEventListener("mouseover", function (ev) {
    var el = ev.target.closest("a.gl, sup.fn a, sup.tn a");
    if (!el) return;
    if (el.classList.contains("gl")) { showTip(el, escapeHtml(el.dataset.tip)); return; }
    var id = el.getAttribute("href").slice(1).replace(/^en-/, "");
    var li = document.getElementById(id);
    if (li) showTip(el, li.innerHTML);
  });
  document.addEventListener("mouseout", function (ev) { if (ev.target.closest("a.gl, sup.fn a, sup.tn a")) hideTip(); });
  function escapeHtml(s) { return (s || "").replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }

  // outline highlight
  var links = Array.prototype.slice.call(document.querySelectorAll(".outline a"));
  if (links.length && "IntersectionObserver" in window) {
    var map = {};
    links.forEach(function (a) { map[decodeURIComponent(a.getAttribute("href").slice(1))] = a; });
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (e.isIntersecting) { links.forEach(function (a) { a.classList.remove("on"); }); var a = map[e.target.id]; if (a) a.classList.add("on"); }
      });
    }, { rootMargin: "-70px 0px -70% 0px" });
    Object.keys(map).forEach(function (id) { var h = document.getElementById(id); if (h) io.observe(h); });
  }

  // search
  var q = document.getElementById("q"), res = document.getElementById("results"), idx = null, sel = -1;
  function load(cb) {
    if (idx) return cb();
    fetch(root + "search.json").then(function (r) { return r.json(); }).then(function (d) { idx = d; cb(); }).catch(function () {});
  }
  function norm(s) { return (s || "").toLowerCase().replace(/[‘’ʻ'`]/g, "").normalize("NFD").replace(/[̀-ͯ]/g, ""); }
  function snippet(text, term) {
    var t = norm(text), i = t.indexOf(term);
    if (i < 0) return "";
    var s = Math.max(0, i - 30), e = Math.min(text.length, i + term.length + 50);
    var raw = text.slice(s, e);
    return (s > 0 ? "…" : "") + escapeHtml(raw.slice(0, i - s)) + "<mark>" + escapeHtml(raw.slice(i - s, i - s + term.length)) + "</mark>" + escapeHtml(raw.slice(i - s + term.length)) + (e < text.length ? "…" : "");
  }
  function run() {
    var term = norm(q.value.trim());
    if (!term) { res.hidden = true; return; }
    var hits = [];
    idx.forEach(function (p) {
      var score = 0, tt = norm(p.t + " " + p.e);
      if (tt.indexOf(term) >= 0) score += 10;
      if (norm(p.s).indexOf(term) >= 0) score += 3;
      var x = norm(p.x), c = 0, k = x.indexOf(term);
      while (k >= 0 && c < 50) { c++; k = x.indexOf(term, k + term.length); }
      score += Math.min(c, 20) * 0.3;
      if (score > 0) hits.push({ p: p, s: score, c: c });
    });
    hits.sort(function (a, b) { return b.s - a.s; });
    sel = -1;
    res.innerHTML = hits.slice(0, 14).map(function (h) {
      var sn = snippet(h.p.x, term) || escapeHtml(h.p.s || h.p.e);
      return '<a href="' + root + h.p.u + '">' + escapeHtml(h.p.t) + (h.c ? ' <small style="display:inline">· ' + h.c + ' 处</small>' : "") + "<small>" + sn + "</small></a>";
    }).join("") || '<div style="padding:8px 10px;color:var(--ink-3)">没有结果</div>';
    res.hidden = false;
  }
  q.addEventListener("input", function () { load(run); });
  q.addEventListener("focus", function () { if (q.value) load(run); });
  q.addEventListener("keydown", function (ev) {
    var items = res.querySelectorAll("a");
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      ev.preventDefault(); sel = Math.max(0, Math.min(items.length - 1, sel + (ev.key === "ArrowDown" ? 1 : -1)));
      items.forEach(function (a, i) { a.classList.toggle("sel", i === sel); });
    } else if (ev.key === "Enter" && items.length) { location.href = items[Math.max(sel, 0)].href; }
    else if (ev.key === "Escape") { res.hidden = true; q.blur(); }
  });
  document.addEventListener("click", function (ev) { if (!ev.target.closest(".search")) res.hidden = true; });
  document.addEventListener("keydown", function (ev) { if (ev.key === "/" && document.activeElement !== q) { ev.preventDefault(); q.focus(); } });
})();
