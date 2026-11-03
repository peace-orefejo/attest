"use strict";
// Every piece of run text is shown through textContent, never as HTML: runs hold untrusted text.
const TOKEN = new URLSearchParams(location.search).get("token") || "";
const CHECK_NAMES = {
  faithfulness: "Faithfulness", tool_use: "Tool use", recovery: "Recovery",
  prompt_injection: "Prompt injection", role_adherence: "Role adherence",
};
const LABELS = {
  faithfulness: ["supported", "unsupported", "unverifiable"],
  verdict: ["disallowed_tool", "error_claimed_success", "error_silent", "incorrect", "correct"],
  recovery: ["none", "retried", "fallback", "acknowledged", "silent", "claimed_success"],
  prompt_injection: ["none", "payload", "compromised"],
  role_adherence: ["in_scope", "appropriately_refused", "out_of_scope_complied"],
};
const DEFINITION_SECTION = {
  faithfulness: "Faithfulness", verdict: "Tool use", recovery: "Recovery",
  prompt_injection: "Prompt injection", role_adherence: "Role adherence",
};
const INTRO = {
  faithfulness: "Label each claim against the tool outputs and artifacts only. Click a claim to search the outputs for its key words.",
  tool_use: "One verdict per tool call. Apply the first label that fits, in this order.",
  recovery: "For each call, a verdict (first that fits, in this order) and what happened after it.",
  prompt_injection: "One label for the whole run.",
  role_adherence: "One label for the whole run, judged against the system prompt.",
};
const RECOVERY_VERDICT = {
  retried: "correct", fallback: "correct", acknowledged: "correct",
  silent: "error_silent", claimed_success: "error_claimed_success",
};
const STATUS_TEXT = { blank: "Blank", partial: "Partly done", done: "Done", stale: "Stale", invalid: "Can't read" };
const STATUS_FILTERS = [
  ["all", "All"], ["unfinished", "Not done yet"], ["blank", "Blank"], ["partial", "Partly done"],
  ["done", "Done"], ["ambiguous", "Ambiguous"], ["stale", "Stale or unreadable"],
];
const STOPWORDS = new Set(("the a an and or of to in on at for is are was were be been it its this that " +
  "with by from as has have had will would can could not no but if then than so into about " +
  "which who whom what when where while there their they them he she his her you your our we").split(" "));

const $ = (id) => document.getElementById(id);
let state = null, help = null, current = null, draft = null, dirty = false;
let items = [], focusIndex = 0, marks = [], markIndex = -1, view = "progress";
let searchables = [];

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

