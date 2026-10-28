import os
import json
import fitz  # pymupdf
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from groq import Groq

# ====================== CONFIGURACIÓN ======================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# Tu ID de Telegram
OWNER_ID = 1065807239

# Lista de usuarios permitidos
ALLOWED_USERS = [
    OWNER_ID,
    # Aquí puedes agregar más IDs si quieres, por ejemplo:
    # 987654321,
]

client = Groq(api_key=GROQ_API_KEY)

DATA_FILE = "user_data.json"
PDF_FOLDER = "pdfs"

# Estados
ESPERANDO_NOMBRE, ESPERANDO_PREGUNTA, ESPERANDO_RESPUESTA_EXAMEN = range(3)

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
    doc = fitz.open(ruta)
    texto = ""
    for pagina in doc:
        texto += pagina.get_text()
    doc.close()
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

# ====================== DECORADOR DE PERMISOS ======================
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
        "/usar <nombre> → Elegir el PDF 
