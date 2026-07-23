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

## Desplegar en un servidor

Cualquier hosting que ejecute Python sirve (Render, Railway, PythonAnywhere,
un VPS propio, etc.). Pasos generales:

1. Sube el proyecto (por ejemplo, con git).
2. Define la variable de entorno `GEMINI_API_KEY` en el panel del hosting
   (no subas el archivo `.env` a un repositorio público).
3. Instala dependencias: `pip install -r requirements.txt`.
4. Arranca con un servidor de producción:
   ```bash
   gunicorn app:app --bind 0.0.0.0:8000
   ```
5. Si usas Nginx u otro proxy delante, apúntalo a ese puerto.

### Ejemplo con Render.com
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- Añade `GEMINI_API_KEY` en **Environment**.

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
