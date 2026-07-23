# ============================================================
# Voz Visible — Generador de audiodescripciones
# Versión con Groq Vision (100% GRATUITO) + Traducción real
# ============================================================

import os
import re
import time
import uuid
import base64
import io
from pathlib import Path
from urllib.parse import quote
from datetime import datetime
from typing import Dict, Optional, List

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, url_for, jsonify, session
from gtts import gTTS
from PIL import Image, ImageStat
from deep_translator import GoogleTranslator

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
GENERATED_DIR = BASE_DIR / "static" / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024
app.secret_key = os.environ.get("SECRET_KEY", "tu-clave-secreta-aqui")

EN_PRODUCCION = os.environ.get('RENDER') == 'true'

# ============================================================
# CÁMARA EN VIVO: LÍMITE DE TIEMPO
# ============================================================
# Corta las llamadas a Groq pasados estos segundos desde el primer
# fotograma de la sesión, aunque el navegador siga insistiendo.
CAMARA_DURACION_MAX_SEG = 20

# ============================================================
# CONFIGURACIÓN GROQ (100% GRATUITO)
# ============================================================
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODELO = "qwen/qwen3.6-27b"  # ✅ ÚNICO MODELO DE VISIÓN DISPONIBLE EN JULIO 2026

# ============================================================
# IDIOMAS
# ============================================================
# "gtts": código que usa gTTS para la voz
# "traductor": código que usa deep-translator (Google Translate) para el texto
IDIOMAS = {
    "es": {"nombre": "Español",    "gtts": "es", "traductor": "es"},
    "en": {"nombre": "Inglés",     "gtts": "en", "traductor": "en"},
    "fr": {"nombre": "Francés",    "gtts": "fr", "traductor": "fr"},
    "de": {"nombre": "Alemán",     "gtts": "de", "traductor": "de"},
    "it": {"nombre": "Italiano",   "gtts": "it", "traductor": "it"},
    "pt": {"nombre": "Portugués",  "gtts": "pt", "traductor": "pt"},
}

# ============================================================
# TRADUCCIÓN (deep-translator, gratuito, sin API key)
# ============================================================

def traducir_texto(texto: str, idioma_destino: str, idioma_origen: str = "es") -> str:
    """
    Traduce `texto` de idioma_origen -> idioma_destino usando deep-translator.
    Si falla (sin internet, texto vacío, etc.) devuelve el texto original
    para que la app nunca se rompa por un error de traducción.
    """
    if not texto or idioma_destino == idioma_origen:
        return texto

    try:
        traducido = GoogleTranslator(
            source=idioma_origen,
            target=idioma_destino
        ).translate(texto)
        if traducido:
            print(f"🌐 Traducido a '{idioma_destino}': {traducido}")
            return traducido
        return texto
    except Exception as e:
        print(f"⚠️ Error traduciendo a '{idioma_destino}': {e}")
        return texto  # fallback: devolvemos el texto en español antes que fallar

# ============================================================
# FUNCIÓN PARA DESCRIBIR CON GROQ (GRATIS)
# ============================================================

