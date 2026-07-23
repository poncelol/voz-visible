(function () {
  "use strict";

  // --- tamaño de texto / alto contraste ---
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

  // --- origen de la imagen: generar / subir ---
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

  // --- confirmación visual mientras se procesa en el servidor ---
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
})();
