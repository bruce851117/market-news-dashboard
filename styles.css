let allNews = [];

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
    el.textContent = "底層資料時間範圍：--";
    return;
  }

  el.textContent =
    "底層資料時間範圍：" +
    formatDisplayTime(minMax.min) +
    " ～ " +
    formatDisplayTime(minMax.max);
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

  let html = "";

  categoryOrder.forEach((category) => {
    const items = grouped[category] || [];

    if (items.length === 0) {
      return;
    }

    html += `
      <section class="category-block category-${category}">
        <div class="category-header">
          <h2>${categoryNames[category] || category}</h2>
          <span>${items.length} 則</span>
        </div>

        <div class="compact-news-list">
          ${items.map(renderCompactNewsItem).join("")}
        </div>
      </section>
    `;
  });

  container.innerHTML = html;
}

function renderCompactNewsItem(item) {
  return `
    <div class="compact-news-item importance-${item.importance || 3}">
      <span class="compact-time">${escapeHtml(item.datetime)}</span>
      <span class="compact-headline">${escapeHtml(shortHeadline(item.headline))}</span>
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

    document.getElementById("generatedAt").textContent = data.generated_at || "--";

    updateDataRangeText();

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
  }
}

document.getElementById("startTime").addEventListener("change", renderNews);
document.getElementById("endTime").addEventListener("change", renderNews);
document.getElementById("keyword").addEventListener("input", renderNews);

document.getElementById("resetBtn").addEventListener("click", () => {
  resetFiltersToDataRange();
});

loadNews();
