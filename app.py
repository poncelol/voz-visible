# ============================================================
# Voz Visible — Generador de audiodescripciones
# Versión con Groq Vision (100% GRATUITO) - IDIOMAS CORREGIDOS
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
# CONFIGURACIÓN GROQ (100% GRATUITO)
# ============================================================
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODELO = "qwen/qwen3.6-27b"

# ============================================================
# IDIOMAS
# ============================================================
IDIOMAS = {
    "es": {"nombre": "Español", "gtts": "es", "idioma_prompt": "Spanish"},
    "en": {"nombre": "Inglés", "gtts": "en", "idioma_prompt": "English"},
    "fr": {"nombre": "Francés", "gtts": "fr", "idioma_prompt": "French"},
    "de": {"nombre": "Alemán", "gtts": "de", "idioma_prompt": "German"},
    "it": {"nombre": "Italiano", "gtts": "it", "idioma_prompt": "Italian"},
    "pt": {"nombre": "Portugués", "gtts": "pt", "idioma_prompt": "Portuguese"},
}

# ============================================================
# FUNCIÓN PARA DESCRIBIR CON GROQ (GRATIS)
# ============================================================

def describir_con_groq(imagen_bytes: bytes, idioma: str = "es") -> str:
    """
    Usa Groq Vision para describir el CONTENIDO REAL de la imagen.
    Ahora soporta múltiples idiomas correctamente.
    """
    if not GROQ_API_KEY:
        print("⚠️ GROQ_API_KEY no configurada")
        return None
    
    try:
        # Obtener idioma del prompt
        idioma_config = IDIOMAS.get(idioma, IDIOMAS["es"])
        idioma_texto = idioma_config["idioma_prompt"]
        
        # Codificar imagen a base64
        imagen_base64 = base64.b64encode(imagen_bytes).decode('utf-8')
        
        # URL de Groq API
        url = "https://api.groq.com/openai/v1/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Prompt en el idioma solicitado
        prompts = {
            "es": "Describe esta imagen en español. Máximo 3 frases. Sé específico sobre lo que ves: personas, objetos, acciones, colores, ambiente. Responde ÚNICAMENTE en español.",
            "en": "Describe this image in English. Maximum 3 sentences. Be specific about what you see: people, objects, actions, colors, environment. Respond ONLY in English.",
            "fr": "Décrivez cette image en français. Maximum 3 phrases. Soyez spécifique sur ce que vous voyez : personnes, objets, actions, couleurs, environnement. Répondez UNIQUEMENT en français.",
            "de": "Beschreiben Sie dieses Bild auf Deutsch. Maximal 3 Sätze. Seien Sie spezifisch darüber, was Sie sehen: Menschen, Objekte, Aktionen, Farben, Umgebung. Antworten Sie NUR auf Deutsch.",
            "it": "Descrivi questa immagine in italiano. Massimo 3 frasi. Sii specifico su ciò che vedi: persone, oggetti, azioni, colori, ambiente. Rispondi SOLO in italiano.",
            "pt": "Descreva esta imagem em português. Máximo 3 frases. Seja específico sobre o que você vê: pessoas, objetos, ações, cores, ambiente. Responda APENAS em português.",
        }
        
        prompt_seleccionado = prompts.get(idioma, prompts["es"])
        
        payload = {
            "model": GROQ_MODELO,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt_seleccionado
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
            "max_tokens": 150,
            "temperature": 0.7
        }
        
        print(f"📤 Enviando a Groq en {idioma_texto}...")
        
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )
        
        print(f"📥 Respuesta Groq ({idioma}): {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            descripcion = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            if descripcion and len(descripcion) > 10:
                print(f"✅ Groq ({idioma}): {descripcion[:80]}...")
                return descripcion
        else:
            print(f"❌ Error Groq: {response.status_code} - {response.text}")
        
        return None
        
    except Exception as e:
        print(f"❌ Error en Groq: {e}")
        return None

# ============================================================
# TRADUCCIÓN CON GROQ (SI NO TENEMOS DESCRIPCIÓN EN ESE IDIOMA)
# ============================================================

def traducir_con_groq(texto: str, idioma_destino: str) -> Optional[str]:
    """
    Traduce texto usando Groq si la descripción falla en idioma nativo.
    """
    if not GROQ_API_KEY:
        return None
    
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        idioma_nombre = IDIOMAS.get(idioma_destino, {}).get("nombre", idioma_destino)
        
        payload = {
            "model": "mixtral-8x7b-32768",  # Modelo más rápido para traducción
            "messages": [
                {
                    "role": "user",
                    "content": f"Traduce este texto a {idioma_nombre}. Responde SOLO con la traducción, sin explicaciones:\n\n{texto}"
                }
            ],
            "max_tokens": 150,
            "temperature": 0.3
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            traduccion = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            if traduccion:
                print(f"✅ Traducción a {idioma_nombre}: OK")
                return traduccion
        
        return None
        
    except Exception as e:
        print(f"❌ Error en traducción: {e}")
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

def describir_imagen(imagen_bytes: bytes, idioma: str = "es") -> str:
    """Intenta con Groq primero en el idioma solicitado, luego fallback."""
    
    # Intentar con Groq en el idioma solicitado
    descripcion = describir_con_groq(imagen_bytes, idioma)
    if descripcion:
        return descripcion
    
    # Si falla, intentar en español y luego traducir
    if idioma != "es":
        print(f"⚠️ Groq falló en {idioma}, intentando en español...")
        descripcion_es = describir_con_groq(imagen_bytes, "es")
        if descripcion_es:
            descripcion_traducida = traducir_con_groq(descripcion_es, idioma)
            if descripcion_traducida:
                return descripcion_traducida
            return descripcion_es
    
    # Fallback técnico
    print("⚠️ Usando fallback técnico")
    return describir_tecnico(imagen_bytes)

# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def generar_audio(texto: str, ruta_salida: Path, idioma_gtts: str = "es") -> None:
    """Genera archivo de audio a partir de texto."""
    try:
        gTTS(text=texto, lang=idioma_gtts, slow=False).save(str(ruta_salida))
    except Exception as e:
        print(f"❌ Error generando audio: {e}")
        raise

def generar_imagen_ia(prompt: str, ruta_salida: Path) -> Path:
    """Genera imagen usando Pollinations AI."""
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
    """Procesa imagen, descripción en múltiples idiomas y genera audio."""
    
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

    # DESCRIBIR EN CADA IDIOMA
    descripciones = {}
    modelos_usados = {}
    
    for codigo in idiomas_elegidos:
        print(f"\n🌐 Procesando idioma: {codigo} ({IDIOMAS.get(codigo, {}).get('nombre', codigo)})")
        
        descripcion = describir_imagen(imagen_bytes, codigo)
        
        # Simplificar si es necesario
        if nivel_cognitivo == "simplificada":
            frases = descripcion.split('. ')
            if len(frases) > 3:
                descripcion = '. '.join(frases[:3]) + '.'
        
        descripciones[codigo] = descripcion
        
        # Detectar si es Groq o fallback
        es_groq = GROQ_API_KEY and "píxeles" not in descripcion.lower() and "composición" not in descripcion.lower()
        modelos_usados[codigo] = "Groq Vision" if es_groq else "Técnico (fallback)"

    # Generar audios
    audios = {}
    for codigo in idiomas_elegidos:
        texto_a_leer = descripciones.get(codigo, "")
        idioma_gtts = IDIOMAS.get(codigo, {}).get("gtts", "es")
        ruta_audio = GENERATED_DIR / f"{session_id}_audio_{codigo}.mp3"
        generar_audio(texto_a_leer, ruta_audio, idioma_gtts)
        audios[codigo] = ruta_audio.name

    return {
        "imagen_nombre": ruta_imagen.name,
        "descripciones": descripciones,
        "audios": audios,
        "nivel_cognitivo": nivel_cognitivo,
        "modelos_usados": modelos_usados,
        "idiomas_procesados": idiomas_elegidos
    }

# ============================================================
# RUTAS
# ============================================================

@app.route("/", methods=["GET"])
def index():
    """Página principal."""
    return render_template(
        "index.html",
        idiomas=IDIOMAS,
        api_configurada=bool(GROQ_API_KEY),
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
        groq_configurada=bool(GROQ_API_KEY)
    )

@app.route("/generar", methods=["POST"])
def generar():
    """Genera audiodescrpciones."""
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
            api_configurada=bool(GROQ_API_KEY),
            en_produccion=EN_PRODUCCION,
            error=None,
            resultado=resultado,
            valores=valores,
            groq_configurada=bool(GROQ_API_KEY)
        )
    except Exception as exc:
        print(f"❌ Error en /generar: {exc}")
        return render_template(
            "index.html",
            idiomas=IDIOMAS,
            api_configurada=bool(GROQ_API_KEY),
            en_produccion=EN_PRODUCCION,
            error=str(exc),
            resultado=None,
            valores=valores,
            groq_configurada=bool(GROQ_API_KEY)
        )

# ============================================================
# RUTAS DE CÁMARA
# ============================================================

@app.route('/api/camara/estado', methods=['GET'])
def estado_camara():
    """Retorna estado de la cámara."""
    return jsonify({
        'activo': True,
        'gratuito': True,
        'modelo': 'Groq Vision' if GROQ_API_KEY else 'Técnico (fallback)',
        'groq_configurada': bool(GROQ_API_KEY),
        'version': '2.1.0'
    })

@app.route('/api/camara/stream', methods=['POST'])
def procesar_stream_camara():
    """Procesa stream de cámara en vivo."""
    try:
        data = request.get_json()
        if not data or 'imagen' not in data:
            return jsonify({'error': 'No se recibió imagen'}), 400
        
        idioma = data.get('idioma', 'es')
        
        image_data = data['imagen']
        if ',' in image_data:
            _, encoded = image_data.split(',', 1)
        else:
            encoded = image_data
        image_bytes = base64.b64decode(encoded)
        
        # Describir imagen en el idioma solicitado
        descripcion = describir_imagen(image_bytes, idioma)
        
        # Generar audio
        session_id = uuid.uuid4().hex[:8]
        idioma_gtts = IDIOMAS.get(idioma, {}).get("gtts", "es")
        audio_path = GENERATED_DIR / f"{session_id}_camara.mp3"
        generar_audio(descripcion, audio_path, idioma_gtts)
        
        # Convertir audio a base64
        with open(audio_path, "rb") as f:
            audio_base64 = base64.b64encode(f.read()).decode('utf-8')
        
        # Limpiar archivo temporal
        try:
            os.remove(audio_path)
        except:
            pass
        
        es_groq = GROQ_API_KEY and "píxeles" not in descripcion.lower() and "composición" not in descripcion.lower()
        
        return jsonify({
            'descripcion': descripcion,
            'audio': audio_base64,
            'timestamp': datetime.now().isoformat(),
            'modelo': 'Groq Vision' if es_groq else 'Técnico (fallback)',
            'es_groq': es_groq,
            'idioma': idioma
        })
        
    except Exception as e:
        print(f"❌ Error en stream: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/estado', methods=['GET'])
def estado_sistema():
    """Retorna estado del sistema."""
    return jsonify({
        'modelo': {
            'nombre': 'Groq Vision' if GROQ_API_KEY else 'Técnico (fallback)',
            'gratuito': True,
            'memoria_mb': '< 50',
            'tipo': 'API externa (groq.com)',
            'groq_configurada': bool(GROQ_API_KEY),
            'descripcion_contenido_real': bool(GROQ_API_KEY),
            'soporta_multiidioma': True
        },
        'camara': {
            'activa': True,
            'gratuita': True,
            'fps': 0.33
        },
        'produccion': EN_PRODUCCION,
        'idiomas': list(IDIOMAS.keys()),
        'version': '2.1.0'
    })

# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == '__main__':
    print("=" * 55)
    print("🚀 Voz Visible — Versión 2.1 con Soporte Multiidioma")
    print("=" * 55)
    print(f"🖼️  Modelo: {'Groq Vision (CONTENIDO REAL)' if GROQ_API_KEY else 'Técnico (fallback)'}")
    print(f"📷 Cámara en vivo: ACTIVADA")
    print(f"🌐 Idiomas soportados: {', '.join([IDIOMAS[k]['nombre'] for k in IDIOMAS.keys()])}")
    print(f"💾 Memoria estimada: < 50 MB")
    print(f"💰 Costo: 100% GRATUITO")
    print("")
    
    if not GROQ_API_KEY:
        print("⚠️  IMPORTANTE: GROQ_API_KEY no configurada")
        print("   Obtén tu API key GRATIS en: https://console.groq.com")
        print("   Luego añádela como variable de entorno:")
        print("   GROQ_API_KEY=tu-api-key")
        print("")
    else:
        print("✅ Groq API configurada correctamente")
        print("   ✓ Descripciones en CONTENIDO REAL")
        print("   ✓ Soporte en 6 idiomas")
        print("   ✓ Traducción automática con Groq")
        print("")
    
    port = int(os.environ.get('PORT', 5000))
    print(f"🔌 Escuchando en http://localhost:{port}")
    print("=" * 55)
    app.run(host='0.0.0.0', port=port, debug=not EN_PRODUCCION)
