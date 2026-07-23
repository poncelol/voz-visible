# ============================================================
# Voz Visible — Generador de audiodescripciones inclusivas
# Con DeepSeek para cámara en vivo y Gemini para imágenes
# ============================================================

import os
import uuid
import base64
import time
import openai  # Para DeepSeek API
from pathlib import Path
from urllib.parse import quote
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, url_for, jsonify
from gtts import gTTS
from PIL import Image
from google import genai
import openai  # Para DeepSeek API

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
GENERATED_DIR = BASE_DIR / "static" / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# CONFIGURACIÓN DE APIS
# ============================================================
# Gemini para imágenes
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# DeepSeek para cámara en vivo
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024  # 12 MB

# ============================================================
# CONFIGURACIÓN DE CUOTA Y RATE LIMITING
# ============================================================
ultima_solicitud = {}
TIEMPO_MINIMO_ENTRE_SOLICITUDES = 5  # segundos (DeepSeek es más permisivo)
MAX_REINTENTOS = 3
TIEMPO_ESPERA_REINTENTO = 5  # segundos base

# ============================================================
# IDIOMAS SOPORTADOS
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

PROMPT_ANALISIS_EN_VIVO = """
Describe de forma muy breve, clara y directa (máximo 1 o 2 oraciones) 
lo que ves en este fotograma de cámara en vivo para explicárselo a alguien en voz alta.
Enfócate en elementos principales como personas, objetos, colores y acciones visibles.
Responde SOLO con la descripción, sin introducciones ni explicaciones adicionales.
"""

MODELO_GEMINI = "gemini-2.5-flash"
MODELO_DEEPSEEK = "deepseek-vl2"  # Modelo de DeepSeek con visión

# ============================================================
# FUNCIONES DE CONTROL DE CUOTA
# ============================================================
def verificar_limite_solicitudes(usuario="default") -> tuple[bool, int]:
    """
    Verifica si se puede hacer una solicitud respetando el rate limit.
    Retorna: (puede_proceder, tiempo_espera_segundos)
    """
    ahora = datetime.now()
    
    if usuario in ultima_solicitud:
        diferencia = (ahora - ultima_solicitud[usuario]).total_seconds()
        if diferencia < TIEMPO_MINIMO_ENTRE_SOLICITUDES:
            tiempo_espera = int(TIEMPO_MINIMO_ENTRE_SOLICITUDES - diferencia) + 1
            return False, tiempo_espera
    
    ultima_solicitud[usuario] = ahora
    return True, 0

def ejecutar_con_reintentos(func, *args, **kwargs):
    """
    Ejecuta una función con reintentos en caso de error.
    """
    for intento in range(MAX_REINTENTOS):
        try:
            # Verificar rate limit
            puede_proceder, tiempo_espera = verificar_limite_solicitudes()
            if not puede_proceder:
                print(f"Rate limit activo. Esperando {tiempo_espera} segundos...")
                time.sleep(tiempo_espera)
                continue
            
            # Ejecutar la función
            return func(*args, **kwargs)
            
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "rate_limit" in error_str.lower():
                print(f"Error de rate limit (intento {intento+1}/{MAX_REINTENTOS}): {error_str}")
                tiempo_espera = 10 * (intento + 1)
                
                if intento < MAX_REINTENTOS - 1:
                    print(f"Esperando {tiempo_espera} segundos antes de reintentar...")
                    time.sleep(tiempo_espera)
                else:
                    raise Exception(f"Error persistente después de {MAX_REINTENTOS} intentos.")
            else:
                raise e
    
    raise Exception("Número máximo de reintentos alcanzado")

# ============================================================
# FUNCIONES PARA GEMINI (IMÁGENES)
# ============================================================
def describir_imagen_gemini(ruta_imagen: Path, nivel_complejidad: str = "estándar") -> str:
    """Envía la imagen a Gemini y devuelve la audiodescripción."""
    imagen = Image.open(ruta_imagen)
    prompt = (
        PROMPT_AUDIODESCRIPCION_SIMPLIFICADA
        if nivel_complejidad == "simplificada"
        else PROMPT_AUDIODESCRIPCION_ESTANDAR
    )
    
    def _describir():
        respuesta = gemini_client.models.generate_content(
            model=MODELO_GEMINI, contents=[prompt, imagen]
        )
        return respuesta.text.strip()
    
    return ejecutar_con_reintentos(_describir)

def traducir_texto_gemini(texto: str, idioma_destino: str) -> str:
    """Traduce un texto usando Gemini."""
    prompt = PROMPT_TRADUCCION.format(idioma_destino=idioma_destino, texto=texto)
    
    def _traducir():
        respuesta = gemini_client.models.generate_content(
            model=MODELO_GEMINI, contents=prompt
        )
        return respuesta.text.strip()
    
    return ejecutar_con_reintentos(_traducir)

