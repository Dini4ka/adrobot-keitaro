/* Adrobot wrapper — фронт без сборки: vanilla JS + fetch к своему API. */
"use strict";

const $ = (sel) => document.querySelector(sel);
const errorBox = $("#error-box");

let catalog = [];

function showError(text) {
  errorBox.textContent = text;
  errorBox.classList.remove("hidden");
}
function clearError() {
  errorBox.classList.add("hidden");
}

async function api(path, options) {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const body = await resp.json();
      if (body.detail && typeof body.detail === "object") detail = body.detail.message || detail;
      else if (body.detail) detail = body.detail;
    } catch (_) { /* ignore */ }
    throw new Error(detail);
  }
  return resp.json();
}

/* ---------- каталог офферов ---------- */

async function loadCatalog() {
  catalog = await api("/api/catalog");
}

function filterOffers(query) {
  const q = query.trim().toLowerCase();
  const byName = [], byId = [];
  for (const item of catalog) {
    if (!q) { byName.push(item); continue; }
    if (String(item.offer_id).startsWith(q)) byId.push(item);
    else if (item.name.toLowerCase().includes(q)) byName.push(item);
  }
  return [...byId, ...byName].slice(0, 8);
}

/* ---------- автокомплит офферов ---------- */

function attachAutocomplete(input, suggest, onPick) {
  let picked = null;

  function render(items) {
    suggest.innerHTML = "";
    if (!items.length) {
      const div = document.createElement("div");
      div.className = "muted";
      div.textContent = "Ничего не найдено";
      suggest.appendChild(div);
      suggest.classList.remove("hidden");
      return;
    }
    for (const item of items) {
      const div = document.createElement("div");
      div.textContent = `${item.offer_id} · ${item.name}`;
      div.addEventListener("mousedown", (e) => {
        e.preventDefault();
        choose(item);
      });
      suggest.appendChild(div);
    }
    suggest.classList.remove("hidden");
  }

  function choose(item) {
    picked = item;
    input.value = `${item.offer_id} · ${item.name}`;
    input.dataset.offerId = item.offer_id;
    suggest.classList.add("hidden");
    onPick(item);
  }

  input.addEventListener("input", () => {
    picked = null;
    delete input.dataset.offerId;
    onPick(null);
    render(filterOffers(input.value));
  });
  input.addEventListener("focus", () => {
    if (input.dataset.offerId) return;
    render(filterOffers(input.value));
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !suggest.classList.contains("hidden")) {
      e.preventDefault();
      const first = suggest.querySelector("div:not(.muted)");
      if (first) first.click();
    }
  });
  document.addEventListener("click", (e) => {
    if (!input.contains(e.target) && !suggest.contains(e.target)) suggest.classList.add("hidden");
  });
  input.addEventListener("blur", () => setTimeout(() => suggest.classList.add("hidden"), 150));
}

/* ---------- доли: сумма всегда 100, остаток первым ---------- */

function normalizeShares(offerIds) {
  if (!offerIds.length) return [];
  const base = Math.floor(100 / offerIds.length);
  const remainder = 100 % offerIds.length;
  return offerIds.map((id, index) => ({
    offer_id: id,
    share: base + (index < remainder ? 1 : 0),
    state: "active",
  }));
}

/* ---------- создаватор ---------- */

async function submitCreate(e) {
  e.preventDefault();
  clearError();
  const offerId = Number($("#f-offer").dataset.offerId);
  if (!offerId) {
    showError("Выберите оффер из списка подсказок.");
    return;
  }
  const btn = $("#btn-create");
  btn.disabled = true;
  btn.textContent = "Создаю…";
  try {
    const result = await api("/api/campaigns", {
      method: "POST",
      body: JSON.stringify({
        name: $("#f-name").value,
        geo: $("#f-geo").value,
        offer_id: offerId,
      }),
    });
    renderCreateResult(result);
  } catch (err) {
    showError(String(err.message || err));
  } finally {
    btn.disabled = false;
    btn.textContent = "Создать в Keitaro";
  }
}

function renderCreateResult(result) {
  $("#create-result").classList.remove("hidden");
  const tbody = $("#create-result-table");
  const rows = [
    ["Кампания", `${result.id} · ${result.name}`],
    ["Гео", result.geo],
    ["Домен", `${result.domain.id} · ${result.domain.name}`],
    ["Группа", `${result.group.id} · ${result.group.name}`],
    ["Источник", `${result.source.id} · ${result.source.name}`],
  ];
  for (const stream of result.streams) {
    rows.push([
      `Поток ${stream.position ?? ""}`,
      `${stream.id} · ${stream.name} (${stream.schema}, ${stream.type})`,
    ]);
  }
  tbody.innerHTML = rows
    .map(([k, v]) => `<tr><td style="color:var(--muted);width:140px">${k}</td><td>${v}</td></tr>`)
    .join("");
  const link = $("#create-admin-link");
  link.href = result.admin_url;
  link.textContent = `Открыть кампанию в админке Keitaro (${result.id})`;
}

