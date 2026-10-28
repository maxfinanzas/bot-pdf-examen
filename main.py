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

    context.user_data["pdf_texto"] = texto
    context.user_data["pdf_nombre"] = nombre

    await update.message.reply_text(
        f"Estás preguntando sobre: **{nombre}**\n\n"
        "Escribe tu pregunta (o /cancelar para salir):"
    )
    return ESPERANDO_PREGUNTA

async def responder_pregunta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pregunta = update.message.text
    texto_pdf = context.user_data.get("pdf_texto", "")
    nombre = context.user_data.get("pdf_nombre", "")

    prompt = f"""Eres un tutor experto. Responde la pregunta basándote ÚNICAMENTE en el siguiente contenido del documento "{nombre}".

Contenido del documento:
{texto_pdf[:120000]}

Pregunta del estudiante: {pregunta}

Instrucciones:
- Responde de forma clara y organizada.
- Si la información no está en el documento, dilo honestamente.
- Usa un tono didáctico."""

    try:
        respuesta = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1024
        )
        await update.message.reply_text(respuesta.choices[0].message.content)
    except Exception as e:
        await update.message.reply_text(f"Error al consultar la IA: {e}")

    await update.message.reply_text("Puedes hacer otra pregunta o usar /cancelar para salir.")
    return ESPERANDO_PREGUNTA

# ====================== EXAMEN ======================
async def examen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context):
        return ConversationHandler.END

    user_id = update.effective_user.id
    datos = cargar_datos()
    nombre, texto = obtener_pdf_activo(user_id, datos)

    if not nombre:
        await update.message.reply_text("No tienes ningún PDF activo. Usa /subir o /usar <nombre>")
        return ConversationHandler.END

    await update.message.reply_text(f"Generando examen de **{nombre}**... espera unos segundos.")

    prompt = f"""A partir del siguiente contenido, genera exactamente 5 preguntas de examen de opción múltiple (A, B, C, D).

Contenido:
{texto[:100000]}

Formato de respuesta (respeta exactamente este formato):

PREGUNTA 1:
[texto de la pregunta]
A) opción
B) opción
C) opción
D) opción
RESPUESTA_CORRECTA: X

PREGUNTA 2:
...
(y así hasta 5)
"""

    try:
        respuesta = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=2000
        )
        contenido = respuesta.choices[0].message.content
    except Exception as e:
        await update.message.reply_text(f"Error generando el examen: {e}")
        return ConversationHandler.END

    preguntas = []
    bloques = contenido.split("PREGUNTA ")[1:]
    for bloque in bloques:
        lineas = bloque.strip().split("\n")
        pregunta_texto = ""
        opciones = {}
        correcta = None
        for linea in lineas:
            linea = linea.strip()
            if linea.startswith("A)"):
                opciones["A"] = linea[2:].strip()
            elif linea.startswith("B)"):
                opciones["B"] = linea[2:].strip()
            elif linea.startswith("C)"):
                opciones["C"] = linea[2:].strip()
            elif linea.startswith("D)"):
                opciones["D"] = linea[2:].strip()
            elif linea.startswith("RESPUESTA_CORRECTA:"):
                correcta = linea.split(":")[-1].strip().upper()
            elif not linea.startswith(("A)", "B)", "C)", "D)")) and "RESPUESTA" not in linea:
                if not pregunta_texto:
                    pregunta_texto = linea

        if pregunta_texto and opciones and correcta:
            preguntas.append({
                "pregunta": pregunta_texto,
                "opciones": opciones,
                "correcta": correcta
            })

    if not preguntas:
        await update.message.reply_text("No pude generar el examen correctamente. Intenta de nuevo.")
        return ConversationHandler.END

    context.user_data["examen"] = preguntas
    context.user_data["indice"] = 0
    context.user_data["aciertos"] = 0

    await enviar_pregunta_examen(update, context)
    return ESPERANDO_RESPUESTA_EXAMEN

async def enviar_pregunta_examen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    examen = context.user_data["examen"]
    indice = context.user_data["indice"]
    pregunta = examen[indice]

    texto = f"**Pregunta {indice + 1} de {len(examen)}**\n\n"
    texto += f"{pregunta['pregunta']}\n\n"
    for letra, opcion in pregunta["opciones"].items():
        texto += f"{letra}) {opcion}\n"

    teclado = ReplyKeyboardMarkup([["A", "B", "C", "D"]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(texto, reply_markup=teclado)

async def recibir_respuesta_examen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    respuesta = update.message.text.strip().upper()
    if respuesta not in ["A", "B", "C", "D"]:
        await update.message.reply_text("Por favor responde con A, B, C o D")
        return ESPERANDO_RESPUESTA_EXAMEN

    examen = context.user_data["examen"]
    indice = context.user_data["indice"]
    pregunta = examen[indice]

    if respuesta == pregunta["correcta"]:
        context.user_data["aciertos"] += 1
        await update.message.reply_text("✅ ¡Correcto!")
    else:
        await update.message.reply_text(f"❌ Incorrecto. La respuesta correcta era **{pregunta['correcta']}**")

    context.user_data["indice"] += 1

    if context.user_data["indice"] >= len(examen):
        aciertos = context.user_data["aciertos"]
        total = len(examen)
        nota = round((aciertos / total) * 10, 1)

        await update.message.reply_text(
            f"🏁 **Examen terminado**\n\n"
            f"Aciertos: {aciertos}/{total}\n"
            f"Nota: {nota}/10\n\n"
            f"{'¡Muy bien!' if nota >= 7 else 'Sigue repasando.'}",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    else:
        await enviar_pregunta_examen(update, context)
        return ESPERANDO_RESPUESTA_EXAMEN

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operación cancelada.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ====================== MAIN (WEBHOOK) ======================
def main():
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        print("ERROR: Falta la variable TELEGRAM_TOKEN")
        return

    app = Application.builder().token(token).build()

    conv_subir = ConversationHandler(
        entry_points=[CommandHandler("subir", subir)],
        states={
            ESPERANDO_NOMBRE: [
                MessageHandler(filters.Document.PDF, recibir_pdf),
                MessageHandler(filters.TEXT & ~filters.COMMAND, guardar_nombre)
            ],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)]
    )

    conv_preguntar = ConversationHandler(
        entry_points=[CommandHandler("preguntar", preguntar)],
        states={
            ESPERANDO_PREGUNTA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, responder_pregunta)
            ],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)]
    )

    conv_examen = ConversationHandler(
        entry_points=[CommandHandler("examen", examen)],
        states={
            ESPERANDO_RESPUESTA_EXAMEN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_respuesta_examen)
            ],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ayuda", ayuda))
    app.add_handler(CommandHandler("mispdfs", mispdfs))
    app.add_handler(CommandHandler("usar", usar))
    app.add_handler(CommandHandler("borrar", borrar))
    app.add_handler(conv_subir)
    app.add_handler(conv_preguntar)
    app.add_handler(conv_examen)

    # Configuración del webhook para Render
    port = int(os.environ.get("PORT", 10000))
    hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME")

    if not hostname:
        print("ERROR: No se encontró RENDER_EXTERNAL_HOSTNAME")
        return

    webhook_url = f"https://{hostname}/{token}"
    print(f"Iniciando webhook en: {webhook_url}")

    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=token,
        webhook_url=webhook_url
    )

if __name__ == "__main__":
    main()
