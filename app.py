# ============================================================
# Voz Visible — Versión con BLIP LOCAL (CONTENIDO REAL)
# ============================================================

import os
import uuid
import base64
import io
import gc
from pathlib import Path
from urllib.parse import quote
from datetime import datetime
from typing import Dict, Optional, List

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, url_for, jsonify
from gtts import gTTS
from PIL import Image, ImageStat

# ============================================================
# IMPORTAR BLIP LOCAL
# ============================================================
try:
    from transformers import BlipProcessor, BlipForConditionalGeneration
    import torch
    BLIP_DISPONIBLE = True
    print("✅ BLIP disponible")
except ImportError:
    BLIP_DISPONIBLE = False
    print("❌ BLIP no disponible")

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
GENERATED_DIR = BASE_DIR / "static" / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024
app.secret_key = os.environ.get("SECRET_KEY", "tu-clave-secreta-aqui")

EN_PRODUCCION = os.environ.get('RENDER') == 'true'

# ============================================================
# CARGAR BLIP
# ============================================================
processor = None
model = None

if BLIP_DISPONIBLE:
    print("🔄 Cargando BLIP...")
    try:
        # Usar cache para evitar descargas repetidas
        cache_dir = os.path.join(BASE_DIR, "model_cache")
        os.makedirs(cache_dir, exist_ok=True)
        
        processor = BlipProcessor.from_pretrained(
            "Salesforce/blip-image-captioning-base",
            cache_dir=cache_dir
        )
        model = BlipForConditionalGeneration.from_pretrained(
            "Salesforce/blip-image-captioning-base",
            cache_dir=cache_dir
        )
        model.eval()
        print("✅ BLIP cargado correctamente")
    except Exception as e:
        print(f"❌ Error cargando BLIP: {e}")
        BLIP_DISPONIBLE = False
        processor = None
        model = None

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
# DESCRIBIR CON BLIP LOCAL (CONTENIDO REAL)
# ============================================================

def describir_con_blip(imagen_bytes: bytes) -> str:
    """Usa BLIP local para describir el CONTENIDO REAL."""
    if not BLIP_DISPONIBLE or model is None or processor is None:
        return None
    
    try:
        # Abrir imagen
        imagen = Image.open(io.BytesIO(imagen_bytes))
        
        # Reducir si es muy grande (ahorra memoria)
        max_size = 800
        if imagen.width > max_size or imagen.height > max_size:
            imagen.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        # Procesar con BLIP
        inputs = processor(imagen, return_tensors="pt")
        
        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_length=50,
                num_beams=4,
                temperature=0.7
            )
            descripcion = processor.decode(out[0], skip_special_tokens=True)
        
        if descripcion and len(descripcion) > 10:
            print(f"✅ BLIP: {descripcion}")
            return descripcion
        
        return None
        
    except Exception as e:
        print(f"❌ Error en BLIP: {e}")
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
    """Intenta BLIP primero, luego fallback."""
    
    # Intentar con BLIP (CONTENIDO REAL)
    descripcion = describir_con_blip(imagen_bytes)
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
# PROCESAMIENTO
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
    
    if nivel_cognitivo == "simplificada":
        frases = descripcion_es.split('. ')
        if len(frases) > 3:
            descripcion_es = '. '.join(frases[:3]) + '.'

    descripciones = {}
    if "es" in idiomas_elegidos:
        descripciones["es"] = descripcion_es

    for codigo in idiomas_elegidos:
        if codigo == "es":
            continue
        descripciones[codigo] = descripcion_es

    audios = {}
    for codigo in idiomas_elegidos:
        texto_a_leer = descripciones.get(codigo, descripcion_es)
        idioma_gtts = IDIOMAS.get(codigo, {}).get("gtts", "es")
        ruta_audio = GENERATED_DIR / f"{session_id}_audio_{codigo}.mp3"
        generar_audio(texto_a_leer, ruta_audio, idioma_gtts)
        audios[codigo] = ruta_audio.name

    es_blip = BLIP_DISPONIBLE and "píxeles" not in descripcion_es.lower() and "composición" not in descripcion_es.lower()

    return {
        "imagen_nombre": ruta_imagen.name,
        "descripciones": descripciones,
        "audios": audios,
        "nivel_cognitivo": nivel_cognitivo,
        "modelo_usado": "BLIP Local" if es_blip else "Técnico (fallback)",
        "es_blip": es_blip
    }

