// PoE Tracker: canvas tree viewer (Atlas tree, snapshot passive trees) and the
// hover card for items. A tree box is <div class="pt-atlas pt-canvas" data-scene="url">;
// the scene (see ui/tree_scene.py) is fetched and drawn on a canvas, so panning
// and zooming stay smooth with thousands of nodes.
(() => {
  const views = (window.ptViews = window.ptViews || {});
  const esc = (x) => String(x || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  const STYLE = [  // links: not taken, next to your points, yours
    [["rgba(150,130,95,.35)", 10]],
    [["rgba(150,130,95,.55)", 12]],
    [["rgba(226,184,98,.28)", 34], ["#e8c06a", 13]],
  ];

  // ---- the hover card (tree nodes and items share it)
  let tipEl = null, tipKey = null;
  function tip(e, key, title, text, note, colour, base, extra, html) {
    if (!tipEl) { tipEl = document.createElement("div"); tipEl.id = "pt-atlas-tip"; document.body.appendChild(tipEl); }
    if (key !== tipKey) {
      tipKey = key;
      tipEl.classList.toggle("card", !!html);
      if (html) { tipEl.innerHTML = html; tipEl.style.display = "block"; }
      else tipEl.innerHTML = `<b style="${colour ? "color:" + colour : ""}">${esc(title)}</b>` +
        (base ? `<div style="color:#c8c8c8">${esc(base)}</div>` : "") +
        (text ? String(text).split("\n").map((x) => `<div>${esc(x)}</div>`).join("") : "") +
        (extra ? `<div style="color:#4fb3a5">${esc(extra)}</div>` : "") +
        (note ? `<i>${esc(note)}</i>` : "");
      tipEl.style.display = "block";
    }
    const r = tipEl.getBoundingClientRect();
    tipEl.style.left = Math.min(e.clientX + 16, window.innerWidth - r.width - 8) + "px";
    tipEl.style.top = Math.min(e.clientY + 16, window.innerHeight - r.height - 8) + "px";
  }
  function untip() { if (tipEl) tipEl.style.display = "none"; tipKey = null; }
  document.addEventListener("pointermove", (e) => {
    if (e.target.closest && e.target.closest(".pt-canvas")) return;    // the tree does its own
    const g = e.target.closest && e.target.closest(".pt-tipable");
    if (!g) { if (tipKey && !String(tipKey).startsWith("t:")) untip(); return; }
    tip(e, g, g.dataset.n, g.dataset.s, g.dataset.a, g.dataset.c, g.dataset.b, g.dataset.g, g.dataset.tip);
  });

  // ---- the tree viewer
  function mount(box) {
    if (box._pt) return;
    const st = (box._pt = { key: box.dataset.key || box.dataset.scene, sc: null, imgs: [], view: null,
                            W: 0, H: 0, raf: 0, grid: null, pats: {} });
    const cv = document.createElement("canvas");
    cv.className = "pt-cv";
    box.prepend(cv);
    const ctx = cv.getContext("2d");

    const fit = (r) => ({ cx: r[0] + r[2] / 2, cy: r[1] + r[3] / 2,
                          s: Math.min(st.W / r[2], st.H / r[3]) || 0.05 });
    const rect = () => { const v = st.view; return [v.cx - st.W / 2 / v.s, v.cy - st.H / 2 / v.s, st.W / v.s, st.H / v.s]; };
    const save = () => { views[st.key] = rect(); };
    const draw = () => { if (!st.raf) st.raf = requestAnimationFrame(paint); };

    function size() {
      const b = box.getBoundingClientRect(), d = window.devicePixelRatio || 1;
      st.W = b.width; st.H = b.height;
      cv.width = Math.max(1, Math.round(b.width * d)); cv.height = Math.max(1, Math.round(b.height * d));
      cv.style.width = b.width + "px"; cv.style.height = b.height + "px";
      if (st.sc && st.view) draw();
    }

    function layer(list, v) {
      const pad = 200;
      for (const d of list) {
        const im = st.imgs[d[0]];
        if (!im || !im.complete || !im.naturalWidth) continue;
        if (d[5] > v[0] + v[2] + pad || d[5] + d[7] < v[0] - pad || d[6] > v[1] + v[3] + pad || d[6] + d[8] < v[1] - pad) continue;
        ctx.globalAlpha = d[9];
        if (d[10]) {
          ctx.save(); ctx.translate(0, 2 * d[6] + d[8]); ctx.scale(1, -1);
          ctx.drawImage(im, d[1], d[2], d[3], d[4], d[5], d[6], d[7], d[8]);
          ctx.restore();
        } else if (d[3] === 0) {
          ctx.drawImage(im, d[5], d[6], d[7], d[8]);
        } else {
          ctx.drawImage(im, d[1], d[2], d[3], d[4], d[5], d[6], d[7], d[8]);
        }
      }
      ctx.globalAlpha = 1;
    }

    function links(list, s) {
      for (let t = 0; t < 3; t++) {
        for (const [col, w] of STYLE[t]) {
          ctx.beginPath();
          for (const l of list) {
            if (l[0] !== t) continue;
            ctx.moveTo(l[1], l[2]);
            if (l.length > 5) ctx.arc(l[5], l[6], l[7], l[8], l[9], !!l[10]);
            else ctx.lineTo(l[3], l[4]);
          }
          ctx.strokeStyle = col; ctx.lineWidth = Math.max(w, 1.3 / s); ctx.lineCap = "round";
          ctx.stroke();
        }
      }
    }

    function paint() {
      st.raf = 0;
      const sc = st.sc, v = st.view; if (!sc) return;
      const d = window.devicePixelRatio || 1;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.fillStyle = "#07080b"; ctx.fillRect(0, 0, cv.width, cv.height);
      ctx.setTransform(d * v.s, 0, 0, d * v.s, d * (st.W / 2 - v.cx * v.s), d * (st.H / 2 - v.cy * v.s));
      const r = rect();
      const bg = sc.bg, bim = bg && st.imgs[bg.i];
      if (bim && bim.complete && bim.naturalWidth) {
        if (bg.cover) {
          ctx.globalAlpha = bg.a || 1;
          ctx.drawImage(bim, bg.s[0], bg.s[1], bg.s[2], bg.s[3], bg.cover[0], bg.cover[1], bg.cover[2], bg.cover[3]);
          ctx.globalAlpha = 1;
        } else if (bg.tile) {
          if (!st.pats.bg) {
            const oc = document.createElement("canvas"); oc.width = bg.s[2]; oc.height = bg.s[3];
            oc.getContext("2d").drawImage(bim, bg.s[0], bg.s[1], bg.s[2], bg.s[3], 0, 0, bg.s[2], bg.s[3]);
            st.pats.bg = ctx.createPattern(oc, "repeat");
            st.pats.bg.setTransform(new DOMMatrix().scale(bg.tile[0] / bg.s[2], bg.tile[1] / bg.s[3]));
          }
          ctx.fillStyle = st.pats.bg; ctx.fillRect(r[0], r[1], r[2], r[3]);
        }
      }
      for (const [kind, list] of sc.layers) kind === "l" ? links(list, v.s) : layer(list, r);
    }

    // hover: bucket the hit spots so finding the one under the mouse is quick
    function buildGrid() {
      const G = 400, grid = new Map();
      st.sc.hits.forEach((h, i) => {
        const k = Math.floor(h[0] / G) + "," + Math.floor(h[1] / G);
        if (!grid.has(k)) grid.set(k, []);
        grid.get(k).push(i);
      });
      st.grid = grid; st.G = G;
    }
    function hitAt(x, y) {
      const sc = st.sc, G = st.G;
      let lo = 0;
      if (sc.cover && Math.hypot(x - sc.cover[0], y - sc.cover[1]) < sc.cover[2]) lo = sc.cover[3];
      let best = -1, bd = 1e9;
      const gx = Math.floor(x / G), gy = Math.floor(y / G);
      for (let i = -1; i <= 1; i++) for (let j = -1; j <= 1; j++) {
        for (const n of st.grid.get(gx + i + "," + (gy + j)) || []) {
          if (n < lo) continue;
          const h = sc.hits[n], dd = Math.hypot(x - h[0], y - h[1]);
          if (dd < h[2] && dd < bd) { bd = dd; best = n; }
        }
      }
      return best;
    }
    const toTree = (e) => { const b = cv.getBoundingClientRect(), v = st.view;
      return [v.cx + (e.clientX - b.left - st.W / 2) / v.s, v.cy + (e.clientY - b.top - st.H / 2) / v.s]; };
    const zoom = (f, x, y) => {
      const v = st.view, full = st.sc.vb;
      const s = Math.min(Math.max(v.s * f, Math.min(st.W / full[2], st.H / full[3]) * 0.8), 3);
      const k = s / v.s;
      v.cx = x - (x - v.cx) / k; v.cy = y - (y - v.cy) / k; v.s = s;
      save(); draw();
    };

    box.addEventListener("wheel", (e) => {
      if (!st.sc) return;
      e.preventDefault();
      const [x, y] = toTree(e);
      zoom(e.deltaY > 0 ? 1 / 1.2 : 1.2, x, y);
    }, { passive: false });
    let drag = null;
    cv.addEventListener("pointerdown", (e) => {
      if (e.button !== 0 || !st.sc) return;
      drag = { x: e.clientX, y: e.clientY, cx: st.view.cx, cy: st.view.cy };
      cv.setPointerCapture(e.pointerId); cv.classList.add("grab"); untip();
    });
    cv.addEventListener("pointermove", (e) => {
      if (!st.sc) return;
      if (drag) {
        st.view.cx = drag.cx - (e.clientX - drag.x) / st.view.s;
        st.view.cy = drag.cy - (e.clientY - drag.y) / st.view.s;
        draw(); return;
      }
      const [x, y] = toTree(e), n = hitAt(x, y);
      if (n < 0) { untip(); cv.style.cursor = "grab"; return; }
      cv.style.cursor = "help";
      const h = st.sc.hits[n], t = st.sc.tips[h[3]];
      tip(e, "t:" + st.key + ":" + n, t[0], t[1], t[2], t[3]);
    });
    const end = () => { if (drag) { drag = null; cv.classList.remove("grab"); save(); } };
    cv.addEventListener("pointerup", end);
    cv.addEventListener("pointercancel", end);
    cv.addEventListener("pointerleave", () => { if (!drag) untip(); });
    box.addEventListener("click", (e) => {
      const b = e.target.closest("[data-atlas]"); if (!b || !st.sc) return;
      if (b.dataset.atlas === "fit") { st.view = fit(st.sc.vb); save(); draw(); return; }
      zoom(b.dataset.atlas === "in" ? 1.4 : 1 / 1.4, st.view.cx, st.view.cy);
    });
    new ResizeObserver(size).observe(box);
    size();

    fetch(box.dataset.scene).then((r) => r.json()).then((sc) => {
      if (!sc || !sc.vb) { box.insertAdjacentHTML("beforeend", '<div class="pt-tree-msg">No tree in this snapshot.</div>'); return; }
      st.sc = sc;
      st.imgs = sc.img.map((u) => { const im = new Image(); im.onload = draw; im.src = u; return im; });
      st.view = fit(views[st.key] || sc.start || sc.vb);
      buildGrid(); draw();
    }).catch(() => box.insertAdjacentHTML("beforeend", '<div class="pt-tree-msg">Could not load the tree.</div>'));
  }

  // wire up tree boxes as they're added to the page (looking only at what was added)
  const scan = (n) => {
    if (n.nodeType !== 1) return;
    if (n.matches(".pt-canvas[data-scene]")) mount(n);
    else if (n.querySelector) n.querySelectorAll(".pt-canvas[data-scene]").forEach(mount);
  };
  new MutationObserver((muts) => { for (const m of muts) m.addedNodes.forEach(scan); })
    .observe(document.body, { childList: true, subtree: true });
  document.querySelectorAll(".pt-canvas[data-scene]").forEach(mount);

  // tell the tracker when this window is hidden (behind the game, minimised) so it
  // doesn't redraw pages nobody is looking at
  document.addEventListener("visibilitychange", () => emitEvent("pt_vis", document.hidden));
})();

// weapon set I / II on a snapshot's inventory
document.addEventListener("click", (e) => {
  const b = e.target.closest(".pt-swap button"); if (!b) return;
  const gear = b.closest(".pt-geardoll");
  gear.querySelector(".pt-paperdoll").classList.toggle("alt", b.dataset.set === "2");
  gear.querySelectorAll(".pt-swap button").forEach((x) => x.classList.toggle("on", x === b));
});

// character picker: arrows scroll the row; the mouse wheel scrolls it sideways
document.addEventListener("click", (e) => {
  const b = e.target.closest(".pt-cp-arrow"); if (!b) return;
  const row = b.parentElement.querySelector(".pt-cp-row");
  row.scrollBy({ left: Number(b.dataset.cp) * row.clientWidth * 0.8 });
});
// arrows only when the row doesn't fit
const ptFitRows = () => document.querySelectorAll(".pt-charpick").forEach((p) => {
  const row = p.querySelector(".pt-cp-row"); if (!row) return;
  p.classList.toggle("over", row.scrollWidth > row.clientWidth + 2);
});
new MutationObserver(ptFitRows).observe(document.body, { childList: true, subtree: true });
window.addEventListener("resize", ptFitRows);

// sockets on / off on the inventory (remembered in this browser)
const ptSockPref = () => { try { return localStorage.getItem("pt-sockets") !== "0"; } catch (e) { return true; } };
document.addEventListener("change", (e) => {
  const box = e.target.closest(".pt-socktog input"); if (!box) return;
  box.closest(".pt-geardoll").querySelector(".pt-paperdoll").classList.toggle("nosock", !box.checked);
  try { localStorage.setItem("pt-sockets", box.checked ? "1" : "0"); } catch (err) { /* private window */ }
});
new MutationObserver(() => {
  document.querySelectorAll(".pt-geardoll:not([data-sk])").forEach((g) => {
    g.dataset.sk = "1";
    const on = ptSockPref();
    g.querySelector(".pt-paperdoll").classList.toggle("nosock", !on);
    const i = g.querySelector(".pt-socktog input"); if (i) i.checked = on;
  });
}).observe(document.body, { childList: true, subtree: true });

// the build's two columns end flush: the jewels go on the side that leaves the smaller gap,
// then CSS stretches the shorter side's last block (both jewel copies are rendered; one is shown)
const ptJewelSide = () => document.querySelectorAll(".pt-buildgrid").forEach((g) => {
  const cols = g.children; if (cols.length < 2) return;
  g.classList.add("pt-meas");          // natural heights, nothing stretched
  const h = (col) => {
    const top = col.getBoundingClientRect().top; let bot = top;
    for (const c of col.children) {
      if (c.classList.contains("pt-jb") || !c.offsetParent) continue;
      bot = Math.max(bot, c.getBoundingClientRect().bottom);
    }
    return bot - top;
  };
  const L = h(cols[0]), R = h(cols[1]);
  const jb = g.querySelector(".pt-jb-l") || g.querySelector(".pt-jb-r");
  let side = "n";
  if (jb) {
    const vis = [...g.querySelectorAll(".pt-jb-l, .pt-jb-r")].find((x) => x.offsetParent);
    const J = (vis ? vis.getBoundingClientRect().height : 0) + 12;
    // on the right only if they fit there whole (their panel stretches to the bottom); otherwise on the
    // left, and the skill cards spread out to meet them. The gear stats never have to stretch.
    side = R + J <= L ? "r" : "l";
  }
  g.classList.remove("pt-meas");
  if (g.dataset.jw !== side) g.dataset.jw = side;
});
let ptJwT = 0;
const ptJwSoon = () => { clearTimeout(ptJwT); ptJwT = setTimeout(ptJewelSide, 60); };
new MutationObserver((ms) => { if (ms.some((m) => m.type === "childList")) ptJwSoon(); })
  .observe(document.body, { childList: true, subtree: true });
window.addEventListener("resize", ptJwSoon);
