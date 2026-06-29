
let allNews = [];

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

function getSelectedCategories() {
  return Array.from(document.querySelectorAll(".category-filter input:checked"))
    .map((el) => el.value);
}

function stars(n) {
  return "★".repeat(n) + "☆".repeat(5 - n);
}

function renderNews() {
  const container = document.getElementById("newsContainer");
  const startValue = document.getElementById("startTime").value;
  const endValue = document.getElementById("endTime").value;
  const keyword = document.getElementById("keyword").value.trim().toLowerCase();
  const selectedCategories = getSelectedCategories();

  const start = startValue ? new Date(startValue) : null;
  const end = endValue ? new Date(endValue) : null;

  const filtered = allNews.filter((item) => {
    const dt = parseDateTime(item.datetime);
    if (!dt) return false;

    if (start && dt < start) return false;
    if (end && dt > end) return false;
    if (!selectedCategories.includes(item.category)) return false;

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

  container.innerHTML = filtered
    .map((item) => {
      const tags = Array.isArray(item.tags) ? item.tags : [];
      const categoryName = item.category_name || categoryNames[item.category] || item.category;

      return `
        <article class="news-card importance-${item.importance}">
          <div class="news-top">
            <div>
              <div class="news-time">${item.datetime}</div>
              <div class="stars">${stars(item.importance || 3)}</div>
            </div>
            <span class="category-badge">${categoryName}</span>
          </div>

          <h2 class="news-title">${escapeHtml(item.headline || "")}</h2>
          <p class="news-summary">${escapeHtml(item.summary || "")}</p>

          <div class="tags">
            ${tags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}
          </div>
        </article>
      `;
    })
    .join("");
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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

document.querySelectorAll(".category-filter input").forEach((el) => {
  el.addEventListener("change", renderNews);
});

document.getElementById("resetBtn").addEventListener("click", () => {
  const now = new Date();
  const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

  document.getElementById("startTime").value = toDateTimeLocalValue(sevenDaysAgo);
  document.getElementById("endTime").value = toDateTimeLocalValue(now);
  document.getElementById("keyword").value = "";

  document.querySelectorAll(".category-filter input").forEach((el) => {
    el.checked = true;
  });

  renderNews();
});

loadNews();
