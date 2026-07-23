# ============================================================
# Voz Visible — Generador de audiodescripciones inclusivas
# Versión LIGERA con Pollinations (100% gratuito, sin API key)
# Compatible con el nuevo HTML
# ============================================================

import os
import uuid
import base64
import io
import time
from pathlib import Path
from urllib.parse import quote
from datetime import datetime
from typing import Dict, Optional, List, Tuple

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, url_for, jsonify
from gtts import gTTS
from PIL import Image, ImageStat, ImageFilter

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
GENERATED_DIR = BASE_DIR / "static" / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024
app.secret_key = os.environ.get("SECRET_KEY", "tu-clave-secreta-aqui")

EN_PRODUCCION = os.environ.get('RENDER') == 'true'

# ============================================================
# IDIOMAS
# ============================================================
IDIOMAS = {
    "es": {"nombre": "Español", "gtts": "es"},
    "en": {"nombre": "Inglés", "gtts": "en"},
    "fr": {"nombre": "Francés", "gtts": "fr"},
    "de": {"nombre": "Alemán", "gtts": "de"},
    "it": {"nombre": "Italiano", "gtts": "it"},
    "pt": {"nombre": "Portugués", "gtts": "pt"},
}

# ============================================================
# FUNCIONES DE DESCRIPCIÓN CON POLLINATIONS
# ============================================================

def describir_con_pollinations(imagen_bytes: bytes, idioma: str = "es") -> str:
    """
    Usa Pollinations.ai para describir el contenido REAL de la imagen.
    100% gratuito, sin API key, sin límites.
    """
    try:
        # Codificar imagen a base64
        imagen_base64 = base64.b64encode(imagen_bytes).decode('utf-8')
        
        # URL del endpoint de descripción
        url = "https://image.pollinations.ai/describe"
        
        # Prompt según idioma
        prompt_text = "Describe this image in Spanish, max 3 sentences. Be specific about what you see." if idioma == "es" else "Describe this image in English, max 3 sentences. Be specific."
        
        print(f"📤 Enviando imagen a Pollinations... ({len(imagen_bytes)} bytes)")
        
        response = requests.post(
            url,
            json={
                "image": imagen_base64,
                "prompt": prompt_text
            },
            timeout=45,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"📥 Respuesta: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            # Intentar diferentes formatos de respuesta
            descripcion = None
            if isinstance(data, dict):
                descripcion = data.get("description") or data.get("text") or data.get("caption")
            elif isinstance(data, list) and len(data) > 0:
                if isinstance(data[0], dict):
                    descripcion = data[0].get("description") or data[0].get("text")
                else:
                    descripcion = str(data[0])
            elif isinstance(data, str):
                descripcion = data
            
            if descripcion and len(descripcion) > 10 and "píxeles" not in descripcion.lower():
                print(f"✅ Pollinations: {descripcion}")
                return descripcion
            else:
                print(f"⚠️ Respuesta inválida: {descripcion}")
        else:
            print(f"❌ Error: {response.status_code} - {response.text[:200]}")
        
        # Si falla, usar fallback técnico
        return describir_tecnico(imagen_bytes)
        
    except requests.exceptions.Timeout:
        print("⏰ Timeout en Pollinations")
        return describir_tecnico(imagen_bytes)
    except Exception as e:
        print(f"❌ Error en Pollinations: {e}")
        return describir_tecnico(imagen_bytes)

def describir_tecnico(imagen_bytes: bytes) -> str:
    """Descripción técnica (fallback)."""
    try:
        imagen = Image.open(io.BytesIO(imagen_bytes))
        ancho, alto = imagen.size
        
        # Color dominante
        img_pequena = imagen.resize((50, 50))
        colores = img_pequena.getcolors(2500)
        color = "color"
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
        brillo_texto = "brillante" if brillo > 150 else "oscuro" if brillo < 50 else "luminosidad media"
        
        return f"Imagen de {ancho}x{alto} píxeles, colores {color}, {brillo_texto}."
    except:
        return "Imagen capturada por la cámara."

def describir_imagen(imagen_bytes: bytes, idioma: str = "es") -> str:
    """Función principal - usa Pollinations con reintentos."""
    
    # Intentar con Pollinations (2 intentos)
    for intento in range(2):
        print(f"🔄 Intento {intento + 1}/2 con Pollinations...")
        descripcion = describir_con_pollinations(imagen_bytes, idioma)
        
        # Verificar si es una descripción válida (no técnica)
        if descripcion and "píxeles" not in descripcion.lower() and len(descripcion) > 15:
            print(f"✅ Descripción válida")
            return descripcion
        
        if intento < 1:
            time.sleep(2)
    
    # Si todos los intentos fallan, usar fallback
    print("⚠️ Usando fallback técnico")
    return describir_tecnico(imagen_bytes)

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
    """Traducción simple (fallback si no hay Gemini)."""
    # Si no hay Gemini, devolvemos el texto original
    return texto

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

    # DESCRIBIR con Pollinations
    descripcion_es = describir_imagen(imagen_bytes, "es")
    
    # Si es nivel simplificado, acortar
    if nivel_cognitivo == "simplificada":
        frases = descripcion_es.split('. ')
        if len(frases) > 3:
            descripcion_es = '. '.join(frases[:3]) + '.'

    # Generar descripciones por idioma
    descripciones = {}
    if "es" in idiomas_elegidos:
        descripciones["es"] = descripcion_es

    # Traducciones (simplificadas)
    for codigo in idiomas_elegidos:
        if codigo == "es":
            continue
        if incluir_traduccion:
            # Usar traducción simple (o la misma si no hay Gemini)
            descripciones[codigo] = traducir_texto_simple(descripcion_es, codigo)
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
        "modelo_usado": "Pollinations AI",
    }

