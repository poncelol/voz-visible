# ============================================================
# Voz Visible — Generador de audiodescripciones inclusivas
# Con DeepSeek para imágenes y cámara en vivo
# ============================================================

import os
import uuid
import base64
import time
import json
import io
from pathlib import Path
from urllib.parse import quote
from datetime import datetime
from typing import Tuple

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, url_for, jsonify
from gtts import gTTS
from PIL import Image

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
GENERATED_DIR = BASE_DIR / "static" / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# CONFIGURACIÓN
# ============================================================
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
EN_PRODUCCION = os.environ.get('RENDER') == 'true' or os.environ.get('PORT') is not None

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024
app.secret_key = os.environ.get("SECRET_KEY", "tu-clave-secreta-aqui")

# ============================================================
# CONFIGURACIÓN DE CUOTA
# ============================================================
ultima_solicitud = {}
TIEMPO_MINIMO_ENTRE_SOLICITUDES = 3
MAX_REINTENTOS = 3

# ============================================================
# IDIOMAS
# ============================================================
IDIOMAS = {
    "es": {"nombre": "Español", "traduccion": "español", "gtts": "es"},
    "en": {"nombre": "Inglés", "traduccion": "inglés", "gtts": "en"},
    "fr": {"nombre": "Francés", "traduccion": "francés", "gtts": "fr"},
    "de": {"nombre": "Alemán", "traduccion": "alemán", "gtts": "de"},
    "it": {"nombre": "Italiano", "traduccion": "italiano", "gtts": "it"},
    "pt": {"nombre": "Portugués", "traduccion": "portugués", "gtts": "pt"},
}

# ============================================================
# PROMPTS
# ============================================================
PROMPT_AUDIODESCRIPCION_ESTANDAR = """
Describe esta imagen para una persona ciega o con baja visión.
Sigue estas reglas:
1. Máximo 4 frases, lenguaje claro y directo.
2. Empieza por lo más importante en primer plano.
3. Menciona después elementos relevantes del fondo.
4. Incluye colores y detalles visuales solo si aportan información útil.
5. Si hay texto visible en la imagen, transcríbelo.
6. No hagas interpretaciones subjetivas.
"""

PROMPT_AUDIODESCRIPCION_SIMPLIFICADA = """
Describe esta imagen de forma MUY SIMPLE.
Reglas:
1. MÁXIMO 3 frases muy cortas.
2. Usa palabras comunes.
3. Empieza diciendo QUÉ es lo principal.
4. Di DÓNDE están las cosas.
5. Si hay colores importantes, menciónalos.
6. Si hay texto, transcríbelo tal cual.
"""

PROMPT_TRADUCCION = """
Traduce el siguiente texto al idioma {idioma_destino}.
Responde SOLO con el texto traducido.

Texto original:
{texto}
"""

PROMPT_CAMARA_EN_VIVO = """
Describe de forma breve (1-2 oraciones) lo que ves en esta imagen de cámara.
Enfócate en elementos principales: personas, objetos, colores y acciones.
Responde SOLO con la descripción.
"""

PROMPT_ANALISIS_DETALLADO_CAMARA = """
Analiza esta escena con más detalle (3-4 oraciones):
1. Personas presentes (cuántas, qué hacen)
2. Objetos principales y ubicación
3. Ambiente general
4. Texto visible
Responde SOLO con la descripción.
"""

# ============================================================
# FUNCIONES DE CONTROL
# ============================================================
def verificar_limite_solicitudes(usuario="default") -> Tuple[bool, int]:
    ahora = datetime.now()
    if usuario in ultima_solicitud:
        diferencia = (ahora - ultima_solicitud[usuario]).total_seconds()
        if diferencia < TIEMPO_MINIMO_ENTRE_SOLICITUDES:
            return False, int(TIEMPO_MINIMO_ENTRE_SOLICITUDES - diferencia) + 1
    ultima_solicitud[usuario] = ahora
    return True, 0

