import os
import json
import asyncio
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from groq import Groq
from pypdf import PdfReader

# ====================== CONFIGURACIÓN ======================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

OWNER_ID = 1065807239

ALLOWED_USERS = [
    OWNER_ID,
]

client = Groq(api_key=GROQ_API_KEY)

DATA_FILE = "user_data.json"
PDF_FOLDER = "pdfs"

ESPERANDO_NOMBRE, ESPERANDO_PREGUNTA, ESPERANDO_RESPUESTA_EXAMEN = range(3)

# Definimos el modelo actual estable de Groq
MODELO_GROQ = "llama-3.1-70b-versatile"

# ====================== UTILIDADES ======================
def cargar_datos():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def guardar_datos(datos):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

def extraer_texto_pdf(ruta):
    reader = PdfReader(ruta)
    texto = ""
    for pagina in reader.pages:
        texto += pagina.extract_text() or ""
    return texto.strip()

def obtener_pdf_activo(user_id, datos):
    user = datos.get(str(user_id), {})
    activo = user.get("activo")
    if not activo:
        return None, None
    pdfs = user.get("pdfs", {})
    if activo not in pdfs:
        return None, None
    return activo, pdfs[activo]["texto"]

def tiene_permiso(user_id: int) -> bool:
    return user_id in ALLOWED_USERS

async def check_permission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not tiene_permiso(user_id):
        await update.message.reply_text(
            "⛔ No tienes permiso para usar este bot.\n"
            "Contacta al administrador para solicitar acceso."
        )
        return False
    return True

# ====================== COMANDOS ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context):
        return

    texto = (
        "¡Hola! Soy tu bot de estudio con PDFs.\n\n"
        "Comandos disponibles:\n"
        "/subir → Subir un nuevo PDF\n"
        "/mispdfs → Ver tus PDFs\n"
        "/usar <nombre> → Elegir el PDF activo\n"
        "/preguntar → Hacer una pregunta\n"
        "/examen → Iniciar simulador de examen\n"
        "/borrar <nombre> → Eliminar un PDF\n"
        "/ayuda → Ver esta ayuda\n\n"
        "Primero sube un PDF con /subir"
    )
    await update.message.reply_text(texto)

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def subir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context):
        return ConversationHandler.END

    await update.message.reply_text(
        "Envíame el PDF que quieres subir.\n"
        "Después te pediré que le pongas un nombre corto (ej: anatomia, historia...)."
    )
    return ESPERANDO_NOMBRE

async def recibir_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.document:
        await update.message.reply_text("Por favor envía un archivo PDF.")
        return ESPERANDO_NOMBRE

    documento = update.message.document
    if documento.mime_type != "application/pdf":
        await update.message.reply_text("Solo acepto archivos PDF.")
        return ESPERANDO_NOMBRE

    os.makedirs(PDF_FOLDER, exist_ok=True)
    file = await documento.get_file()
    temp_path = os.path.join(PDF_FOLDER, f"temp_{update.effective_user.id}.pdf")
    await file.download_to_drive(temp_path)

    context.user_data["temp_pdf"] = temp_path
    await update.message.reply_text(
        "PDF recibido. Ahora escríbeme un **nombre corto** para identificarlo "
        "(ejemplo: anatomia, derecho, quimica):"
    )
    return ESPERANDO_NOMBRE

async def guardar_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nombre = update.message.text.strip().lower().replace(" ", "_")
    user_id = str(update.effective_user.id)
    temp_path = context.user_data.get("temp_pdf")

    if not temp_path or not os.path.exists(temp_path):
        await update.message.reply_text("Hubo un error. Usa /subir de nuevo.")
        return ConversationHandler.END

    try:
        texto = extraer_texto_pdf(temp_path)
        if len(texto) < 50:
            await update.message.reply_text(
                "El PDF parece estar vacío o es una imagen escaneada. Intenta con otro."
            )
            os.remove(temp_path)
            return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f"Error al leer el PDF: {e}")
        return ConversationHandler.END

    final_path = os.path.join(PDF_FOLDER, f"{user_id}_{nombre}.pdf")
    os.rename(temp_path, final_path)

    datos = cargar_datos()
    if user_id not in datos:
        datos[user_id] = {"pdfs": {}, "activo": None}

    datos[user_id]["pdfs"][nombre] = {
        "archivo": final_path,
        "texto": texto[:150000]
    }
    datos[user_id]["activo"] = nombre
    guardar_datos(datos)

    await update.message.reply_text(
        f"✅ PDF guardado como **{nombre}** y seleccionado como activo.\n\n"
        f"Ahora puedes usar:\n"
        f"/preguntar → Hacer preguntas\n"
        f"/examen → Hacer un simulacro"
    )
    return ConversationHandler.END

