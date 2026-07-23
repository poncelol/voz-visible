# ============================================================
# Voz Visible — Generador de audiodescripciones inclusivas
# Migración a Flask del notebook original de Colab.
#
# Pensado para que una TERCERA PERSONA (familiar, docente,
# persona cuidadora, profesional de accesibilidad) prepare una
# audiodescripción y se la comparta a la persona ciega, con baja
# visión o con discapacidad cognitiva a la que acompaña.
#
# CONFIGURACIÓN:
#   1. pip install -r requirements.txt
#   2. copia .env.example a .env y pon tu GEMINI_API_KEY
#      (gratis en https://aistudio.google.com/apikey)
#   3. python app.py   (o gunicorn app:app en producción)
# ============================================================

import os
import uuid
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, url_for
from gtts import gTTS
from PIL import Image

from google import genai

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
GENERATED_DIR = BASE_DIR / "static" / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024  # 12 MB por subida

# ============================================================
# IDIOMAS SOPORTADOS
# código app -> (nombre visible, nombre largo para el prompt de traducción, código gTTS)
# ============================================================
IDIOMAS = {
    "es": {"nombre": "Español",   "traduccion": "español",   "gtts": "es"},
    "en": {"nombre": "Inglés",    "traduccion": "inglés",    "gtts": "en"},
    "fr": {"nombre": "Francés",   "traduccion": "francés",   "gtts": "fr"},
    "de": {"nombre": "Alemán",    "traduccion": "alemán",    "gtts": "de"},
    "it": {"nombre": "Italiano",  "traduccion": "italiano",  "gtts": "it"},
    "pt": {"nombre": "Portugués", "traduccion": "portugués", "gtts": "pt"},
    "ja": {"nombre": "Japonés",   "traduccion": "japonés",   "gtts": "ja"},
    "zh": {"nombre": "Chino",     "traduccion": "chino",     "gtts": "zh-CN"},
}

# ============================================================
# PROMPTS (idénticos en espíritu a los del notebook original)
# ============================================================
PROMPT_AUDIODESCRIPCION_ESTANDAR = """
Describe esta imagen para una persona ciega o con baja visión.
Sigue estas reglas:
1. Máximo 4 frases, lenguaje claro y directo.
2. Empieza por lo más importante en primer plano.
3. Menciona después elementos relevantes del fondo.
4. Incluye colores y detalles visuales solo si aportan información útil.
5. Si hay texto visible en la imagen (carteles, pantallas), transcríbelo.
6. No hagas interpretaciones subjetivas. Describe solo lo objetivamente visible.
7. No empieces con "esta imagen muestra"; ve directo al contenido.
"""

PROMPT_AUDIODESCRIPCION_SIMPLIFICADA = """
Describe esta imagen de forma MUY SIMPLE, para personas que necesitan
un lenguaje claro y directo.
Reglas OBLIGATORIAS:
1. MÁXIMO 3 frases muy cortas (una idea por frase).
2. Usa palabras comunes, nada complicado.
3. Empieza diciendo QUÉ es lo principal (ejemplo: "Un perro").
4. Di DÓNDE están las cosas (ejemplo: "El perro está en el sofá").
5. Si hay colores importantes, menciónalos (ejemplo: "El perro es marrón").
6. Si hay texto, transcríbelo tal cual.
7. Nada de explicaciones ni sentimientos. Solo hechos.

Ejemplo correcto: "Hay una cocina grande y luminosa. Dos personas cocinan juntas.
La mujer revuelve una olla. El hombre pela verduras."

Ejemplo INCORRECTO: "Una hermosa cocina moderna, donde dos personas colaboran
con entusiasmo en la preparación de ingredientes frescos y orgánicos..."
"""

PROMPT_TRADUCCION = """
Traduce el siguiente texto al idioma {idioma_destino}.
Mantén el tono accesible y directo.
Responde SOLO con el texto traducido, sin explicaciones.

Texto original:
{texto}
"""

MODELO_GEMINI = "gemini-2.5-flash"


# ============================================================
# FUNCIONES (equivalentes a las del notebook)
# ============================================================
def describir_imagen(ruta_imagen: Path, nivel_complejidad: str = "estándar") -> str:
    """Envía la imagen a Gemini y devuelve la audiodescripción en español."""
    imagen = Image.open(ruta_imagen)
    prompt = (
        PROMPT_AUDIODESCRIPCION_SIMPLIFICADA
        if nivel_complejidad == "simplificada"
        else PROMPT_AUDIODESCRIPCION_ESTANDAR
    )
    respuesta = gemini_client.models.generate_content(
        model=MODELO_GEMINI, contents=[prompt, imagen]
    )
    return respuesta.text.strip()


def traducir_texto(texto: str, idioma_destino: str) -> str:
    """Traduce un texto usando Gemini."""
    prompt = PROMPT_TRADUCCION.format(idioma_destino=idioma_destino, texto=texto)
    respuesta = gemini_client.models.generate_content(
        model=MODELO_GEMINI, contents=prompt
    )
    return respuesta.text.strip()


def generar_audio(texto: str, ruta_salida: Path, idioma_gtts: str = "es") -> None:
    """Convierte el texto en un archivo mp3 con gTTS."""
    gTTS(text=texto, lang=idioma_gtts, slow=False).save(str(ruta_salida))


