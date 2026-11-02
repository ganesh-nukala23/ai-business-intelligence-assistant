// Talks to the backend. No answers are hardcoded here: everything shown comes from /api/ask.
const questionBox = document.getElementById("question");
const loadingBox = document.getElementById("loading");
const errorBox = document.getElementById("error");
const resultBox = document.getElementById("result");

function show(element, visible) {
  element.classList.toggle("hidden", !visible);
}

// Build a table from a list of objects (textContent is used, so no HTML injection)
function makeTable(rows) {
  const table = document.createElement("table");
  const columns = Object.keys(rows[0]);
  const headerRow = table.insertRow();
  columns.forEach(function (name) {
    const th = document.createElement("th");
    th.textContent = name;
    headerRow.appendChild(th);
  });
  rows.forEach(function (row) {
    const tr = table.insertRow();
    columns.forEach(function (name) {
      tr.insertCell().textContent = row[name] === null ? "-" : row[name];
    });
  });
  return table;
}

function renderData(data) {
  const container = document.getElementById("data");
  container.innerHTML = "";
  const simpleRows = [];
  Object.keys(data).forEach(function (key) {
    const value = data[key];
    if (Array.isArray(value) && value.length > 0 && typeof value[0] === "object") {
      const title = document.createElement("strong");
      title.textContent = key;
      container.appendChild(title);
      container.appendChild(makeTable(value));
    } else {
      simpleRows.push({ item: key, value: value === null ? "n/a" : value });
    }
  });
  if (simpleRows.length > 0) {
    container.insertBefore(makeTable(simpleRows), container.firstChild);
  }
}

async function askQuestion() {
  const question = questionBox.value.trim();
  show(errorBox, false);
  show(resultBox, false);
  if (question === "") {
    errorBox.textContent = "Please type a question first.";
    show(errorBox, true);
    return;
  }
  show(loadingBox, true);
  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question }),
    });
    const body = await response.json();
    if (!response.ok) {
      errorBox.textContent = body.message || "Something went wrong.";
      show(errorBox, true);
    } else {
      document.getElementById("answer").textContent = body.answer;
      const who = body.interpreted_by === "llm" ? "LLM" : "rule-based fallback (not an LLM)";
      document.getElementById("meta").textContent = "Interpreted by: " + who + ". " + (body.ai_note || "");
      document.getElementById("sql").textContent = body.sql;
      renderData(body.data);
      show(resultBox, true);
    }
  } catch (err) {
    errorBox.textContent = "Could not reach the server. Is it running?";
    show(errorBox, true);
  }
  show(loadingBox, false);
}

document.getElementById("ask-button").addEventListener("click", askQuestion);
questionBox.addEventListener("keydown", function (event) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    askQuestion();
  }
});
document.querySelectorAll(".example").forEach(function (button) {
  button.addEventListener("click", function () {
    questionBox.value = button.textContent;
    askQuestion();
  });
});