def describir_con_groq(imagen_bytes: bytes) -> str:
    """
    Usa Groq Vision para describir el CONTENIDO REAL de la imagen.
    100% GRATUITO - sin límites conocidos.
    """
    if not GROQ_API_KEY:
        print("⚠️ GROQ_API_KEY no configurada")
        return None

    try:
        # Codificar imagen a base64
        imagen_base64 = base64.b64encode(imagen_bytes).decode('utf-8')

        # URL de Groq API
        url = "https://api.groq.com/openai/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": GROQ_MODELO,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Describe esta imagen en español. Máximo 3 frases. Sé específico sobre lo que ves: personas, objetos, acciones, colores, ambiente."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{imagen_base64}"
                            }
                        }
                    ]
                }
            ],
            # qwen/qwen3.6-27b es un modelo "razonador": por defecto piensa en voz alta
            # (en inglés) antes de responder. Sin esto, ese pensamiento se cuela como
            # respuesta si se corta antes de terminar. "hidden" = solo devuelve la
            # respuesta final; "none" = ni siquiera razona, más rápido para esta tarea.
            "reasoning_format": "hidden",
            "reasoning_effort": "none",
            "max_tokens": 400,   # margen de sobra por si acaso
            "temperature": 0.7
        }

        print(f"📤 Enviando a Groq...")

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )

        print(f"📥 Respuesta Groq: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            descripcion = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Red de seguridad: por si algún resto de razonamiento se cuela en el
            # contenido (con o sin cierre de etiqueta), lo eliminamos.
            if descripcion:
                descripcion = re.sub(r"<think>.*?</think>", "", descripcion, flags=re.DOTALL)
                descripcion = re.sub(r"<think>.*", "", descripcion, flags=re.DOTALL)
                descripcion = descripcion.strip()

            if descripcion and len(descripcion) > 10:
                print(f"✅ Groq: {descripcion}")
                return descripcion
        else:
            print(f"❌ Error Groq: {response.status_code} - {response.text}")

        return None

    except Exception as e:
        print(f"❌ Error en Groq: {e}")
        return None

# ============================================================
# DESCRIPCIÓN TÉCNICA (FALLBACK)
# ============================================================

def describir_tecnico(imagen_bytes: bytes) -> str:
    """Descripción técnica (fallback)."""
    try:
        imagen = Image.open(io.BytesIO(imagen_bytes))
        ancho, alto = imagen.size

        # Color
        img_pequena = imagen.resize((50, 50))
        colores = img_pequena.getcolors(2500)
        color = "varios colores"
        if colores:
            colores_ordenados = sorted(colores, key=lambda x: x[0], reverse=True)
            r, g, b = colores_ordenados[0][1]
            if r > 200 and g > 200 and b > 200:
                color = "blanco"
            elif r < 50 and g < 50 and b < 50:
                color = "negro"
            elif r > 200 and g < 100 and b < 100:
                color = "rojo"
            elif r < 100 and g > 200 and b < 100:
                color = "verde"
            elif r < 100 and g < 100 and b > 200:
                color = "azul"
            elif r > 200 and g > 200 and b < 100:
                color = "amarillo"

        # Brillo
        gris = imagen.convert('L')
        stat = ImageStat.Stat(gris)
        brillo = stat.mean[0]
        brillo_texto = "muy brillante" if brillo > 200 else "brillante" if brillo > 150 else "luminosidad media" if brillo > 100 else "oscuro" if brillo > 50 else "muy oscuro"

        # Forma
        if ancho > alto * 1.5:
            forma = "horizontal"
        elif alto > ancho * 1.5:
            forma = "vertical"
        else:
            forma = "cuadrada"

        return f"Imagen {forma}, colores {color}, {brillo_texto}."
    except:
        return "Imagen capturada por la cámara."

# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================

def describir_imagen(imagen_bytes: bytes) -> str:
    """Intenta con Groq primero, luego fallback."""

    # Intentar con Groq (CONTENIDO REAL)
    descripcion = describir_con_groq(imagen_bytes)
    if descripcion:
        return descripcion

    # Fallback técnico
    print("⚠️ Usando fallback técnico")
    return describir_tecnico(imagen_bytes)

# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def generar_audio(texto: str, ruta_salida: Path, idioma_gtts: str = "es") -> None:
    """Genera archivo de audio a partir de texto."""
    try:
        gTTS(text=texto, lang=idioma_gtts, slow=False).save(str(ruta_salida))
    except Exception as e:
        print(f"❌ Error generando audio: {e}")
        raise

def generar_imagen_ia(prompt: str, ruta_salida: Path) -> Path:
    """Genera imagen usando Pollinations AI."""
    url = f"https://image.pollinations.ai/prompt/{quote(prompt)}"
    respuesta = requests.get(
        url, params={"width": 1024, "height": 1024, "nologo": "true"}, timeout=60
    )
    respuesta.raise_for_status()
    ruta_salida.write_bytes(respuesta.content)
    return ruta_salida

# ============================================================
# PROCESAMIENTO PRINCIPAL
# ============================================================

def procesar_todo_inclusivo(
    origen: str,
    session_id: str,
    prompt_imagen: Optional[str],
    archivo_subido,
    nivel_cognitivo: str,
    idiomas_elegidos: List[str],
    incluir_traduccion: bool,
) -> Dict:
    """Procesa imagen, descripción, traducción y genera audio."""

    # Obtener imagen
    if origen == "subir":
        if archivo_subido is None or archivo_subido.filename == "":
            raise ValueError("No se ha subido ninguna imagen.")
        extension = Path(archivo_subido.filename).suffix.lower() or ".jpg"
        if extension not in (".jpg", ".jpeg", ".png", ".webp"):
            extension = ".jpg"
        ruta_imagen = GENERATED_DIR / f"{session_id}_original{extension}"
        archivo_subido.save(ruta_imagen)
        with open(ruta_imagen, "rb") as f:
            imagen_bytes = f.read()
    else:
        prompt_final = (prompt_imagen or "").strip() or "Una escena cotidiana, foto realista"
        ruta_imagen = GENERATED_DIR / f"{session_id}_generada.png"
        generar_imagen_ia(prompt_final, ruta_imagen)
        with open(ruta_imagen, "rb") as f:
            imagen_bytes = f.read()

    # DESCRIBIR (siempre se genera primero en español)
    descripcion_es = describir_imagen(imagen_bytes)

    if nivel_cognitivo == "simplificada":
        frases = descripcion_es.split('. ')
        if len(frases) > 3:
            descripcion_es = '. '.join(frases[:3]) + '.'

    # Preparar descripciones en varios idiomas (TRADUCIENDO de verdad)
    descripciones = {}
    if "es" in idiomas_elegidos:
        descripciones["es"] = descripcion_es

    for codigo in idiomas_elegidos:
        if codigo == "es":
            continue
        idioma_traductor = IDIOMAS.get(codigo, {}).get("traductor", codigo)
        descripciones[codigo] = traducir_texto(descripcion_es, idioma_traductor, "es")

    # Generar audios (cada uno lee el texto YA traducido a su idioma)
    audios = {}
    for codigo in idiomas_elegidos:
        texto_a_leer = descripciones.get(codigo, descripcion_es)
        idioma_gtts = IDIOMAS.get(codigo, {}).get("gtts", "es")
        ruta_audio = GENERATED_DIR / f"{session_id}_audio_{codigo}.mp3"
        generar_audio(texto_a_leer, ruta_audio, idioma_gtts)
        audios[codigo] = ruta_audio.name

    es_groq = GROQ_API_KEY and "píxeles" not in descripcion_es.lower() and "composición" not in descripcion_es.lower()

    return {
        "imagen_nombre": ruta_imagen.name,
        "descripciones": descripciones,
        "audios": audios,
        "nivel_cognitivo": nivel_cognitivo,
        "modelo_usado": "Groq Vision" if es_groq else "Técnico (fallback)",
        "es_groq": es_groq
    }

# ============================================================
# RUTAS
# ============================================================

@app.route("/", methods=["GET"])
def index():
    """Página principal."""
    return render_template(
        "index.html",
        idiomas=IDIOMAS,
        api_configurada=bool(GROQ_API_KEY),
        en_produccion=EN_PRODUCCION,
        error=None,
        resultado=None,
        valores={
            "nivel": "estándar",
            "idiomas": ["es"],
            "origen": "generar",
            "prompt": "Una cocina luminosa con dos personas cocinando",
            "traducir": False
        },
        groq_configurada=bool(GROQ_API_KEY)
    )

@app.route("/generar", methods=["POST"])
def generar():
    """Genera audiodescrpciones."""
    valores = {
        "nivel": request.form.get("nivel", "estándar"),
        "idiomas": request.form.getlist("idiomas") or ["es"],
        "origen": request.form.get("origen", "generar"),
        "prompt": request.form.get("prompt", "").strip(),
        "traducir": request.form.get("traducir") == "on",
    }

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
            "index.html",
            idiomas=IDIOMAS,
            api_configurada=bool(GROQ_API_KEY),
            en_produccion=EN_PRODUCCION,
            error=None,
            resultado=resultado,
            valores=valores,
            groq_configurada=bool(GROQ_API_KEY)
        )
    except Exception as exc:
        return render_template(
            "index.html",
            idiomas=IDIOMAS,
            api_configurada=bool(GROQ_API_KEY),
            en_produccion=EN_PRODUCCION,
            error=str(exc),
            resultado=None,
            valores=valores,
            groq_configurada=bool(GROQ_API_KEY)
        )

