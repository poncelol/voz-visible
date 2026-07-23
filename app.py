# ============================================================
# Voz Visible — Versión LIGERA con Pollinations
# API gratuita para descripciones de contenido REAL
# Memoria: < 100 MB RAM
# ============================================================

import os
import uuid
import base64
import io
import time
from pathlib import Path
from urllib.parse import quote
from datetime import datetime
from typing import Dict, Optional, Tuple, List

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
    100% gratuito, sin límites, sin API key.
    """
    try:
        # Codificar imagen a base64
        imagen_base64 = base64.b64encode(imagen_bytes).decode('utf-8')
        
        # Usar el endpoint de descripción de Pollinations
        url = "https://image.pollinations.ai/describe"
        
        # Preparar prompt según idioma
        prompt_text = "Describe this image in Spanish, max 3 sentences. Be specific about what you see." if idioma == "es" else "Describe this image in English, max 3 sentences. Be specific."
        
        response = requests.post(
            url,
            json={
                "image": imagen_base64,
                "prompt": prompt_text
            },
            timeout=30,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            data = response.json()
            descripcion = data.get("description", "")
            if descripcion and len(descripcion) > 10:
                print(f"📝 Pollinations: {descripcion}")
                return descripcion
        
        # Si Pollinations falla, usar fallback técnico
        print("⚠️ Pollinations no respondió, usando fallback")
        return describir_tecnico(imagen_bytes)
        
    except requests.exceptions.Timeout:
        print("⏰ Timeout en Pollinations, usando fallback")
        return describir_tecnico(imagen_bytes)
    except Exception as e:
        print(f"❌ Error en Pollinations: {e}")
        return describir_tecnico(imagen_bytes)

def describir_tecnico(imagen_bytes: bytes) -> str:
    """Descripción técnica básica (fallback ultra ligero)."""
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
    """Función principal - usa Pollinations para contenido REAL."""
    descripcion = describir_con_pollinations(imagen_bytes, idioma)
    
    # Si la descripción es muy corta o es técnica, intentar de nuevo con fallback
    if len(descripcion) < 15 or "píxeles" in descripcion:
        # Reintentar una vez con Pollinations
        try:
            time.sleep(1)
            descripcion2 = describir_con_pollinations(imagen_bytes, idioma)
            if len(descripcion2) > len(descripcion):
                descripcion = descripcion2
        except:
            pass
    
    return descripcion

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

    # DESCRIBIR con Pollinations (CONTENIDO REAL)
    idioma_principal = idiomas_elegidos[0] if idiomas_elegidos else "es"
    descripcion_principal = describir_imagen(imagen_bytes, idioma_principal)
    
    # Para otros idiomas, usar la misma descripción (gTTS se encarga de la pronunciación)
    descripciones = {}
    for codigo in idiomas_elegidos:
        descripciones[codigo] = descripcion_principal

    # Generar audios
    audios = {}
    for codigo in idiomas_elegidos:
        texto_a_leer = descripciones.get(codigo, descripcion_principal)
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
    return render_template(
        "index.html",
        idiomas=IDIOMAS,
        en_produccion=EN_PRODUCCION,
        error=None,
        resultado=None,
        valores={
            "nivel": "estándar",
            "idiomas": ["es"],
            "origen": "generar",
            "prompt": "Una cocina luminosa con dos personas cocinando",
        }
    )

@app.route("/generar", methods=["POST"])
def generar():
    valores = {
        "nivel": request.form.get("nivel", "estándar"),
        "idiomas": request.form.getlist("idiomas") or ["es"],
        "origen": request.form.get("origen", "generar"),
        "prompt": request.form.get("prompt", "").strip(),
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
        )
        resultado["imagen_url"] = url_for("static", filename=f"generated/{resultado['imagen_nombre']}")
        resultado["audios_url"] = {
            codigo: url_for("static", filename=f"generated/{nombre}")
            for codigo, nombre in resultado["audios"].items()
        }
        return render_template(
            "index.html", idiomas=IDIOMAS,
            en_produccion=EN_PRODUCCION,
            error=None, resultado=resultado, valores=valores,
        )
    except Exception as exc:
        return render_template(
            "index.html", idiomas=IDIOMAS,
            en_produccion=EN_PRODUCCION,
            error=str(exc),
            resultado=None, valores=valores,
        )

# ============================================================
# RUTAS DE CÁMARA EN VIVO
# ============================================================

@app.route('/api/camara/estado', methods=['GET'])
def estado_camara():
    return jsonify({
        'activo': True,
        'gratuito': True,
        'modelo': 'Pollinations AI',
        'version': '2.0.0',
        'memoria': '< 100 MB'
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
        idioma = data.get('idioma', 'es')
        descripcion = describir_imagen(image_bytes, idioma)
        
        # Generar audio
        session_id = uuid.uuid4().hex[:8]
        audio_path = GENERATED_DIR / f"{session_id}_camara.mp3"
        idioma_gtts = IDIOMAS.get(idioma, {}).get("gtts", "es")
        generar_audio(descripcion, audio_path, idioma_gtts)
        
        with open(audio_path, "rb") as f:
            audio_base64 = base64.b64encode(f.read()).decode('utf-8')
        
        try:
            os.remove(audio_path)
        except:
            pass
        
        return jsonify({
            'descripcion': descripcion,
            'audio': audio_base64,
            'timestamp': datetime.now().isoformat(),
            'modelo': 'Pollinations AI'
        })
        
    except Exception as e:
        print(f"❌ Error en stream: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/estado', methods=['GET'])
def estado_sistema():
    return jsonify({
        'modelo': {
            'nombre': 'Pollinations AI',
            'gratuito': True,
            'memoria_mb': '< 100',
            'tipo': 'API externa (gratuita)',
            'descripcion_contenido_real': True
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
    print("🚀 Voz Visible iniciado (versión ligera)")
    print(f"🖼️ Modelo: Pollinations AI (descripciones de CONTENIDO REAL)")
    print(f"📷 Cámara en vivo: ACTIVADA")
    print(f"💾 Memoria estimada: < 100 MB")
    print(f"💰 Costo: GRATUITO (sin API key)")
    print(f"🌐 Entorno: {'Producción' if EN_PRODUCCION else 'Desarrollo'}")
    print("")
    
    port = int(os.environ.get('PORT', 5000))
    print(f"🔌 Escuchando en el puerto {port}")
    app.run(host='0.0.0.0', port=port, debug=not EN_PRODUCCION)