def ejecutar_con_reintentos(func, *args, **kwargs):
    for intento in range(MAX_REINTENTOS):
        try:
            puede_proceder, tiempo_espera = verificar_limite_solicitudes()
            if not puede_proceder:
                print(f"⏳ Rate limit. Esperando {tiempo_espera}s...")
                time.sleep(tiempo_espera)
                continue
            return func(*args, **kwargs)
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e).lower():
                time.sleep(5 * (intento + 1))
            else:
                raise e
    raise Exception("Máximo de reintentos alcanzado")

# ============================================================
# FUNCIÓN PRINCIPAL PARA DEEPSEEK
# ============================================================
def describir_imagen_deepseek(imagen_bytes: bytes, prompt_texto: str) -> str:
    """Envía imagen a DeepSeek y devuelve descripción."""
    
    if not DEEPSEEK_API_KEY:
        raise Exception("DEEPSEEK_API_KEY no configurada")

    try:
        # Procesar imagen con PIL
        with Image.open(io.BytesIO(imagen_bytes)) as img:
            # Redimensionar a máximo 800px
            max_size = 800
            if max(img.size) > max_size:
                ratio = max_size / max(img.size)
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # Convertir a RGB
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            
            # Guardar en buffer
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=80)
            imagen_bytes = buffer.getvalue()
    except Exception as e:
        print(f"⚠️ Error procesando imagen: {e}")
        # Si falla PIL, intentar usar los bytes originales

    # Codificar a base64
    imagen_base64 = base64.b64encode(imagen_bytes).decode('utf-8')
    data_url = f"data:image/jpeg;base64,{imagen_base64}"

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_texto},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": data_url
                        }
                    }
                ]
            }
        ],
        "max_tokens": 300,
        "temperature": 0.4
    }
    
    def _describir():
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        
        # Log para debugging
        print(f"📡 DeepSeek response status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ Error response: {response.text[:200]}")
            response.raise_for_status()
            
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
    
    return ejecutar_con_reintentos(_describir)

def traducir_texto_deepseek(texto: str, idioma_destino: str) -> str:
    if not DEEPSEEK_API_KEY:
        raise Exception("DEEPSEEK_API_KEY no configurada")
    
    prompt = PROMPT_TRADUCCION.format(idioma_destino=idioma_destino, texto=texto)
    
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 200,
        "temperature": 0.3
    }
    
    def _traducir():
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
    
    return ejecutar_con_reintentos(_traducir)

# ============================================================
# FUNCIONES AUXILIARES
# ============================================================
def generar_audio(texto: str, ruta_salida: Path, idioma_gtts: str = "es") -> None:
    try:
        gTTS(text=texto, lang=idioma_gtts, slow=False).save(str(ruta_salida))
    except Exception as e:
        print(f"❌ Error generando audio: {e}")
        raise

def generar_imagen_ia(prompt: str, ruta_salida: Path) -> Path:
    url = f"https://image.pollinations.ai/prompt/{quote(prompt)}"
    respuesta = requests.get(
        url, params={"width": 1024, "height": 1024, "nologo": "true"}, timeout=60
    )
    respuesta.raise_for_status()
    ruta_salida.write_bytes(respuesta.content)
    return ruta_salida

