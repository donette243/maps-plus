const map = L.map("map").setView(
  [55.751244, 37.618423],
  10
);

L.tileLayer(
  "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }
).addTo(map);

const form = document.querySelector("#meeting-form");
const statusBox = document.querySelector("#status");
const resultBox = document.querySelector("#result");
const modeSelect = document.querySelector("#mode");
const submitButton = form.querySelector("button");
let layerGroup = L.layerGroup().addTo(map);

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  submitButton.disabled = true;
  statusBox.className = "";
  statusBox.textContent =
    "Выполняется расчёт маршрутов…";
  resultBox.classList.add("hidden");
  resultBox.innerHTML = "";
  layerGroup.clearLayers();

  const formData = new FormData(form);
  const payload = {
    participant_a: formData
      .get("participantA")
      .trim(),
    participant_b: formData
      .get("participantB")
      .trim(),
    mode: formData.get("mode"),
  };

  try {
    const response = await fetch(
      "/api/meeting-points",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      }
    );

    const body = await response.json();

    if (!response.ok) {
      throw new Error(
        body.detail
          || "Во время расчёта произошла ошибка"
      );
    }

    renderResult(body);
    statusBox.textContent = "";
  } catch (error) {
    statusBox.className = "error";
    statusBox.textContent = error.message;
  } finally {
    submitButton.disabled = false;
  }
});

modeSelect.addEventListener("change", () => {
  updateButtonText();
});

function updateButtonText() {
  if (modeSelect.value === "transit") {
    submitButton.textContent =
      "Найти лучшую станцию встречи";
  } else {
    submitButton.textContent =
      "Найти лучшее место встречи";
  }
}

function renderResult(data) {
  const best = data.best_meeting_point;
  const isTransit = data.mode === "transit";
  const isEstimated =
    data.provider === "Расчётное время по расстоянию";
  const title = isTransit
    ? "Лучшая станция встречи"
    : "Лучшее место встречи";
  const meetingLabel = isTransit
    ? "Станция встречи"
    : "Место встречи";

  let providerMessage = "";

  if (isEstimated) {
    providerMessage = `
      <p class="provider-note">
        Время указано приблизительно:
        лимит бесплатного API 2GIS временно исчерпан.
      </p>
    `;
  } else {
    providerMessage = `
      <p class="provider-note">
        Источник маршрутов: ${escapeHtml(data.provider)}
      </p>
    `;
  }

  resultBox.innerHTML = `
    <h2>${title}</h2>
    <p>${escapeHtml(best.place.name)}</p>
    <div class="score">
      <span class="pill">
        Участник A · ${best.time_a_minutes} мин
      </span>
      <span class="pill">
        Участник B · ${best.time_b_minutes} мин
      </span>
      <span class="pill">
        Разница · ${best.difference_minutes} мин
      </span>
    </div>
    ${providerMessage}
  `;

  resultBox.classList.remove("hidden");

  const locations = [
    [
      data.origin_a,
      "Точка отправления A",
      "#3478f6",
    ],
    [
      data.origin_b,
      "Точка отправления B",
      "#8b5cf6",
    ],
    [
      best.place,
      meetingLabel,
      "#e53935",
    ],
  ];

  const bounds = [];

  for (const [place, label, color] of locations) {
    const coordinates = [
      place.latitude,
      place.longitude,
    ];
    bounds.push(coordinates);

    L.circleMarker(coordinates, {
      radius: label === meetingLabel ? 11 : 8,
      color,
      fillColor: color,
      fillOpacity: 0.9,
    })
      .bindPopup(
        `<strong>${escapeHtml(label)}</strong><br>` +
          escapeHtml(place.name)
      )
      .addTo(layerGroup);
  }

  L.polyline(bounds, {
    color: "#172032",
    dashArray: "6 8",
    weight: 2,
  }).addTo(layerGroup);

  map.fitBounds(bounds, {
    padding: [50, 50],
  });
}

function escapeHtml(value) {
  const element = document.createElement("div");
  element.textContent = value;
  return element.innerHTML;
}

updateButtonText();