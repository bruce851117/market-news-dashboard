let allNews = [];
let briefPoints = [];

const categoryOrder = [
Subtitles = {  "bond",
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

function makeFallbackBriefPoints() {
  if (!allNews || allNews.length === 0) {
    return [];
  }

  const sorted = [...allNews].sort((a, b) => {
    const ia = Number(a.importance || 3);

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

