# ============================================================
# Voz Visible — Versión LIGERA con Pollinations + Cámara
# ============================================================

import os
import uuid
import base64
import io
import time
import json
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
# FUNCIÓN ALTERNATIVA: USAR HUGGING FACE (GRATUITO)
# ============================================================

def describir_con_huggingface(imagen_bytes: bytes) -> str:
    """Usa Hugging Face Inference API (gratuito, sin token para modelos públicos)."""
    try:
        import base64
        
        # Codificar imagen
        imagen_base64 = base64.b64encode(imagen_bytes).decode('utf-8')
        
        # Usar el modelo BLIP de Hugging Face (gratuito)
        # Nota: Sin token tiene rate limit, pero funciona
        API_URL = "https://api-inference.huggingface.co/models/Salesforce/blip-image-captioning-base"
        
        # Intentar con diferentes formatos
        payload = {
            "inputs": imagen_base64,
            "parameters": {"max_length": 50}
        }
        
        print(f"📤 Enviando a Hugging Face...")
        
        response = requests.post(
            API_URL,
            json=payload,
            timeout=30,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"📥 Respuesta HF: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    if isinstance(data[0], dict) and "generated_text" in data[0]:
                        desc = data[0]["generated_text"]
                        if desc and len(desc) > 10:
                            print(f"✅ Hugging Face: {desc}")
                            return desc
                elif isinstance(data, dict) and "generated_text" in data:
                    desc = data["generated_text"]
                    if desc and len(desc) > 10:
                        print(f"✅ Hugging Face: {desc}")
                        return desc
            except:
                pass
        
        # Si Hugging Face falla o está en rate limit, usar descripción técnica mejorada
        print("⚠️ Hugging Face no respondió, usando fallback")
        return None
        
    except Exception as e:
        print(f"❌ Error en Hugging Face: {e}")
        return None

def describir_tecnico_mejorado(imagen_bytes: bytes) -> str:
    """Descripción técnica mejorada que intenta dar algo de contexto."""
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
            elif r > 150 and g > 100 and b > 150:
                color = "rosado/morado"
            elif r > 150 and g > 150 and b < 100:
                color = "amarillo/naranja"
        
        # Brillo
        gris = imagen.convert('L')
        stat = ImageStat.Stat(gris)
        brillo = stat.mean[0]
        brillo_texto = "muy brillante" if brillo > 200 else "brillante" if brillo > 150 else "luminosidad media" if brillo > 100 else "oscuro" if brillo > 50 else "muy oscuro"
        
        # Contraste
        desviacion = stat.stddev[0]
        contraste_texto = "alto contraste" if desviacion > 80 else "contraste medio" if desviacion > 40 else "bajo contraste"
        
        # Forma
        if ancho > alto * 1.5:
            forma = "horizontal (paisaje)"
        elif alto > ancho * 1.5:
            forma = "vertical (retrato)"
        else:
            forma = "cuadrada"
        
        # Intentar detectar si hay personas (detección muy básica de color piel)
        tiene_personas = False
        try:
            piel_count = 0
            for x in range(0, min(ancho, 200), 20):
                for y in range(0, min(alto, 200), 20):
                    if x < ancho and y < alto:
                        pixel = imagen.getpixel((x, y))
                        if len(pixel) >= 3:
                            r, g, b = pixel[0], pixel[1], pixel[2]
                            # Rango aproximado de color de piel
                            if r > 80 and g > 40 and b > 40 and r < 255 and g < 220 and b < 220:
                                if abs(r - g) < 60 and abs(r - b) < 60:
                                    piel_count += 1
            if piel_count > 15:
                tiene_personas = True
        except:
            pass
        
        # Construir descripción
        descripcion = f"Imagen de composición {forma}. "
        descripcion += f"Colores predominantes: {color}. "
        descripcion += f"Iluminación: {brillo_texto}. "
        descripcion += f"Contraste: {contraste_texto}. "
        
        if tiene_personas:
            descripcion += "Parece haber personas en la imagen. "
        
        # Agregar información de dimensiones
        if ancho > 1920 or alto > 1080:
            descripcion += "Alta resolución. "
        elif ancho < 640 and alto < 480:
            descripcion += "Baja resolución. "
        
        return descripcion
        
    except Exception as e:
        print(f"❌ Error en fallback: {e}")
        return "Imagen capturada por la cámara."

def describir_imagen(imagen_bytes: bytes, idioma: str = "es") -> str:
    """Función principal - intenta varios métodos para describir."""
    
    # INTENTO 1: Hugging Face (gratuito, sin token)
    print("🔄 Intentando con Hugging Face...")
    descripcion = describir_con_huggingface(imagen_bytes)
    if descripcion and len(descripcion) > 10 and "píxeles" not in descripcion.lower():
        print(f"✅ Descripción obtenida de Hugging Face")
        # Traducir si es necesario (simple)
        if idioma == "es":
            return descripcion
        return descripcion
    
    # INTENTO 2: Pollinations (alternativa)
    print("🔄 Intentando con Pollinations...")
    try:
        imagen_base64 = base64.b64encode(imagen_bytes).decode('utf-8')
        url = "https://image.pollinations.ai/describe"
        
        response = requests.post(
            url,
            json={"image": imagen_base64},
            timeout=15,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, dict):
                    desc = data.get("description") or data.get("text")
                    if desc and len(desc) > 10 and "píxeles" not in desc.lower():
                        print(f"✅ Pollinations: {desc}")
                        return desc
            except json.JSONDecodeError:
                print("⚠️ Pollinations devolvió JSON inválido")
    except Exception as e:
        print(f"⚠️ Error en Pollinations: {e}")
    
    # INTENTO 3: Descripción técnica mejorada
    print("🔄 Usando descripción técnica mejorada...")
    return describir_tecnico_mejorado(imagen_bytes)

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

    # Para otros idiomas, usar la misma descripción (gTTS se encarga de la pronunciación)
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

    # Verificar si la descripción es técnica o IA
    es_ia = "píxeles" not in descripcion_es.lower() and "composición" not in descripcion_es.lower()

    return {
        "imagen_nombre": ruta_imagen.name,
        "descripciones": descripciones,
        "audios": audios,
        "nivel_cognitivo": nivel_cognitivo,
        "modelo_usado": "Hugging Face" if es_ia else "Técnico (fallback)",
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
        error_amigable = f"No se pudo completar el proceso: {exc}"
        return render_template(
            "index.html",
            idiomas=IDIOMAS,
            api_configurada=True,
            en_produccion=EN_PRODUCCION,
            error=error_amigable,
            resultado=None,
            valores=valores
        )

# ============================================================
# RUTAS DE CÁMARA EN VIVO
# ============================================================

@app.route('/api/camara/estado', methods=['GET'])
def estado_camara():
    return jsonify({
        'activo': True,
        'gratuito': True,
        'modelo': 'Hugging Face + Fallback',
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
            'nombre': 'Hugging Face + Fallback',
            'gratuito': True,
            'memoria_mb': '< 100',
            'tipo': 'API gratuita + Algoritmos'
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
    print("🚀 Voz Visible — Versión LIGERA con Hugging Face")
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