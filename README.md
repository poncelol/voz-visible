# Voz Visible

Migración a Flask del notebook original de Colab. Genera audiodescripciones
claras (o en lectura fácil) de una imagen, en varios idiomas, con un archivo
mp3 real por idioma.

Pensada para que la use una **tercera persona que acompaña**: familiar,
docente, cuidador/a o profesional de accesibilidad, que prepara el audio y
se lo comparte a la persona con discapacidad visual o cognitiva.

## Qué hace

1. Consigue una imagen (la genera con Pollinations.ai a partir de una frase,
   o la subes tú).
2. Gemini (`gemini-2.5-flash`) la describe, en nivel estándar o en lectura
   fácil.
3. Si lo pides, traduce esa descripción a los idiomas que elijas.
4. gTTS genera un mp3 real por cada idioma, reproducible desde la propia
   página y descargable.

## Instalación local

```bash
python -m venv venv
source venv/bin/activate        # en Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# abre .env y pega tu GEMINI_API_KEY (gratis en https://aistudio.google.com/apikey)
python app.py
```

Abre `http://localhost:5000`.

## Estructura

```
voz-visible/
├── app.py                  # toda la lógica (equivalente a las funciones del notebook)
├── requirements.txt
├── .env.example
├── templates/
│   └── index.html          # formulario + resultados (Jinja2)
└── static/
    ├── css/style.css
    ├── js/app.js            # solo interfaz: mostrar/ocultar bloques, accesibilidad
    └── generated/           # aquí se guardan las imágenes y audios generados
```

## Desplegar en Render (recomendado para empezar)

Este proyecto incluye `render.yaml`, así que el despliegue es casi de un clic:

1. Sube el proyecto a un repositorio de GitHub (asegúrate de que `.env` **no**
   se sube — está en `.gitignore`).
2. En [render.com](https://render.com), pulsa **New +** → **Blueprint**.
3. Conecta tu repositorio. Render detecta `render.yaml` y configura solo el
   servicio: build, arranque con `gunicorn app:app`, plan gratuito.
4. Te pedirá el valor de `GEMINI_API_KEY` (definida en `render.yaml` como
   secreta, así que no queda escrita en el repo). Pégala ahí.
5. Pulsa **Apply**. En uno o dos minutos tendrás una URL pública tipo
   `https://voz-visible.onrender.com`.

**Nota sobre el plan gratuito:** si nadie visita la página durante 15
minutos, el servicio se "duerme" y la siguiente visita tarda entre 30 y 60
segundos en responder mientras arranca de nuevo. Para el uso previsto (una
persona que prepara audiodescripciones de vez en cuando) es aceptable. Si
más adelante lo usa un centro de forma constante, el plan de pago (desde
unos 7 $/mes por servicio) elimina esa espera.

**Nota sobre los archivos generados:** las imágenes y audios en
`static/generated/` viven en el disco del servicio. En el plan gratuito ese
disco no es permanente entre reinicios (el código y la variable de entorno
sí se conservan). Para uso puntual no supone un problema; si necesitas que
los audios generados persistan siempre, Render ofrece discos persistentes
como add-on de pago.

### Sin usar el Blueprint

Si prefieres configurarlo manualmente en el panel de Render en vez de con
`render.yaml`:
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn app:app`
- **Environment → Add Environment Variable:** `GEMINI_API_KEY` = tu clave

## Otros servidores

- **Railway** ([railway.app](https://railway.app)): conecta el repo, define
  `GEMINI_API_KEY` en Variables, y usa el mismo `Procfile` (`web: gunicorn app:app`).
- **PythonAnywhere**: sube el código, crea una app Flask desde su panel,
  apunta el WSGI a `app.py` (variable `app`), y define `GEMINI_API_KEY` en
  la pestaña **Web → Environment variables**.
- **VPS propio** (DigitalOcean, Hetzner, etc.): instala Python, clona el
  repo, `pip install -r requirements.txt`, exporta `GEMINI_API_KEY`, y
  arranca con `gunicorn app:app --bind 0.0.0.0:8000` detrás de Nginx.


## Notas importantes

- La clave de Gemini se configura **una vez, en el servidor**. Las personas
  que usan el formulario no necesitan tener ni pegar ninguna clave.
- Los archivos generados se guardan en `static/generated/`. En producción
  conviene limpiar esa carpeta periódicamente (por ejemplo con una tarea
  programada) para no acumular imágenes y audios.
- gTTS necesita conexión a internet para generar el audio (usa el servicio
  de Google Translate por detrás); no requiere clave propia.
- Los códigos de idioma de audio siguen el estándar de gTTS; el chino usa
  `zh-CN` internamente aunque en la interfaz se muestre como "ZH".
