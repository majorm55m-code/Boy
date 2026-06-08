import os
import logging
import asyncio
import json
from typing import Dict, List

from dotenv import load_dotenv
from openai import AsyncOpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
import uvicorn

# ───────────────────────────────────────────────
# إعدادات البيئة
# ───────────────────────────────────────────────
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8718072176:AAGdVgKlOBlF_VBwkrjAeYoYlkH3m1jcsMc")
API_KEY = os.getenv("API_KEY", "sk-11CpcT60eObiShJYGyhQbVVQDGqFyWmcxzq0rFauR2oc1J3k")
BASE_URL = os.getenv("BASE_URL", "https://api.bluesminds.com/v1")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "z-ai/glm-5.1")
RAILWAY_URL = os.getenv("RAILWAY_URL", "")  # Railway يولده تلقائياً

# ───────────────────────────────────────────────
# إعدادات اللوج
# ───────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ───────────────────────────────────────────────
# عميل OpenAI (BlueSminds API)
# ───────────────────────────────────────────────
client = AsyncOpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
)

# النماذج المتاحة
MODELS = {
    "glm-5.1": "z-ai/glm-5.1",
    "gemini-3.1-pro": "gemini-3.1-pro-preview",
    "gpt-4o": "gpt-4o",
}

# ───────────────────────────────────────────────
# ذاكرة المحادثات (في الذاكرة المؤقتة - للإنتاج استخدم Redis/DB)
# ───────────────────────────────────────────────
user_sessions: Dict[int, Dict] = {}

SYSTEM_PROMPT = """أنت مساعد ذكاء اصطناعي احترافي متخصص في:
1. الردود الذكية والدقيقة باللغة العربية والإنجليزية.
2. كتابة الأكواد البرمجية بجودة عالية مع شرح مفصل.
3. التوضيح التقني والمساعدة في حل المشاكل البرمجية.

عند كتابة الأكواد:
- استخدم Markdown code blocks مع تحديد لغة البرمجة.
- اشرح الكود بخطوات واضحة.
- قدّم أفضل الممارسات (Best Practices)."""

CODE_SYSTEM_PROMPT = """أنت مبرمج خبير. المستخدم يطلب كود برمجي.
- اكتب الكود كاملاً وجاهزاً للنسخ واللصق.
- استخدم Markdown code blocks مع تحديد اللغة.
- أضف تعليقات توضيحية باللغة المناسبة.
- تأكد من خلو الكود من الأخطاء."""

def get_user_context(user_id: int) -> List[Dict]:
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}],
            "model": DEFAULT_MODEL,
            "code_mode": False,
        }
    return user_sessions[user_id]["messages"]

def get_user_model(user_id: int) -> str:
    return user_sessions.get(user_id, {}).get("model", DEFAULT_MODEL)

def set_user_model(user_id: int, model: str):
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}],
            "model": model,
            "code_mode": False,
        }
    else:
        user_sessions[user_id]["model"] = model

