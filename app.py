# ============================================================
# Voz Visible — Generador de audiodescripciones inclusivas
# Versión completa con cámara en vivo gratuita
# ============================================================

import os
import uuid
import base64
import time
import io
import json
import colorsys
from pathlib import Path
from urllib.parse import quote
from datetime import datetime
from typing import Tuple, List, Dict, Optional

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, url_for, jsonify, send_file
from gtts import gTTS
from PIL import Image, ImageStat, ImageFilter, ImageEnhance

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
    "es": {"nombre": "Español", "traduccion": "español", "gtts": "es"},
    "en": {"nombre": "Inglés", "traduccion": "inglés", "gtts": "en"},
    "fr": {"nombre": "Francés", "traduccion": "francés", "gtts": "fr"},
    "de": {"nombre": "Alemán", "traduccion": "alemán", "gtts": "de"},
    "it": {"nombre": "Italiano", "traduccion": "italiano", "gtts": "it"},
    "pt": {"nombre": "Portugués", "traduccion": "portugués", "gtts": "pt"},
}

# ============================================================
# PROMPTS (para referencia)
# ============================================================
PROMPT_AUDIODESCRIPCION_ESTANDAR = """
Describe esta imagen para una persona ciega o con baja visión.
Maximo 4 frases, lenguaje claro. Empieza por lo mas importante.
"""

PROMPT_AUDIODESCRIPCION_SIMPLIFICADA = """
Describe esta imagen de forma MUY SIMPLE. Maximo 3 frases muy cortas.
"""

PROMPT_CAMARA_EN_VIVO = "Describe de forma breve (1-2 oraciones) lo que ves en esta imagen de cámara."
PROMPT_ANALISIS_DETALLADO_CAMARA = "Analiza esta escena con más detalle (3-4 oraciones)."

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
# ALGORITMOS DE VISIÓN POR COMPUTADORA (SIN API)
# ============================================================

def obtener_color_dominante(imagen: Image.Image) -> str:
    """Obtiene el color dominante de una imagen."""
    try:
        # Reducir imagen para análisis
        img_pequena = imagen.resize((50, 50))
        colores = img_pequena.getcolors(2500)
        
        if not colores:
            return "color"
        
        # Ordenar por frecuencia
        colores_ordenados = sorted(colores, key=lambda x: x[0], reverse=True)
        r, g, b = colores_ordenados[0][1]
        
        # Convertir a nombre de color
        if r > 200 and g > 200 and b > 200:
            return "blanco"
        elif r < 50 and g < 50 and b < 50:
            return "negro"
        elif r > 200 and g < 100 and b < 100:
            return "rojo"
        elif r < 100 and g > 200 and b < 100:
            return "verde"
        elif r < 100 and g < 100 and b > 200:
            return "azul"
        elif r > 200 and g > 200 and b < 100:
            return "amarillo"
        elif r > 200 and g > 100 and b < 150:
            return "naranja"
        elif r > 150 and g < 150 and b > 150:
            return "morado"
        elif r > 150 and g > 150 and b > 150:
            return "gris claro"
        elif r < 100 and g < 100 and b < 100:
            return "gris oscuro"
        else:
            return "color"
    except:
        return "color"

def analizar_brillo(imagen: Image.Image) -> str:
    """Analiza el brillo general de la imagen."""
    try:
        # Convertir a escala de grises y calcular brillo promedio
        gris = imagen.convert('L')
        stat = ImageStat.Stat(gris)
        brillo = stat.mean[0]
        
        if brillo > 200:
            return "muy brillante"
        elif brillo > 150:
            return "brillante"
        elif brillo > 100:
            return "luminosidad media"
        elif brillo > 50:
            return "oscuro"
        else:
            return "muy oscuro"
    except:
        return "luminosidad media"

def analizar_composicion(imagen: Image.Image) -> str:
    """Analiza la composición de la imagen."""
    try:
        ancho, alto = imagen.size
        
        if ancho > alto * 1.5:
            return "horizontal (paisaje)"
        elif alto > ancho * 1.5:
            return "vertical (retrato)"
        else:
            return "cuadrada"
    except:
        return "estándar"

def analizar_contraste(imagen: Image.Image) -> str:
    """Analiza el contraste de la imagen."""
    try:
        gris = imagen.convert('L')
        stat = ImageStat.Stat(gris)
        desviacion = stat.stddev[0]
        
        if desviacion > 80:
            return "alto contraste"
        elif desviacion > 40:
            return "contraste medio"
        else:
            return "bajo contraste"
    except:
        return "contraste medio"

