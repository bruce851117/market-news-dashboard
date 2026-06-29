const APP_VERSION = "render-all-v2";

let allNews = [];
let briefPoints = [];

const categoryOrder = [
  "bond",
  "equity",
  "central_bank",
  "economy",
  "war",
  "commodity",
  "other",
];

const categoryNames = {
  bond: "債市",
  equity: "股市",
  central_bank: "央行",
  economy: "經濟",
  war: "戰爭",
  commodity: "商品",
  other: "其他",
};

const categorySubtitles = {
  bond: "利率、美債、殖利率、信用與債市政策",
  equity: "股市、科技龍頭、AI 供應鏈與主要股指",
  central_bank: "Fed、ECB、BOJ、BOE、PBOC 與央行政策",
  economy: "CPI、PPI、PMI、GDP、就業、關稅與財政政策",
  war: "戰爭、地緣政治、制裁與軍事衝突",
  commodity: "原油、天然氣、黃金、銅與能源供應",
  other: "其他重要市場訊息",
};

function normalizeCategory(category) {
  const c = String(category || "").trim();

  if (c === "bond" || c === "債市" || c === "债市") return "bond";
  if (c === "equity" || c === "股市") return "equity";
  if (c === "central_bank" || c === "央行") return "central_bank";
  if (c === "economy" || c === "經濟" || c === "经济") return "economy";
  if (c === "war" || c === "戰爭" || c === "战争" || c === "地緣政治" || c === "地缘政治") return "war";
  if (c === "commodity" || c === "商品" || c === "大宗商品" || c === "能源") return "commodity";

  return "other";
}

function parseDateTime(s) {
  if (!s) return null;

  const text = String(s).trim();

  if (!text) return null;

  const d = new Date(text.replace(" ", "T"));

  if (isNaN(d.getTime())) return null;

  return d;
}

function formatDisplayTime(date) {
  if (!date || isNaN(date.getTime())) return "--";

  const pad = (n) => String(n).padStart(2, "0");

  return (
    date.getFullYear() +
    "-" +
    pad(date.getMonth() + 1) +
    "-" +
    pad(date.getDate()) +
    " " +
    pad(date.getHours()) +
    ":" +
    pad(date.getMinutes())
  );
}

function toDateTimeLocalValue(date) {
  if (!date || isNaN(date.getTime())) return "";

  const pad = (n) => String(n).padStart(2, "0");

  return (
    date.getFullYear() +
    "-" +
    pad(date.getMonth() + 1) +
    "-" +
    pad(date.getDate()) +
    "T" +
    pad(date.getHours()) +
    ":" +
    pad(date.getMinutes())
  );
}