def generar_imagen_ia(prompt: str, ruta_salida: Path) -> Path:
    """Genera una imagen gratis con Pollinations.ai."""
    url = f"https://image.pollinations.ai/prompt/{quote(prompt)}"
    respuesta = requests.get(
        url, params={"width": 1024, "height": 1024, "nologo": "true"}, timeout=60
    )
    respuesta.raise_for_status()
    ruta_salida.write_bytes(respuesta.content)
    return ruta_salida


def procesar_todo_inclusivo(
    origen: str,
    session_id: str,
    prompt_imagen: str | None,
    archivo_subido,
    nivel_cognitivo: str,
    idiomas_elegidos: list[str],
    incluir_traduccion: bool,
) -> dict:
    """
    Flujo completo, equivalente a procesar_todo_inclusivo() del notebook:
    1. Consigue la imagen (generada o subida)
    2. Describe la imagen con Gemini
    3. Traduce si se pide
    4. Genera un audio mp3 real por idioma con gTTS
    """
    # 1) Imagen
    if origen == "subir":
        if archivo_subido is None or archivo_subido.filename == "":
            raise ValueError("No se ha subido ninguna imagen.")
        extension = Path(archivo_subido.filename).suffix.lower() or ".jpg"
        if extension not in (".jpg", ".jpeg", ".png", ".webp"):
            extension = ".jpg"
        ruta_imagen = GENERATED_DIR / f"{session_id}_original{extension}"
        archivo_subido.save(ruta_imagen)
    else:
        prompt_final = (prompt_imagen or "").strip() or "Una escena cotidiana, foto realista"
        ruta_imagen = GENERATED_DIR / f"{session_id}_generada.png"
        generar_imagen_ia(prompt_final, ruta_imagen)

    # 2) Descripción base en español
    descripcion_es = describir_imagen(ruta_imagen, nivel_cognitivo)
    descripciones = {}
    if "es" in idiomas_elegidos:
        descripciones["es"] = descripcion_es

    # 3) Traducción (si se pide) al resto de idiomas elegidos
    for codigo in idiomas_elegidos:
        if codigo == "es":
            continue
        if incluir_traduccion:
            nombre_largo = IDIOMAS.get(codigo, {}).get("traduccion", codigo)
            descripciones[codigo] = traducir_texto(descripcion_es, nombre_largo)
        else:
            descripciones[codigo] = descripcion_es

    # 4) Audio real (mp3) por idioma
    audios = {}
    for codigo in idiomas_elegidos:
        texto_a_leer = descripciones.get(codigo, descripcion_es)
        idioma_gtts = IDIOMAS.get(codigo, {}).get("gtts", "es")
        ruta_audio = GENERATED_DIR / f"{session_id}_audio_{codigo}.mp3"
        generar_audio(texto_a_leer, ruta_audio, idioma_gtts)
        audios[codigo] = ruta_audio.name

    return {
        "imagen_nombre": ruta_imagen.name,
        "descripciones": descripciones,
        "audios": audios,
        "nivel_cognitivo": nivel_cognitivo,
    }


# ============================================================
# RUTAS
# ============================================================
@app.route("/", methods=["GET"])
def index():
    return render_template(
        "index.html",
        idiomas=IDIOMAS,
        api_configurada=bool(GEMINI_API_KEY),
        error=None,
        resultado=None,
        valores={"nivel": "estándar", "idiomas": ["es"], "origen": "generar",
                 "prompt": "Una cocina luminosa con dos personas cocinando juntas, foto realista",
                 "traducir": False},
    )


@app.route("/generar", methods=["POST"])
def generar():
    valores = {
        "nivel": request.form.get("nivel", "estándar"),
        "idiomas": request.form.getlist("idiomas") or ["es"],
        "origen": request.form.get("origen", "generar"),
        "prompt": request.form.get("prompt", "").strip(),
        "traducir": request.form.get("traducir") == "on",
    }

    if not GEMINI_API_KEY:
        return render_template(
            "index.html", idiomas=IDIOMAS, api_configurada=False,
            error="Falta configurar GEMINI_API_KEY en el servidor (archivo .env). "
                  "Quien administra esta página debe añadir la clave antes de poder usarla.",
            resultado=None, valores=valores,
        )

    try:
        session_id = uuid.uuid4().hex[:10]
        resultado = procesar_todo_inclusivo(
            origen=valores["origen"],
            session_id=session_id,
            prompt_imagen=valores["prompt"],
            archivo_subido=request.files.get("imagen"),
            nivel_cognitivo=valores["nivel"],
            idiomas_elegidos=valores["idiomas"],
            incluir_traduccion=valores["traducir"],
        )
        resultado["imagen_url"] = url_for("static", filename=f"generated/{resultado['imagen_nombre']}")
        resultado["audios_url"] = {
            codigo: url_for("static", filename=f"generated/{nombre}")
            for codigo, nombre in resultado["audios"].items()
        }
        return render_template(
            "index.html", idiomas=IDIOMAS, api_configurada=True,
            error=None, resultado=resultado, valores=valores,
        )
    except Exception as exc:  # noqa: BLE001 - queremos mostrar cualquier error al usuario
        return render_template(
            "index.html", idiomas=IDIOMAS, api_configurada=True,
            error=f"No se pudo completar el proceso: {exc}",
            resultado=None, valores=valores,
        )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
