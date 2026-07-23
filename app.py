# ============================================================
# Voz Visible — Generador de audiodescripciones inclusivas
# Versión con BLIP para descripciones de CONTENIDO REAL
# ============================================================

import os
import uuid
import base64
import time
import io
import json
from pathlib import Path
from urllib.parse import quote
from datetime import datetime
from typing import Tuple, List, Dict, Optional

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, url_for, jsonify
from gtts import gTTS
from PIL import Image, ImageStat, ImageFilter

# ============================================================
# IMPORTAR BLIP PARA DESCRIPCIONES DE CONTENIDO REAL
# ============================================================
try:
    from transformers import BlipProcessor, BlipForConditionalGeneration
    import torch
    BLIP_DISPONIBLE = True
    print("✅ BLIP disponible - Descripciones de CONTENIDO REAL")
except ImportError:
    BLIP_DISPONIBLE = False
    print("⚠️ BLIP no disponible - Usando análisis básico")

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
GENERATED_DIR = BASE_DIR / "static" / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024
app.secret_key = os.environ.get("SECRET_KEY", "tu-clave-secreta-aqui")

EN_PRODUCCION = os.environ.get('RENDER') == 'true'

# ============================================================
# INICIALIZAR BLIP (MODELO GRATUITO)
# ============================================================
if BLIP_DISPONIBLE:
    print("🔄 Cargando modelo BLIP...")
    try:
        processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
        model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
        print("✅ BLIP cargado correctamente")
    except Exception as e:
        print(f"❌ Error cargando BLIP: {e}")
        BLIP_DISPONIBLE = False
        processor = None
        model = None
else:
    processor = None
    model = None

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
TIEMPO_MINIMO_ENTRE_SOLICITUDES = 1

def verificar_limite_solicitudes(usuario="default") -> Tuple[bool, int]:
    ahora = datetime.now()
    if usuario in ultima_solicitud:
        diferencia = (ahora - ultima_solicitud[usuario]).total_seconds()
        if diferencia < TIEMPO_MINIMO_ENTRE_SOLICITUDES:
            return False, int(TIEMPO_MINIMO_ENTRE_SOLICITUDES - diferencia) + 1
    ultima_solicitud[usuario] = ahora
    return True, 0

# ============================================================
# FUNCIÓN PRINCIPAL: DESCRIPCIÓN CON BLIP (CONTENIDO REAL)
# ============================================================

def describir_imagen_con_blip(imagen_bytes: bytes) -> str:
    """Describe el CONTENIDO REAL de la imagen usando BLIP."""
    
    try:
        imagen = Image.open(io.BytesIO(imagen_bytes))
        
        # ============================================================
        # USAR BLIP PARA DESCRIBIR EL CONTENIDO REAL
        # ============================================================
        if BLIP_DISPONIBLE and model is not None and processor is not None:
            try:
                # Procesar imagen con BLIP
                inputs = processor(imagen, return_tensors="pt")
                
                # Generar descripción
                with torch.no_grad():
                    out = model.generate(
                        **inputs, 
                        max_length=50, 
                        num_beams=4,
                        temperature=0.7
                    )
                    descripcion = processor.decode(out[0], skip_special_tokens=True)
                
                if descripcion:
                    print(f"📝 BLIP: {descripcion}")
                    return descripcion
                    
            except Exception as e:
                print(f"❌ Error en BLIP: {e}")
                # Si BLIP falla, usar fallback
        
        # ============================================================
        # FALLBACK: DESCRIPCIÓN TÉCNICA (solo si BLIP no funciona)
        # ============================================================
        color = "desconocido"
        try:
            img_pequena = imagen.resize((50, 50))
            colores = img_pequena.getcolors(2500)
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
        except:
            pass
        
        return f"Imagen con colores predominantes {color}. (Descripción de contenido no disponible)"
        
    except Exception as e:
        print(f"❌ Error en análisis: {e}")
        return "No se pudo analizar la imagen."

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

    # DESCRIBIR CON BLIP (CONTENIDO REAL)
    descripcion_es = describir_imagen_con_blip(imagen_bytes)
    
    descripciones = {}
    if "es" in idiomas_elegidos:
        descripciones["es"] = descripcion_es

    # Traducciones (simplificadas)
    for codigo in idiomas_elegidos:
        if codigo == "es":
            continue
        descripciones[codigo] = descripcion_es  # Por ahora igual

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
        "modelo_usado": "BLIP" if BLIP_DISPONIBLE else "Fallback",
    }

