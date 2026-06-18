const tg = window.Telegram?.WebApp;
const statusEl = document.querySelector("#status");
const messageEl = document.querySelector("#message");
const payButton = document.querySelector("#pay");
const productTitle = document.querySelector("#product-title");
const productPrice = document.querySelector("#product-price");
const products = [...document.querySelectorAll(".product")];

let selectedProduct = "photo_pack";

function setStatus(text, kind = "") {
  statusEl.textContent = text;
  statusEl.className = `status ${kind}`.trim();
}

function setMessage(text) {
  messageEl.textContent = text;
}

function initData() {
  return tg?.initData || "";
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || "請求失敗");
  }
  return data;
}

async function verifyTelegramSession() {
  if (!tg) {
    setStatus("預覽", "");
    setMessage("請從 Telegram Mini App 開啟以啟用付款。");
    return false;
  }
  tg.ready();
  tg.expand();
  try {
    await postJson("/api/telegram/validate-init-data", { init_data: initData() });
    setStatus("已連線", "ready");
    return true;
  } catch (error) {
    setStatus("驗證失敗", "error");
    setMessage(error.message);
    return false;
  }
}

function openInvoice(invoiceLink) {
  if (tg?.openInvoice) {
    tg.openInvoice(invoiceLink, (status) => {
      if (status === "paid") {
        setMessage("付款完成，權益會由 bot 自動發放。");
      } else if (status === "cancelled") {
        setMessage("付款已取消。");
      } else {
        setMessage(`付款狀態：${status}`);
      }
    });
    return;
  }
  if (window.Telegram?.WebView?.showInvoice) {
    window.Telegram.WebView.showInvoice(invoiceLink);
    return;
  }
  window.location.href = invoiceLink;
}

products.forEach((button) => {
  button.addEventListener("click", () => {
    products.forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    selectedProduct = button.dataset.product;
    productTitle.textContent = button.dataset.title;
    productPrice.textContent = button.dataset.price;
  });
});

payButton.addEventListener("click", async () => {
  if (!initData()) {
    setMessage("請從 Telegram Mini App 開啟後再付款。");
    return;
  }
  payButton.disabled = true;
  setMessage("正在開立 Stars 發票...");
  try {
    const invoice = await postJson("/api/payments/stars/invoice-link", {
      init_data: initData(),
      product: selectedProduct,
    });
    openInvoice(invoice.invoice_link);
  } catch (error) {
    setStatus("錯誤", "error");
    setMessage(error.message);
  } finally {
    payButton.disabled = false;
  }
});

verifyTelegramSession();
