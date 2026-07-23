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
  // 4. CÁMARA EN VIVO (CORREGIDO PARA TU HTML)
  // ============================================================
  var video = document.getElementById("videoCamara");
  var canvas = document.getElementById("canvasCamara");
  var btnStart = document.getElementById("btnIniciarCamara");
  var btnStop = document.getElementById("btnDetenerCamara");
  var btnCapturar = document.getElementById("btnCapturarCamara");
  var statusCamara = document.getElementById("statusCamara");
  var descripcionCamara = document.getElementById("descripcionCamara");
  var audioContainer = document.getElementById("audioCamaraContainer");
  var audioPlayer = document.getElementById("audioCamara");
  var modeloCamara = document.getElementById("modeloCamara");

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
    if (statusCamara) {
      if (active) {
        statusCamara.className = "status-badge status-active";
        statusCamara.textContent = message || "🟢 Activa";
      } else {
        statusCamara.className = "status-badge status-inactive";
        statusCamara.textContent = message || "⚪ Inactiva";
      }
    }
  }

  function setDescripcion(texto) {
    if (descripcionCamara) {
      descripcionCamara.innerHTML = `<p>${texto}</p>`;
    }
  }

  function setModelo(texto, esIA) {
    if (modeloCamara) {
      modeloCamara.textContent = texto;
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
      // Configurar canvas con las dimensiones del video
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      var ctx = canvas.getContext("2d");
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      // Generar la imagen en base64
      var imageData = canvas.toDataURL("image/jpeg", 0.8);

      // Enviar al servidor
      fetch("/api/camara/stream", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          imagen: imageData
        }),
        signal: AbortSignal.timeout(15000)
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
          setStatus(false, "Error");
          setModelo("Error", false);
        } else if (data.descripcion) {
          setDescripcion(data.descripcion);
          setStatus(true, "✅ Analizado correctamente");
          
          // Mostrar modelo usado
          if (data.modelo) {
            setModelo(data.modelo, data.es_ia);
          } else if (data.es_ia) {
            setModelo("🧠 IA activa", true);
          } else {
            setModelo("⚠️ Modo técnico", false);
          }
          
          // Reproducir audio si existe
          if (data.audio && audioContainer && audioPlayer) {
            audioContainer.style.display = "block";
            var audioBlob = base64ToBlob(data.audio, "audio/mp3");
            var audioUrl = URL.createObjectURL(audioBlob);
            audioPlayer.src = audioUrl;
            audioPlayer.play().catch(function(e) {
              console.warn("Error al reproducir audio:", e);
            });
          }
        } else {
          setDescripcion("⚠️ No se recibió descripción");
          setStatus(false, "Respuesta vacía");
        }
      })
      .catch(function(error) {
        analizando = false;
        console.error("Error en fetch:", error);
        if (error.name === "TimeoutError" || error.name === "AbortError") {
          setDescripcion("⏳ Tiempo de espera agotado. Reintentando...");
          setStatus(false, "Timeout");
        } else {
          setDescripcion("❌ Error de conexión. Reintentando...");
          setStatus(false, "Error de conexión");
        }
      });

    } catch (error) {
      analizando = false;
      console.error("Error capturando imagen:", error);
      setDescripcion("❌ Error al capturar la imagen");
      setStatus(false, "Error en cámara");
    }
  }

  // Función para convertir base64 a Blob
  function base64ToBlob(base64, mimeType) {
    var byteCharacters = atob(base64);
    var byteArrays = [];
    for (var i = 0; i < byteCharacters.length; i++) {
      byteArrays.push(byteCharacters.charCodeAt(i));
    }
    var byteArray = new Uint8Array(byteArrays);
    return new Blob([byteArray], { type: mimeType });
  }

  // ============================================================
  // 4.3 INICIAR CÁMARA
  // ============================================================
  btnStart.addEventListener("click", function() {
    if (isRunning) return;

    var constraints = {
      video: {
        facingMode: "environment",
        width: { ideal: 640 },
        height: { ideal: 480 }
      },
      audio: false
    };

    setStatus(true, "📷 Solicitando acceso a la cámara...");
    setDescripcion("Solicitando permisos de cámara...");
    setModelo("Conectando...", false);

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
        if (btnCapturar) btnCapturar.disabled = false;
        setStatus(true, "✅ Cámara activa");
        setDescripcion("📷 Observando entorno...");
        setModelo("Conectado", false);

        // Iniciar análisis automático cada 3 segundos
        if (intervalId) clearInterval(intervalId);
        intervalId = setInterval(captureAndProcess, 3000);

        // Análisis inmediato después de iniciar
        setTimeout(captureAndProcess, 500);

        console.log("✅ Cámara iniciada correctamente");
      })
      .catch(function(error) {
        console.error("Error accediendo a la cámara:", error);
        setStatus(false, "❌ Error al acceder a la cámara");
        
        var mensajeError = "❌ No se pudo acceder a la cámara. ";
        if (error.name === "NotAllowedError" || error.name === "PermissionDeniedError") {
          mensajeError += "Permiso denegado. Verifica los permisos en el navegador.";
        } else if (error.name === "NotFoundError" || error.name === "DevicesNotFoundError") {
          mensajeError += "No se encontró ninguna cámara conectada.";
        } else if (error.name === "NotReadableError" || error.name === "TrackStartError") {
          mensajeError += "La cámara está siendo usada por otra aplicación.";
        } else {
          mensajeError += "Error: " + error.message;
        }
        setDescripcion(mensajeError);
        setModelo("Error", false);
        btnStart.disabled = false;
      });
  });

  // ============================================================
  // 4.4 DETENER CÁMARA
  // ============================================================
  btnStop.addEventListener("click", function() {
    detenerCamara();
  });

  function detenerCamara() {
    // Detener intervalo de análisis
    if (intervalId) {
      clearInterval(intervalId);
      intervalId = null;
    }

    // Detener todos los tracks de la cámara
    if (stream) {
      stream.getTracks().forEach(function(track) { 
        track.stop(); 
      });
      stream = null;
    }

    // Limpiar el video
    if (video) {
      video.srcObject = null;
    }

    isRunning = false;
    analizando = false;
    btnStart.disabled = false;
    btnStop.disabled = true;
    if (btnCapturar) btnCapturar.disabled = true;
    setStatus(false, "⏹️ Cámara detenida");
    setDescripcion("Presiona 'Iniciar Cámara' para comenzar a describir tu entorno...");
    setModelo("Detenido", false);
    
    // Ocultar audio
    if (audioContainer) {
      audioContainer.style.display = "none";
    }
    
    console.log("⏹️ Cámara detenida");
  }

  // ============================================================
  // 4.5 BOTÓN CAPTURAR MANUAL
  // ============================================================
  if (btnCapturar) {
    btnCapturar.addEventListener("click", function() {
      if (isRunning) {
        captureAndProcess();
      } else {
        setDescripcion("⚠️ Inicia la cámara primero");
        setStatus(false, "Cámara no iniciada");
      }
    });
  }

  // ============================================================
  // 4.6 LIMPIEZA AL SALIR DE LA PÁGINA
  // ============================================================
  window.addEventListener("beforeunload", function() {
    detenerCamara();
  });

  // ============================================================
  // 4.7 DETECTAR CUANDO LA PÁGINA SE VUELVE VISIBLE/OCULTA
  // ============================================================
  document.addEventListener("visibilitychange", function() {
    if (document.hidden && isRunning) {
      // Pausar análisis cuando la página no está visible
      if (intervalId) {
        clearInterval(intervalId);
        intervalId = null;
        console.log("⏸️ Análisis pausado (página oculta)");
      }
    } else if (!document.hidden && isRunning) {
      // Reanudar análisis cuando la página vuelve a ser visible
      if (!intervalId) {
        intervalId = setInterval(captureAndProcess, 3000);
        console.log("▶️ Análisis reanudado (página visible)");
        setTimeout(captureAndProcess, 500);
      }
    }
  });

  // ============================================================
  // 4.8 RECUPERAR CÁMARA SI SE PIERDE LA CONEXIÓN
  // ============================================================
  if (video) {
    video.addEventListener("pause", function() {
      if (isRunning && stream) {
        console.log("⚠️ Video pausado inesperadamente. Intentando reanudar...");
        video.play().catch(function(e) {
          console.error("Error al reanudar video:", e);
        });
      }
    });
  }

  console.log("✅ Voz Visible - app.js cargado correctamente");
  console.log("📷 Para usar la cámara, presiona 'Iniciar Cámara'");
})();