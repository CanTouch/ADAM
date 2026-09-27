// Adam Bridge: connects to Adam on this computer and carries out its browser commands
// in one tab (grouped and labelled "Adam"). config.js is written by Adam on startup.
importScripts("config.js"); // defines ADAM_PORT and ADAM_TOKEN

let ws = null;
let adamTabId = null;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function connect() {
  if (ws && ws.readyState <= WebSocket.OPEN) return; // connecting or open
  ws = new WebSocket(`ws://127.0.0.1:${ADAM_PORT}/?token=${ADAM_TOKEN}`);
  ws.onmessage = async (event) => {
    const msg = JSON.parse(event.data);
    if (!msg.cmd) return;
    let reply;
    try {
      const handler = COMMANDS[msg.cmd];
      if (!handler) throw new Error(`Unknown command ${msg.cmd}`);
      reply = { id: msg.id, ok: true, result: await handler(msg.args || {}) };
    } catch (err) {
      reply = { id: msg.id, ok: false, error: String((err && err.message) || err) };
    }
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(reply));
  };
  ws.onclose = () => { ws = null; };
}

// Keep the connection (and this service worker) alive; reconnect when Adam restarts.
setInterval(() => {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send('{"type":"keepalive"}');
  else connect();
}, 5000);
chrome.alarms.create("adam-reconnect", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(connect);
chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(connect);
connect();

// ---- tab helpers ----

async function currentAdamTab() {
  if (adamTabId === null) return null;
  try {
    return await chrome.tabs.get(adamTabId);
  } catch (e) {
    adamTabId = null; // the user closed it
    return null;
  }
}

async function requireAdamTab() {
  const tab = await currentAdamTab();
  if (!tab) throw new Error("Adam has no tab yet. Use open_url first, or use_current_tab.");
  return tab;
}

async function labelTab(tabId) {
  try {
    const group = await chrome.tabs.group({ tabIds: tabId });
    await chrome.tabGroups.update(group, { title: "Adam", color: "purple" });
  } catch (e) { /* grouping is cosmetic */ }
}

async function settle(tabId, maxMs = 30000) {
  await sleep(300);
  const end = Date.now() + maxMs;
  while (Date.now() < end) {
    const t = await chrome.tabs.get(tabId);
    if (t.status === "complete") return;
    await sleep(250);
  }
}

async function where(tabId) {
  const t = await chrome.tabs.get(tabId);
  return `Now at: '${t.title}' ${t.url}`;
}

async function inPage(tabId, action, selector, value) {
  const [res] = await chrome.scripting.executeScript({
    target: { tabId }, func: pageAction, args: [action, selector, value ?? null],
  });
  return res && res.result;
}

// Runs inside the web page. Must be self-contained.
function pageAction(action, selector, value) {
  const visible = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const textOf = (el) => (el.innerText || el.value || el.getAttribute("aria-label") || "").trim().toLowerCase();
  function find(sel) {
    if (sel.startsWith("text=")) {
      const want = sel.slice(5).trim().replace(/^["']|["']$/g, "").toLowerCase();
      const clickable = [...document.querySelectorAll(
        'a, button, [role=button], [role=link], [role=tab], [role=menuitem], input[type=submit], input[type=button], summary, label'
      )].filter(visible);
      return clickable.find((el) => textOf(el) === want)
        || clickable.find((el) => textOf(el).includes(want))
        || [...document.querySelectorAll("body *")].filter(visible).reverse().find((el) => textOf(el) === want)
        || null;
    }
    return document.querySelector(sel);
  }
  let el;
  try { el = find(selector); } catch (e) { return { found: false, error: `Bad selector: ${selector}` }; }
  if (!el) return { found: false };
  if (action === "inspect") {
    const t = el.closest("button, input, a, [role=button]") || el;
    const label = (t.innerText || t.value || t.getAttribute("aria-label") || t.title || "").slice(0, 200);
    return { found: true, label, submits: !!t.form && (t.type === "submit" || t.type === "image") };
  }
  el.scrollIntoView({ block: "center" });
  if (action === "click") {
    el.click();
    return { found: true };
  }
  if (action === "fill") {
    el.focus();
    if (el.isContentEditable) {
      document.execCommand("selectAll");
      document.execCommand("insertText", false, value);
    } else {
      const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
        : el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value); // works with React inputs
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }
    return { found: true };
  }
  return { found: true, error: `Unknown action ${action}` };
}

function mustFind(result, selector) {
  if (!result || !result.found) throw new Error((result && result.error) || `Nothing on the page matches ${selector}`);
}

// ---- commands from Adam ----

const COMMANDS = {
  async ping() {
    return "pong";
  },

  async open_url({ url }) {
    if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(url)) {
      url = (/^(localhost|127\.|\[::1\])/i.test(url) ? "http://" : "https://") + url;
    }
    let tab = await currentAdamTab();
    if (tab) {
      tab = await chrome.tabs.update(tab.id, { url, active: true });
    } else {
      const win = await chrome.windows.getLastFocused({ windowTypes: ["normal"] }).catch(() => null);
      tab = win
        ? await chrome.tabs.create({ windowId: win.id, url, active: true })
        : (await chrome.windows.create({ url, focused: true })).tabs[0];
      adamTabId = tab.id;
      await labelTab(tab.id);
    }
    await chrome.windows.update(tab.windowId, { focused: true });
    await settle(tab.id);
    return where(tab.id);
  },

  async use_current_tab() {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (!tab) throw new Error("No active tab in Chrome.");
    adamTabId = tab.id;
    return where(tab.id);
  },

  async inspect({ selector }) {
    const tab = await requireAdamTab();
    return inPage(tab.id, "inspect", selector);
  },

  async click({ selector }) {
    const tab = await requireAdamTab();
    mustFind(await inPage(tab.id, "click", selector), selector);
    await sleep(400);
    await settle(tab.id, 10000);
    return "Clicked. " + (await where(tab.id));
  },

  async fill_form({ selector, value }) {
    const tab = await requireAdamTab();
    mustFind(await inPage(tab.id, "fill", selector, value), selector);
    return `Filled ${selector}.`;
  },

  async get_page_text() {
    const tab = await requireAdamTab();
    const [res] = await chrome.scripting.executeScript({
      target: { tabId: tab.id }, func: () => (document.body ? document.body.innerText : ""),
    });
    return (await where(tab.id)) + "\n\n" + ((res && res.result) || "");
  },

  async screenshot() {
    const tab = await requireAdamTab();
    await chrome.tabs.update(tab.id, { active: true });
    await sleep(150);
    return chrome.tabs.captureVisibleTab(tab.windowId, { format: "png" });
  },
};
