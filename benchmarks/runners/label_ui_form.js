"use strict";
// The label form, saving, the guidelines panel, keyboard shortcuts and start-up.

function sentence(text) { return text ? text[0].toUpperCase() + text.slice(1) + "." : ""; }
function readOnly() { return ["stale", "invalid"].includes(current.summary.status); }

function stepTool(step) {
  const run = current.trajectory || {}, call = ((run.steps || [])[step] || {}).tool_call;
  return call ? call.name : "?";
}

function labelItem(spec) {
  const name = `item-${items.length}`;
  const defs = definitions(spec.kind);
  const definition = el("p", { class: "definition" });
  const hint = el("p", { class: "hint", role: "note" });
  const fieldset = el("fieldset", { class: "item", tabindex: "-1" }, el("legend", { text: spec.legend }));
  if (spec.claim) {
    fieldset.append(el("button", { type: "button", class: "claim-text", text: spec.claim,
      title: "Search the tool outputs for this claim's key words", onclick: () => searchFor(spec.claim) }));
  }
  const options = spec.options.map((value, i) => {
    const input = el("input", { type: "radio", name, value, checked: spec.get() === value,
      onchange: () => { spec.set(value); changed(); items.forEach((i) => i.update()); } });
    return el("label", { class: "option", title: defs[value] || "" }, input,
      el("span", {}, i < 9 ? el("kbd", { text: String(i + 1) }) : null, value));
  });
  fieldset.append(el("div", { class: "options" }, options), definition, hint);
  const item = { el: fieldset, inputs: options.map((o) => o.querySelector("input")), step: spec.step, spec };
  function update() {
    const value = spec.get();
    fieldset.classList.toggle("unanswered", value === null);
    definition.textContent = value && defs[value] ? `${value}: ${defs[value]}` : "";
    hint.textContent = spec.hint ? spec.hint() : "";
  }
  item.update = update;
  update();
  fieldset.addEventListener("focusin", () => focusItem(items.indexOf(item), false));
  items.push(item);
  return fieldset;
}

function recoveryHint(call) {
  return () => {
    const expected = RECOVERY_VERDICT[call.recovery];
    if (!expected || !call.verdict || call.verdict === expected || call.verdict === "disallowed_tool") return "";
    return `The guidelines pair recovery ${call.recovery} with verdict ${expected}.`;
  };
}

function labelSpecs() {
  const check = current.summary.check, labels = draft.labels;
  if (check === "faithfulness") {
    return labels.claims.map((claim, i) => ({ kind: "faithfulness", legend: `Claim ${i + 1}`, claim: claim.text,
      options: LABELS.faithfulness, get: () => claim.label, set: (v) => { claim.label = v; } }));
  }
  if (check === "tool_use" || check === "recovery") {
    return labels.calls.flatMap((call) => {
      const head = `Step ${call.step} · ${stepTool(call.step)}`;
      const specs = [{ kind: "verdict", legend: check === "recovery" ? `${head}: verdict` : head, step: call.step,
        options: LABELS.verdict, get: () => call.verdict, set: (v) => { call.verdict = v; } }];
      if (check === "recovery") {
        specs.push({ kind: "recovery", legend: `${head}: recovery`, step: call.step, options: LABELS.recovery,
          get: () => call.recovery, set: (v) => { call.recovery = v; }, hint: recoveryHint(call) });
        specs[0].hint = recoveryHint(call);
      }
      return specs;
    });
  }
  return [{ kind: check, legend: "The run", options: LABELS[check] || [],
    get: () => labels.label, set: (v) => { labels.label = v; } }];
}

