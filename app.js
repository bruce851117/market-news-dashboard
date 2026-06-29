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

const categoryDescriptions = {
  bond: "利率、美債、殖利率、信用市場、財政部標售",
  equity: "主要股指、科技龍頭、AI供應鏈、重大財報",
  central_bank: "Fed、ECB、BOJ、BOE、PBOC、官員談話與政策預期",
  economy: "CPI、PPI、PMI、GDP、就業、薪資、消費、關稅與財政政策",
  war: "戰爭、地緣政治、制裁、中東、俄烏、台海與軍事衝突",
  commodity: "原油、天然氣、黃金、銅、能源與大宗商品",
};

function parseDateTime(s) {
  if (!s) return null;
  return new Date(s.replace(" ", "T"));
}

function toDateTimeLocalValue(date) {
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

function stars(n) {
  return "★".repeat(n) + "☆".repeat(5 - n);
}

function escapeHtml(str) {
  return String(str || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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
    if (!dt) return false;

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
    container.innerHTML = `<div class="empty">沒有符合條件的新聞</div>`;
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
          <div>
            <h2>${categoryNames[category] || category}</h2>
            <p>${categoryDescriptions[category] || ""}</p>
          </div>
          <div class="category-count">${items.length} 則</div>
        </div>

        <div class="category-news-list">
          ${items.map(renderNewsCard).join("")}
        </div>
      </section>
    `;
  });

  container.innerHTML = html;
}

function renderNewsCard(item) {
  const tags = Array.isArray(item.tags) ? item.tags : [];

  return `
    <article class="news-card importance-${item.importance || 3}">
      <div class="news-top">
        <div>
          <div class="news-time">${escapeHtml(item.datetime)}</div>
          <div class="stars">${stars(item.importance || 3)}</div>
        </div>
      </div>

      <h3 class="news-title">${escapeHtml(item.headline)}</h3>
      <p class="news-summary">${escapeHtml(item.summary)}</p>

      <div class="tags">
        ${tags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}
      </div>
    </article>
  `;
}

async function loadNews() {
  try {
    const res = await fetch("data/news.json?ts=" + Date.now());
    const data = await res.json();

    allNews = data.items || [];
    document.getElementById("generatedAt").textContent = data.generated_at || "--";

    const now = new Date();
    const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

    document.getElementById("startTime").value = toDateTimeLocalValue(sevenDaysAgo);
    document.getElementById("endTime").value = toDateTimeLocalValue(now);

    renderNews();
  } catch (err) {
    console.error(err);
    document.getElementById("newsContainer").innerHTML =
      `<div class="empty">讀取 data/news.json 失敗，請先執行 GitHub Actions。</div>`;
  }
}

document.getElementById("startTime").addEventListener("change", renderNews);
document.getElementById("endTime").addEventListener("change", renderNews);
document.getElementById("keyword").addEventListener("input", renderNews);

document.getElementById("resetBtn").addEventListener("click", () => {
  const now = new Date();
  const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

  document.getElementById("startTime").value = toDateTimeLocalValue(sevenDaysAgo);
  document.getElementById("endTime").value = toDateTimeLocalValue(now);
  document.getElementById("keyword").value = "";

  renderNews();
});

loadNews();
