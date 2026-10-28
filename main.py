import os
import json
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
PORT = int(os.environ.get("PORT", 10000))

OWNER_ID = 1065807239

ALLOWED_USERS = [
    OWNER_ID,
]

client = Groq(api_key=GROQ_API_KEY)

DATA_FILE = "user_data.json"
PDF_FOLDER = "pdfs"

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
    reader = PdfReader(ruta)
    texto = ""
    for pagina in reader.pages:
        texto 