# ============================================================
# PROCESAMIENTO DE IMÁGENES
# ============================================================
def procesar_todo_inclusivo(
    origen: str,
    session_id: str,
    prompt_imagen: str | None,
    archivo_subido,
    nivel_cognitivo: str,
    idiomas_elegidos: list[str],
    incluir_traduccion: bool,
) -> dict:
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

    # Elegir prompt
    if nivel_cognitivo == "simplificada":
        prompt = PROMPT_AUDIODESCRIPCION_SIMPLIFICADA
    else:
        prompt = PROMPT_AUDIODESCRIPCION_ESTANDAR

    descripcion_es = describir_imagen_deepseek(imagen_bytes, prompt)
    descripciones = {}
    if "es" in idiomas_elegidos:
        descripciones["es"] = descripcion_es

    for codigo in idiomas_elegidos:
        if codigo == "es":
            continue
        if incluir_traduccion:
            nombre_largo = IDIOMAS.get(codigo, {}).get("traduccion", codigo)
            descripciones[codigo] = traducir_texto_deepseek(descripcion_es, nombre_largo)
        else:
            descripciones[codigo] = descripcion_es

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
# RUTAS FLASK
# ============================================================
@app.route("/", methods=["GET"])
def index():
    return render_template(
        "index.html",
        idiomas=IDIOMAS,
        api_configurada=bool(DEEPSEEK_API_KEY),
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

    if not DEEPSEEK_API_KEY:
        return render_template(
            "index.html", idiomas=IDIOMAS, api_configurada=False,
            en_produccion=EN_PRODUCCION,
            error="❌ Falta configurar DEEPSEEK_API_KEY",
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
            en_produccion=EN_PRODUCCION,
            error=None, resultado=resultado, valores=valores,
        )
    except Exception as exc:
        error_amigable = f"No se pudo completar el proceso: {exc}"
        return render_template(
            "index.html", idiomas=IDIOMAS, api_configurada=True,
            en_produccion=EN_PRODUCCION,
            error=error_amigable,
            resultado=None, valores=valores,
        )

@app.route('/analizar-camara', methods=['POST'])
def analizar_camara():
    """Analiza un fotograma de cámara con DeepSeek."""
    
    if not DEEPSEEK_API_KEY:
        return jsonify({
            'error': 'no_api_key',
            'mensaje': 'DEEPSEEK_API_KEY no configurada'
        }), 503

    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No se recibieron datos'}), 400
            
        image_data = data.get('imagen', '')
        modo_detalle = data.get('detalle', False)
        
        if not image_data:
            return jsonify({'error': 'No se recibió imagen'}), 400

        # Decodificar base64
        try:
            if ',' in image_data:
                _, encoded = image_data.split(',', 1)
            else:
                encoded = image_data
            image_bytes = base64.b64decode(encoded)
        except Exception as e:
            print(f"❌ Error decodificando base64: {e}")
            return jsonify({'error': 'Error decodificando la imagen'}), 400

        # Verificar rate limit
        ip_usuario = request.remote_addr or "default"
        puede_proceder, tiempo_espera = verificar_limite_solicitudes(ip_usuario)
        
        if not puede_proceder:
            return jsonify({
                'error': 'rate_limit',
                'mensaje': f'Espera {tiempo_espera} segundos'
            }), 429

        # Analizar con DeepSeek
        if modo_detalle:
            prompt = PROMPT_ANALISIS_DETALLADO_CAMARA
        else:
            prompt = PROMPT_CAMARA_EN_VIVO

        print(f"📷 Analizando fotograma... (modo: {'detallado' if modo_detalle else 'rápido'})")
        descripcion = describir_imagen_deepseek(image_bytes, prompt)
        print(f"✅ Descripción: {descripcion[:100]}...")

        return jsonify({
            'descripcion': descripcion,
            'modo': 'detallado' if modo_detalle else 'rápido',
            'modelo': 'DeepSeek'
        })

    except requests.exceptions.RequestException as e:
        print(f"❌ Error de red con DeepSeek: {e}")
        return jsonify({
            'error': 'api_error',
            'mensaje': f'Error de conexión: {str(e)}'
        }), 500
    except Exception as e:
        print(f"❌ Error en análisis: {e}")
        return jsonify({
            'error': 'error',
            'mensaje': f'Error: {str(e)}'
        }), 500

@app.route('/api/estado', methods=['GET'])
def estado_sistema():
    return jsonify({
        'deepseek': {'configurada': bool(DEEPSEEK_API_KEY)},
        'produccion': EN_PRODUCCION,
        'rate_limit': {'minimo_segundos': TIEMPO_MINIMO_ENTRE_SOLICITUDES}
    })

# ============================================================
# EJECUCIÓN
# ============================================================
if __name__ == '__main__':
    print("🚀 Voz Visible iniciado")
    print(f"🖼️ Modelo: DeepSeek")
    print(f"🌐 Entorno: {'Producción' if EN_PRODUCCION else 'Desarrollo'}")
    print(f"✅ DeepSeek API: {'Configurada' if DEEPSEEK_API_KEY else '❌ No configurada'}")
    print("")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=not EN_PRODUCCION)