def toggle_code_mode(user_id: int) -> bool:
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}],
            "model": DEFAULT_MODEL,
            "code_mode": True,
        }
    else:
        user_sessions[user_id]["code_mode"] = not user_sessions[user_id]["code_mode"]
        # تحديث system prompt حسب الوضع
        if user_sessions[user_id]["code_mode"]:
            user_sessions[user_id]["messages"][0] = {
                "role": "system",
                "content": CODE_SYSTEM_PROMPT,
            }
        else:
            user_sessions[user_id]["messages"][0] = {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
    return user_sessions[user_id]["code_mode"]

def clear_history(user_id: int):
    if user_id in user_sessions:
        current_model = user_sessions[user_id]["model"]
        code_mode = user_sessions[user_id]["code_mode"]
        prompt = CODE_SYSTEM_PROMPT if code_mode else SYSTEM_PROMPT
        user_sessions[user_id] = {
            "messages": [{"role": "system", "content": prompt}],
            "model": current_model,
            "code_mode": code_mode,
        }

# ───────────────────────────────────────────────
# Handlers
# ───────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🤖 تغيير النموذج", callback_data="models_menu")],
        [InlineKeyboardButton("💻 وضع الأكواد", callback_data="toggle_code")],
        [InlineKeyboardButton("🗑️ مسح الذاكرة", callback_data="clear_history")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 *أهلاً بك في بوت الذكاء الاصطناعي الاحترافي!*\n\n"
        "🧠 *النموذج الحالي:* `GLM-5.1`\n"
        "💡 أرسل أي سؤال أو اطلب كود برمجي.\n"
        "⚙️ استخدم الأزرار أدناه للتحكم.",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📋 *الأوامر المتاحة:*\n\n"
        "/start - بدء البوت وعرض الأزرار\n"
        "/model - تغيير نموذج الذكاء الاصطناعي\n"
        "/code - تفعيل/إلغاء وضع الأكواد البرمجية\n"
        "/clear - مسح سجل المحادثة\n"
        "/status - عرض النموذج الحالي والإعدادات\n\n"
        "📝 *طريقة الاستخدام:*\n"
        "فقط أرسل رسالتك وسأرد عليك بالذكاء الاصطناعي."
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("GLM-5.1 (افتراضي)", callback_data="model_glm-5.1"),
            InlineKeyboardButton("Gemini 3.1 Pro", callback_data="model_gemini-3.1-pro"),
        ],
        [InlineKeyboardButton("GPT-4o", callback_data="model_gpt-4o")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🧠 *اختر نموذج الذكاء الاصطناعي:*",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )

async def code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_code = toggle_code_mode(user_id)
    status = "✅ *تم تفعيل* وضع الأكواد البرمجية!" if is_code else "❌ *تم إلغاء* وضع الأكواد."
    await update.message.reply_text(
        f"{status}\n\n"
        f"{'سأركز الآن على كتابة الأكواد بجودة عالية.' if is_code else 'سأعود للوضع العادي للمحادثات.'}",
        parse_mode="Markdown",
    )

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    clear_history(user_id)
    await update.message.reply_text(
        "🗑️ *تم مسح ذاكرة المحادثة بنجاح!*\nبدأنا محادثة جديدة.",
        parse_mode="Markdown",
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    model = get_user_model(user_id)
    code_mode = user_sessions.get(user_id, {}).get("code_mode", False)
    await update.message.reply_text(
        f"⚙️ *الإعدادات الحالية:*\n\n"
        f"🧠 *النموذج:* `{model}`\n"
        f"💻 *وضع الأكواد:* {'مفعّل' if code_mode else 'معطّل'}\n"
        f"💬 *رسائل المحادثة:* {len(get_user_context(user_id))} رسالة",
        parse_mode="Markdown",
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text

    if not user_message:
        return

    # إظهار "يكتب..."
    await update.message.chat.send_action(action="typing")

    # حفظ رسالة المستخدم
    messages = get_user_context(user_id)
    messages.append({"role": "user", "content": user_message})

    model = get_user_model(user_id)

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=4000,
            stream=False,
        )

        ai_reply = response.choices[0].message.content

        # حفظ رد المساعد
        messages.append({"role": "assistant", "content": ai_reply})

        # تقسيم الرسالة إذا كانت طويلة (Telegram limit: 4096)
        if len(ai_reply) > 4000:
            parts = [ai_reply[i:i+4000] for i in range(0, len(ai_reply), 4000)]
            for part in parts:
                await update.message.reply_text(part, parse_mode="Markdown")
        else:
            await update.message.reply_text(ai_reply, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(
            "❌ حدث خطأ أثناء الاتصال بالذكاء الاصطناعي.\n"
            "يرجى المحاولة مرة أخرى أو التحقق من النموذج المختار.",
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data

    if data == "models_menu":
        keyboard = [
            [
                InlineKeyboardButton("GLM-5.1", callback_data="model_glm-5.1"),
                InlineKeyboardButton("Gemini 3.1 Pro", callback_data="model_gemini-3.1-pro"),
            ],
            [InlineKeyboardButton("GPT-4o", callback_data="model_gpt-4o")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
        ]
        await query.edit_message_text(
            "🧠 *اختر النموذج المفضل:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data.startswith("model_"):
        model_key = data.replace("model_", "")
        model_name = MODELS.get(model_key, DEFAULT_MODEL)
        set_user_model(user_id, model_name)
        await query.edit_message_text(
            f"✅ *تم تغيير النموذج إلى:* `{model_name}`\n\n"
            f"يمكنك الآن إرسال رسالتك.",
            parse_mode="Markdown",
        )

    elif data == "toggle_code":
        is_code = toggle_code_mode(user_id)
        status = "✅ مفعّل" if is_code else "❌ معطّل"
        await query.edit_message_text(
            f"💻 *وضع الأكواد:* {status}\n\n"
            f"{'سأركز على كتابة الأكواد الاحترافية.' if is_code else 'سأعود للوضع العادي.'}",
            parse_mode="Markdown",
        )

    elif data == "clear_history":
        clear_history(user_id)
        await query.edit_message_text(
            "🗑️ *تم مسح الذاكرة!* بدأنا محادثة جديدة.",
            parse_mode="Markdown",
        )

    elif data == "back_main":
        keyboard = [
            [InlineKeyboardButton("🤖 تغيير النموذج", callback_data="models_menu")],
            [InlineKeyboardButton("💻 وضع الأكواد", callback_data="toggle_code")],
            [InlineKeyboardButton("🗑️ مسح الذاكرة", callback_data="clear_history")],
        ]
        await query.edit_message_text(
            "👋 *القائمة الرئيسية:*\n\nاختر أحد الخيارات:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

# ───────────────────────────────────────────────
# إعداد Webhook + Starlette App (لـ Railway)
# ───────────────────────────────────────────────
async def telegram_webhook(request: Request):
    application = request.app.state.application
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return Response(status_code=200)

async def health_check(request: Request):
    return Response("OK", status_code=200)

def main():
    # بناء التطبيق
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # إضافة handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("model", model_command))
    application.add_handler(CommandHandler("code", code_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # التشغيل على Railway (Webhook) أو محلياً (Polling)
    if RAILWAY_URL:
        # وضع الإنتاج: Webhook
        port = int(os.getenv("PORT", "8080"))
        webhook_path = "/webhook"
        webhook_url = f"{RAILWAY_URL}{webhook_path}"

        # Starlette app
        starlette_app = Starlette()
        starlette_app.state.application = application

        starlette_app.add_route(webhook_path, telegram_webhook, methods=["POST"])
        starlette_app.add_route("/health", health_check, methods=["GET"])

        async def on_startup():
            await application.bot.set_webhook(url=webhook_url, allowed_updates=Update.ALL_TYPES)
            await application.initialize()
            await application.start()
            logger.info(f"Webhook set to: {webhook_url}")

        async def on_shutdown():
            await application.stop()
            await application.shutdown()

        starlette_app.add_event_handler("startup", on_startup)
        starlette_app.add_event_handler("shutdown", on_shutdown)

        logger.info(f"Starting server on port {port}")
        uvicorn.run(starlette_app, host="0.0.0.0", port=port)

    else:
        # وضع التطوير: Polling
        logger.info("Running in polling mode (development)")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