# ============================================================
# RUTAS FLASK
# ============================================================

@app.route("/", methods=["GET"])
def index():
    # Verificar si Pollinations funciona
    pollinations_ok = verificar_pollinations()
    
    return render_template(
        "index.html",
        idiomas=IDIOMAS,
        api_configurada=True,  # Pollinations siempre está disponible
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
        pollinations_ok=pollinations_ok
    )

def verificar_pollinations():
    """Verifica si Pollinations responde correctamente."""
    try:
        # Crear una imagen de prueba
        from PIL import Image
        img = Image.new('RGB', (50, 50), color='red')
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG')
        img_bytes = img_byte_arr.getvalue()
        
        desc = describir_con_pollinations(img_bytes)
        return desc is not None and "píxeles" not in desc.lower() and len(desc) > 10
    except:
        return False

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
            "index.html",
            idiomas=IDIOMAS,
            api_configurada=True,
            en_produccion=EN_PRODUCCION,
            error=None,
            resultado=resultado,
            valores=valores,
            pollinations_ok=True
        )
    except Exception as exc:
        error_amigable = f"No se pudo completar el proceso: {exc}"
        return render_template(
            "index.html",
            idiomas=IDIOMAS,
            api_configurada=True,
            en_produccion=EN_PRODUCCION,
            error=error_amigable,
            resultado=None,
            valores=valores,
            pollinations_ok=False
        )

# ============================================================
# RUTAS DE CÁMARA EN VIVO (para el HTML anterior)
# ============================================================

@app.route('/api/camara/estado', methods=['GET'])
def estado_camara():
    pollinations_ok = verificar_pollinations()
    return jsonify({
        'activo': True,
        'gratuito': True,
        'modelo': 'Pollinations AI' if pollinations_ok else 'Técnico (fallback)',
        'pollinations_funciona': pollinations_ok,
        'version': '2.0.0'
    })

@app.route('/api/camara/stream', methods=['POST'])
def procesar_stream_camara():
    try:
        data = request.get_json()
        if not data or 'imagen' not in data:
            return jsonify({'error': 'No se recibió imagen'}), 400
        
        # Decodificar imagen
        image_data = data['imagen']
        if ',' in image_data:
            _, encoded = image_data.split(',', 1)
        else:
            encoded = image_data
        image_bytes = base64.b64decode(encoded)
        
        # DESCRIBIR con Pollinations
        descripcion = describir_imagen(image_bytes, "es")
        
        # Generar audio
        session_id = uuid.uuid4().hex[:8]
        audio_path = GENERATED_DIR / f"{session_id}_camara.mp3"
        generar_audio(descripcion, audio_path, "es")
        
        with open(audio_path, "rb") as f:
            audio_base64 = base64.b64encode(f.read()).decode('utf-8')
        
        try:
            os.remove(audio_path)
        except:
            pass
        
        es_ia = "píxeles" not in descripcion.lower()
        
        return jsonify({
            'descripcion': descripcion,
            'audio': audio_base64,
            'timestamp': datetime.now().isoformat(),
            'modelo': 'Pollinations AI' if es_ia else 'Técnico (fallback)',
            'es_ia': es_ia
        })
        
    except Exception as e:
        print(f"❌ Error en stream: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/estado', methods=['GET'])
def estado_sistema():
    pollinations_ok = verificar_pollinations()
    return jsonify({
        'modelo': {
            'nombre': 'Pollinations AI' if pollinations_ok else 'Técnico (fallback)',
            'gratuito': True,
            'memoria_mb': '< 100',
            'tipo': 'API externa (gratuita)',
            'descripcion_contenido_real': pollinations_ok
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
    print("=" * 50)
    print("🚀 Voz Visible — Versión LIGERA con Pollinations")
    print("=" * 50)
    print(f"🖼️ Modelo: Pollinations AI (descripciones de CONTENIDO REAL)")
    print(f"📷 Cámara en vivo: ACTIVADA")
    print(f"💾 Memoria estimada: < 100 MB")
    print(f"💰 Costo: 100% GRATUITO (sin API key)")
    print(f"🌐 Entorno: {'Producción' if EN_PRODUCCION else 'Desarrollo'}")
    print("")
    print("🔍 Probando conexión con Pollinations...")
    pollinations_ok = verificar_pollinations()
    print(f"✅ Pollinations {'funciona ✅' if pollinations_ok else '⚠️ NO funciona (usando fallback técnico)'}")
    print("")
    
    port = int(os.environ.get('PORT', 5000))
    print(f"🔌 Escuchando en http://localhost:{port}")
    print("=" * 50)
    app.run(host='0.0.0.0', port=port, debug=not EN_PRODUCCION)