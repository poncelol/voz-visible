# ============================================================
# Voz Visible — Generador de audiodescripciones inclusivas
# Con Llama 3.2 Vision para cámara y DeepSeek para imágenes
# ============================================================

import os
import sys
import uuid
import base64
import time
import json
import io
from pathlib import Path
from urllib.parse import quote
from datetime import datetime
from typing import Optional, Tuple

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, url_for, jsonify
from gtts import gTTS
from PIL import Image

# Intentar importar Ollama (opcional)
OLLAMA_DISPONIBLE = False
try:
    import ollama
    OLLAMA_DISPONIBLE = True
except ImportError:
    print("ℹ️ Ollama no está instalado. La funcionalidad de cámara estará desactivada.")

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
GENERATED_DIR = BASE_DIR / "static" / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# CONFIGURACIÓN DE APIS
# ============================================================
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# Ollama para cámara en vivo (solo si está disponible)
OLLAMA_MODELO = "llama3.2-vision"
OLLAMA_URL = "http://localhost:11434/api/chat"

# Detectar si estamos en producción (Render)
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
# IDIOMAS SOPORTADOS
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
3. Empieza diciendo QUÉ es lo principal.
4. Di DÓNDE están las cosas.
5. Si hay colores importantes, menciónalos.
6. Si hay texto, transcríbelo tal cual.
7. Nada de explicaciones ni sentimientos. Solo hechos.

Ejemplo correcto: "Hay una cocina grande y luminosa. Dos personas cocinan juntas.
La mujer revuelve una olla. El hombre pela verduras."
"""

PROMPT_TRADUCCION = """
Traduce el siguiente texto al idioma {idioma_destino}.
Mantén el tono accesible y directo.
Responde SOLO con el texto traducido, sin explicaciones.

Texto original:
{texto}
"""

PROMPT_CAMARA_EN_VIVO = """
Describe de forma muy breve, clara y directa (máximo 1 o 2 oraciones) 
lo que ves en este fotograma de cámara en vivo para explicárselo a alguien en voz alta.
Enfócate en elementos principales como personas, objetos, colores y acciones visibles.
Responde SOLO con la descripción, sin introducciones ni explicaciones adicionales.
"""

PROMPT_ANALISIS_DETALLADO_CAMARA = """
Analiza esta escena de cámara en vivo con más detalle (máximo 3-4 oraciones).
Describe:
1. Personas presentes (cuántas, qué hacen, cómo van vestidas)
2. Objetos principales y su ubicación
3. Ambiente y contexto general
4. Cualquier texto visible