function formView() {
  items = [];
  const summary = current.summary;
  const section = el("section", { class: "labels", "aria-label": "Your labels" });
  section.append(el("h2", { text: `Your labels: ${CHECK_NAMES[summary.check] || summary.check}` }),
    el("p", { class: "intro", text: INTRO[summary.check] || "" }));
  if (readOnly()) {
    const where = `${state.folder}/${summary.id}.json`;
    const command = `${state.regenerate} --check ${summary.check}` + (summary.split ? ` --split ${summary.split}` : "");
    section.append(el("div", { class: "banner bad", role: "alert" },
      el("strong", { text: summary.status === "stale" ? "Stale, read-only. " : "Can't read this file. " }),
      sentence(summary.reason || ""), " ",
      summary.reason === "the case is no longer in the datasets"
        ? ["Delete ", el("code", { text: where }), "."]
        : ["To label the current run, delete ", el("code", { text: where }), " and run ", el("code", { text: command }), "."]));
  }
  const fields = el("fieldset", { disabled: readOnly() });
  if (draft) {
    fields.append(...labelSpecs().map(labelItem));
    fields.append(labelItem({ kind: "confidence", legend: "Confidence", options: ["high", "medium", "low"],
      get: () => draft.confidence, set: (v) => { draft.confidence = v; } }));
    fields.append(el("label", { class: "check-row" }, el("input", { type: "checkbox", checked: draft.ambiguous,
      onchange: (e) => { draft.ambiguous = e.target.checked; changed(); } }),
    el("span", {}, el("strong", { text: "Ambiguous" }), ": a careful person could reasonably label it either way.")));
    const rationale = el("textarea", { id: "rationale", "aria-describedby": "rationale-help",
      oninput: () => { draft.rationale = rationale.value; changed(); } });
    rationale.value = draft.rationale;
    fields.append(el("label", { class: "field-label", for: "rationale", text: "Rationale" }), rationale,
      el("p", { id: "rationale-help", class: "muted small", text: "One or two sentences on why. Any open question goes here too." }));
  }
  const message = el("p", { id: "save-message", class: "message", role: "status" });
  const errors = el("ul", { id: "save-errors", class: "errors", role: "alert" });
  fields.append(el("div", { class: "save-row" },
    el("button", { type: "button", class: "primary", onclick: save, text: "Save (s)" }),
    el("button", { type: "button", onclick: nextUnfinished, text: "Next unfinished (n)" })), message, errors);
  section.append(fields);
  return section;
}

function changed() { dirty = true; document.title = "• attest labelling"; const m = $("save-message"); if (m) { m.className = "message"; m.textContent = "Unsaved changes."; } }

function focusItem(index, move = true) {
  if (!items.length) return;
  focusIndex = Math.max(0, Math.min(items.length - 1, index));
  items.forEach((item, i) => item.el.classList.toggle("focused", i === focusIndex));
  document.querySelectorAll(".step.linked").forEach((s) => s.classList.remove("linked"));
  const item = items[focusIndex];
  if (item.step !== undefined) {
    const card = $(`step-${item.step}`);
    if (card) { card.classList.add("linked"); if (move) card.scrollIntoView({ block: "nearest" }); }
  }
  if (move) {
    const target = item.inputs.find((i) => i.checked) || item.inputs[0];
    (target || item.el).focus({ preventScroll: true });
    item.el.scrollIntoView({ block: "nearest" });
  }
}

function pick(number) {
  const item = items[focusIndex];
  if (!item || readOnly()) return;
  const input = item.inputs[number - 1];
  if (!input) return;
  input.checked = true; item.spec.set(input.value); changed();
  items.forEach((i) => i.update());
}

async function save() {
  if (!current || !draft || readOnly()) return;
  const result = await api("PUT", `/api/case/${encodeURIComponent(current.summary.id)}`,
    { labels: draft.labels, confidence: draft.confidence, ambiguous: draft.ambiguous, rationale: draft.rationale, version: current.version });
  const errors = (result.data && (result.data.errors || (result.data.error ? [result.data.error] : []))) || [];
  if (!result.ok || !result.data.saved) {
    $("save-errors").replaceChildren(...errors.map((e) => el("li", { text: e })));
    $("save-message").className = "message"; $("save-message").textContent = "Not saved.";
    return;
  }
  dirty = false; document.title = "attest labelling";
  current = result.data.case;
  state.cases = state.cases.map((c) => (c.id === current.summary.id ? current.summary : c));
  refreshChrome();
  const s = current.summary;
  $("save-errors").replaceChildren();
  $("save-message").className = "message ok";
  $("save-message").textContent = s.status === "done" ? "Saved. This case is done."
    : `Saved. Still unfinished: ${s.labelled} of ${s.total} labels given` + (draft.confidence ? "" : ", no confidence")
      + (draft.rationale.trim() ? "." : ", no rationale.");
  document.querySelectorAll(".run-head .badge:last-child").forEach((b) => b.replaceWith(statusBadge(s)));
}

function leaveOk() {
  if (!dirty) return true;
  if (!confirm("You have unsaved changes to this case. Leave without saving?")) return false;
  dirty = false; document.title = "attest labelling";
  return true;
}

async function openCase(id) {
  if (current && current.summary.id === id) return;
  if (!leaveOk()) return;
  const result = await api("GET", `/api/case/${encodeURIComponent(id)}`);
  if (!result.ok) { alert(result.data.error || "Couldn't open the case."); return; }
  current = result.data; view = "case";
  draft = current.labels && typeof current.labels === "object" ? {
    labels: JSON.parse(JSON.stringify(current.labels)), confidence: current.confidence,
    ambiguous: current.ambiguous, rationale: current.rationale,
  } : null;
  history.replaceState(null, "", `#case=${encodeURIComponent(id)}`);
  $("view").replaceChildren(el("div", { class: "case-grid" }, runView(current.trajectory, current.summary), formView()));
  renderList(); renderHelp();
  focusItem(0, false);
}