# ============================================================
# RUTAS
# ============================================================

@app.route("/", methods=["GET"])
def index():
    return render_template(
        "index.html",
        idiomas=IDIOMAS,
        api_configurada=BLIP_DISPONIBLE,
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
        blip_disponible=BLIP_DISPONIBLE
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
            api_configurada=BLIP_DISPONIBLE,
            en_produccion=EN_PRODUCCION,
            error=None,
            resultado=resultado,
            valores=valores,
            blip_disponible=BLIP_DISPONIBLE
        )
    except Exception as exc:
        return render_template(
            "index.html",
            idiomas=IDIOMAS,
            api_configurada=BLIP_DISPONIBLE,
            en_produccion=EN_PRODUCCION,
            error=str(exc),
            resultado=None,
            valores=valores,
            blip_disponible=BLIP_DISPONIBLE
        )

# ============================================================
# RUTAS DE CÁMARA
# ============================================================

@app.route('/api/camara/estado', methods=['GET'])
def estado_camara():
    return jsonify({
        'activo': True,
        'gratuito': True,
        'modelo': 'BLIP Local' if BLIP_DISPONIBLE else 'Técnico (fallback)',
        'blip_disponible': BLIP_DISPONIBLE,
        'version': '2.0.0'
    })

@app.route('/api/camara/stream', methods=['POST'])
def procesar_stream_camara():
    try:
        data = request.get_json()
        if not data or 'imagen' not in data:
            return jsonify({'error': 'No se recibió imagen'}), 400
        
        image_data = data['imagen']
        if ',' in image_data:
            _, encoded = image_data.split(',', 1)
        else:
            encoded = image_data
        image_bytes = base64.b64decode(encoded)
        
        descripcion = describir_imagen(image_bytes)
        
        session_id = uuid.uuid4().hex[:8]
        audio_path = GENERATED_DIR / f"{session_id}_camara.mp3"
        generar_audio(descripcion, audio_path, "es")
        
        with open(audio_path, "rb") as f:
            audio_base64 = base64.b64encode(f.read()).decode('utf-8')
        
        try:
            os.remove(audio_path)
        except:
            pass
        
        es_blip = BLIP_DISPONIBLE and "píxeles" not in descripcion.lower() and "composición" not in descripcion.lower()
        
        return jsonify({
            'descripcion': descripcion,
            'audio': audio_base64,
            'timestamp': datetime.now().isoformat(),
            'modelo': 'BLIP Local' if es_blip else 'Técnico (fallback)',
            'es_blip': es_blip
        })
        
    except Exception as e:
        print(f"❌ Error en stream: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/estado', methods=['GET'])
def estado_sistema():
    return jsonify({
        'modelo': {
            'nombre': 'BLIP Local' if BLIP_DISPONIBLE else 'Técnico (fallback)',
            'gratuito': True,
            'memoria_mb': '~500' if BLIP_DISPONIBLE else '< 100',
            'tipo': 'IA local (Transformers)',
            'blip_disponible': BLIP_DISPONIBLE,
            'descripcion_contenido_real': BLIP_DISPONIBLE
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
    print("🚀 Voz Visible — Versión con BLIP LOCAL")
    print("=" * 55)
    print(f"🖼️ Modelo: {'BLIP Local (CONTENIDO REAL)' if BLIP_DISPONIBLE else 'Técnico (fallback)'}")
    print(f"📷 Cámara en vivo: ACTIVADA")
    print(f"💾 Memoria estimada: {'~500 MB' if BLIP_DISPONIBLE else '< 100 MB'}")
    print(f"💰 Costo: 100% GRATUITO")
    print("")
    print("📝 Ejemplo de descripción que verás:")
    print("   ✅ 'Una mujer está cocinando en una cocina moderna'")
    print("   ❌ 'Imagen cuadrada, colores negro, muy oscuro'")
    print("")
    
    port = int(os.environ.get('PORT', 5000))
    print(f"🔌 Escuchando en http://localhost:{port}")
    print("=" * 55)
    app.run(host='0.0.0.0', port=port, debug=not EN_PRODUCCION)