let allNews = [];
let briefPoints = [];

const categoryOrder = [
  "bond",
  "equity",
  "central_bank",
  "economy",
  "war",
  "commodity",
];

const categoryNames = {
  bond: "債市",
  equity: "股市",
  central_bank: "央行",
  economy: "經濟",
  war: "戰爭",
  commodity: "商品",
};

const categorySubtitles = {
  bond: "利率、美債、殖利率、信用與債市政策",
  equity: "股市、科技龍頭、AI 供應鏈與主要股指",
  central_bank: "Fed、ECB、BOJ、BOE、PBOC 與央行政策",
  economy: "CPI、PPI、PMI、GDP、就業、關稅與財政政策",
  war: "戰爭、地緣政治、制裁與軍事衝突",
  commodity: "原油、天然氣、黃金、銅與能源供應",
};

function parseDateTime(s) {
  if (!s) return null;
  return new Date(String(s).replace(" ", "T"));
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

function shortHeadline(str) {
  const text = String(str || "").trim();

  if (text.length > 30) {
    return text.slice(0, 30);
  }

  return text;
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
  const minMax = getMinMaxNewsTime(allNews);
  const el = document.getElementById("dataRange");

  if (!el) return;

  if (!minMax.min || !minMax.max) {
    el.textContent = "--";
    return;
  }

  el.textContent =
    formatDisplayTime(minMax.min) +
    " ～ " +
    formatDisplayTime(minMax.max);
}

function renderBrief() {
  const briefList = document.getElementById("briefList");

  if (!briefList) return;

  if (!briefPoints || briefPoints.length === 0) {
    briefList.innerHTML = "<li>目前沒有可顯示的重點摘要。</li>";
    return;
  }

  briefList.innerHTML = briefPoints
    .slice(0, 10)
    .map((point) => `<li>${escapeHtml(point)}</li>`)
    .join("");
}

function resetFiltersToDataRange() {
  const minMax = getMinMaxNewsTime(allNews);

  document.getElementById("keyword").value = "";

  if (minMax.min && minMax.max) {
    document.getElementById("startTime").value = toDateTimeLocalValue(minMax.min);
    document.getElementById("endTime").value = toDateTimeLocalValue(minMax.max);
  }

  renderNews();
}

function renderNews() {
  const container = document.getElementById("newsContainer");
  const startValue = document.getElementById("startTime").value;
  const endValue = document.getElementById("endTime").value;
  const keyword = document.getElementById("keyword").value.trim().toLowerCase();

  const start = startValue ? new Date(startValue) : null;
  const end = endValue ? new Date(endValue) : null;

  const filtered = allNews.filter((item) => {
    const dt = parseDateTime(item.datetime);

    if (!dt || isNaN(dt.getTime())) return false;

    if (start && dt < start) return false;
    if (end && dt > end) return false;

    if (keyword) {
      const text = [
        item.datetime,
        item.category,
        item.category_name,
        item.headline,
        item.summary,
        Array.isArray(item.tags) ? item.tags.join(" ") : "",
      ].join(" ").toLowerCase();

      if (!text.includes(keyword)) return false;
    }

    return true;
  });

  filtered.sort((a, b) => {
    const da = parseDateTime(a.datetime);
    const db = parseDateTime(b.datetime);
    return da - db;
  });

  document.getElementById("visibleCount").textContent = filtered.length;

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="empty">
        沒有符合條件的新聞。<br/>
        目前底層資料時間範圍請看上方說明，或按「重設時間與搜尋」。
      </div>
    `;
    return;
  }

  const grouped = {};

  categoryOrder.forEach((category) => {
    grouped[category] = [];
  });

  filtered.forEach((item) => {
    const category = item.category || "economy";

    if (!grouped[category]) {
      grouped[category] = [];
    }

    grouped[category].push(item);
  });

  Object.keys(grouped).forEach((category) => {
    grouped[category].sort((a, b) => {
      const da = parseDateTime(a.datetime);
      const db = parseDateTime(b.datetime);
      return da - db;
    });
  });

  let html = "";

  categoryOrder.forEach((category) => {
    const items = grouped[category] || [];

    if (items.length === 0) {
      return;
    }

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
    <div class="timeline-item importance-${item.importance || 3}">
      <div class="timeline-dot"></div>
      <div class="timeline-time">${escapeHtml(item.datetime)}</div>
      <div class="timeline-headline">${escapeHtml(shortHeadline(item.headline))}</div>
    </div>
  `;
}

async function loadNews() {
  try {
    const res = await fetch("data/news.json?ts=" + Date.now());

    if (!res.ok) {
      throw new Error("Cannot load data/news.json");
    }

    const data = await res.json();

    allNews = data.items || [];
    briefPoints = data.brief_points || [];

    document.getElementById("generatedAt").textContent = data.generated_at || "--";

    updateDataRangeText();
    renderBrief();

    if (allNews.length === 0) {
      document.getElementById("visibleCount").textContent = "0";
      document.getElementById("newsContainer").innerHTML = `
        <div class="empty">
          data/news.json 已讀取，但 items 是空的。<br/>
          這代表 Gemini 可能把新聞全部刪掉，或 workflow 沒成功產生資料。
        </div>
      `;
      return;
    }

    resetFiltersToDataRange();
  } catch (err) {
    console.error(err);

    document.getElementById("newsContainer").innerHTML = `
      <div class="empty">
        讀取 data/news.json 失敗。<br/>
        請確認 GitHub Actions 已成功執行，且 repo 裡存在 data/news.json。
      </div>
    `;

    document.getElementById("briefList").innerHTML =
      "<li>讀取 summary 失敗。</li>";
  }
}

document.getElementById("startTime").addEventListener("change", renderNews);
document.getElementById("endTime").addEventListener("change", renderNews);
document.getElementById("keyword").addEventListener("input", renderNews);

document.getElementById("resetBtn").addEventListener("click", () => {
  resetFiltersToDataRange();
});

loadNews();