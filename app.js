const APP_VERSION = "clean-render-v3";

let allNews = [];
 +let briefPoints = [];
    pad(date.getDate()) +
    "T" +
    pad(date.getHours()) +
    ":" +
    pad(date.getMinutes())
  );
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function shortText(value, maxLength) {
  const text = String(value || "").trim();

  if (text.length > maxLength) {
    return text.slice(0, maxLength);
  }

  return text;
}

function getMinMaxNewsTime(items) {
  const dates = items
    .map((item) => parseDateTime(item.datetime))
    .filter((date) => date && !isNaN(date.getTime()));

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
  const rangeEl = document.getElementById("dataRange");
  const minMax = getMinMaxNewsTime(allNews);

  if (!rangeEl) return;

  if (!minMax.min || !minMax.max) {
    rangeEl.textContent = "--";
    return;
  }

  rangeEl.textContent =
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

  if (startEl && minMax.min) {
    startEl.value = toDateTimeLocalValue(minMax.min);
  }

  if (endEl && minMax.max) {
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
        const categoryName = categoryNames[normalizeCategory(item.category)] || "市場";
        const text = item.summary || item.content || item.headline || "";
        return categoryName + "：" + text;
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
  const keywordEl = document.getElementById("keyword");
  const keyword = keywordEl ? keywordEl.value.trim().toLowerCase() : "";

  let filtered = allNews.slice();

  if (keyword) {
    filtered = filtered.filter((item) => {
      const searchableText = [
        item.datetime,
        item.category,
        item.category_name,
        item.headline,
        item.summary,
        item.content,
        Array.isArray(item.tags) ? item.tags.join(" ") : "",
      ]
        .join(" ")
        .toLowerCase();

      return searchableText.includes(keyword);
    });
  }

  return filtered;
}

function renderNews() {
  const container = document.getElementById("newsContainer");
  const visibleCountEl = document.getElementById("visibleCount");

  if (!container || !visibleCountEl) return;

  let filtered = getFilteredNews();

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
  return `
    <article class="timeline-item importance-${item.importance || 3}">
      <div class="timeline-dot"></div>
      <time class="timeline-time">${escapeHtml(item.datetime)}</time>
      <div class="timeline-body">
        ${item.summary ? `<div class="timeline-summary">${escapeHtml(item.summary)}</div>` : ""}
      </div>
    </article>
  `;
}

function showLoadError(message) {
  const generatedAtEl = document.getElementById("generatedAt");
  const dataRangeEl = document.getElementById("dataRange");
  const visibleCountEl = document.getElementById("visibleCount");
  const briefList = document.getElementById("briefList");
  const container = document.getElementById("newsContainer");

  if (generatedAtEl) generatedAtEl.textContent = "--";
  if (dataRangeEl) dataRangeEl.textContent = "--";
  if (visibleCountEl) visibleCountEl.textContent = "0";

  if (briefList) {
    briefList.innerHTML = "<li>讀取 summary 失敗。</li>";
  }

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
    const response = await fetch(url);

    if (!response.ok) {
      throw new Error("Cannot load data/news.json, status=" + response.status);
    }

    const data = await response.json();

    console.log("Loaded data/news.json:", data);

    allNews = Array.isArray(data.items) ? data.items : [];
    briefPoints = Array.isArray(data.brief_points) ? data.brief_points : [];

    const generatedAtEl = document.getElementById("generatedAt");

    if (generatedAtEl) {
      generatedAtEl.textContent = data.generated_at || "--";
    }

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

function normalizeCategory(value) {
  const c = String(value || "").trim();

  if (c === "bond" || c === "債市" || c === "债市") return "bond";
  if (c === "equity" || c === "股市") return "equity";
  if (c === "central_bank" || c === "央行") return "central_bank";
  if (c === "economy" || c === "經濟" || c === "经济") return "economy";
  if (c === "war" || c === "戰爭" || c === "战争" || c === "地緣政治" || c === "地缘政治") return "war";
  if (c === "commodity" || c === "商品" || c === "能源" || c === "大宗商品") return "commodity";

  return "other";
}

function parseDateTime(value) {
  if (!value) return null;

  const text = String(value).trim();
  const date = new Date(text.replace(" ", "T"));

  if (isNaN(date.getTime())) return null;

  return date;
}

function pad(n) {
  return String(n).padStart(2, "0");
}

function formatDisplayTime(date) {
  if (!date || isNaN(date.getTime())) return "--";

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

  return (
    date.getFullYear() +
    "-" +
    pad(date.getMonth() + 1) +
