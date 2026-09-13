// ==UserScript==
// @name         Watch Later triage helper
// @namespace    yt-watchlater-triage
// @version      1.2.0
// @description  Export a YouTube playlist (Watch Later or any list) to the triage app, and remove IDs the app marked.
// @match        https://www.youtube.com/playlist?list=*
// @grant        GM_setValue
// @grant        GM_getValue
// @run-at       document-idle
// ==/UserScript==

(function () {
  "use strict";

  const QUEUE = "triage-remove-ids";
  const LOG = "triage-removed-log";
  const DELAY_MS = 900;

  let ids = new Set(GM_getValue(QUEUE, []));
  let removedLog = new Set(GM_getValue(LOG, []));
  let running = false;

  function playlistId() {
    try {
      return new URLSearchParams(location.search).get("list") || "unknown";
    } catch {
      return "unknown";
    }
  }

  function videoIdFrom(renderer) {
    const href =
      renderer.querySelector("a#video-title")?.href ||
      renderer.querySelector("a#thumbnail")?.href ||
      "";
    const m = href.match(/[?&]v=([\w-]{11})/);
    return m ? m[1] : null;
  }

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  function renderers() {
    return [...document.querySelectorAll("ytd-playlist-video-renderer")];
  }

  function rowFrom(renderer, fallbackPos) {
    const videoId = videoIdFrom(renderer);
    if (!videoId) return null;
    const titleEl = renderer.querySelector("a#video-title");
    const channelEl =
      renderer.querySelector("#channel-name a") ||
      renderer.querySelector("ytd-channel-name #text") ||
      renderer.querySelector("#channel-name yt-formatted-string");
    const durEl =
      renderer.querySelector("ytd-thumbnail-overlay-time-status-renderer #text") ||
      renderer.querySelector("span.ytd-thumbnail-overlay-time-status-renderer");
    const indexEl = renderer.querySelector("#index");
    const indexText = (indexEl?.textContent || "").replace(/\D+/g, "");
    const position = indexText ? Number(indexText) : fallbackPos;
    const href = titleEl?.href || `https://www.youtube.com/watch?v=${videoId}`;
    return {
      position,
      videoId,
      title: (titleEl?.textContent || "").trim(),
      url: href,
      channel: (channelEl?.textContent || "").trim(),
      duration: (durEl?.textContent || "").trim() || null,
    };
  }

  function playlistPayload(videos) {
    return {
      source: "userscript",
      kind: "playlist",
      playlistId: playlistId(),
      exportedAt: new Date().toISOString(),
      videos,
    };
  }

  function downloadJson(filename, data) {
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function copyJson(data) {
    const text = JSON.stringify(data, null, 2);
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      return false;
    }
  }

  async function collectPlaylist() {
    const seen = new Map();
    let stuck = 0;
    let lastY = -1;
    while (stuck < 10) {
      const nodes = renderers();
      nodes.forEach((node, i) => {
        const row = rowFrom(node, seen.size + i + 1);
        if (row) seen.set(row.videoId, row);
      });
      const last = nodes.at(-1);
      last?.scrollIntoView({ block: "end" });
      await sleep(800);
      const y = window.scrollY;
      if (y <= lastY && nodes.length === seen.size) stuck += 1;
      else stuck = 0;
      lastY = y;
      if (nodes.length && seen.size >= nodes.length && stuck >= 3) {
        const before = seen.size;
        await sleep(1100);
        renderers().forEach((node, i) => {
          const row = rowFrom(node, seen.size + i + 1);
          if (row) seen.set(row.videoId, row);
        });
        if (seen.size === before) break;
        stuck = 0;
      }
    }
    return [...seen.values()].sort((a, b) => a.position - b.position);
  }

  function resultPayload(remaining) {
    return {
      source: "userscript",
      exportedAt: new Date().toISOString(),
      removedVideoIds: [...removedLog],
      remainingVideoIds: [...remaining],
    };
  }

  async function clickRemove(renderer) {
    const direct = renderer.querySelector(
      'button[aria-label*="Remove from Watch later"], button[aria-label*="Remove from Watch Later"]',
    );
    if (direct) {
      direct.click();
      return true;
    }
    const menu =
      renderer.querySelector("#menu #button") ||
      renderer.querySelector("ytd-menu-renderer button") ||
      renderer.querySelector('button[aria-label="Action menu"]') ||
      renderer.querySelector('button[aria-label="More actions"]');
    if (!menu) return false;
    menu.click();
    await sleep(350);
    const items = [
      ...document.querySelectorAll(
        "ytd-menu-service-item-renderer, ytd-menu-navigation-item-renderer, yt-list-item-view-model, tp-yt-paper-item, [role='menuitem']",
      ),
    ];
    const hit = items.find((el) =>
      /remove from (watch later|playlist|LL)/i.test(el.textContent || ""),
    );
    if (hit) {
      hit.click();
      return true;
    }
    document.body.click();
    return false;
  }

  function parseIncoming(text) {
    const trimmed = text.trim();
    if (!trimmed) return { queue: [], removed: [] };
    const parsed = JSON.parse(trimmed);
    if (Array.isArray(parsed)) {
      return { queue: parsed.filter((x) => typeof x === "string"), removed: [] };
    }
    const queue = [
      ...(Array.isArray(parsed.remainingVideoIds)
        ? parsed.remainingVideoIds
        : []),
      ...(Array.isArray(parsed.videoIds) ? parsed.videoIds : []),
    ].filter((x) => typeof x === "string");
    const removed = Array.isArray(parsed.removedVideoIds)
      ? parsed.removedVideoIds.filter((x) => typeof x === "string")
      : [];
    return { queue, removed };
  }

  function panel() {
    const root = document.createElement("div");
    root.id = "wl-triage-panel";
    root.innerHTML = `
      <strong>Triage helper</strong>
      <p class="hint">Export this playlist, then Pull in the app.</p>
      <div class="row">
        <button type="button" data-act="export">Export playlist</button>
      </div>
      <textarea placeholder='Paste {"videoIds":[...]} from the app to remove'></textarea>
      <div class="row">
        <button type="button" data-act="load">Load</button>
        <button type="button" data-act="start">Start remove</button>
        <button type="button" data-act="stop">Stop</button>
      </div>
      <div class="row">
        <button type="button" data-act="copy">Copy result</button>
        <button type="button" data-act="download">Download result</button>
      </div>
      <p class="status">queue ${ids.size} · already removed ${removedLog.size}</p>
    `;
    Object.assign(root.style, {
      position: "fixed",
      right: "16px",
      bottom: "16px",
      zIndex: "999999",
      width: "300px",
      padding: "12px",
      background: "#1c1916",
      color: "#f4efe6",
      font: "12px/1.4 system-ui,sans-serif",
      border: "1px solid #5c5346",
      borderRadius: "12px",
      boxShadow: "0 12px 40px rgba(0,0,0,.4)",
    });
    const hint = root.querySelector(".hint");
    Object.assign(hint.style, { margin: "6px 0", color: "#cbbba6" });
    const ta = root.querySelector("textarea");
    Object.assign(ta.style, {
      width: "100%",
      height: "64px",
      margin: "8px 0",
      background: "#111",
      color: "#eee",
      border: "1px solid #444",
      borderRadius: "8px",
    });
    root.querySelectorAll("button").forEach((b) => {
      Object.assign(b.style, {
        margin: "0 6px 6px 0",
        padding: "4px 8px",
        cursor: "pointer",
      });
    });
    document.documentElement.appendChild(root);
    return root;
  }

  const ui = panel();
  const status = () => ui.querySelector(".status");

  ui.addEventListener("click", async (e) => {
    const act = e.target?.dataset?.act;
    if (act === "export") {
      status().textContent = "scrolling playlist…";
      const videos = await collectPlaylist();
      const payload = playlistPayload(videos);
      const copied = await copyJson(payload);
      downloadJson(`youtube-playlist-${playlistId()}.json`, payload);
      status().textContent = copied
        ? `exported ${videos.length} · copied — Pull in the app`
        : `exported ${videos.length} · downloaded (clipboard blocked)`;
    }
    if (act === "load") {
      try {
        const incoming = parseIncoming(ui.querySelector("textarea").value);
        incoming.removed.forEach((id) => removedLog.add(id));
        ids = new Set(incoming.queue.filter((id) => !removedLog.has(id)));
        GM_setValue(QUEUE, [...ids]);
        GM_setValue(LOG, [...removedLog]);
        status().textContent = `queue ${ids.size} · already removed ${removedLog.size}`;
      } catch (err) {
        status().textContent = String(err.message || err);
      }
    }
    if (act === "stop") running = false;
    if (act === "copy") {
      const ok = await copyJson(resultPayload(ids));
      status().textContent = ok
        ? `copied ${removedLog.size} removed · ${ids.size} remaining`
        : "clipboard blocked — use Download result";
    }
    if (act === "download") downloadJson("watchlater-removed.json", resultPayload(ids));
    if (act === "start") {
      if (!ids.size) {
        status().textContent = "load IDs first";
        return;
      }
      if (ids.size > 20 && !confirm(`Remove ${ids.size} playlist videos?`))
        return;
      running = true;
      await run();
    }
  });

  async function run() {
    const remaining = new Set(ids);
    let removed = 0;
    let stuck = 0;
    while (running && remaining.size) {
      status().textContent = `removed ${removed} · left ${remaining.size}`;
      const nodes = renderers();
      let hit = false;
      for (const node of nodes) {
        const id = videoIdFrom(node);
        if (!id || !remaining.has(id)) continue;
        node.scrollIntoView({ block: "center" });
        await sleep(250);
        const ok = await clickRemove(node);
        if (ok) {
          remaining.delete(id);
          removedLog.add(id);
          removed += 1;
          hit = true;
          stuck = 0;
          GM_setValue(LOG, [...removedLog]);
          await sleep(DELAY_MS);
          break;
        }
      }
      if (hit) continue;
      const before = nodes.length;
      nodes.at(-1)?.scrollIntoView({ block: "end" });
      await sleep(1100);
      const after = renderers().length;
      if (after <= before) {
        stuck += 1;
        window.scrollTo(0, 0);
        await sleep(600);
        if (stuck >= 6) break;
      }
    }
    running = false;
    ids = remaining;
    GM_setValue(QUEUE, [...ids]);
    GM_setValue(LOG, [...removedLog]);
    const payload = resultPayload(remaining);
    const copied = await copyJson(payload);
    downloadJson("watchlater-removed.json", payload);
    status().textContent = remaining.size
      ? `stopped · ${removed} removed this run · ${remaining.size} not found. Result ${copied ? "copied + " : ""}downloaded.`
      : `done · ${removed} removed. Result ${copied ? "copied + " : ""}downloaded.`;
  }
})();
