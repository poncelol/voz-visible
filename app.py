# ============================================================
# Voz Visible — Versión con Hugging Face API
# 100% gratuito, sin PyTorch, < 100 MB RAM
# ============================================================

import os
import uuid
import base64
import io
from pathlib import Path
from urllib.parse import quote
from datetime import datetime
from typing import Dict, Optional, List

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, url_for, jsonify
from gtts import gTTS
from PIL import Image, ImageStat

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
# FUNCIÓN PARA DESCRIBIR CON HUGGING FACE (GRATIS)
# ============================================================

def describir_con_huggingface(imagen_bytes: bytes) -> str:
    """
    Usa Hugging Face Inference API (gratuito, sin API key).
    Modelo: BLIP-base (descripciones de contenido REAL)
    """
    try:
        # Codificar imagen a base64
        imagen_base64 = base64.b64encode(imagen_bytes).decode('utf-8')
        
        # API de Hugging Face (gratuita, sin token para modelos públicos)
        # Usamos BLIP que describe contenido real
        API_URL = "https://api-inference.huggingface.co/models/Salesforce/blip-image-captioning-base"
        
        headers = {
            "Content-Type": "application/json"
            # No necesitas token para modelos públicos con rate limit
        }
        
        payload = {
            "inputs": imagen_base64,
            "parameters": {
                "max_length": 50,
                "num_beams": 4
            }
        }
        
        print(f"📤 Enviando a Hugging Face...")
        
        response = requests.post(
            API_URL,
            json=payload,
            headers=headers,
            timeout=30
        )
        
        print(f"📥 Respuesta: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            # Procesar respuesta
            if isinstance(data, list) and len(data) > 0:
                if isinstance(data[0], dict) and "generated_text" in data[0]:
                    descripcion = data[0]["generated_text"]
                    if descripcion and len(descripcion) > 10:
                        print(f"✅ Hugging Face: {descripcion}")
                        return descripcion
            elif isinstance(data, dict) and "generated_text" in data:
                descripcion = data["generated_text"]
                if descripcion and len(descripcion) > 10:
                    print(f"✅ Hugging Face: {descripcion}")
                    return descripcion
        
        # Si el rate limit está activo (429), esperar y reintentar
        if response.status_code == 429:
            print("⏳ Rate limit de Hugging Face, esperando...")
            time.sleep(3)
            # Reintentar una vez
            response = requests.post(API_URL, json=payload, headers=headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    if isinstance(data[0], dict) and "generated_text" in data[0]:
                        descripcion = data[0]["generated_text"]
                        if descripcion and len(descripcion) > 10:
                            return descripcion
        
        print("⚠️ Hugging Face no respondió correctamente")
        return None
        
    except requests.exceptions.Timeout:
        print("⏰ Timeout en Hugging Face")
        return None
    except Exception as e:
        print(f"❌ Error en Hugging Face: {e}")
        return None

# ============================================================
# DESCRIPCIÓN TÉCNICA (FALLBACK)
# ============================================================

def describir_tecnico(imagen_bytes: bytes) -> str:
    """Descripción técnica (fallback cuando la API falla)."""
    try:
        imagen = Image.open(io.BytesIO(imagen_bytes))
        ancho, alto = imagen.size
        
        # Color dominante
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
        if brillo > 200:
            brillo_texto = "muy brillante"
        elif brillo > 150:
            brillo_texto = "brillante"
        elif brillo > 100:
            brillo_texto = "luminosidad media"
        elif brillo > 50:
            brillo_texto = "oscuro"
        else:
            brillo_texto = "muy oscuro"
        
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
# FUNCIÓN PRINCIPAL DE DESCRIPCIÓN
# ============================================================

def describir_imagen(imagen_bytes: bytes) -> str:
    """Intenta con Hugging Face primero, luego fallback."""
    
    # Intentar con Hugging Face
    descripcion = describir_con_huggingface(imagen_bytes)
    if descripcion:
        return descripcion
    
    # Fallback técnico
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

    # DESCRIBIR
    descripcion_es = describir_imagen(imagen_bytes)
    
    # Si es nivel simplificado, acortar
    if nivel_cognitivo == "simplificada":
        frases = descripcion_es.split('. ')
        if len(frases) > 3:
            descripcion_es = '. '.join(frases[:3]) + '.'

    # Generar descripciones por idioma
    descripciones = {}
    if "es" in idiomas_elegidos:
        descripciones["es"] = descripcion_es

    for codigo in idiomas_elegidos:
        if codigo == "es":
            continue
        descripciones[codigo] = descripcion_es

    # Generar audios
    audios = {}
    for codigo in idiomas_elegidos:
        texto_a_leer = descripciones.get(codigo, descripcion_es)
        idioma_gtts = IDIOMAS.get(codigo, {}).get("gtts", "es")
        ruta_audio = GENERATED_DIR / f"{session_id}_audio_{codigo}.mp3"
        generar_audio(texto_a_leer, ruta_audio, idioma_gtts)
        audios[codigo] = ruta_audio.name

    es_ia = "píxeles" not in descripcion_es.lower() and "composición" not in descripcion_es.lower()

    return {
        "imagen_nombre": ruta_imagen.name,
        "descripciones": descripciones,
        "audios": audios,
        "nivel_cognitivo": nivel_cognitivo,
        "modelo_usado": "Hugging Face API" if es_ia else "Técnico (fallback)",
        "es_ia": es_ia
    }

# ============================================================
# RUTAS FLASK
# ============================================================

@app.route("/", methods=["GET"])
def index():
    return render_template(
        "index.html",
        idiomas=IDIOMAS,
        api_configurada=True,
        en_produccion=EN_PRODUCCION,
        error=None,
        resultado=None,
        valores={
            "nivel": "estándar",
            "idiomas": ["es"],
            "origen": "generar",
            "prompt": "Una cocina luminosa con dos personas cocinando",
            "traducir": False
        }
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
            "index.html",
            idiomas=IDIOMAS,
            api_configurada=True,
            en_produccion=EN_PRODUCCION,
            error=None,
            resultado=resultado,
            valores=valores
        )
    except Exception as exc:
        return render_template(
            "index.html",
            idiomas=IDIOMAS,
            api_configurada=True,
            en_produccion=EN_PRODUCCION,
            error=str(exc),
            resultado=None,
            valores=valores
        )

# ============================================================
# RUTAS DE CÁMARA
# ============================================================

@app.route('/api/camara/estado', methods=['GET'])
def estado_camara():
    return jsonify({
        'activo': True,
        'gratuito': True,
        'modelo': 'Hugging Face API',
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
        
        # DESCRIBIR
        descripcion = describir_imagen(image_bytes)
        
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
        
        es_ia = "píxeles" not in descripcion.lower() and "composición" not in descripcion.lower()
        
        return jsonify({
            'descripcion': descripcion,
            'audio': audio_base64,
            'timestamp': datetime.now().isoformat(),
            'modelo': 'Hugging Face' if es_ia else 'Técnico (fallback)',
            'es_ia': es_ia
        })
        
    except Exception as e:
        print(f"❌ Error en stream: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/estado', methods=['GET'])
def estado_sistema():
    return jsonify({
        'modelo': {
            'nombre': 'Hugging Face API',
            'gratuito': True,
            'memoria_mb': '< 100',
            'tipo': 'API externa (gratuita)'
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
    print("🚀 Voz Visible — Versión Hugging Face API")
    print("=" * 50)
    print(f"🖼️ Modelo: Hugging Face BLIP (descripciones de CONTENIDO REAL)")
    print(f"📷 Cámara en vivo: ACTIVADA")
    print(f"💾 Memoria estimada: < 100 MB")
    print(f"💰 Costo: 100% GRATUITO (sin API key)")
    print(f"🌐 Entorno: {'Producción' if EN_PRODUCCION else 'Desarrollo'}")
    print("")
    
    port = int(os.environ.get('PORT', 5000))
    print(f"🔌 Escuchando en http://localhost:{port}")
    print("=" * 50)
    app.run(host='0.0.0.0', port=port, debug=not EN_PRODUCCION)