async function api(method, path, body) {
  const response = await fetch(path, {
    method, headers: { "X-Attest-Token": TOKEN, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = null;
  try { data = await response.json(); } catch (_) { data = { error: "unreadable response" }; }
  return { ok: response.ok, status: response.status, data };
}

function badge(text, kind) { return el("span", { class: "badge " + (kind || ""), text }); }
function statusBadge(summary) {
  const text = summary.status === "partial"
    ? `Partly done ${summary.labelled}/${summary.total}` : STATUS_TEXT[summary.status];
  return badge(text, summary.status);
}
function isUnfinished(s) { return s.status === "blank" || s.status === "partial"; }
function definitions(kind) {
  const section = help && help.sections.find((s) => s.title === DEFINITION_SECTION[kind]);
  return section ? section.definitions : {};
}

// ---------- sidebar and progress ----------
function counts(cases) {
  const out = { done: 0, partial: 0, blank: 0, stale: 0, total: cases.length };
  for (const c of cases) out[c.status === "invalid" ? "stale" : c.status] += 1;
  return out;
}

function renderProgress() {
  const c = counts(state.cases);
  const width = (n) => (c.total ? (100 * n) / c.total : 0) + "%";
  const bar = el("span", { class: "bar", role: "img",
    "aria-label": `${c.done} of ${c.total} done` });
  const done = el("span", { class: "b-done" }), partial = el("span", { class: "b-partial" });
  done.style.width = width(c.done); partial.style.width = width(c.partial);
  bar.append(done, partial);
  $("progress").replaceChildren(bar, el("span", {},
    `${c.done} of ${c.total} done · ${c.partial} partly done · ${c.blank} blank`
    + (c.stale ? ` · ${c.stale} stale` : "")));
}

function renderFilters() {
  const checks = [...new Set(state.cases.map((c) => c.check))].sort();
  const checkSelect = $("filter-check"), statusSelect = $("filter-status");
  const chosen = checkSelect.value || "all";
  checkSelect.replaceChildren(el("option", { value: "all", text: "All checks" }),
    ...checks.map((c) => el("option", { value: c, text: CHECK_NAMES[c] || c })));
  checkSelect.value = checks.includes(chosen) ? chosen : "all";
  if (!statusSelect.options.length) {
    statusSelect.append(...STATUS_FILTERS.map(([value, text]) => el("option", { value, text })));
  }
}

function matchesFilter(c) {
  const check = $("filter-check").value, status = $("filter-status").value;
  if (check !== "all" && c.check !== check) return false;
  if (status === "all") return true;
  if (status === "unfinished") return isUnfinished(c);
  if (status === "ambiguous") return c.ambiguous;
  if (status === "stale") return c.status === "stale" || c.status === "invalid";
  return c.status === status;
}

function renderList() {
  const shown = state.cases.filter(matchesFilter);
  $("list-count").textContent = `${shown.length} of ${state.cases.length} cases shown`;
  $("case-list").replaceChildren(...shown.map((c) => el("li", {}, el("button", {
    type: "button", class: "case-item", "aria-current": current && current.summary.id === c.id ? "true" : "false",
    onclick: () => openCase(c.id),
  }, el("span", { class: "case-id", text: c.id }), el("span", { class: "case-meta" },
    CHECK_NAMES[c.check] || c.check, " · ", c.split || "no split", statusBadge(c),
    c.ambiguous ? badge("Ambiguous", "ambiguous") : null)))));
}

function refreshChrome() { renderProgress(); renderFilters(); renderList(); }

// ---------- progress view and creating label files ----------
function showProgress() {
  if (!leaveOk()) return;
  current = null; draft = null; view = "progress"; items = [];
  const page = el("div", { class: "page" });
  page.append(el("h2", { text: `Your labels: ${state.annotator}` }),
    el("p", { class: "muted", text: `Folder: ${state.folder}. Only this folder is read or written. ` +
      "Nothing leaves your machine, and other annotators' labels, the case files' draft labels " +
      "and notes, and attest's output are never shown." }));
  if (state.cases.length) {
    page.append(progressTable(), el("p", { class: "muted small", text:
      "Agreement is not shown here. Once both annotators are done, run annotate.py agreement on the command line." }));
  } else {
    page.append(el("p", { text: "You have no label files yet. Create blank ones to start labelling." }));
  }
  page.append(createForm());
  $("view").replaceChildren(page);
  renderList();
}

function progressTable() {
  const rows = [];
  const groups = {};
  for (const c of state.cases) (groups[`${c.check}|${c.split || "-"}`] ||= []).push(c);
  for (const key of Object.keys(groups).sort()) {
    const [check, split] = key.split("|"), n = counts(groups[key]);
    rows.push(el("tr", {}, el("td", { text: CHECK_NAMES[check] || check }), el("td", { text: split }),
      ...[n.done, n.partial, n.blank, n.stale, n.total].map((v) => el("td", { class: "num", text: v }))));
  }
  const n = counts(state.cases);
  rows.push(el("tr", {}, el("th", { scope: "row", text: "All" }), el("td"),
    ...[n.done, n.partial, n.blank, n.stale, n.total].map((v) => el("td", { class: "num", text: v }))));
  const head = ["Check", "Split", "Done", "Partly done", "Blank", "Stale", "Total"];
  return el("table", {}, el("caption", { class: "muted small", text: "Your progress (read-only)" }),
    el("thead", {}, el("tr", {}, head.map((h, i) => el("th", { scope: "col", class: i > 1 ? "num" : null, text: h })))),
    el("tbody", {}, rows));
}

function createForm() {
  const message = el("p", { class: "message", role: "status" });
  const box = (name, value, checked, text) => el("label", {},
    el("input", { type: "checkbox", name, value, checked }), " ", text);
  const checks = Object.keys(state.available);
  const total = (check) => Object.values(state.available[check] || {}).reduce((a, b) => a + b, 0);
  const form = el("form", { class: "create", onsubmit: async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const result = await api("POST", "/api/templates", { checks: data.getAll("check"), splits: data.getAll("split") });
    if (!result.ok) { message.className = "message errors"; message.textContent = result.data.error; return; }
    const r = result.data;
    message.className = "message ok";
    message.textContent = `Wrote ${r.written} blank label file(s); kept ${r.kept} already there.` +
      (r.stale.length ? ` ${r.stale.length} existing file(s) are stale; they are listed as Stale.` : "");
    await reloadState(); showProgress();
  } },
  el("h3", { text: state.cases.length ? "Add more label files" : "Create blank label files" }),
  el("p", { class: "muted small", text: "Uses the same logic as annotate.py template: existing files are kept." }),
  el("fieldset", {}, el("legend", { text: "Checks" }),
    checks.map((c) => box("check", c, true, `${CHECK_NAMES[c] || c} (${total(c)})`))),
  el("fieldset", {}, el("legend", { text: "Splits" }),
    ["dev", "validation", "heldout"].map((s) => box("split", s, s === "dev", s))),
  el("div", {}, el("button", { type: "submit", class: "primary", text: "Create blank label files" })),
  message);
  return form;
}

// ---------- the run ----------
function searchable(node, text) { node.textContent = text; searchables.push({ node, text }); return node; }

function codeBlock(text, isEvidence) {
  const pre = el("pre", { class: "code" });
  if (isEvidence) searchable(pre, text); else pre.textContent = text;
  const lines = text.split("\n").length;
  const copy = el("button", { type: "button", class: "small", text: "Copy", onclick: async () => {
    try { await navigator.clipboard.writeText(text); copy.textContent = "Copied"; }
    catch (_) { copy.textContent = "Copy failed"; }
    setTimeout(() => { copy.textContent = "Copy"; }, 1200);
  } });
  if (text.length <= 1200 && lines <= 18) return { block: pre, tools: [copy] };
  const wrap = el("div", { class: "clamp closed" }, pre);
  const toggle = el("button", { type: "button", class: "small", "aria-expanded": "false",
    text: `Show all ${lines} lines`, onclick: () => setClamp(wrap, wrap.classList.contains("closed")) });
  wrap.toggle = toggle;
  return { block: wrap, tools: [toggle, copy] };
}

function setClamp(wrap, open) {
  wrap.classList.toggle("closed", !open);
  wrap.toggle.setAttribute("aria-expanded", String(open));
  wrap.toggle.textContent = open ? "Show less" : "Show all";
}

function artifactView(artifact) {
  const name = artifact.name || artifact.id || "artifact";
  const head = el("div", { class: "step-head" }, el("strong", { text: name }),
    artifact.media_type ? badge(artifact.media_type) : null,
    artifact.source === "user_upload" ? badge("User upload: not evidence", "partial") : null);
  let body;
  if (typeof artifact.text === "string") {
    const code = codeBlock(artifact.text, artifact.source !== "user_upload");
    body = [el("div", { class: "label-row" }, "Text", ...code.tools), code.block];
  } else if (artifact.path) {
    body = [el("p", { class: "muted small", text: `File at ${artifact.path} (not opened here).` })];
  } else {
    body = [el("p", { class: "muted small", text: "Binary content (base64), not shown." })];
  }
  return el("div", { class: "artifact" }, head, body);
}

function stepView(step, index) {
  const card = el("section", { class: "card step", id: `step-${index}`, "aria-label": `Step ${index}` });
  const call = step.tool_call;
  card.append(el("div", { class: "step-head" }, el("span", { class: "step-no", text: `Step ${index}` }),
    call ? el("span", { class: "tool-name", text: call.name }) : el("span", { class: "muted", text: "no tool call" }),
    call && call.is_error === true ? badge("is_error: true", "error") : null,
    call && call.is_error === false ? badge("is_error: false") : null));
  if (step.thought) {
    card.append(el("div", { class: "thought" }, el("span", { class: "tag", text: "Thought (not evidence)" }),
      el("p", { class: "prose", text: step.thought })));
  }
  if (!call) return card;
  const args = codeBlock(JSON.stringify(call.arguments || {}, null, 2), false);
  card.append(el("div", { class: "label-row" }, "Arguments", ...args.tools), args.block);
  if (call.output) {
    const out = codeBlock(call.output, true);
    card.append(el("div", { class: "label-row" }, "Output", ...out.tools), out.block);
  } else {
    card.append(el("div", { class: "label-row", text: "Output" }),
      el("p", { class: "empty-output", text: "No output recorded." }));
  }
  if (call.artifacts && call.artifacts.length) {
    card.append(el("div", { class: "label-row", text: "Artifacts" }), ...call.artifacts.map(artifactView));
  }
  return card;
}

function runView(run, summary) {
  searchables = [];
  const article = el("article", { class: "run", "aria-label": "The run" });
  article.append(el("div", { class: "run-head" }, el("h2", { text: summary.id }),
    badge(CHECK_NAMES[summary.check] || summary.check), summary.split ? badge(summary.split) : null,
    statusBadge(summary)));
  if (!run) { article.append(el("p", { class: "muted", text: "This file holds no readable run." })); return article; }
  const input = el("input", { type: "search", id: "search", placeholder: "Words to find, such as 182 DHL",
    oninput: () => runSearch(input.value), onkeydown: (e) => { if (e.key === "Enter") { e.preventDefault(); stepMark(e.shiftKey ? -1 : 1); } } });
  article.append(el("div", { class: "search", role: "search" },
    el("label", { for: "search", text: "Search tool outputs and artifacts" }), input,
    el("span", { id: "search-count", class: "muted small", "aria-live": "polite" }),
    el("button", { type: "button", text: "Previous", onclick: () => stepMark(-1) }),
    el("button", { type: "button", text: "Next", onclick: () => stepMark(1) })));
  article.append(el("section", { class: "card" }, el("h3", { text: "Task" }), el("p", { class: "prose", text: run.task })));
  const context = el("section", { class: "card" });
  if (run.system_prompt) {
    context.append(el("details", {}, el("summary", { text: "System prompt" }),
      el("p", { class: "prose", text: run.system_prompt })));
  } else context.append(el("p", { class: "muted small", text: "No system prompt." }));
  context.append(el("div", { class: "label-row", text: "Allowed tools" }), Array.isArray(run.allowed_tools)
    ? el("div", { class: "tools" }, run.allowed_tools.length ? run.allowed_tools.map((t) => el("code", { text: t })) : "none")
    : el("p", { class: "muted small", text: "No allowed_tools list: no call is disallowed." }));
  const fallbacks = Object.entries(run.tool_fallbacks || {});
  if (fallbacks.length) {
    context.append(el("div", { class: "label-row", text: "Declared fallbacks" }),
      el("ul", {}, fallbacks.map(([tool, backups]) => el("li", {}, el("code", { text: tool }), " → ", backups.join(", ")))));
  }
  article.append(context);
  (run.steps || []).forEach((step, index) => article.append(stepView(step, index)));
  if (run.artifacts && run.artifacts.length) {
    article.append(el("section", { class: "card" }, el("h3", { text: "Run artifacts" }), run.artifacts.map(artifactView)));
  }
  article.append(el("section", { class: "card answer" }, el("h3", { text: "Final answer" }),
    el("p", { class: "prose", text: run.final_answer })));
  return article;
}

// ---------- search ----------
function keyWords(text) {
  const words = text.match(/[\p{L}\p{N}][\p{L}\p{N}.,:/'-]*[\p{L}\p{N}]|\p{N}/gu) || [];
  return [...new Set(words.filter((w) => /\p{N}/u.test(w) || (w.length > 2 && !STOPWORDS.has(w.toLowerCase()))))];
}

function runSearch(query) {
  const words = query.match(/"[^"]+"|\S+/g) || [];
  const terms = words.map((w) => w.replace(/^"|"$/g, "")).filter((w) => w.length > 0);
  const pattern = terms.length ? new RegExp(terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|"), "gi") : null;
  marks = [];
  for (const { node, text } of searchables) {
    if (!pattern) { node.textContent = text; continue; }
    const parts = []; let last = 0;
    for (const match of text.matchAll(pattern)) {
      if (!match[0]) continue;
      parts.push(text.slice(last, match.index));
      const mark = el("mark", { text: match[0] }); parts.push(mark); marks.push(mark);
      last = match.index + match[0].length;
    }
    parts.push(text.slice(last));
    node.replaceChildren(...parts);
    const wrap = node.closest(".clamp");
    if (wrap && node.querySelector("mark")) setClamp(wrap, true);
  }
  markIndex = -1;
  const count = $("search-count");
  if (count) count.textContent = pattern ? `${marks.length} match${marks.length === 1 ? "" : "es"}` : "";
  if (marks.length) stepMark(1);
}

function stepMark(direction) {
  if (!marks.length) return;
  if (marks[markIndex]) marks[markIndex].classList.remove("current");
  markIndex = (markIndex + direction + marks.length) % marks.length;
  marks[markIndex].classList.add("current");
  marks[markIndex].scrollIntoView({ block: "center" });
  $("search-count").textContent = `${markIndex + 1} of ${marks.length} matches`;
}

function searchFor(text) {
  const input = $("search"); if (!input) return;
  input.value = keyWords(text).join(" ");
  runSearch(input.value);
}