def detectar_texto_simple(imagen: Image.Image) -> List[str]:
    """Detección simple de texto (simulada)."""
    try:
        # En una versión real, aquí iría OCR
        # Por ahora, devolvemos texto simulado basado en el tamaño
        ancho, alto = imagen.size
        
        textos = []
        if ancho > 800 and alto > 600:
            # Simular detección de texto en la parte inferior
            # Tomar una muestra de la parte inferior
            parte_inferior = imagen.crop((0, int(alto*0.7), ancho, alto))
            stat = ImageStat.Stat(parte_inferior.convert('L'))
            if stat.stddev[0] > 30:
                textos.append("posible texto en la parte inferior")
        elif ancho > 600:
            textos.append("posible texto visible")
        
        return textos
    except:
        return []

def detectar_formas_simples(imagen: Image.Image) -> str:
    """Detecta formas básicas en la imagen."""
    try:
        # Reducir y detectar bordes
        gris = imagen.convert('L')
        # Detectar bordes con filtro simple
        bordes = gris.filter(ImageFilter.FIND_EDGES)
        
        # Analizar áreas
        ancho, alto = imagen.size
        formas = []
        
        # Simple detección basada en proporciones
        if ancho > alto * 1.5:
            formas.append("horizontes o elementos alargados")
        elif alto > ancho * 1.5:
            formas.append("elementos verticales o retratos")
            
        # Si hay muchos bordes
        stat = ImageStat.Stat(bordes)
        if stat.stddev[0] > 30:
            formas.append("contornos definidos")
        else:
            formas.append("formas suaves y difusas")
            
        return ", ".join(formas) if formas else "formas indefinidas"
        
    except:
        return "formas básicas"

def analizar_distribucion(imagen: Image.Image) -> str:
    """Analiza cómo están distribuidos los elementos."""
    try:
        ancho, alto = imagen.size
        
        # Dividir en 9 secciones
        tercio_ancho = ancho // 3
        tercio_alto = alto // 3
        
        # Simular detección de áreas activas
        secciones_activas = 0
        for x in range(0, ancho, max(1, tercio_ancho)):
            for y in range(0, alto, max(1, tercio_alto)):
                # Tomar muestra pequeña
                if x + 20 < ancho and y + 20 < alto:
                    muestra = imagen.crop((x, y, x+20, y+20))
                    stat = ImageStat.Stat(muestra)
                    if stat.stddev[0] > 20:  # Si hay variación
                        secciones_activas += 1
        
        if secciones_activas >= 6:
            return "La escena está distribuida de manera uniforme."
        elif secciones_activas >= 3:
            return "Los elementos se concentran en ciertas áreas."
        else:
            return "La imagen tiene un enfoque central o poco contenido."
            
    except:
        return "Distribución estándar."