function escapeHtml(str) {
  return String(str || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function getMinMaxNewsTime(items) {
  const dates = items
    .map((item) => parseDateTime(item.datetime))
    .filter((d) => d && !isNaN(d.getTime()));

  if (dates.length === 0) {
    return {
      min: null,
      max: null,
    };
  }

  dates.sort((a, b) => a - b);

  return {
    min: dates[0],
    max: dates[dates.length - 1],
  };
}

function updateDataRangeText() {
  const el = document.getElementById("dataRange");
  if (!el) return;

  const minMax = getMinMaxNewsTime(allNews);

  if (!minMax.min || !minMax.max) {
    el.textContent = "--";
    return;
  }

  el.textContent =
    formatDisplayTime(minMax.min) +
    " ～ " +
    formatDisplayTime(minMax.max);
}

function resetFiltersToDataRange() {
  const minMax = getMinMaxNewsTime(allNews);

  const keywordEl = document.getElementById("keyword");
  const startEl = document.getElementById("startTime");
  const endEl = document.getElementById("endTime");

  if (keywordEl) keywordEl.value = "";

  if (minMax.min && minMax.max) {
    startEl.value = toDateTimeLocalValue(minMax.min);
    endEl.value = toDateTimeLocalValue(minMax.max);
  }

  renderNews();
}

function renderBrief() {
  const briefList = document.getElementById("briefList");
  if (!briefList) return;

  let points = Array.isArray(briefPoints) ? briefPoints.filter(Boolean) : [];

  if (points.length === 0 && allNews.length > 0) {
    points = allNews
      .slice()
      .sort((a, b) => Number(b.importance || 3) - Number(a.importance || 3))
      .slice(0, 10)
      .map((item) => {
        const category = categoryNames[normalizeCategory(item.category)] || "市場";
        const text = item.summary || item.content || item.headline || "";
        return category + "：" + text;
      });
  }

  if (points.length === 0) {
    briefList.innerHTML = "<li>目前沒有可顯示的重點摘要。</li>";
    return;
  }

  briefList.innerHTML = points
    .slice(0, 10)
    .map((point) => `<li>${escapeHtml(point)}</li>`)
    .join("");
}

function getFilteredNews() {
  const keyword = document.getElementById("keyword").value.trim().toLowerCase();

  let filtered = allNews.slice();

  if (keyword) {
    filtered = filtered.filter((item) => {
      const text = [
        item.datetime,
        item.category,
        item.category_name,
        item.headline,
        item.summary,
        item.content,
        Array.isArray(item.tags) ? item.tags.join(" ") : "",
      ].join(" ").toLowerCase();

      return text.includes(keyword);
    });
  }

  return filtered;
}

function renderNews() {
  const container = document.getElementById("newsContainer");
  const visibleCountEl = document.getElementById("visibleCount");

  if (!container || !visibleCountEl) return;

  let filtered = getFilteredNews();

  /*
    這版刻意不使用日期篩選來排除新聞。
    日期欄位只用來顯示與重設，避免瀏覽器 datetime-local 格式導致 filtered = 0。
  */
  if (!document.getElementById("keyword").value.trim()) {
    filtered = allNews.slice();
  }

  filtered.sort((a, b) => {
    const da = parseDateTime(a.datetime);
    const db = parseDateTime(b.datetime);

    if (!da || !db) return 0;

    return da - db;
  });

  visibleCountEl.textContent = filtered.length;

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="empty">
        已讀取 data/news.json，但目前沒有符合搜尋條件的新聞。<br/>
        請清空搜尋關鍵字，或按「重設時間與搜尋」。
      </div>
    `;
    return;
  }

  const grouped = {};

  categoryOrder.forEach((category) => {
    grouped[category] = [];
  });

  filtered.forEach((item) => {
    const category = normalizeCategory(item.category);

    if (!grouped[category]) {
      grouped[category] = [];
    }

    grouped[category].push(item);
  });

  let html = "";

  categoryOrder.forEach((category) => {
    const items = grouped[category] || [];

    if (items.length === 0) return;

    html += `
      <section class="category-block category-${category}">
        <div class="category-header">
          <div>
            <h2>${categoryNames[category] || category}</h2>
            <p>${categorySubtitles[category] || ""}</p>
          </div>
          <span>${items.length} 則</span>
        </div>

        <div class="timeline-list">
          ${items.map(renderTimelineItem).join("")}
        </div>
      </section>
    `;
  });

  container.innerHTML = html;
}

function renderTimelineItem(item) {
  const summary = item.summary || "";
  const content = item.content || "";

  return `
    <div class="timeline-item importance-${item.importance || 3}">
      <div class="timeline-dot"></div>
      <div class="timeline-time">${escapeHtml(item.datetime)}</div>
      <div class="timeline-body">
        <div class="timeline-headline">${escapeHtml(item.headline || "")}</div>
        ${summary ? `<div class="timeline-summary">${escapeHtml(summary)}</div>` : ""}
        ${content && content !== summary ? `<div class="timeline-content">${escapeHtml(content)}</div>` : ""}
      </div>
    </div>
  `;
}

function showLoadError(message) {
  document.getElementById("generatedAt").textContent = "--";
  document.getElementById("dataRange").textContent = "--";
  document.getElementById("visibleCount").textContent = "0";

  const briefList = document.getElementById("briefList");
  if (briefList) {
    briefList.innerHTML = "<li>讀取 summary 失敗。</li>";
  }

  const container = document.getElementById("newsContainer");
  if (container) {
    container.innerHTML = `
      <div class="empty">
        ${escapeHtml(message)}
      </div>
    `;
  }
}

async function loadNews() {
  try {
    console.log("APP_VERSION:", APP_VERSION);

    const url = "data/news.json?ts=" + Date.now();
    console.log("Loading news from:", url);

    const res = await fetch(url);

    if (!res.ok) {
      throw new Error("Cannot load data/news.json, status=" + res.status);
    }

    const data = await res.json();

    console.log("Loaded data/news.json:", data);

    allNews = Array.isArray(data.items) ? data.items : [];
    briefPoints = Array.isArray(data.brief_points) ? data.brief_points : [];

    document.getElementById("generatedAt").textContent = data.generated_at || "--";

    updateDataRangeText();
    renderBrief();

    if (allNews.length === 0) {
      document.getElementById("visibleCount").textContent = "0";
      document.getElementById("newsContainer").innerHTML = `
        <div class="empty">
          data/news.json 已讀取，但 items 是空的。
        </div>
      `;
      return;
    }

    resetFiltersToDataRange();
  } catch (err) {
    console.error("loadNews failed:", err);
    showLoadError("讀取 data/news.json 失敗：" + err.message);
  }
}

document.getElementById("startTime").addEventListener("change", renderNews);
document.getElementById("endTime").addEventListener("change", renderNews);
document.getElementById("keyword").addEventListener("input", renderNews);

document.getElementById("resetBtn").addEventListener("click", () => {
  resetFiltersToDataRange();
});

loadNews();