async def mispdfs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context):
        return

    user_id = str(update.effective_user.id)
    datos = cargar_datos()
    user = datos.get(user_id, {})
    pdfs = user.get("pdfs", {})

    if not pdfs:
        await update.message.reply_text("No tienes ningún PDF subido. Usa /subir")
        return

    activo = user.get("activo")
    lista = "Tus PDFs:\n\n"
    for nombre in pdfs:
        marca = " ← (activo)" if nombre == activo else ""
        lista += f"• {nombre}{marca}\n"

    lista += "\nUsa /usar <nombre> para cambiar el PDF activo."
    await update.message.reply_text(lista)

async def usar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context):
        return

    if not context.args:
        await update.message.reply_text("Uso: /usar <nombre>\nEjemplo: /usar anatomia")
        return

    nombre = context.args[0].lower()
    user_id = str(update.effective_user.id)
    datos = cargar_datos()
    user = datos.get(user_id, {})

    if nombre not in user.get("pdfs", {}):
        await update.message.reply_text(f"No encontré el PDF '{nombre}'. Usa /mispdfs")
        return

    datos[user_id]["activo"] = nombre
    guardar_datos(datos)
    await update.message.reply_text(f"✅ Ahora estás usando: **{nombre}**")

async def borrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context):
        return

    if not context.args:
        await update.message.reply_text("Uso: /borrar <nombre>")
        return

    nombre = context.args[0].lower()
    user_id = str(update.effective_user.id)
    datos = cargar_datos()
    user = datos.get(user_id, {})

    if nombre not in user.get("pdfs", {}):
        await update.message.reply_text(f"No encontré el PDF '{nombre}'.")
        return

    ruta = user["pdfs"][nombre]["archivo"]
    if os.path.exists(ruta):
        os.remove(ruta)

    del datos[user_id]["pdfs"][nombre]
    if user.get("activo") == nombre:
        datos[user_id]["activo"] = None
    guardar_datos(datos)

    await update.message.reply_text(f"🗑️ PDF '{nombre}' eliminado.")

# ====================== PREGUNTAR ======================
async def preguntar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context):
        return ConversationHandler.END

    user_id = update.effective_user.id
    datos = cargar_datos()
    nombre, texto = obtener_pdf_activo(user_id, datos)

    if not nombre:
        await update.message.reply_text("No tienes ningún PDF activo. Usa /subir o /usar <nombre>")
        return ConversationHandler.END

    await update.message.reply_text(
        f"Pregúntame lo que quieras sobre el documento activo: **{nombre}**\n"
        "Escribe /cancelar en cualquier momento para salir."
    )
    return ESPERANDO_PREGUNTA

async def responder_pregunta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pregunta_usuario = update.message.text.strip()
    user_id = update.effective_user.id
    datos = cargar_datos()
    nombre, texto_contexto = obtener_pdf_activo(user_id, datos)

    await update.message.reply_chat_action(action="typing")

    try:
        # Llamada corregida con el nuevo modelo activo de Groq
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": f"Eres un asistente de estudio útil. Responde la pregunta basándote estrictamente en el siguiente fragmento de texto extraído de un PDF llamado '{nombre}':\n\n{texto_contexto[:8000]}"
                },
                {
                    "role": "user",
                    "content": pregunta_usuario
                }
            ],
            model=MODELO_GROQ,
            temperature=0.3
        )
        respuesta = chat_completion.choices[0].message.content
        await update.message.reply_text(respuesta)
    except Exception as e:
        await update.message.reply_text(f"❌ Error al procesar tu pregunta en Groq: {e}")

    return ESPERANDO_PREGUNTA

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Acción cancelada.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

