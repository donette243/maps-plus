const DEFAULT_CENTER = [55.751244, 37.618423];
const DEFAULT_ZOOM = 10;
const REQUEST_TIMEOUT_MS = 45000;

const map = L.map("map").setView(
  DEFAULT_CENTER,
  DEFAULT_ZOOM
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

  const formData = new FormData(form);
  const participantA = String(
    formData.get("participantA") || ""
  ).trim();
  const participantB = String(
    formData.get("participantB") || ""
  ).trim();

  if (participantA.length < 2) {
    showError(
      "Укажите начальную точку первого участника"
    );
    return;
  }

  if (participantB.length < 2) {
    showError(
      "Укажите начальную точку второго участника"
    );
    return;
  }

  if (
    participantA.toLocaleLowerCase("ru")
    === participantB.toLocaleLowerCase("ru")
  ) {
    showError(
      "Начальные точки участников должны отличаться"
    );
    return;
  }

  const payload = {
    participant_a: participantA,
    participant_b: participantB,
    mode: String(formData.get("mode") || "transit"),
  };
  const controller = new AbortController();
  const timeoutId = window.setTimeout(
    () => controller.abort(),
    REQUEST_TIMEOUT_MS
  );

  setLoadingState(true);

  try {
    const response = await fetch(
      "/api/meeting-points",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      }
    );
    const body = await readResponseBody(response);

    if (!response.ok) {
      throw new Error(
        extractErrorMessage(
          body,
          "Во время расчёта произошла ошибка"
        )
      );
    }

    renderResult(body);
    statusBox.className = "";
    statusBox.textContent = "";
  } catch (error) {
    if (
      error instanceof DOMException
      && error.name === "AbortError"
    ) {
      showError(
        "Расчёт занял слишком много времени. "
        + "Попробуйте ещё раз."
      );
    } else if (error instanceof TypeError) {
      showError(
        "Не удалось соединиться с сервером приложения"
      );
    } else if (error instanceof Error) {
      showError(error.message);
    } else {
      showError(
        "Во время расчёта произошла ошибка"
      );
    }
  } finally {
    window.clearTimeout(timeoutId);
    setLoadingState(false);
  }
});

modeSelect.addEventListener("change", () => {
  updateButtonText();
});

function setLoadingState(isLoading) {
  submitButton.disabled = isLoading;

  if (isLoading) {
    statusBox.className = "";
    statusBox.textContent =
      "Выполняется расчёт маршрутов…";
    resultBox.classList.add("hidden");
    resultBox.innerHTML = "";
    layerGroup.clearLayers();
  }
}

function showError(message) {
  statusBox.className = "error";
  statusBox.textContent = message;
}

async function readResponseBody(response) {
  const text = await response.text();

  if (!text) {
    return {};
  }

  try {
    return JSON.parse(text);
  } catch {
    if (!response.ok) {
      return {
        detail: (
          "Сервер вернул некорректный ответ"
        ),
      };
    }

    throw new Error(
      "Сервер вернул некорректный ответ"
    );
  }
}

function extractErrorMessage(body, fallback) {
  if (
    body
    && typeof body.detail === "string"
    && body.detail.trim()
  ) {
    return body.detail;
  }

  if (body && Array.isArray(body.detail)) {
    const messages = body.detail
      .map((item) => {
        if (
          item
          && typeof item.msg === "string"
        ) {
          return item.msg;
        }

        return null;
      })
      .filter(Boolean);

    if (messages.length > 0) {
      return messages.join(". ");
    }
  }

  return fallback;
}

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
  const isEstimated = (
    data.provider
    === "Расчётное время по расстоянию"
  );
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
        внешний сервис маршрутов временно недоступен.
      </p>
    `;
  } else {
    providerMessage = `
      <p class="provider-note">
        Источник маршрутов:
        ${escapeHtml(data.provider)}
      </p>
    `;
  }

  resultBox.innerHTML = `
    <h2>${title}</h2>
    <p>${escapeHtml(best.place.name)}</p>
    <div class="score">
      <span class="pill">
        Участник A ·
        ${best.time_a_minutes} мин
      </span>
      <span class="pill">
        Участник B ·
        ${best.time_b_minutes} мин
      </span>
      <span class="pill">
        Разница ·
        ${best.difference_minutes} мин
      </span>
    </div>
    ${providerMessage}
  `;

  resultBox.classList.remove("hidden");

  const locations = [
    {
      place: data.origin_a,
      label: "Точка отправления A",
      color: "#3478f6",
    },
    {
      place: data.origin_b,
      label: "Точка отправления B",
      color: "#8b5cf6",
    },
    {
      place: best.place,
      label: meetingLabel,
      color: "#e53935",
    },
  ];
  const bounds = locations.map(
    ({ place }) => [
      place.latitude,
      place.longitude,
    ]
  );

  for (const {
    place,
    label,
    color,
  } of locations) {
    const coordinates = [
      place.latitude,
      place.longitude,
    ];

    L.circleMarker(coordinates, {
      radius: label === meetingLabel ? 11 : 8,
      color,
      fillColor: color,
      fillOpacity: 0.9,
    })
      .bindPopup(
        `<strong>${escapeHtml(label)}</strong><br>`
        + escapeHtml(place.name)
      )
      .addTo(layerGroup);
  }

  const meetingCoordinates = [
    best.place.latitude,
    best.place.longitude,
  ];

  for (const origin of [
    data.origin_a,
    data.origin_b,
  ]) {
    L.polyline(
      [
        [
          origin.latitude,
          origin.longitude,
        ],
        meetingCoordinates,
      ],
      {
        color: "#172032",
        dashArray: "6 8",
        weight: 2,
      }
    ).addTo(layerGroup);
  }

  map.fitBounds(bounds, {
    padding: [50, 50],
  });
}

function escapeHtml(value) {
  const element = document.createElement("div");
  element.textContent = String(value ?? "");
  return element.innerHTML;
}

updateButtonText();