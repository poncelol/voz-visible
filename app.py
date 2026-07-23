# ============================================================
# Voz Visible — Generador de audiodescripciones inclusivas
# Con BLIP (gratuito, sin API) para imágenes y cámara
# ============================================================

import os
import uuid
import base64
import time
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

# Importar BLIP
from transformers import BlipProcessor, BlipForConditionalGeneration

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
GENERATED_DIR = BASE_DIR / "static" / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024
app.secret_key = os.environ.get("SECRET_KEY", "tu-clave-secreta-aqui")

# ============================================================
# CARGAR MODELO BLIP (GRATUITO)
# ============================================================
print("🔄 Cargando modelo BLIP (puede tardar unos segundos la primera vez)...")
try:
    processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
    model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
    MODELO_CARGADO = True
    print("✅ Modelo BLIP cargado correctamente")
except Exception as e:
    print(f"❌ Error cargando BLIP: {e}")
    MODELO_CARGADO = False

EN_PRODUCCION = os.environ.get('RENDER') == 'true' or os.environ.get('PORT') is not None

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
# FUNCIONES DE CONTROL
# ============================================================
ultima_solicitud = {}
TIEMPO_MINIMO_ENTRE_SOLICITUDES = 2

def verificar_limite_solicitudes(usuario="default") -> Tuple[bool, int]:
    ahora = datetime.now()
    if usuario in ultima_solicitud:
        diferencia = (ahora - ultima_solicitud[usuario]).total_seconds()
        if diferencia < TIEMPO_MINIMO_ENTRE_SOLICITUDES:
            return False, int(TIEMPO_MINIMO_ENTRE_SOLICITUDES - diferencia) + 1
    ultima_solicitud[usuario] = ahora
    return True, 0

# ============================================================
# FUNCIÓN DE DESCRIPCIÓN CON BLIP (GRATUITA)
# ============================================================
def describir_imagen_blip(imagen_bytes: bytes, prompt_texto: str = "") -> str:
    """Genera descripción de imagen usando BLIP (gratuito, sin API)."""
    
    if not MODELO_CARGADO:
        return "⚠️ El modelo BLIP no está disponible. Usa el modo de respaldo."
    
    try:
        # Abrir imagen
        imagen = Image.open(io.BytesIO(imagen_bytes))
        
        # Si hay prompt personalizado, usarlo, si no, descripción automática
        if prompt_texto:
            # BLIP también puede usar prompts para guiar la descripción
            inputs = processor(imagen, prompt_texto, return_tensors="pt")
        else:
            inputs = processor(imagen, return_tensors="pt")
        
        # Generar descripción
        out = model.generate(**inputs, max_length=60, num_beams=4, temperature=0.7)
        descripcion = processor.decode(out[0], skip_special_tokens=True)
        
        return descripcion
        
    except Exception as e:
        print(f"❌ Error en BLIP: {e}")
        return f"Error al describir: {str(e)}"

# ============================================================
# FUNCIÓN DE DESCRIPCIÓN CON TAGS (RESPALDO)
# ============================================================
def describir_imagen_tags(imagen_bytes: bytes) -> str:
    """Versión de respaldo que usa tags básicos de la imagen."""
    try:
        from PIL import Image, ImageFilter
        import colorsys
        
        imagen = Image.open(io.BytesIO(imagen_bytes))
        
        # Obtener colores dominantes
        imagen_pequena = imagen.resize((50, 50))
        colores = imagen_pequena.getcolors(2500)
        if colores:
            # Ordenar por frecuencia
            colores_ordenados = sorted(colores, key=lambda x: x[0], reverse=True)
            colores_principales = []
            for count, rgb in colores_ordenados[:3]:
                # Convertir RGB a nombre de color básico
                r, g, b = rgb
                if r > 200 and g > 200 and b > 200:
                    nombre_color = "claro"
                elif r < 50 and g < 50 and b < 50:
                    nombre_color = "oscuro"
                elif r > 200 and g < 100 and b < 100:
                    nombre_color = "rojo"
                elif r < 100 and g > 200 and b < 100:
                    nombre_color = "verde"
                elif r < 100 and g < 100 and b > 200:
                    nombre_color = "azul"
                elif r > 200 and g > 200 and b < 100:
                    nombre_color = "amarillo"
                else:
                    nombre_color = "color"
                colores_principales.append(nombre_color)
        
        # Obtener dimensiones
        ancho, alto = imagen.size
        orientacion = "horizontal" if ancho > alto else "vertical"
        
        # Generar descripción básica
        descripcion = f"Esta es una imagen {orientacion}. "
        if colores_principales:
            descripcion += f"Los colores principales son {', '.join(colores_principales)}. "
        descripcion += f"Tiene {ancho}x{alto} píxeles."
        
        return descripcion
        
    except Exception as e:
        print(f"❌ Error en tags: {e}")
        return "No se pudo describir la imagen."

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