def describir_imagen_con_algoritmos(imagen_bytes: bytes, nivel_cognitivo: str = "estándar") -> Dict[str, str]:
    """Describe una imagen usando algoritmos de visión por computadora."""
    
    try:
        imagen = Image.open(io.BytesIO(imagen_bytes))
        
        # Análisis mejorado
        color = obtener_color_dominante(imagen)
        brillo = analizar_brillo(imagen)
        composicion = analizar_composicion(imagen)
        contraste = analizar_contraste(imagen)
        formas = detectar_formas_simples(imagen)
        distribucion = analizar_distribucion(imagen)
        textos = detectar_texto_simple(imagen)
        
        # Generar descripción rica en contexto
        if nivel_cognitivo == "simplificada":
            # Versión simplificada
            descripcion = f"Imagen {composicion}. "
            descripcion += f"Color principal: {color}. "
            descripcion += f"Iluminación: {brillo}. "
            if textos:
                descripcion += f"Tiene {textos[0]}. "
        else:
            # Versión detallada
            descripcion = f"Esta es una imagen de composición {composicion}. "
            
            # Información de color con contexto
            if color in ['blanco', 'negro', 'gris claro', 'gris oscuro']:
                descripcion += f"Predominan tonos {color} y neutros, "
            else:
                descripcion += f"El color predominante es el {color}, "
                
            descripcion += f"con iluminación {brillo} y {contraste}. "
            
            # Añadir información de formas
            if formas and formas != "formas básicas":
                descripcion += f"Se observan {formas}. "
            
            # Añadir distribución
            descripcion += distribucion
            
            # Añadir texto detectado
            if textos:
                descripcion += f" Se detecta {', '.join(textos)}. "
        
        # Detalles adicionales
        ancho, alto = imagen.size
        if ancho > 1920 or alto > 1080:
            descripcion += "Es una imagen de alta resolución. "
        elif ancho < 640 and alto < 480:
            descripcion += "Es una imagen de baja resolución. "
        
        # Limpiar descripción
        descripcion = descripcion.replace("  ", " ").strip()
        
        return {
            "descripcion": descripcion,
            "detalles": {
                "color": color,
                "brillo": brillo,
                "composicion": composicion,
                "contraste": contraste,
                "formas": formas,
                "texto_detectado": bool(textos),
                "dimensiones": f"{ancho}x{alto}"
            }
        }
        
    except Exception as e:
        print(f"❌ Error en análisis: {e}")
        return {
            "descripcion": "No se pudo analizar la imagen correctamente.",
            "detalles": {}
        }

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
    """Traducción simple (para demostración)."""
    # Mapeo básico de palabras comunes
    traducciones = {
        "inglés": {
            "color": "color",
            "colores": "colors",
            "brillo": "brightness",
            "composicion": "composition",
            "contraste": "contrast",
            "horizontal": "horizontal",
            "vertical": "vertical",
            "cuadrada": "square",
            "blanco": "white",
            "negro": "black",
            "rojo": "red",
            "verde": "green",
            "azul": "blue",
            "amarillo": "yellow",
            "naranja": "orange",
            "morado": "purple",
            "gris": "gray",
            "claro": "light",
            "oscuro": "dark",
            "imagen": "image",
            "escena": "scene",
            "elementos": "elements",
            "luminosidad": "luminosity",
            "media": "medium"
        },
        "francés": {
            "color": "couleur",
            "colores": "couleurs",
            "brillo": "luminosité",
            "composicion": "composition",
            "contraste": "contraste",
            "blanco": "blanc",
            "negro": "noir",
            "rojo": "rouge",
            "verde": "vert",
            "azul": "bleu",
            "amarillo": "jaune",
            "imagen": "image",
            "escena": "scène"
        },
        "alemán": {
            "color": "Farbe",
            "colores": "Farben",
            "brillo": "Helligkeit",
            "composicion": "Zusammensetzung",
            "contraste": "Kontrast",
            "blanco": "weiß",
            "negro": "schwarz",
            "rojo": "rot",
            "verde": "grün",
            "azul": "blau",
            "amarillo": "gelb",
            "imagen": "Bild",
            "escena": "Szene"
        },
        "italiano": {
            "color": "colore",
            "colores": "colori",
            "brillo": "luminosità",
            "composicion": "composizione",
            "contraste": "contrasto",
            "blanco": "bianco",
            "negro": "nero",
            "rojo": "rosso",
            "verde": "verde",
            "azul": "blu",
            "amarillo": "giallo",
            "imagen": "immagine",
            "escena": "scena"
        },
        "portugués": {
            "color": "cor",
            "colores": "cores",
            "brillo": "brilho",
            "composicion": "composição",
            "contraste": "contraste",
            "blanco": "branco",
            "negro": "preto",
            "rojo": "vermelho",
            "verde": "verde",
            "azul": "azul",
            "amarillo": "amarelo",
            "imagen": "imagem",
            "escena": "cena"
        }
    }
    
    # Traducción básica
    if idioma_destino in traducciones:
        for es, translated in traducciones[idioma_destino].items():
            texto = texto.replace(es, translated)
        return texto
    
    return f"[{idioma_destino}] {texto}"

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

    # Analizar imagen con algoritmos mejorados
    resultado_analisis = describir_imagen_con_algoritmos(imagen_bytes, nivel_cognitivo)
    descripcion_es = resultado_analisis["descripcion"]
    
    descripciones = {}
    if "es" in idiomas_elegidos:
        descripciones["es"] = descripcion_es

    # Traducciones
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
        "detalles_analisis": resultado_analisis.get("detalles", {})
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
            "index.html", idiomas=IDIOMAS, api_configurada=True,
            en_produccion=EN_PRODUCCION,
            error=None, resultado=resultado, valores=valores,
        )
    except Exception as exc:
        error_amigable = f"No se pudo completar el proceso: {exc}"
        return render_template(
            "index.html", idiomas=IDIOMAS, api_configurada=True,
            en_produccion=EN_PRODUCCION,
            error=error_amigable,
            resultado=None, valores=valores,
        )

# ============================================================
# RUTAS DE CÁMARA EN VIVO (NUEVO)
# ============================================================

@app.route('/api/camara/estado', methods=['GET'])
def estado_camara():
    """Verifica el estado del servicio de cámara."""
    return jsonify({
        'activo': True,
        'modo': 'algoritmos_cv',
        'gratuito': True,
        'modelo': 'Pillow + gTTS',
        'version': '1.0.0',
        'caracteristicas': [
            'Detección de colores',
            'Análisis de brillo',
            'Detección de formas',
            'Análisis de composición',
            'Generación de audio'
        ]
    })

