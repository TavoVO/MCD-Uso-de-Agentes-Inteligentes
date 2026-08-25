const uploadForm = document.getElementById("uploadForm");
const pdfInput = document.getElementById("pdfInput");
const uploadMessage = document.getElementById("uploadMessage");
const uploadState = document.getElementById("uploadState");
const uploadCounts = document.getElementById("uploadCounts");
const uploadProgress = document.getElementById("uploadProgress");
const resetUploadBtn = document.getElementById("resetUploadBtn");
const chatForm = document.getElementById("chatForm");
const questionInput = document.getElementById("questionInput");
const chatStatus = document.getElementById("chatStatus");
const answerText = document.getElementById("answerText");
const sourcesList = document.getElementById("sourcesList");
const healthStatus = document.getElementById("healthStatus");
const healthDetails = document.getElementById("healthDetails");

let activeUploadId = Number(localStorage.getItem("ragPdfUploadId") || 0) || null;
let pollingTimer = null;

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setHealth(status, label, details) {
  healthStatus.className = `status-pill ${status}`;
  healthStatus.textContent = label;
  healthDetails.textContent = details;
}

function setUploadUi(upload) {
  if (!upload) {
    uploadState.textContent = "Sin documento activo";
    uploadCounts.textContent = "";
    uploadProgress.style.width = "0%";
    uploadMessage.textContent = "Todavía no se ha cargado ningún documento.";
    uploadMessage.className = "message muted";
    return;
  }

  uploadState.textContent = `Estado: ${upload.status}`;
  uploadCounts.textContent = `Páginas: ${upload.page_count} · Chunks: ${upload.chunk_count}`;

  if (upload.status === "completed") {
    uploadProgress.style.width = "100%";
    uploadMessage.textContent = `Documento listo: ${upload.original_filename}`;
    uploadMessage.className = "message";
  } else if (upload.status === "failed") {
    uploadProgress.style.width = "100%";
    uploadMessage.textContent = `Falló el procesamiento: ${upload.error_message || "error desconocido"}`;
    uploadMessage.className = "message";
  } else {
    uploadProgress.style.width = "65%";
    uploadMessage.textContent = `Procesando ${upload.original_filename}...`;
    uploadMessage.className = "message muted";
  }
}

async function fetchHealth() {
  try {
    const response = await fetch("/health");
    const data = await response.json();
    if (data.status === "ok") {
      setHealth("good", "Listo", `PostgreSQL y Ollama están disponibles. Modelos: ${data.llm_model} / ${data.embedding_model}`);
    } else {
      setHealth("warn", "Parcial", `Estado degradado. DB: ${data.database}. Ollama: ${data.ollama}`);
    }
  } catch (error) {
    setHealth("bad", "Sin conexión", `No se pudo consultar /health: ${error.message}`);
  }
}

async function pollUpload(uploadId) {
  if (pollingTimer) {
    clearInterval(pollingTimer);
  }

  const tick = async () => {
    try {
      const response = await fetch(`/api/uploads/${uploadId}`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const upload = await response.json();
      activeUploadId = upload.id;
      localStorage.setItem("ragPdfUploadId", String(upload.id));
      setUploadUi(upload);

      if (upload.status === "completed" || upload.status === "failed") {
        clearInterval(pollingTimer);
        pollingTimer = null;
        if (upload.status === "completed") {
          chatStatus.textContent = "Ya puedes hacer preguntas sobre el PDF.";
        }
      }
    } catch (error) {
      clearInterval(pollingTimer);
      pollingTimer = null;
      uploadMessage.textContent = `No se pudo consultar el estado del upload: ${error.message}`;
      uploadMessage.className = "message";
    }
  };

  await tick();
  pollingTimer = setInterval(tick, 1500);
}

async function loadStoredUpload() {
  if (!activeUploadId) {
    setUploadUi(null);
    chatStatus.textContent = "Sube un PDF para activar la búsqueda semántica.";
    return;
  }

  await pollUpload(activeUploadId);
}

async function clearUploadState() {
  if (!activeUploadId) {
    setUploadUi(null);
    localStorage.removeItem("ragPdfUploadId");
    chatStatus.textContent = "Estado limpiado. Ya puedes subir un PDF nuevo.";
    return;
  }

  try {
    const response = await fetch(`/api/uploads/${activeUploadId}`, {
      method: "DELETE",
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "No se pudo limpiar el estado.");
    }

    if (pollingTimer) {
      clearInterval(pollingTimer);
      pollingTimer = null;
    }

    activeUploadId = null;
    localStorage.removeItem("ragPdfUploadId");
    pdfInput.value = "";
    questionInput.value = "";
    answerText.textContent = "La respuesta aparecerá aquí.";
    sourcesList.innerHTML = '<p class="muted">Aquí se mostrarán los fragmentos que alimentaron la respuesta.</p>';
    uploadMessage.textContent = data.message;
    uploadMessage.className = "message";
    chatStatus.textContent = "Estado limpio. Sube un PDF nuevo para continuar.";
    setUploadUi(null);
  } catch (error) {
    chatStatus.textContent = `No se pudo limpiar el estado: ${error.message}`;
  }
}

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = pdfInput.files[0];

  if (!file) {
    uploadMessage.textContent = "Selecciona un PDF antes de subirlo.";
    uploadMessage.className = "message";
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  uploadMessage.textContent = "Subiendo archivo...";
  uploadMessage.className = "message muted";
  uploadState.textContent = "Cargando...";
  uploadProgress.style.width = "30%";

  try {
    const response = await fetch("/api/uploads", {
      method: "POST",
      body: formData,
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "No se pudo subir el archivo.");
    }

    uploadMessage.textContent = data.message;
    uploadMessage.className = "message";
    activeUploadId = data.upload_id;
    localStorage.setItem("ragPdfUploadId", String(data.upload_id));
    chatStatus.textContent = "Procesando el PDF. Espera a que termine para preguntar.";
    await pollUpload(data.upload_id);
  } catch (error) {
    uploadMessage.textContent = `Error: ${error.message}`;
    uploadMessage.className = "message";
    uploadProgress.style.width = "0%";
  }
});

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = questionInput.value.trim();

  if (!question) {
    chatStatus.textContent = "Escribe una pregunta para continuar.";
    return;
  }

  if (!activeUploadId) {
    chatStatus.textContent = "Primero sube y procesa un PDF.";
    return;
  }

  chatStatus.textContent = "Consultando el contenido recuperado...";
  answerText.textContent = "Pensando...";
  sourcesList.innerHTML = '<p class="muted">Recuperando fragmentos...</p>';

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        question,
        upload_id: activeUploadId,
      }),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "No se pudo generar la respuesta.");
    }

    answerText.textContent = data.answer;
    chatStatus.textContent = `Respuesta generada con ${data.sources.length} fragmentos recuperados.`;
    sourcesList.innerHTML = data.sources.map((source) => `
      <article class="source-item">
        <div class="source-meta">
          <span>Archivo: ${escapeHtml(source.file_name)}</span>
          <span>Página: ${source.page_number}</span>
          <span>Chunk: ${source.chunk_index}</span>
          <span>Distancia: ${source.distance.toFixed(4)}</span>
        </div>
        <p class="source-text">${escapeHtml(source.chunk_text)}</p>
      </article>
    `).join("");
  } catch (error) {
    answerText.textContent = "No se pudo responder la pregunta.";
    sourcesList.innerHTML = "";
    chatStatus.textContent = `Error: ${error.message}`;
  }
});

resetUploadBtn.addEventListener("click", clearUploadState);

fetchHealth();
loadStoredUpload();