def traducir_texto_simple(texto: str, idioma_destino: str) -> str:
    """Traducción simple sin API (solo para demostración)."""
    # Esta es una traducción muy básica para demostración
    # En producción, usarías una biblioteca como googletrans o deep-translator
    if idioma_destino == "español":
        return texto
    # Por ahora, solo devolvemos el texto original con un indicador
    return f"[{idioma_destino}] {texto}"

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
        with open(ruta_imagen, "rb") as f:
            imagen_bytes = f.read()
    else:
        prompt_final = (prompt_imagen or "").strip() or "Una escena cotidiana, foto realista"
        ruta_imagen = GENERATED_DIR / f"{session_id}_generada.png"
        generar_imagen_ia(prompt_final, ruta_imagen)
        with open(ruta_imagen, "rb") as f:
            imagen_bytes = f.read()

    # Describir con BLIP o con tags de respaldo
    if MODELO_CARGADO:
        descripcion_es = describir_imagen_blip(imagen_bytes, prompt_imagen or "")
    else:
        descripcion_es = describir_imagen_tags(imagen_bytes)

    # Si está vacía o es muy corta, usar tags como respaldo
    if len(descripcion_es) < 10:
        descripcion_tags = describir_imagen_tags(imagen_bytes)
        if len(descripcion_tags) > len(descripcion_es):
            descripcion_es = descripcion_tags

    descripciones = {}
    if "es" in idiomas_elegidos:
        descripciones["es"] = descripcion_es

    # Traducciones (usando función simple por ahora)
    for codigo in idiomas_elegidos:
        if codigo == "es":
            continue
        if incluir_traduccion:
            nombre_largo = IDIOMAS.get(codigo, {}).get("traduccion", codigo)
            descripciones[codigo] = traducir_texto_simple(descripcion_es, nombre_largo)
        else:
            descripciones[codigo] = descripcion_es

    # Generar audios
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
        api_configurada=MODELO_CARGADO,  # BLIP siempre "configurado" si cargó
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
            "index.html", idiomas=IDIOMAS, api_configurada=MODELO_CARGADO,
            en_produccion=EN_PRODUCCION,
            error=None, resultado=resultado, valores=valores,
        )
    except Exception as exc:
        error_amigable = f"No se pudo completar el proceso: {exc}"
        return render_template(
            "index.html", idiomas=IDIOMAS, api_configurada=MODELO_CARGADO,
            en_produccion=EN_PRODUCCION,
            error=error_amigable,
            resultado=None, valores=valores,
        )

@app.route('/analizar-camara', methods=['POST'])
def analizar_camara():
    """Analiza un fotograma de cámara con BLIP."""
    
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

        # Analizar con BLIP
        if MODALIDAD_CAMARA:
            descripcion = describir_imagen_blip(image_bytes, "Describe what you see in this photo")
        else:
            descripcion = describir_imagen_tags(image_bytes)

        return jsonify({
            'descripcion': descripcion,
            'modo': 'detallado' if modo_detalle else 'rápido',
            'modelo': 'BLIP' if MODELO_CARGADO else 'Tags'
        })

    except Exception as e:
        print(f"❌ Error en análisis: {e}")
        return jsonify({
            'error': 'error',
            'mensaje': f'Error: {str(e)}'
        }), 500

@app.route('/api/estado', methods=['GET'])
def estado_sistema():
    return jsonify({
        'modelo': {
            'nombre': 'BLIP' if MODELO_CARGADO else 'Tags (respaldo)',
            'gratuito': True,
            'cargado': MODELO_CARGADO
        },
        'produccion': EN_PRODUCCION,
        'rate_limit': {'minimo_segundos': TIEMPO_MINIMO_ENTRE_SOLICITUDES}
    })

# ============================================================
# EJECUCIÓN
# ============================================================
if __name__ == '__main__':
    print("🚀 Voz Visible iniciado")
    print(f"🖼️ Modelo: {'BLIP (gratuito)' if MODELO_CARGADO else 'Tags (respaldo)'}")
    print(f"🌐 Entorno: {'Producción' if EN_PRODUCCION else 'Desarrollo'}")
    print("")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=not EN_PRODUCCION)