/* ---------- редактор ---------- */

let editorCampaign = null;

async function loadCampaignList() {
  const campaigns = await api("/api/campaigns");
  const sel = $("#sel-campaign");
  sel.innerHTML = campaigns
    .map((c) => `<option value="${c.id}">${c.id} · ${c.name}</option>`)
    .join("");
  if (!campaigns.length) {
    $("#editor-body").innerHTML = '<div class="empty">Кампаний на стенде нет. Сначала создайте одну.</div>';
    return;
  }
  loadEditor(campaigns[0].id);
}

async function loadEditor(campaignId) {
  clearError();
  try {
    editorCampaign = await api(`/api/campaigns/${campaignId}`);
    renderEditor();
  } catch (err) {
    showError(String(err.message || err));
  }
}

function renderEditor() {
  const body = $("#editor-body");
  const c = editorCampaign;
  const parts = [
    `<div class="stream-head" style="margin-top:14px">
       <div><span class="flow-badge">${c.name}</span>
         <div class="meta">домен ${c.domain_id ?? "—"} · группа ${c.group_id ?? "—"} · источник ${c.traffic_source_id ?? "—"}</div>
       </div>
       <a class="btn ghost small" target="_blank" rel="noopener"
          href="${c.admin_url || "#"}">Открыть в Keitaro</a>
     </div>`,
  ];
  for (const stream of c.streams) {
    if (stream.is_offer_stream) parts.push(renderOfferStream(stream));
    else parts.push(renderGeoStream(stream));
  }
  body.innerHTML = parts.join("");
}

function renderGeoStream(stream) {
  const filters = (stream.filters || [])
    .map((f) => `${f.name} ${f.mode} [${(f.payload || []).join(", ")}]`)
    .join("; ");
  return `
    <div class="stream-card">
      <div class="stream-head">
        <div>
          <span class="stream-name">${stream.name}</span>
          <span class="pill">${stream.schema} · ${stream.type}</span>
        </div>
      </div>
      <div class="meta">Действие: ${stream.action_type || "—"} ${stream.action_payload || ""}</div>
      ${filters ? `<div class="filters">Фильтр: ${filters}</div>` : ""}
      <div class="empty" style="padding:8px 0 0">Редирект по гео, офферов нет</div>
    </div>`;
}

function renderOfferStream(stream) {
  const offers = stream.offers || [];
  const sum = offers.reduce((acc, o) => acc + o.share, 0);
  const rows = offers
    .map(
      (o) => `
      <tr>
        <td>${o.offer_id}</td>
        <td>${o.name}</td>
        <td class="num">${o.share}%</td>
        <td class="num" style="width:110px">
          <button class="btn danger small" data-remove="${o.offer_id}">Удалить</button>
        </td>
      </tr>`,
    )
    .join("");
  return `
    <div class="stream-card" data-stream-id="${stream.id}" data-stream-name="${stream.name}">
      <div class="stream-head">
        <div>
          <span class="stream-name">${stream.name}</span>
          <span class="pill ok">офферный поток</span>
        </div>
        <div>
          <span class="pill ${sum === 100 ? "ok" : "warn"}" id="sum-${stream.id}">сумма ${sum}%</span>
          <button class="btn small" data-save="${stream.id}" ${sum !== 100 ? "disabled" : ""}>Сохранить в Keitaro</button>
        </div>
      </div>
      <table class="grid">
        <thead><tr><th style="width:70px">ID</th><th>Оффер</th><th class="num" style="width:90px">Доля</th><th></th></tr></thead>
        <tbody>${rows || '<tr><td colspan="4" class="empty">В потоке нет офферов</td></tr>'}</tbody>
      </table>
      <div class="add-row">
        <div class="autocomplete">
          <input type="text" placeholder="поиск оффера по имени или id…" autocomplete="off"
                 data-stream-add="${stream.id}">
          <div class="suggest hidden"></div>
        </div>
        <button class="btn primary small" data-add="${stream.id}">Добавить</button>
      </div>
    </div>`;
}

/* локальное перераспределение долей в состоянии редактора */
function streamOffers(streamId) {
  const stream = editorCampaign.streams.find((s) => s.id === streamId);
  return stream ? stream.offers : [];
}