# ============================================================
# RUTAS FLASK
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
            "index.html", idiomas=IDIOMAS, api_configurada=BLIP_DISPONIBLE,
            en_produccion=EN_PRODUCCION,
            error=None, resultado=resultado, valores=valores,
            blip_disponible=BLIP_DISPONIBLE
        )
    except Exception as exc:
        error_amigable = f"No se pudo completar el proceso: {exc}"
        return render_template(
            "index.html", idiomas=IDIOMAS, api_configurada=BLIP_DISPONIBLE,
            en_produccion=EN_PRODUCCION,
            error=error_amigable,
            resultado=None, valores=valores,
            blip_disponible=BLIP_DISPONIBLE
        )

# ============================================================
# RUTAS DE CÁMARA EN VIVO
# ============================================================

@app.route('/api/camara/estado', methods=['GET'])
def estado_camara():
    return jsonify({
        'activo': True,
        'modo': 'BLIP' if BLIP_DISPONIBLE else 'Fallback',
        'gratuito': True,
        'modelo': 'BLIP (descripciones de contenido real)' if BLIP_DISPONIBLE else 'Análisis básico',
        'version': '2.0.0',
        'blip_disponible': BLIP_DISPONIBLE
    })

@app.route('/api/camara/stream', methods=['POST'])
def procesar_stream_camara():
    """Procesa fotogramas con BLIP para descripciones de CONTENIDO REAL."""
    try:
        data = request.get_json()
        if not data or 'imagen' not in data:
            return jsonify({'error': 'No se recibió imagen'}), 400

        # Rate limit
        ip_usuario = request.remote_addr or "default"
        puede_proceder, tiempo_espera = verificar_limite_solicitudes(ip_usuario)
        if not puede_proceder:
            return jsonify({
                'error': 'rate_limit',
                'mensaje': f'Espera {tiempo_espera} segundos'
            }), 429

        # Decodificar imagen
        image_data = data['imagen']
        if ',' in image_data:
            _, encoded = image_data.split(',', 1)
        else:
            encoded = image_data
        image_bytes = base64.b64decode(encoded)
        
        # DESCRIBIR CON BLIP (CONTENIDO REAL)
        descripcion = describir_imagen_con_blip(image_bytes)
        
        # Generar audio
        session_id = uuid.uuid4().hex[:8]
        audio_path = GENERATED_DIR / f"{session_id}_camara.mp3"
        
        idioma = data.get('idioma', 'es')
        idioma_gtts = IDIOMAS.get(idioma, {}).get("gtts", "es")
        
        generar_audio(descripcion, audio_path, idioma_gtts)
        
        # Convertir audio a base64
        with open(audio_path, "rb") as f:
            audio_base64 = base64.b64encode(f.read()).decode('utf-8')
        
        # Limpiar archivo temporal
        try:
            os.remove(audio_path)
        except:
            pass
        
        return jsonify({
            'descripcion': descripcion,
            'audio': audio_base64,
            'timestamp': datetime.now().isoformat(),
            'modelo': 'BLIP' if BLIP_DISPONIBLE else 'Fallback'
        })
        
    except Exception as e:
        print(f"❌ Error en stream: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/estado', methods=['GET'])
def estado_sistema():
    return jsonify({
        'modelo': {
            'nombre': 'BLIP' if BLIP_DISPONIBLE else 'Fallback',
            'gratuito': True,
            'memoria_mb': '< 500' if BLIP_DISPONIBLE else '< 100',
            'tipo': 'IA para descripción de contenido',
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
    print("🚀 Voz Visible iniciado")
    print(f"🖼️ Modelo: {'BLIP (descripciones de CONTENIDO REAL)' if BLIP_DISPONIBLE else 'Fallback (solo formato)'}")
    print(f"📷 Cámara en vivo: ACTIVADA")
    print(f"💾 Memoria estimada: {'~500 MB' if BLIP_DISPONIBLE else '< 100 MB'}")
    print(f"🌐 Entorno: {'Producción' if EN_PRODUCCION else 'Desarrollo'}")
    print("")
    
    port = int(os.environ.get('PORT', 5000))
    print(f"🔌 Escuchando en el puerto {port}")
    app.run(host='0.0.0.0', port=port, debug=not EN_PRODUCCION)