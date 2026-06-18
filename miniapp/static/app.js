/* videoGirl Mini App — multi-screen SPA */

const tg = window.Telegram?.WebApp;

// ---- State ----
let sessionToken = null;
let userStatus = null;

// ---- Telegram WebApp init ----
if (tg) {
  tg.ready();
  tg.expand();
}

// ---- Tab navigation ----
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const tabId = btn.dataset.tab;
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`tab-${tabId}`).classList.add("active");
    if (tabId === "personas") loadPersonas();
    if (tabId === "wallet") loadWallet();
    if (tabId === "store") loadStore();
  });
});

// ---- Auth ----
async function authenticate() {
  const initData = tg?.initData || "";
  if (!initData) {
    setHomeMessage("請從 Telegram 開啟此 Mini App。", true);
    return false;
  }
  try {
    const res = await postJson("/api/auth/session", { init_data: initData });
    sessionToken = res.token;
    return true;
  } catch (err) {
    setHomeMessage("驗證失敗：" + err.message, true);
    return false;
  }
}

// ---- HTTP helpers ----
async function postJson(url, body) {
  const headers = { "Content-Type": "application/json" };
  if (sessionToken) headers["Authorization"] = `Bearer ${sessionToken}`;
  const r = await fetch(url, { method: "POST", headers, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "請求失敗");
  return data;
}

async function getJson(url) {
  const headers = {};
  if (sessionToken) headers["Authorization"] = `Bearer ${sessionToken}`;
  const r = await fetch(url, { headers });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "請求失敗");
  return data;
}

// ---- Home tab ----
function setHomeMessage(msg, isError = false) {
  const el = document.getElementById("home-msg");
  el.textContent = msg;
  el.className = isError ? "hint error-text" : "hint";
}

async function loadHome() {
  try {
    userStatus = await getJson("/api/user/status");
    document.getElementById("home-persona-name").textContent = userStatus.active_persona_slug;
    document.getElementById("home-level-label").textContent = `關係：${userStatus.intimacy_level_name}`;
    document.getElementById("home-score").textContent = Math.round(userStatus.intimacy_score);
    document.getElementById("home-streak").textContent = `${userStatus.streak_days} 天`;
    document.getElementById("home-vip").textContent = userStatus.is_vip ? "✅ VIP" : "未開通";
    document.getElementById("home-balance").textContent = `${userStatus.balance} 點`;
    setHomeMessage("");
  } catch (err) {
    setHomeMessage("載入失敗：" + err.message, true);
  }
}

// ---- Personas tab ----
async function loadPersonas() {
  const list = document.getElementById("personas-list");
  const msg = document.getElementById("personas-msg");
  list.innerHTML = "";
  msg.textContent = "載入中…";
  try {
    const personas = await getJson("/api/personas");
    msg.textContent = "";
    const current = userStatus?.active_persona_slug;
    personas.forEach((p) => {
      const item = document.createElement("div");
      item.className = "card-item" + (p.slug === current ? " selected" : "");
      item.innerHTML = `
        <div class="card-info">
          <div class="card-title">${p.name}</div>
          <div class="card-desc">${p.personality}</div>
        </div>
        ${p.slug === current ? '<span class="card-badge">使用中</span>' : ""}
      `;
      item.addEventListener("click", () => switchPersona(p.slug, p.name));
      list.appendChild(item);
    });
  } catch (err) {
    msg.textContent = "載入失敗：" + err.message;
    msg.className = "hint error-text";
  }
}

async function switchPersona(slug, name) {
  try {
    await postJson("/api/personas/switch", { slug });
    if (userStatus) userStatus.active_persona_slug = slug;
    document.getElementById("home-persona-name").textContent = slug;
    await loadPersonas();
    tg?.showAlert?.(`已切換到 ${name}！`);
  } catch (err) {
    tg?.showAlert?.("切換失敗：" + err.message);
  }
}

// ---- Wallet tab ----
const TOPUP_PRODUCTS = [
  { slug: "credits_100", label: "100 點數", price: "50 Stars" },
];

async function loadWallet() {
  const msg = document.getElementById("wallet-msg");
  try {
    const status = await getJson("/api/user/status");
    document.getElementById("wallet-balance").textContent = status.balance;
    msg.textContent = "";
  } catch (err) {
    msg.textContent = "載入失敗：" + err.message;
  }
  const list = document.getElementById("topup-products");
  list.innerHTML = "";
  TOPUP_PRODUCTS.forEach((p) => {
    const item = buildProductCard(p.label, p.price, () => buyProduct(p.slug));
    list.appendChild(item);
  });
}

// ---- Store tab ----
const STORE_PRODUCTS = [
  { slug: "photo_pack",  label: "寫真解鎖包",    price: "25 Stars",  desc: "解鎖 AI 女友數位寫真" },
  { slug: "vip_day",     label: "VIP 一日體驗",   price: "99 Stars",  desc: "24 小時 VIP 權益體驗" },
  { slug: "credits_100", label: "儲值 100 點",    price: "50 Stars",  desc: "可用於圖片、語音、影片" },
];

function loadStore() {
  const list = document.getElementById("store-products");
  list.innerHTML = "";
  STORE_PRODUCTS.forEach((p) => {
    const item = buildProductCard(p.label, p.price, () => buyProduct(p.slug), p.desc);
    list.appendChild(item);
  });
}

function buildProductCard(label, price, onClick, desc = "") {
  const item = document.createElement("div");
  item.className = "card-item";
  item.innerHTML = `
    <div class="card-info">
      <div class="card-title">${label}</div>
      ${desc ? `<div class="card-desc">${desc}</div>` : ""}
    </div>
    <span class="card-badge">${price}</span>
  `;
  item.addEventListener("click", onClick);
  return item;
}

async function buyProduct(slug) {
  if (!sessionToken) {
    tg?.showAlert?.("請先完成驗證後再購買。");
    return;
  }
  try {
    const invoice = await postJson("/api/payments/stars/invoice-link", { product: slug });
    if (tg?.openInvoice) {
      tg.openInvoice(invoice.invoice_link, (status) => {
        if (status === "paid") {
          tg.showAlert?.("付款完成！權益由 bot 自動發放 💕");
          loadHome();
          loadWallet();
        } else if (status !== "cancelled") {
          tg.showAlert?.(`付款狀態：${status}`);
        }
      });
    } else {
      window.open(invoice.invoice_link, "_blank");
    }
  } catch (err) {
    tg?.showAlert?.("開立發票失敗：" + err.message);
  }
}

// ---- Boot ----
(async () => {
  const authed = await authenticate();
  if (authed) await loadHome();
})();
