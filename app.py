# ============================================================
# Voz Visible — Generador de audiodescripciones inclusivas
# Con DeepSeek para imágenes y cámara en vivo
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

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
GENERATED_DIR = BASE_DIR / "static" / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# CONFIGURACIÓN DE APIS
# ============================================================
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# Detectar si estamos en producción
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
# FUNCIÓN PARA ENVIAR IMAGEN A DEEPSEEK (IMÁGENES ESTÁTICAS Y CÁMARA)
# ============================================================
def describir_imagen_deepseek(imagen_bytes: bytes, nivel_complejidad: str = "estándar", es_camara: bool = False) -> str:
    """Envía una imagen a DeepSeek y devuelve la descripción."""
    
    if not DEEPSEEK_API_KEY:
        raise Exception("DEEPSEEK_API_KEY no configurada")

    try:
        # Redimensionar para evitar problemas de tamaño
        with Image.open(io.BytesIO(imagen_bytes)) as img:
            max_size = 1024
            if max(img.size) > max_size:
                ratio = max_size / max(img.size)
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
                
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=85)
            imagen_bytes = buffer.getvalue()
    except Exception as e:
        print(f"⚠️ Error procesando imagen: {e}")

    imagen_base64 = base64.b64encode(imagen_bytes).decode('utf-8')
    data_url = f"data:image/jpeg;base64,{imagen_base64}"

    # Elegir prompt según contexto
    if es_camara:
        prompt = PROMPT_ANALISIS_DETALLADO_CAMARA if nivel_complejidad == "detallado" else PROMPT_CAMARA_EN_VIVO
    else:
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
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": data_url
                        }
                    }
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
    """Traduce un texto usando DeepSeek."""
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
# PROCESAMIENTO PRINCIPAL (IMÁGENES ESTÁTICAS)
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

    # Descripción con DeepSeek
    descripcion_es = describir_imagen_deepseek(imagen_bytes, nivel_cognitivo, es_camara=False)
    descripciones = {}
    if "es" in idiomas_elegidos:
        descripciones["es"] = descripcion_es

    # Traducciones
    for codigo in idiomas_elegidos:
        if codigo == "es":
            continue
        if incluir_traduccion:
            nombre_largo = IDIOMAS.get(codigo, {}).get("traduccion", codigo)
            descripciones[codigo] = traducir_texto_deepseek(descripcion_es, nombre_largo)
        else:
            descripciones[codigo] = descripcion_es

    # Audio
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
            en_produccion=EN_PRODUCCION,
            error=error_amigable,
            resultado=None, valores=valores,
        )

@app.route('/analizar-camara', methods=['POST'])
def analizar_camara():
    """Analiza un fotograma de cámara en tiempo real con DeepSeek."""
    
    if not DEEPSEEK_API_KEY:
        return jsonify({
            'error': 'no_api_key',
            'mensaje': 'DEEPSEEK_API_KEY no configurada. Configura la variable de entorno.'
        }), 503
        
    try:
        data = request.get_json()
        image_data = data.get('imagen', '')
        modo_detalle = data.get('detalle', False)
        
        if not image_data:
            return jsonify({'error': 'No se recibió ninguna imagen'}), 400
        
        # Decodificar base64
        if ',' in image_data:
            _, encoded = image_data.split(',', 1)
        else:
            encoded = image_data
            
        image_bytes = base64.b64decode(encoded)
        
        # Verificar rate limit
        ip_usuario = request.remote_addr or "default"
        puede_proceder, tiempo_espera = verificar_limite_solicitudes(ip_usuario)
        
        if not puede_proceder:
            return jsonify({
                'error': 'rate_limit',
                'mensaje': f'Demasiadas solicitudes. Espera {tiempo_espera} segundos.',
                'tiempo_espera': tiempo_espera
            }), 429
        
        # Analizar con DeepSeek
        nivel = "detallado" if modo_detalle else "estándar"
        descripcion = describir_imagen_deepseek(image_bytes, nivel, es_camara=True)
        
        return jsonify({
            'descripcion': descripcion,
            'modo': 'detallado' if modo_detalle else 'rápido',
            'modelo': 'DeepSeek-Vision'
        })
        
    except Exception as e:
        print(f"❌ Error en el análisis: {e}")
        return jsonify({'error': f'Error al analizar: {str(e)}'}), 500

@app.route('/api/estado', methods=['GET'])
def estado_sistema():
    return jsonify({
        'deepseek': {
            'configurada': bool(DEEPSEEK_API_KEY)
        },
        'produccion': EN_PRODUCCION,
        'rate_limit': {
            'minimo_segundos': TIEMPO_MINIMO_ENTRE_SOLICITUDES
        }
    })

# ============================================================
# EJECUCIÓN
# ============================================================
if __name__ == '__main__':
    print("🚀 Voz Visible iniciado")
    print(f"🖼️ Modelo para imágenes y cámara: DeepSeek")
    print(f"⏱️  Tiempo mínimo entre solicitudes: {TIEMPO_MINIMO_ENTRE_SOLICITUDES}s")
    print(f"🌐 Entorno: {'Producción' if EN_PRODUCCION else 'Desarrollo'}")
    print("")
    
    if DEEPSEEK_API_KEY:
        print(f"✅ DeepSeek API: Configurada")
    else:
        print(f"❌ DeepSeek API: No configurada (falta DEEPSEEK_API_KEY)")
    
    print("")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=not EN_PRODUCCION)