function nextUnfinished() {
  const check = $("filter-check").value;
  const pool = state.cases.filter((c) => isUnfinished(c) && (check === "all" || c.check === check));
  if (!pool.length) { const m = $("save-message"); if (m) m.textContent = "No unfinished cases left."; return; }
  const at = current ? state.cases.findIndex((c) => c.id === current.summary.id) : -1;
  const next = pool.find((c) => state.cases.indexOf(c) > at && (!current || c.id !== current.summary.id)) || pool[0];
  if (!current || next.id !== current.summary.id) openCase(next.id);
}

// ---------- guidelines ----------
function renderHelp() {
  if (!help || $("help").hidden) return;
  const check = current ? current.summary.check : null;
  const first = { faithfulness: ["Faithfulness"], tool_use: ["Tool use"], recovery: ["Recovery", "Tool use"],
    prompt_injection: ["Prompt injection"], role_adherence: ["Role adherence"] }[check] || [];
  const open = new Set([...first, "General rules", "Rulings log"]);
  const ordered = [...first, "General rules", "Rulings log"].map((t) => help.sections.find((s) => s.title === t)).filter(Boolean);
  for (const s of help.sections) if (!ordered.includes(s)) ordered.push(s);
  $("help-body").replaceChildren(...ordered.map((s) => {
    const body = el("div");
    body.innerHTML = s.html; // escaped server-side from guidelines.md
    return el("details", { open: open.has(s.title) }, el("summary", { text: s.title }), body);
  }));
}

function toggleHelp(show) {
  const panel = $("help");
  panel.hidden = show === undefined ? !panel.hidden : !show;
  $("toggle-help").setAttribute("aria-expanded", String(!panel.hidden));
  if (!panel.hidden) { renderHelp(); $("close-help").focus(); } else $("toggle-help").focus();
}

// ---------- keyboard and start-up ----------
document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); save(); return; }
  const t = e.target;
  const typing = t instanceof HTMLTextAreaElement || t instanceof HTMLSelectElement
    || (t instanceof HTMLInputElement && !["radio", "checkbox"].includes(t.type));
  if (e.key === "Escape") { if (!$("help").hidden) toggleHelp(false); else if (typing) t.blur(); return; }
  if (typing || e.ctrlKey || e.metaKey || e.altKey || $("keys").open) return;
  if (/^[1-9]$/.test(e.key) && view === "case") { e.preventDefault(); pick(Number(e.key)); }
  else if (e.key === "j" && view === "case") { e.preventDefault(); focusItem(focusIndex + 1); }
  else if (e.key === "k" && view === "case") { e.preventDefault(); focusItem(focusIndex - 1); }
  else if (e.key === "n") { e.preventDefault(); nextUnfinished(); }
  else if (e.key === "s") { e.preventDefault(); save(); }
  else if (e.key === "/" && $("search")) { e.preventDefault(); $("search").focus(); }
  else if (e.key === "?") { $("keys").showModal(); }
});

window.addEventListener("beforeunload", (e) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });

async function reloadState() {
  const result = await api("GET", "/api/state");
  if (!result.ok) throw new Error(result.data.error || "couldn't load");
  state = result.data;
  $("who").textContent = `Annotator ${state.annotator}`;
  refreshChrome();
}

async function start() {
  $("filter-check").addEventListener("change", renderList);
  $("filter-status").addEventListener("change", renderList);
  $("show-progress").addEventListener("click", showProgress);
  $("toggle-help").addEventListener("click", () => toggleHelp());
  $("close-help").addEventListener("click", () => toggleHelp(false));
  $("show-keys").addEventListener("click", () => $("keys").showModal());
  try { await reloadState(); } catch (error) {
    $("view").replaceChildren(el("div", { class: "page" }, el("h2", { text: "Can't load your labels" }),
      el("p", { text: String(error.message) + ". Open the link the serve command printed." })));
    return;
  }
  const helpResult = await api("GET", "/api/help");
  if (helpResult.ok) help = helpResult.data;
  const wanted = decodeURIComponent((location.hash.match(/^#case=(.+)$/) || [])[1] || "");
  const first = state.cases.find((c) => c.id === wanted) || state.cases.find(isUnfinished);
  if (first) await openCase(first.id); else showProgress();
}

start();