# ============================================================
# RUTAS DE CÁMARA
# ============================================================

@app.route('/api/camara/estado', methods=['GET'])
def estado_camara():
    """Retorna estado de la cámara."""
    return jsonify({
        'activo': True,
        'gratuito': True,
        'modelo': 'Groq Vision' if GROQ_API_KEY else 'Técnico (fallback)',
        'groq_configurada': bool(GROQ_API_KEY),
        'version': '2.0.0'
    })

@app.route('/api/camara/iniciar', methods=['POST'])
def iniciar_camara():
    """
    Marca el inicio de una sesión de cámara en vivo. El frontend debe llamar
    a esto justo cuando el usuario pulsa 'Iniciar cámara', para que el
    contador de 20 segundos empiece en ese momento (y no arrastre tiempo
    de una sesión anterior).
    """
    session['camara_inicio'] = time.time()
    return jsonify({'ok': True, 'duracion_max_seg': CAMARA_DURACION_MAX_SEG})

@app.route('/api/camara/stream', methods=['POST'])
def procesar_stream_camara():
    """Procesa stream de cámara en vivo, con corte automático a los 20s."""
    try:
        # Si no hay inicio registrado (p. ej. el frontend no llamó a /iniciar),
        # lo fijamos ahora mismo con este primer fotograma.
        inicio = session.get('camara_inicio')
        if inicio is None:
            inicio = time.time()
            session['camara_inicio'] = inicio

        transcurrido = time.time() - inicio

        if transcurrido >= CAMARA_DURACION_MAX_SEG:
            # No llamamos a Groq: cortamos aquí para no seguir gastando tokens.
            print(f"⏹️ Límite de {CAMARA_DURACION_MAX_SEG}s alcanzado, se ignora el fotograma")
            return jsonify({
                'limite_alcanzado': True,
                'mensaje': f'Sesión de cámara detenida tras {CAMARA_DURACION_MAX_SEG} segundos.',
                'duracion_max_seg': CAMARA_DURACION_MAX_SEG
            }), 200

        data = request.get_json()
        if not data or 'imagen' not in data:
            return jsonify({'error': 'No se recibió imagen'}), 400

        image_data = data['imagen']
        if ',' in image_data:
            _, encoded = image_data.split(',', 1)
        else:
            encoded = image_data
        image_bytes = base64.b64decode(encoded)

        # Idioma opcional para la cámara en vivo (por defecto español)
        idioma_camara = data.get('idioma', 'es')

        # Describir imagen (siempre en español primero)
        descripcion_es = describir_imagen(image_bytes)

        # Traducir si el idioma pedido no es español
        idioma_traductor = IDIOMAS.get(idioma_camara, {}).get("traductor", "es")
        descripcion = traducir_texto(descripcion_es, idioma_traductor, "es")

        # Generar audio en el idioma correspondiente
        session_id = uuid.uuid4().hex[:8]
        idioma_gtts = IDIOMAS.get(idioma_camara, {}).get("gtts", "es")
        audio_path = GENERATED_DIR / f"{session_id}_camara.mp3"
        generar_audio(descripcion, audio_path, idioma_gtts)

        # Convertir audio a base64
        with open(audio_path, "rb") as f:
            audio_base64 = base64.b64encode(f.read()).decode('utf-8')

        # Limpiar archivo temporal
        try:
            os.remove(audio_path)
        except:
            pass

        es_groq = GROQ_API_KEY and "píxeles" not in descripcion_es.lower() and "composición" not in descripcion_es.lower()

        # Segundos que quedan antes del corte, útil para que el frontend lo muestre
        segundos_restantes = max(0, round(CAMARA_DURACION_MAX_SEG - transcurrido, 1))

        return jsonify({
            'descripcion': descripcion,
            'audio': audio_base64,
            'timestamp': datetime.now().isoformat(),
            'segundos_restantes': segundos_restantes,
            'modelo': 'Groq Vision' if es_groq else 'Técnico (fallback)',
            'es_groq': es_groq
        })

    except Exception as e:
        print(f"❌ Error en stream: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/camara/detener', methods=['POST'])
def detener_camara():
    """Limpia el contador de sesión para que la próxima vez que se inicie la
    cámara vuelva a tener sus 20 segundos completos."""
    session.pop('camara_inicio', None)
    return jsonify({'ok': True})

@app.route('/api/estado', methods=['GET'])
def estado_sistema():
    """Retorna estado del sistema."""
    return jsonify({
        'modelo': {
            'nombre': 'Groq Vision' if GROQ_API_KEY else 'Técnico (fallback)',
            'gratuito': True,
            'memoria_mb': '< 50',
            'tipo': 'API externa (groq.com)',
            'groq_configurada': bool(GROQ_API_KEY),
            'descripcion_contenido_real': bool(GROQ_API_KEY)
        },
        'camara': {
            'activa': True,
            'gratuita': True,
            'fps': 0.33
        },
        'produccion': EN_PRODUCCION,
        'idiomas': list(IDIOMAS.keys()),
        'version': '2.0.0'
    })

# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == '__main__':
    print("=" * 55)
    print("🚀 Voz Visible — Versión con Groq Vision + Traducción")
    print("=" * 55)
    print(f"🖼️  Modelo: {'Groq Vision (CONTENIDO REAL)' if GROQ_API_KEY else 'Técnico (fallback)'}")
    print(f"📷 Cámara en vivo: ACTIVADA")
    print(f"🌐 Traducción: deep-translator (Google Translate, gratis)")
    print(f"💾 Memoria estimada: < 50 MB")
    print(f"💰 Costo: 100% GRATUITO")
    print("")

    if not GROQ_API_KEY:
        print("⚠️  IMPORTANTE: GROQ_API_KEY no configurada")
        print("   Obtén tu API key GRATIS en: https://console.groq.com")
        print("   Luego añádela como variable de entorno:")
        print("   GROQ_API_KEY=tu-api-key")
        print("")
    else:
        print("✅ Groq API configurada correctamente")
        print("   Las descripciones serán de CONTENIDO REAL")
        print("   Ejemplo: 'Una mujer cocinando en una cocina moderna'")
        print("")

    port = int(os.environ.get('PORT', 5000))
    print(f"🔌 Escuchando en http://localhost:{port}")
    print("=" * 55)
    app.run(host='0.0.0.0', port=port, debug=not EN_PRODUCCION)
