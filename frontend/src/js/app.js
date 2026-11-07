import { initTheme } from "./theme.js";
import { initDialogs, initDrawer } from "./modal.js";
initTheme(document.querySelector("#theme-btn"));
let toastTimeout;
function notify(message) {
  const toast = document.querySelector("#toast");
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => (toast.hidden = true), 3500);
}
initDialogs(notify);
initDrawer(notify);
const sidebar = document.querySelector("#sidebar"),
  overlay = document.querySelector("#overlay"),
  menu = document.querySelector("#menu-btn");
function toggleMenu(force) {
  const opened =
    typeof force === "boolean" ? force : !sidebar.classList.contains("is-open");
  sidebar.classList.toggle("is-open", opened);
  overlay.classList.toggle("is-open", opened);
  menu.setAttribute("aria-expanded", String(opened));
  if (!opened) menu.focus();
}
menu.addEventListener("click", () => toggleMenu());
overlay.addEventListener("click", () => toggleMenu(false));
sidebar.querySelectorAll("a").forEach((a) =>
  a.addEventListener("click", () => {
    if (innerWidth < 768) toggleMenu(false);
  }),
);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && sidebar.classList.contains("is-open"))
    toggleMenu(false);
});
document
  .querySelector("#settings-btn")
  .addEventListener("click", () =>
    notify("Settings page is outside PBI-004 scope."),
  );
document
  .querySelector("#scope-btn")
  .addEventListener("click", () =>
    notify("Scope is demo data; API integration belongs to feature PBIs."),
  );
document
  .querySelector("#inspect-btn")
  .addEventListener("click", () =>
    notify("Deep Scan API is not connected in this demo."),
  );
const axes = [
  "Distributed Systems",
  "Concurrency",
  "Observability",
  "System Design",
  "Kernel & eBPF",
  "Testing / Chaos",
  "API Architecture",
  "Code Velocity",
];
const datasets = {
  combined: [96, 91, 82, 88, 94, 84, 90, 89],
  public: [94, 88, 79, 85, 91, 86, 89, 90],
  private: [91, 93, 86, 89, 90, 78, 84, 82],
};
const target = [91, 89, 87, 92, 90, 87, 88, 85];
let active = 0;
function point(i, value) {
  const angle = -Math.PI / 2 + (i * Math.PI) / 4;
  return [
    290 + Math.cos(angle) * value * 1.67,
    225 + Math.sin(angle) * value * 1.67,
  ];
}
function points(values) {
  return values.map((v, i) => point(i, v).join(",")).join(" ");
}
function svg(tag, attributes, text) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attributes).forEach(([key, val]) =>
    el.setAttribute(key, String(val)),
  );
  if (text !== undefined) el.textContent = text;
  return el;
}
function renderRadar(scope = "combined") {
  const root = document.querySelector("#radar");
  root.replaceChildren();
  [20, 40, 60, 80, 100].forEach((level) =>
    root.append(
      svg("polygon", {
        points: points(Array(8).fill(level)),
        class: "grid-line",
      }),
    ),
  );
  axes.forEach((name, i) => {
    const [x, y] = point(i, 100);
    root.append(svg("line", { x1: 290, y1: 225, x2: x, y2: y, class: "axis" }));
  });
  root.append(svg("polygon", { points: points(target), class: "target" }));
  root.append(
    svg("polygon", { points: points(datasets[scope]), class: "actual" }),
  );
  axes.forEach((name, i) => {
    const [x, y] = point(i, datasets[scope][i]),
      [lx, ly] = point(i, 116);
    const circle = svg("circle", {
      cx: x,
      cy: y,
      r: active === i ? 7 : 5,
      class: "point axis-button",
      tabindex: 0,
      role: "button",
      "aria-label": `${name}: ${datasets[scope][i]} out of 100`,
    });
    circle.addEventListener("click", () => selectAxis(i, scope));
    circle.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectAxis(i, scope);
      }
    });
    root.append(circle);
    const anchor =
      Math.abs(lx - 290) < 30 ? "middle" : lx > 290 ? "start" : "end";
    root.append(
      svg(
        "text",
        { x: lx, y: ly, "text-anchor": anchor },
        `${name} (${datasets[scope][i]}%)`,
      ),
    );
  });
  document.querySelector("#axis-id").textContent =
    `AXIS_${String(active + 1).padStart(2, "0")}`;
  document.querySelector("#axis-name").textContent =
    `${axes[active]} — ${datasets[scope][active]}/100`;
  document.querySelector("#axis-description").textContent =
    `Verified competency evidence for ${axes[active]}; this screen uses illustrative fixture data, not a live AST analysis.`;
}
function selectAxis(i, scope) {
  active = i;
  renderRadar(scope);
}
let scope = "combined";
document.querySelectorAll("[data-scope]").forEach((btn) =>
  btn.addEventListener("click", () => {
    scope = btn.dataset.scope;
    document
      .querySelectorAll("[data-scope]")
      .forEach((el) => el.setAttribute("aria-pressed", String(el === btn)));
    renderRadar(scope);
  }),
);
renderRadar();
document.querySelector("#export-btn").addEventListener("click", () => {
  const data = {
    source: "PBI-004 fixture (not real GitHub evidence)",
    scope,
    axes: axes.map((name, i) => ({
      name,
      score: datasets[scope][i],
      target: target[i],
    })),
  };
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = "competency-demo.json";
  a.click();
  URL.revokeObjectURL(url);
});
const repos = [
  {
    name: "raft-consensus-core",
    desc: "Production-grade Raft consensus implementation with snapshot replication.",
    lang: "Go 1.22",
    commits: "1,820",
    kind: "public",
  },
  {
    name: "ebpf-mesh-proxy",
    desc: "Kernel-level L7 proxy hook using eBPF sockops for zero-copy mesh.",
    lang: "C / eBPF",
    commits: "640",
    kind: "private",
  },
  {
    name: "event-stream-cdc",
    desc: "Postgres logical replication decoder streaming binary WAL changefeeds.",
    lang: "Rust",
    commits: "1,104",
    kind: "public",
  },
];
let repoKind = "all";
const grid = document.querySelector("#repo-grid");
function renderRepos() {
  const term = document
    .querySelector("#repo-search")
    .value.trim()
    .toLowerCase();
  const filtered = repos.filter(
    (r) =>
      (repoKind === "all" || r.kind === repoKind) &&
      `${r.name} ${r.desc} ${r.lang}`.toLowerCase().includes(term),
  );
  grid.replaceChildren();
  for (const r of filtered) {
    const card = document.createElement("article");
    card.className = "repo-card";
    const title = document.createElement("h3");
    title.textContent = r.name;
    const badge = document.createElement("span");
    badge.className = `badge ${r.kind === "public" ? "badge--success" : ""}`;
    badge.textContent = r.kind.toUpperCase();
    const desc = document.createElement("p");
    desc.textContent = r.desc;
    const foot = document.createElement("footer");
    const left = document.createElement("span");
    left.textContent = r.lang;
    const right = document.createElement("span");
    right.textContent = `${r.commits} commits`;
    foot.append(left, right);
    card.append(title, badge, desc, foot);
    grid.append(card);
  }
  document.querySelector("#repo-empty").hidden = filtered.length !== 0;
}
document.querySelector("#repo-search").addEventListener("input", renderRepos);
document.querySelector("#filter-btn").addEventListener("click", (event) => {
  repoKind =
    repoKind === "all" ? "public" : repoKind === "public" ? "private" : "all";
  event.currentTarget.textContent = `Filter: ${repoKind[0].toUpperCase() + repoKind.slice(1)}`;
  renderRepos();
});
renderRepos();