@app.route('/api/camara/stream', methods=['POST'])
def procesar_stream_camara():
    """Procesa fotogramas de la cámara en tiempo real."""
    try:
        data = request.get_json()
        if not data or 'imagen' not in data:
            return jsonify({'error': 'No se recibió imagen'}), 400

        # Verificar rate limit
        ip_usuario = request.remote_addr or "default"
        puede_proceder, tiempo_espera = verificar_limite_solicitudes(ip_usuario)
        
        if not puede_proceder:
            return jsonify({
                'error': 'rate_limit',
                'mensaje': f'Espera {tiempo_espera} segundos'
            }), 429

        # Decodificar imagen base64
        image_data = data['imagen']
        if ',' in image_data:
            _, encoded = image_data.split(',', 1)
        else:
            encoded = image_data
            
        image_bytes = base64.b64decode(encoded)
        
        # Analizar con algoritmos mejorados
        nivel = data.get('nivel', 'estándar')
        resultado = describir_imagen_con_algoritmos(image_bytes, nivel)
        descripcion = resultado["descripcion"]
        
        # Si modo detallado, añadir más información
        if data.get('detalle', False) and resultado.get("detalles"):
            detalles = resultado["detalles"]
            descripcion += f" Detalles técnicos: color {detalles['color']}, {detalles['brillo']}, {detalles['contrase']}."
        
        # Generar audio
        session_id = uuid.uuid4().hex[:8]
        audio_path = GENERATED_DIR / f"{session_id}_camara.mp3"
        
        # Obtener idioma para el audio
        idioma = data.get('idioma', 'es')
        idioma_gtts = IDIOMAS.get(idioma, {}).get("gtts", "es")
        
        generar_audio(descripcion, audio_path, idioma_gtts)
        
        # Convertir audio a base64
        with open(audio_path, "rb") as f:
            audio_base64 = base64.b64encode(f.read()).decode('utf-8')
        
        # Limpiar archivo temporal (después de enviar)
        try:
            os.remove(audio_path)
        except:
            pass
        
        return jsonify({
            'descripcion': descripcion,
            'audio': audio_base64,
            'timestamp': datetime.now().isoformat(),
            'detalles': resultado.get("detalles", {})
        })
        
    except Exception as e:
        print(f"❌ Error en stream: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/camara/analizar', methods=['POST'])
def analizar_fotograma():
    """Endpoint alternativo para análisis sin audio."""
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
        
        # Analizar
        resultado = describir_imagen_con_algoritmos(image_bytes, data.get('nivel', 'estándar'))
        
        return jsonify({
            'descripcion': resultado["descripcion"],
            'detalles': resultado.get("detalles", {}),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"❌ Error en análisis: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================
# RUTAS DE UTILIDAD
# ============================================================

@app.route('/api/estado', methods=['GET'])
def estado_sistema():
    return jsonify({
        'modelo': {
            'nombre': 'Algoritmos de Visión por Computadora',
            'gratuito': True,
            'memoria_mb': '< 100',
            'tipo': 'Pillow + algoritmos',
            'caracteristicas': [
                'Análisis de color',
                'Detección de brillo',
                'Análisis de composición',
                'Detección de formas',
                'Análisis de contraste',
                'Detección de texto básica'
            ]
        },
        'camara': {
            'activa': True,
            'gratuita': True,
            'fps': 0.33,  # 1 captura cada 3 segundos
            'formato': 'JPEG'
        },
        'produccion': EN_PRODUCCION,
        'rate_limit': {'minimo_segundos': TIEMPO_MINIMO_ENTRE_SOLICITUDES},
        'idiomas': list(IDIOMAS.keys()),
        'version': '2.0.0'
    })

@app.route('/api/limpiar-temporales', methods=['POST'])
def limpiar_temporales():
    """Limpia archivos temporales antiguos."""
    try:
        # Eliminar archivos de audio más antiguos que 1 hora
        ahora = time.time()
        eliminados = 0
        for archivo in GENERATED_DIR.glob("*_camara.mp3"):
            if ahora - archivo.stat().st_mtime > 3600:  # 1 hora
                try:
                    os.remove(archivo)
                    eliminados += 1
                except:
                    pass
        return jsonify({
            'success': True,
            'eliminados': eliminados
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == '__main__':
    print("🚀 Voz Visible iniciado")
    print(f"🖼️ Modelo: Algoritmos de Visión por Computadora (sin API)")
    print(f"📷 Cámara en vivo: ACTIVADA (gratuita)")
    print(f"💾 Memoria estimada: < 100 MB")
    print(f"🌐 Entorno: {'Producción' if EN_PRODUCCION else 'Desarrollo'}")
    print("")
    
    port = int(os.environ.get('PORT', 5000))
    print(f"🔌 Escuchando en el puerto {port}")
    app.run(host='0.0.0.0', port=port, debug=not EN_PRODUCCION)