Responde SOLO con la descripción, sin introducciones.
"""

MODELO_DEEPSEEK = "deepseek-chat"

# ============================================================
# FUNCIONES DE CONTROL DE CUOTA
# ============================================================
def verificar_limite_solicitudes(usuario="default") -> Tuple[bool, int]:
    ahora = datetime.now()
    if usuario in ultima_solicitud:
        diferencia = (ahora - ultima_solicitud[usuario]).total_seconds()
        if diferencia < TIEMPO_MINIMO_ENTRE_SOLICITUDES:
            tiempo_espera = int(TIEMPO_MINIMO_ENTRE_SOLICITUDES - diferencia) + 1
            return False, tiempo_espera
    ultima_solicitud[usuario] = ahora
    return True, 0

def ejecutar_con_reintentos(func, *args, **kwargs):
    for intento in range(MAX_REINTENTOS):
        try:
            puede_proceder, tiempo_espera = verificar_limite_solicitudes()
            if not puede_proceder:
                print(f"⏳ Rate limit activo. Esperando {tiempo_espera} segundos...")
                time.sleep(tiempo_espera)
                continue
            return func(*args, **kwargs)
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "rate_limit" in error_str.lower():
                print(f"⚠️ Error de rate limit (intento {intento+1}/{MAX_REINTENTOS})")
                tiempo_espera = 10 * (intento + 1)
                if intento < MAX_REINTENTOS - 1:
                    print(f"⏳ Esperando {tiempo_espera} segundos...")
                    time.sleep(tiempo_espera)
                else:
                    raise Exception(f"Error persistente después de {MAX_REINTENTOS} intentos.")
            else:
                raise e
    raise Exception("Número máximo de reintentos alcanzado")

# ============================================================
# FUNCIONES PARA DEEPSEEK
# ============================================================
def describir_imagen_deepseek(ruta_imagen: Path, nivel_complejidad: str = "estándar") -> str:
    if not DEEPSEEK_API_KEY:
        raise Exception("DEEPSEEK_API_KEY no configurada")
    
    with open(ruta_imagen, "rb") as f:
        imagen_bytes = f.read()
    imagen_base64 = base64.b64encode(imagen_bytes).decode('utf-8')
    
    prompt = PROMPT_AUDIODESCRIPCION_SIMPLIFICADA if nivel_complejidad == "simplificada" else PROMPT_AUDIODESCRIPCION_ESTANDAR
    
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": MODELO_DEEPSEEK,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{imagen_base64}"}}
                ]
            }
        ],
        "max_tokens": 200,
        "temperature": 0.4
    }
    
    def _describir():
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
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
        "model": MODELO_DEEPSEEK,
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
# FUNCIONES PARA OLLAMA (solo si está disponible)
# ============================================================
def verificar_ollama() -> bool:
    if not OLLAMA_DISPONIBLE:
        return False
    if EN_PRODUCCION:
        # En producción, Ollama no estará disponible
        return False
    try:
        modelos = ollama.list()
        modelos_disponibles = [m['model'] for m in modelos['models']]
        if OLLAMA_MODELO not in modelos_disponibles:
            print(f"⚠️ Modelo {OLLAMA_MODELO} no encontrado.")
            return False
        return True
    except Exception as e:
        print(f"❌ Error conectando con Ollama: {e}")
        return False

def describir_fotograma_ollama(imagen_bytes: bytes, modo_detalle: bool = False) -> str:
    if not verificar_ollama():
        return "⚠️ Ollama no está disponible. La cámara en vivo solo funciona en desarrollo local."
    
    imagen_base64 = base64.b64encode(imagen_bytes).decode('utf-8')
    prompt = PROMPT_ANALISIS_DETALLADO_CAMARA if modo_detalle else PROMPT_CAMARA_EN_VIVO
    
    try:
        response = ollama.chat(
            model=OLLAMA_MODELO,
            messages=[{
                'role': 'user',
                'content': prompt,
                'images': [imagen_base64]
            }],
            options={
                'temperature': 0.3,
                'num_predict': 100 if modo_detalle else 50,
                'top_p': 0.9
            }
        )
        descripcion = response['message']['content'].strip()
        if len(descripcion) > 150:
            descripcion = descripcion[:150] + "..."
        return descripcion
    except Exception as e:
        print(f"❌ Error con Ollama: {e}")
        return f"Error al analizar: {str(e)}"

def describir_fotograma_ollama_con_redimension(imagen_bytes: bytes, max_size: int = 640) -> str:
    try:
        imagen = Image.open(io.BytesIO(imagen_bytes))
        if max(imagen.size) > max_size:
            ratio = max_size / max(imagen.size)
            nuevo_tamano = (int(imagen.size[0] * ratio), int(imagen.size[1] * ratio))
            imagen = imagen.resize(nuevo_tamano, Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        imagen.save(buffer, format='JPEG', quality=85)
        imagen_bytes_redimensionada = buffer.getvalue()
        return describir_fotograma_ollama(imagen_bytes_redimensionada)
    except Exception as e:
        print(f"⚠️ Error en redimensionamiento: {e}")
        return describir_fotograma_ollama(imagen_bytes)

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
# PROCESAMIENTO PRINCIPAL
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
    else:
        prompt_final = (prompt_imagen or "").strip() or "Una escena cotidiana, foto realista"
        ruta_imagen = GENERATED_DIR / f"{session_id}_generada.png"
        generar_imagen_ia(prompt_final, ruta_imagen)

    descripcion_es = describir_imagen_deepseek(ruta_imagen, nivel_cognitivo)
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
    ollama_ok = verificar_ollama()
    return render_template(
        "index.html",
        idiomas=IDIOMAS,
        api_configurada=bool(DEEPSEEK_API_KEY),
        ollama_disponible=ollama_ok,
        en_produccion=EN_PRODUCCION,
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

    if not DEEPSEEK_API_KEY:
        return render_template(
            "index.html", idiomas=IDIOMAS, api_configurada=False,
            ollama_disponible=verificar_ollama(),
            en_produccion=EN_PRODUCCION,
            error="❌ Falta configurar DEEPSEEK_API_KEY en el servidor.",
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
            ollama_disponible=verificar_ollama(),
            en_produccion=EN_PRODUCCION,
            error=None, resultado=resultado, valores=valores,
        )
    except Exception as exc:
        error_msg = str(exc)
        if "429" in error_msg or "quota" in error_msg.lower():
            error_amigable = "⚠️ Límite de solicitudes alcanzado. Por favor, espera unos segundos y vuelve a intentarlo."
        else:
            error_amigable = f"No se pudo completar el proceso: {exc}"
        
        return render_template(
            "index.html", idiomas=IDIOMAS, api_configurada=True,
            ollama_disponible=verificar_ollama(),
            en_produccion=EN_PRODUCCION,
            error=error_amigable,
            resultado=None, valores=valores,
        )

@app.route('/analizar-camara', methods=['POST'])
def analizar_camara():
    """Analiza un fotograma de cámara en tiempo real con Ollama."""
    if EN_PRODUCCION:
        return jsonify({
            'error': 'no_disponible',
            'mensaje': 'La funcionalidad de cámara en vivo no está disponible en producción. Usa la generación de imágenes estáticas.'
        }), 503
    
    if not verificar_ollama():
        return jsonify({
            'error': 'ollama_no_disponible',
            'mensaje': 'Ollama no está disponible. Asegúrate de que está instalado y ejecutándose localmente.',
            'instrucciones': '1. Instala Ollama desde https://ollama.com\n2. Ejecuta: ollama pull llama3.2-vision\n3. Ejecuta: ollama serve'
        }), 503
        
    try:
        data = request.get_json()
        image_data = data.get('imagen', '')
        modo_detalle = data.get('detalle', False)
        
        if not image_data:
            return jsonify({'error': 'No se recibió ninguna imagen'}), 400
        
        if ',' in image_data:
            _, encoded = image_data.split(',', 1)
        else:
            encoded = image_data
            
        image_bytes = base64.b64decode(encoded)
        
        ip_usuario = request.remote_addr or "default"
        puede_proceder, tiempo_espera = verificar_limite_solicitudes(ip_usuario)
        
        if not puede_proceder:
            return jsonify({
                'error': 'rate_limit',
                'mensaje': f'Demasiadas solicitudes. Espera {tiempo_espera} segundos.',
                'tiempo_espera': tiempo_espera
            }), 429
        
        descripcion = describir_fotograma_ollama_con_redimension(image_bytes, modo_detalle)
        
        return jsonify({
            'descripcion': descripcion,
            'modo': 'detallado' if modo_detalle else 'rápido',
            'modelo': OLLAMA_MODELO
        })
        
    except Exception as e:
        print(f"❌ Error en el análisis: {e}")
        return jsonify({'error': f'Error al analizar: {str(e)}'}), 500

@app.route('/api/estado', methods=['GET'])
def estado_sistema():
    ollama_ok = verificar_ollama()
    return jsonify({
        'ollama': {
            'disponible': ollama_ok,
            'modelo': OLLAMA_MODELO if ollama_ok else None
        },
        'deepseek': {
            'configurada': bool(DEEPSEEK_API_KEY)
        },
        'produccion': EN_PRODUCCION,
        'rate_limit': {
            'minimo_segundos': TIEMPO_MINIMO_ENTRE_SOLICITUDES
        }
    })

# ============================================================
# HTML (versión simplificada que maneja producción)
# ============================================================
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Voz Visible - Audiodescripciones Inclusivas</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: rgba(255,255,255,0.95);
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        h1 {
            color: #2d3748;
            font-size: 2.5em;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 15px;
            flex-wrap: wrap;
        }
        .subtitle {
            color: #718096;
            margin-bottom: 30px;
            font-size: 1.1em;
        }
        .status-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.8em;
            font-weight: 600;
            margin-left: 10px;
        }
        .status-ok { background: #48bb78; color: white; }
        .status-error { background: #fc8181; color: white; }
        .status-warning { background: #f6ad55; color: white; }
        
        .grid-2 {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin-top: 20px;
        }
        .card {
            background: white;
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            border: 1px solid #e2e8f0;
        }
        .card h3 {
            color: #2d3748;
            margin-bottom: 15px;
            font-size: 1.2em;
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            display: block;
            font-weight: 600;
            color: #4a5568;
            margin-bottom: 5px;
            font-size: 0.9em;
        }
        input, select, textarea {
            width: 100%;
            padding: 10px;
            border: 2px solid #e2e8f0;
            border-radius: 8px;
            font-size: 1em;
            transition: border-color 0.3s;
        }
        input:focus, select:focus, textarea:focus {
            outline: none;
            border-color: #667eea;
        }
        textarea {
            resize: vertical;
            min-height: 80px;
        }
        .btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 12px 30px;
            border-radius: 8px;
            font-size: 1em;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
        }
        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }
        
        .resultado {
            margin-top: 30px;
            padding: 20px;
            background: #f7fafc;
            border-radius: 15px;
            border: 2px solid #e2e8f0;
        }
        .resultado img {
            max-width: 100%;
            border-radius: 10px;
            margin: 10px 0;
        }
        .audio-player {
            margin: 10px 0;
        }
        .checkbox-group {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin: 10px 0;
        }
        .checkbox-group label {
            display: flex;
            align-items: center;
            gap: 5px;
            font-weight: normal;
            cursor: pointer;
        }
        .checkbox-group input[type="checkbox"] {
            width: auto;
            margin-right: 5px;
        }
        
        .camara-section {
            margin-top: 15px;
            padding: 15px;
            background: #1a202c;
            border-radius: 15px;
            color: white;
        }
        #video {
            width: 100%;
            max-width: 640px;
            border-radius: 10px;
            background: #2d3748;
        }
        .camara-controls {
            display: flex;
            gap: 10px;
            margin: 10px 0;
            flex-wrap: wrap;
        }
        .camara-controls .btn {
            flex: 1;
            min-width: 100px;
            font-size: 0.9em;
            padding: 10px 15px;
        }
        .btn-secondary {
            background: #4a5568;
        }
        .btn-secondary:hover {
            background: #2d3748;
        }
        .btn-danger {
            background: #fc8181;
        }
        .btn-danger:hover {
            background: #e53e3e;
        }
        #descripcion-camara {
            background: #2d3748;
            padding: 15px;
            border-radius: 10px;
            margin: 10px 0;
            min-height: 60px;
            font-size: 1em;
            line-height: 1.5;
            color: #e2e8f0;
        }
        .produccion-notice {
            background: #f6ad55;
            color: #2d3748;
            padding: 10px;
            border-radius: 8px;
            margin: 10px 0;
            text-align: center;
        }
        
        .error-message {
            background: #fed7d7;
            color: #c53030;
            padding: 15px;
            border-radius: 10px;
            margin: 15px 0;
            border-left: 4px solid #e53e3e;
        }
        
        @media (max-width: 768px) {
            .grid-2 { grid-template-columns: 1fr; }
            h1 { font-size: 1.5em; }
            .container { padding: 15px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>
            🎙️ Voz Visible
            <span class="status-badge {{ 'status-ok' if api_configurada else 'status-error' }}">
                {{ 'DeepSeek OK' if api_configurada else 'DeepSeek ❌' }}
            </span>
            <span class="status-badge {{ 'status-ok' if ollama_disponible else 'status-warning' }}">
                {{ 'Llama 3.2 OK' if ollama_disponible else 'Llama 3.2 ⚠️' }}
            </span>
        </h1>
        <p class="subtitle">Generador de audiodescripciones inclusivas con DeepSeek y Llama 3.2 Vision</p>
        
        {% if en_produccion %}
        <div class="produccion-notice">
            ⚠️ Entorno de producción: La cámara en vivo está desactivada. Usa la generación de imágenes estáticas.
        </div>
        {% endif %}
        
        {% if error %}
        <div class="error-message">{{ error }}</div>
        {% endif %}
        
        <div class="grid-2">
            <!-- Panel de generación de imágenes -->
            <div class="card">
                <h3>🖼️ Generar descripción de imagen</h3>
                <form method="POST" enctype="multipart/form-data" action="/generar">
                    <div class="form-group">
                        <label>Origen de la imagen</label>
                        <select name="origen" id="origen" onchange="toggleOrigen()">
                            <option value="generar" {{ 'selected' if valores.origen == 'generar' }}>Generar con IA</option>
                            <option value="subir" {{ 'selected' if valores.origen == 'subir' }}>Subir imagen propia</option>
                        </select>
                    </div>
                    
                    <div class="form-group" id="prompt-group">
                        <label>Descripción para generar imagen</label>
                        <textarea name="prompt" placeholder="Ej: Una cocina luminosa con dos personas cocinando...">{{ valores.prompt }}</textarea>
                    </div>
                    
                    <div class="form-group" id="file-group" style="display:none;">
                        <label>Seleccionar imagen</label>
                        <input type="file" name="imagen" accept="image/*">
                    </div>
                    
                    <div class="form-group">
                        <label>Nivel cognitivo</label>
                        <select name="nivel">
                            <option value="estándar" {{ 'selected' if valores.nivel == 'estándar' }}>Estándar</option>
                            <option value="simplificada" {{ 'selected' if valores.nivel == 'simplificada' }}>Simplificado</option>
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label>Idiomas</label>
                        <div class="checkbox-group">
                            {% for codigo, info in idiomas.items() %}
                            <label>
                                <input type="checkbox" name="idiomas" value="{{ codigo }}"
                                    {{ 'checked' if codigo in valores.idiomas }}>
                                {{ info.nombre }}
                            </label>
                            {% endfor %}
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label>
                            <input type="checkbox" name="traducir" {{ 'checked' if valores.traducir }}>
                            Traducir al idioma seleccionado
                        </label>
                    </div>
                    
                    <button type="submit" class="btn">🎧 Generar audiodescripción</button>
                </form>
            </div>
            
            <!-- Panel de cámara en vivo -->
            <div class="card">
                <h3>📷 Cámara en vivo con Llama 3.2 Vision</h3>
                <div class="camara-section">
                    <video id="video" autoplay playsinline></video>
                    <div class="camara-controls">
                        <button id="btn-iniciar" class="btn" onclick="iniciarCamara()" {% if en_produccion %}disabled{% endif %}>📷 Iniciar</button>
                        <button id="btn-analizar" class="btn btn-secondary" onclick="analizarFrame()" disabled>🔍 Analizar</button>
                        <button id="btn-detener" class="btn btn-danger" onclick="detenerCamara()" disabled>⏹️ Detener</button>
                    </div>
                    <div class="camara-controls">
                        <button class="btn" onclick="analizarFrameDetallado()" id="btn-detalle" disabled>🔬 Análisis detallado</button>
                    </div>
                    <div id="descripcion-camara">
                        <span style="color: #a0aec0;">{% if en_produccion %}📌 No disponible en producción. Usa la generación de imágenes estáticas.{% else %}La descripción aparecerá aquí...{% endif %}</span>
                    </div>
                    <div id="estado-camara" style="color: #a0aec0; font-size: 0.9em; margin-top: 10px;">
                        Estado: {% if en_produccion %}Desactivado en producción{% else %}Esperando inicio...{% endif %}
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Resultados -->
        {% if resultado %}
        <div class="resultado">
            <h3>✅ Resultado</h3>
            <img src="{{ resultado.imagen_url }}" alt="Imagen generada">
            
            {% for codigo, desc in resultado.descripciones.items() %}
            <div style="margin: 15px 0; padding: 10px; background: white; border-radius: 8px;">
                <strong>{{ idiomas[codigo].nombre }}:</strong>
                <p>{{ desc }}</p>
                {% if codigo in resultado.audios_url %}
                <div class="audio-player">
                    <audio controls>
                        <source src="{{ resultado.audios_url[codigo] }}" type="audio/mpeg">
                        Tu navegador no soporta audio.
                    </audio>
                </div>
                {% endif %}
            </div>
            {% endfor %}
            
            <p style="color: #718096; font-size: 0.9em; margin-top: 10px;">
                Nivel: {{ resultado.nivel_cognitivo }}
            </p>
        </div>
        {% endif %}
    </div>
    
    <script>
        let stream = null;
        let canvas = document.createElement('canvas');
        let contexto = canvas.getContext('2d');
        let analizando = false;
        let intervaloAnalisis = null;
        const enProduccion = {{ 'true' if en_produccion else 'false' }};
        
        function toggleOrigen() {
            const origen = document.getElementById('origen').value;
            document.getElementById('prompt-group').style.display = origen === 'generar' ? 'block' : 'none';
            document.getElementById('file-group').style.display = origen === 'subir' ? 'block' : 'none';
        }
        
        async function iniciarCamara() {
            if (enProduccion) {
                alert('La cámara en vivo no está disponible en producción.');
                return;
            }
            
            try {
                const video = document.getElementById('video');
                stream = await navigator.mediaDevices.getUserMedia({ 
                    video: { 
                        width: { ideal: 640 },
                        height: { ideal: 480 },
                        facingMode: 'environment'
                    } 
                });
                video.srcObject = stream;
                await video.play();
                
                document.getElementById('btn-iniciar').disabled = true;
                document.getElementById('btn-analizar').disabled = false;
                document.getElementById('btn-detener').disabled = false;
                document.getElementById('btn-detalle').disabled = false;
                document.getElementById('estado-camara').textContent = '✅ Cámara activa';
                
                intervaloAnalisis = setInterval(analizarFrame, 3000);
                
            } catch (error) {
                console.error('Error al iniciar cámara:', error);
                document.getElementById('estado-camara').textContent = '❌ Error: ' + error.message;
            }
        }
        
        function detenerCamara() {
            if (stream) {
                stream.getTracks().forEach(track => track.stop());
                stream = null;
                document.getElementById('video').srcObject = null;
            }
            
            if (intervaloAnalisis) {
                clearInterval(intervaloAnalisis);
                intervaloAnalisis = null;
            }
            
            document.getElementById('btn-iniciar').disabled = false;
            document.getElementById('btn-analizar').disabled = true;
            document.getElementById('btn-detener').disabled = true;
            document.getElementById('btn-detalle').disabled = true;
            document.getElementById('estado-camara').textContent = '⏹️ Cámara detenida';
        }
        
        function capturarFrame() {
            const video = document.getElementById('video');
            canvas.width = video.videoWidth || 640;
            canvas.height = video.videoHeight || 480;
            contexto.drawImage(video, 0, 0);
            return canvas.toDataURL('image/jpeg', 0.8);
        }
        
        async function analizarFrame() {
            if (analizando || enProduccion) return;
            analizando = true;
            
            try {
                const imagenData = capturarFrame();
                document.getElementById('estado-camara').textContent = '⏳ Analizando...';
                
                const response = await fetch('/analizar-camara', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ imagen: imagenData, detalle: false })
                });
                
                const data = await response.json();
                
                if (data.error) {
                    if (data.error === 'rate_limit') {
                        document.getElementById('estado-camara').textContent = `⏳ ${data.mensaje}`;
                    } else {
                        document.getElementById('estado-camara').textContent = '❌ Error: ' + data.mensaje;
                    }
                    document.getElementById('descripcion-camara').innerHTML = 
                        `<span style="color: #fc8181;">⚠️ ${data.mensaje || 'Error al analizar'}</span>`;
                } else {
                    document.getElementById('descripcion-camara').textContent = data.descripcion;
                    document.getElementById('estado-camara').textContent = 
                        `✅ Analizado con ${data.modo || 'rápido'} | ${new Date().toLocaleTimeString()}`;
                }
                
            } catch (error) {
                console.error('Error en análisis:', error);
                document.getElementById('estado-camara').textContent = '❌ Error de conexión';
            } finally {
                analizando = false;
            }
        }
        
        async function analizarFrameDetallado() {
            if (analizando || enProduccion) return;
            analizando = true;
            
            try {
                const imagenData = capturarFrame();
                document.getElementById('estado-camara').textContent = '⏳ Análisis detallado...';
                
                const response = await fetch('/analizar-camara', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ imagen: imagenData, detalle: true })
                });
                
                const data = await response.json();
                
                if (data.error) {
                    document.getElementById('descripcion-camara').innerHTML = 
                        `<span style="color: #fc8181;">⚠️ ${data.mensaje || 'Error al analizar'}</span>`;
                } else {
                    document.getElementById('descripcion-camara').textContent = data.descripcion;
                    document.getElementById('estado-camara').textContent = 
                        `✅ Análisis detallado | ${new Date().toLocaleTimeString()}`;
                }
                
            } catch (error) {
                console.error('Error en análisis detallado:', error);
            } finally {
                analizando = false;
            }
        }
        
        toggleOrigen();
    </script>
</body>
</html>
'''

# Guardar el HTML
templates_dir = BASE_DIR / "templates"
templates_dir.mkdir(exist_ok=True)
with open(templates_dir / "index.html", "w", encoding="utf-8") as f:
    f.write(HTML_TEMPLATE)

# ============================================================
# EJECUCIÓN
# ============================================================
if __name__ == '__main__':
    print("🚀 Voz Visible iniciado")
    print(f"📷 Modelo para cámara en vivo: {OLLAMA_MODELO} (Llama 3.2 Vision)")
    print(f"🖼️ Modelo para imágenes estáticas: DeepSeek")
    print(f"⏱️  Tiempo mínimo entre solicitudes: {TIEMPO_MINIMO_ENTRE_SOLICITUDES}s")
    print(f"🌐 Entorno: {'Producción' if EN_PRODUCCION else 'Desarrollo'}")
    print("")
    
    if DEEPSEEK_API_KEY:
        print(f"✅ DeepSeek API: Configurada")
    else:
        print(f"❌ DeepSeek API: No configurada (falta DEEPSEEK_API_KEY)")
    
    if EN_PRODUCCION:
        print(f"ℹ️ Modo producción: Cámara en vivo desactivada")
    else:
        if OLLAMA_DISPONIBLE:
            try:
                modelos = ollama.list()
                print(f"✅ Ollama: Disponible")
                modelos_disponibles = [m['model'] for m in modelos['models']]
                if OLLAMA_MODELO in modelos_disponibles:
                    print(f"✅ Modelo {OLLAMA_MODELO}: Instalado")
                else:
                    print(f"⚠️ Modelo {OLLAMA_MODELO}: No instalado")
                    print(f"   Ejecuta: ollama pull {OLLAMA_MODELO}")
            except Exception as e:
                print(f"❌ Error conectando con Ollama: {e}")
                print(f"   Asegúrate de ejecutar: ollama serve")
        else:
            print(f"❌ Ollama no instalado. Instala desde: https://ollama.com")
    
    print("")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=not EN_PRODUCCION)