function setStreamOffers(streamId, offers) {
  const stream = editorCampaign.streams.find((s) => s.id === streamId);
  stream.offers = offers;
  renderEditor();
}

function rebalanceAfter(streamId, ids) {
  const shares = normalizeShares(ids);
  const names = {};
  for (const o of streamOffers(streamId)) names[o.offer_id] = o.name;
  return shares.map((b) => ({ ...b, name: names[b.offer_id] || `оффер ${b.offer_id}` }));
}

function onRemoveOffer(streamId, offerId) {
  const ids = streamOffers(streamId)
    .filter((o) => o.offer_id !== offerId)
    .map((o) => o.offer_id);
  setStreamOffers(streamId, rebalanceAfter(streamId, ids));
}

function onAddOffer(streamId, offerId) {
  const current = streamOffers(streamId);
  if (current.some((o) => o.offer_id === offerId)) return;
  const ids = current.map((o) => o.offer_id).concat(offerId);
  const shares = normalizeShares(ids);
  const catalogItem = catalog.find((i) => i.offer_id === offerId);
  const names = {};
  for (const o of current) names[o.offer_id] = o.name;
  names[offerId] = catalogItem ? catalogItem.name : `оффер ${offerId}`;
  setStreamOffers(streamId, shares.map((b) => ({ ...b, name: names[b.offer_id] })));
}

async function onSaveStream(streamId) {
  clearError();
  const ids = streamOffers(streamId).map((o) => o.offer_id);
  try {
    await api(`/api/streams/${streamId}/offers`, {
      method: "PUT",
      body: JSON.stringify({ offers: ids.map((id) => ({ offer_id: id, share: 0 })) }),
    });
    await loadEditor(editorCampaign.id);
  } catch (err) {
    showError(String(err.message || err));
  }
}

/* ---------- события ---------- */

document.addEventListener("click", (e) => {
  const removeBtn = e.target.closest("[data-remove]");
  if (removeBtn) {
    const streamId = Number(removeBtn.closest(".stream-card").dataset.streamId);
    onRemoveOffer(streamId, Number(removeBtn.dataset.remove));
    return;
  }
  const addBtn = e.target.closest("[data-add]");
  if (addBtn) {
    const streamId = Number(addBtn.dataset.add);
    const input = document.querySelector(`[data-stream-add="${streamId}"]`);
    const offerId = Number(input.dataset.offerId);
    if (!offerId) {
      showError("Сначала выберите оффер из подсказок.");
      return;
    }
    onAddOffer(streamId, offerId);
    input.value = "";
    delete input.dataset.offerId;
    return;
  }
  const saveBtn = e.target.closest("[data-save]");
  if (saveBtn) {
    onSaveStream(Number(saveBtn.dataset.save));
  }
});

$("#tab-create").addEventListener("click", () => {
  $("#tab-create").classList.add("active");
  $("#tab-edit").classList.remove("active");
  $("#view-create").classList.remove("hidden");
  $("#view-edit").classList.add("hidden");
});
$("#tab-edit").addEventListener("click", () => {
  $("#tab-edit").classList.add("active");
  $("#tab-create").classList.remove("active");
  $("#view-edit").classList.remove("hidden");
  $("#view-create").classList.add("hidden");
  if (!$("#sel-campaign").options.length) loadCampaignList().catch((err) => showError(String(err.message || err)));
});

$("#create-form").addEventListener("submit", submitCreate);
$("#btn-refresh-catalog").addEventListener("click", async () => {
  clearError();
  try {
    await api("/api/catalog/refresh", { method: "POST" });
    await loadCatalog();
  } catch (err) {
    showError(String(err.message || err));
  }
});
$("#btn-reload-campaigns").addEventListener("click", async () => {
  clearError();
  try {
    await loadCampaignList();
  } catch (err) {
    showError(String(err.message || err));
  }
});
$("#sel-campaign").addEventListener("change", (e) => loadEditor(Number(e.target.value)));

/* привязка автокомплита к создаватору; редакторские — после renderEditor */
attachAutocomplete($("#f-offer"), $("#offer-suggest"), () => {});

function attachEditorAutocompletes() {
  for (const stream of editorCampaign.streams) {
    if (!stream.is_offer_stream) continue;
    const input = document.querySelector(`[data-stream-add="${stream.id}"]`);
    const suggest = input.parentElement.querySelector(".suggest");
    attachAutocomplete(input, suggest, () => {});
  }
}

const origRenderEditor = renderEditor;
renderEditor = function () {
  origRenderEditor();
  attachEditorAutocompletes();
};

/* ---------- старт ---------- */

(async function init() {
  try {
    await loadCatalog();
  } catch (err) {
    showError(String(err.message || err));
  }
})();