# ============================================================
# FUNCIONES PARA DEEPSEEK (CÁMARA EN VIVO)
# ============================================================
def describir_fotograma_deepseek(imagen_bytes: bytes) -> str:
    """Analiza un fotograma de cámara en vivo con DeepSeek."""
    
    # Convertir imagen a base64
    imagen_base64 = base64.b64encode(imagen_bytes).decode('utf-8')
    
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
                    {
                        "type": "text",
                        "text": PROMPT_ANALISIS_EN_VIVO
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
        "max_tokens": 100,
        "temperature": 0.3
    }
    
    def _analizar():
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
    
    return ejecutar_con_reintentos(_analizar)

# ============================================================
# FUNCIONES AUXILIARES
# ============================================================
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
    Flujo completo de procesamiento con Gemini para imágenes.
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

    # 2) Descripción base en español (con Gemini)
    descripcion_es = describir_imagen_gemini(ruta_imagen, nivel_cognitivo)
    descripciones = {}
    if "es" in idiomas_elegidos:
        descripciones["es"] = descripcion_es

    # 3) Traducciones (con Gemini)
    for codigo in idiomas_elegidos:
        if codigo == "es":
            continue
        if incluir_traduccion:
            nombre_largo = IDIOMAS.get(codigo, {}).get("traduccion", codigo)
            descripciones[codigo] = traducir_texto_gemini(descripcion_es, nombre_largo)
        else:
            descripciones[codigo] = descripcion_es

    # 4) Audio por idioma
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
        api_configurada=bool(GEMINI_API_KEY and DEEPSEEK_API_KEY),
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
            error="Falta configurar GEMINI_API_KEY en el servidor.",
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
    except Exception as exc:
        error_msg = str(exc)
        if "429" in error_msg or "quota" in error_msg.lower():
            error_amigable = "⚠️ Límite de solicitudes de Gemini alcanzado. Por favor, espera 30 segundos y vuelve a intentarlo."
        else:
            error_amigable = f"No se pudo completar el proceso: {exc}"
        
        return render_template(
            "index.html", idiomas=IDIOMAS, api_configurada=True,
            error=error_amigable,
            resultado=None, valores=valores,
        )

@app.route('/analizar-imagen', methods=['POST'])
def analizar_imagen():
    """Analiza un fotograma de cámara en tiempo real con DeepSeek."""
    try:
        if not DEEPSEEK_API_KEY:
            return jsonify({'error': 'DeepSeek no está configurado. Falta DEEPSEEK_API_KEY.'}), 500
            
        data = request.get_json()
        image_data = data.get('imagen', '')
        
        if not image_data:
            return jsonify({'error': 'No se recibió ninguna imagen'}), 400
        
        # Decodificar base64
        if ',' in image_data:
            header, encoded = image_data.split(',', 1)
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
        
        # Analizar la imagen con DeepSeek
        try:
            descripcion = describir_fotograma_deepseek(image_bytes)
            return jsonify({'descripcion': descripcion})
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "rate_limit" in error_str.lower():
                return jsonify({
                    'error': 'rate_limit',
                    'mensaje': 'Límite de solicitudes de DeepSeek alcanzado. Espera unos segundos.',
                    'tiempo_espera': 10
                }), 429
            raise e
        
    except Exception as e:
        print(f"Error en el análisis: {e}")
        return jsonify({'error': f'Error al analizar: {str(e)}'}), 500

@app.route('/api/estado-cuota', methods=['GET'])
def estado_cuota():
    """Devuelve el estado actual de la cuota."""
    ip_usuario = request.remote_addr or "default"
    puede_proceder, tiempo_espera = verificar_limite_solicitudes(ip_usuario)
    
    return jsonify({
        'puede_proceder': puede_proceder,
        'tiempo_espera': tiempo_espera if not puede_proceder else 0,
        'api_imagenes': 'Gemini' if GEMINI_API_KEY else 'No configurada',
        'api_camara': 'DeepSeek' if DEEPSEEK_API_KEY else 'No configurada',
        'mensaje': 'Listo' if puede_proceder else f'Espera {tiempo_espera} segundos'
    })

# ============================================================
# EJECUCIÓN
# ============================================================
# ============================================================
# EJECUCIÓN
# ============================================================
if __name__ == '__main__':
    print("🚀 Voz Visible iniciado")
    print(f"📊 Modelo para imágenes: {MODELO_GEMINI} (Gemini)")
    print(f"📷 Modelo para cámara: {MODELO_DEEPSEEK} (DeepSeek)")
    print(f"⏱️  Tiempo mínimo entre solicitudes: {TIEMPO_MINIMO_ENTRE_SOLICITUDES}s")
    print(f"🔄 Máximo de reintentos: {MAX_REINTENTOS}")
    print("")
    print(f"✅ Gemini API: {'Configurada' if GEMINI_API_KEY else '❌ No configurada'}")
    print(f"✅ DeepSeek API: {'Configurada' if DEEPSEEK_API_KEY else '❌ No configurada'}")
    
    # Para producción en Render, usar el puerto de la variable de entorno
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)