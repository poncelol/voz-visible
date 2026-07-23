(function () {
  "use strict";

  // ============================================================
  // 1. ACCESIBILIDAD: TAMAÑO DE TEXTO Y ALTO CONTRASTE
  // ============================================================
  var step = 1;
  var btnMas = document.getElementById("btn-font-mas");
  var btnMenos = document.getElementById("btn-font-menos");
  var btnContraste = document.getElementById("btn-contraste");

  if (btnMas) {
    btnMas.addEventListener("click", function () {
      step = Math.min(1.4, step + 0.1);
      document.documentElement.style.setProperty("--step", step.toFixed(2));
    });
  }
  if (btnMenos) {
    btnMenos.addEventListener("click", function () {
      step = Math.max(0.85, step - 0.1);
      document.documentElement.style.setProperty("--step", step.toFixed(2));
    });
  }
  if (btnContraste) {
    btnContraste.addEventListener("click", function () {
      var on = document.documentElement.classList.toggle("contraste");
      btnContraste.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  // ============================================================
  // 2. ORIGEN DE LA IMAGEN: GENERAR / SUBIR
  // ============================================================
  var srcGenerar = document.getElementById("src-generar");
  var srcSubir = document.getElementById("src-subir");
  var bloqueGenerar = document.getElementById("bloque-generar");
  var bloqueSubir = document.getElementById("bloque-subir");
  var inputOrigen = document.getElementById("input-origen");

  function elegirOrigen(valor) {
    inputOrigen.value = valor;
    var esGenerar = valor === "generar";
    srcGenerar.setAttribute("aria-pressed", esGenerar ? "true" : "false");
    srcSubir.setAttribute("aria-pressed", esGenerar ? "false" : "true");
    bloqueGenerar.style.display = esGenerar ? "" : "none";
    bloqueSubir.style.display = esGenerar ? "none" : "";
  }

  if (srcGenerar && srcSubir) {
    srcGenerar.addEventListener("click", function () { elegirOrigen("generar"); });
    srcSubir.addEventListener("click", function () { elegirOrigen("subir"); });
  }

  // ============================================================
  // 3. CONFIRMACIÓN VISUAL AL ENVIAR EL FORMULARIO
  // ============================================================
  var form = document.getElementById("form-config");
  if (form) {
    form.addEventListener("submit", function () {
      var btn = form.querySelector(".run-btn");
      if (btn && !btn.disabled) {
        btn.disabled = true;
        btn.textContent = "Generando… puede tardar unos segundos";
      }
    });
  }

  // ============================================================
  // 4. CÁMARA EN VIVO CON DEEPSEEK
  // ============================================================
  var video = document.getElementById("webcam");
  var canvas = document.getElementById("canvas");
  var btnStart = document.getElementById("btnStart");
  var btnStop = document.getElementById("btnStop");
  var statusDot = document.getElementById("statusDot");
  var statusText = document.getElementById("statusText");
  var descripcionText = document.getElementById("descripcionText");

  // Si no existen los elementos de cámara, salimos
  if (!video || !btnStart || !btnStop) {
    console.log("ℹ️ Elementos de cámara no encontrados");
    return;
  }

  var stream = null;
  var intervalId = null;
  var isRunning = false;
  var analizando = false;

  // ============================================================
  // 4.1 FUNCIONES DE ESTADO
  // ============================================================
  function setStatus(active, message) {
    if (statusDot) {
      statusDot.className = "dot " + (active ? "active" : "inactive");
    }
    if (statusText) {
      statusText.textContent = message || (active ? "Sistema activo" : "Sistema inactivo");
    }
  }

  function setDescripcion(texto) {
    if (descripcionText) {
      descripcionText.textContent = texto;
    }
  }

  // ============================================================
  // 4.2 CAPTURAR Y PROCESAR IMAGEN
  // ============================================================
  function captureAndProcess() {
    if (!isRunning || analizando) return;

    analizando = true;
    setStatus(true, "📷 Capturando...");

    try {
      // Configurar canvas
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      var ctx = canvas.getContext("2d");
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      // Convertir a base64 con formato correcto
      var imageData = canvas.toDataURL("image/jpeg", 0.8);

      // Enviar al servidor
      fetch("/analizar-camara", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          imagen: imageData,
          detalle: false // Cambiar a true para análisis detallado
        }),
        timeout: 15000 // 15 segundos de timeout
      })
      .then(function(response) {
        if (!response.ok) {
          return response.json().then(function(data) {
            throw new Error(data.mensaje || "Error " + response.status);
          });
        }
        return response.json();
      })
      .then(function(data) {
        analizando = false;
        if (data.error) {
          console.error("Error del servidor:", data.mensaje);
          setDescripcion("⚠️ " + data.mensaje);
          setStatus(false, "Error: " + data.mensaje);
        } else if (data.descripcion) {
          setDescripcion(data.descripcion);
          setStatus(true, "✅ Analizado correctamente");
        } else {
          setDescripcion("⚠️ No se recibió descripción");
          setStatus(false, "Respuesta vacía");
        }
      })
      .catch(function(error) {
        analizando = false;
        console.error("Error en fetch:", error);
        setDescripcion("❌ Error de conexión. Reintentando...");
        setStatus(false, "Error de conexión");
      });

    } catch (error) {
      analizando = false;
      console.error("Error capturando imagen:", error);
      setDescripcion("❌ Error al capturar la imagen");
      setStatus(false, "Error en cámara");
    }
  }

  // ============================================================
  // 4.3 ANÁLISIS DETALLADO
  // ============================================================
  function captureAndProcessDetailed() {
    if (!isRunning || analizando) return;

    analizando = true;
    setStatus(true, "🔬 Analizando en detalle...");

    try {
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      var ctx = canvas.getContext("2d");
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      var imageData = canvas.toDataURL("image/jpeg", 0.8);

      fetch("/analizar-camara", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          imagen: imageData,
          detalle: true
        }),
        timeout: 20000
      })
      .then(function(response) {
        if (!response.ok) {
          return response.json().then(function(data) {
            throw new Error(data.mensaje || "Error " + response.status);
          });
        }
        return response.json();
      })
      .then(function(data) {
        analizando = false;
        if (data.error) {
          setDescripcion("⚠️ " + data.mensaje);
          setStatus(false, "Error: " + data.mensaje);
        } else if (data.descripcion) {
          setDescripcion(data.descripcion);
          setStatus(true, "✅ Análisis detallado completado");
        } else {
          setDescripcion("⚠️ No se recibió descripción");
          setStatus(false, "Respuesta vacía");
        }
      })
      .catch(function(error) {
        analizando = false;
        console.error("Error en análisis detallado:", error);
        setDescripcion("❌ Error en análisis detallado");
        setStatus(false, "Error");
      });

    } catch (error) {
      analizando = false;
      console.error("Error:", error);
      setDescripcion("❌ Error al capturar");
      setStatus(false, "Error en cámara");
    }
  }

  // ============================================================
  // 4.4 INICIAR CÁMARA
  // ============================================================
  btnStart.addEventListener("click", function() {
    if (isRunning) return;

    // Verificar si estamos en producción
    var enProduccion = document.body.dataset.produccion === "true";

    if (enProduccion) {
      setDescripcion("📌 La cámara en vivo no está disponible en producción.");
      setStatus(false, "No disponible en producción");
      return;
    }

    // Verificar que la API de DeepSeek está configurada
    fetch("/api/estado")
      .then(function(response) { return response.json(); })
      .then(function(data) {
        if (!data.deepseek || !data.deepseek.configurada) {
          setDescripcion("❌ DeepSeek no está configurado. Contacta al administrador.");
          setStatus(false, "API no configurada");
          return;
        }
        iniciarCamara();
      })
      .catch(function(error) {
        console.error("Error verificando estado:", error);
        setDescripcion("❌ Error verificando configuración");
        setStatus(false, "Error");
      });
  });

  function iniciarCamara() {
    var constraints = {
      video: {
        facingMode: "environment",
        width: { ideal: 640 },
        height: { ideal: 480 }
      }
    };

    navigator.mediaDevices.getUserMedia(constraints)
      .then(function(mediaStream) {
        stream = mediaStream;
        video.srcObject = stream;
        return video.play();
      })
      .then(function() {
        isRunning = true;
        btnStart.disabled = true;
        btnStop.disabled = false;
        setStatus(true, "✅ Cámara activa");
        setDescripcion("📷 Observando entorno...");

        // Iniciar análisis automático cada 3 segundos
        if (intervalId) clearInterval(intervalId);
        intervalId = setInterval(captureAndProcess, 3000);

        // Análisis inmediato
        setTimeout(captureAndProcess, 500);
      })
      .catch(function(error) {
        console.error("Error accediendo a la cámara:", error);
        setStatus(false, "❌ Error al acceder a la cámara");
        setDescripcion("❌ No se pudo acceder a la cámara. Verifica permisos.");
        btnStart.disabled = false;
      });
  }

  // ============================================================
  // 4.5 DETENER CÁMARA
  // ============================================================
  btnStop.addEventListener("click", function() {
    detenerCamara();
  });

  function detenerCamara() {
    // Detener intervalo
    if (intervalId) {
      clearInterval(intervalId);
      intervalId = null;
    }

    // Detener tracks de la cámara
    if (stream) {
      stream.getTracks().forEach(function(track) { track.stop(); });
      stream = null;
    }

    // Limpiar video
    if (video) {
      video.srcObject = null;
    }

    isRunning = false;
    analizando = false;
    btnStart.disabled = false;
    btnStop.disabled = true;
    setStatus(false, "⏹️ Cámara detenida");
    setDescripcion("Presiona 'Iniciar Cámara' para comenzar a describir tu entorno...");
  }

  // ============================================================
  // 4.6 BOTONES ADICIONALES (Si existen)
  // ============================================================
  // Botón para análisis detallado si existe
  var btnDetalle = document.getElementById("btnDetalle");
  if (btnDetalle) {
    btnDetalle.addEventListener("click", function() {
      if (isRunning) {
        captureAndProcessDetailed();
      } else {
        setDescripcion("⚠️ Inicia la cámara primero");
      }
    });
  }

  // ============================================================
  // 4.7 LIMPIEZA AL SALIR DE LA PÁGINA
  // ============================================================
  window.addEventListener("beforeunload", function() {
    detenerCamara();
  });

  // ============================================================
  // 4.8 DETECTAR CUANDO LA PÁGINA SE VUELVE VISIBLE
  // ============================================================
  document.addEventListener("visibilitychange", function() {
    if (document.hidden && isRunning) {
      // Pausar análisis cuando la página no está visible
      if (intervalId) {
        clearInterval(intervalId);
        intervalId = null;
      }
    } else if (!document.hidden && isRunning) {
      // Reanudar análisis cuando la página vuelve a ser visible
      if (!intervalId) {
        intervalId = setInterval(captureAndProcess, 3000);
      }
    }
  });

  console.log("✅ Voz Visible - app.js cargado correctamente");
})();