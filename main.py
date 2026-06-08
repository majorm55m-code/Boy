import os
from collections import defaultdict
from openai import AsyncOpenAI
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ========== الإعدادات ==========
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8718072176:AAF6qhvXD3UO17OzClIPRDMXYE4_oYIDr_k")
API_KEY = os.getenv("BLUESMINDS_API_KEY", "sk-11CpcT60eObiShJYGyhQbVVQDGqFyWmcxzq0rFauR2oc1J3k")
BASE_URL = "https://api.bluesminds.com/v1"
DEFAULT_MODEL = "z-ai/glm-5.1"
ALLOWED_MODELS = ["z-ai/glm-5.1", "gemini-3.1-pro-preview", "gpt-4o"]

client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)

user_contexts = defaultdict(list)
user_models = defaultdict(lambda: DEFAULT_MODEL)

SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "You are an intelligent assistant specialized in coding and general knowledge. "
        "You provide helpful, accurate responses and can write code in various programming languages. "
        "Always respond in the same language as the user. Be concise but complete."
    )
}

MAX_CONTEXT_MESSAGES = 20

def get_context(chat_id: int):
    if not user_contexts[chat_id]:
        user_contexts[chat_id] = [SYSTEM_PROMPT]
    return user_contexts[chat_id]

async def call_ai(chat_id: int, user_text: str) -> str:
    context = get_context(chat_id)
    context.append({"role": "user", "content": user_text})
    if len(context) > MAX_CONTEXT_MESSAGES + 1:
        context = [SYSTEM_PROMPT] + context[-(MAX_CONTEXT_MESSAGES):]
        user_contexts[chat_id] = context

    model = user_models[chat_id]
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=context,
            temperature=0.7,
            max_tokens=2048
        )
        reply = response.choices[0].message.content.strip()
    except Exception as e:
        reply = f"❌ حدث خطأ أثناء الاتصال بالنموذج:\n`{str(e)}`"
        return reply

    context.append({"role": "assistant", "content": reply})
    user_contexts[chat_id] = context
    return reply

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 مرحباً! أنا بوت ذكي يعمل بالذكاء الاصطناعي.\n"
        "يمكنني مساعدتك في كتابة الأكواد، الإجابة عن الأسئلة، وغير ذلك.\n\n"
        "📌 استخدم /model لاختيار النموذج:\n"
        "- `z-ai/glm-5.1` (الافتراضي)\n"
        "- `gemini-3.1-pro-preview`\n"
        "- `gpt-4o`\n\n"
        "🔄 استخدم /reset لمسح سجل المحادثة.\n"
        "ℹ️ استخدم /help لعرض الأوامر."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 **الأوامر المتاحة:**\n"
        "/start - بدء المحادثة\n"
        "/model <الاسم> - تغيير النموذج (مثال: /model gpt-4o)\n"
        "/reset - مسح السياق الحالي\n"
        "/help - هذه القائمة"
    )

async def set_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text(
            f"النموذج الحالي: `{user_models[chat_id]}`\n"
            "استخدم `/model <الاسم>` للتغيير. النماذج المتاحة:\n" +
            "\n".join([f"- `{m}`" for m in ALLOWED_MODELS])
        )
        return
    model_name = context.args[0].strip()
    if model_name in ALLOWED_MODELS:
        user_models[chat_id] = model_name
        await update.message.reply_text(f"✅ تم تغيير النموذج إلى `{model_name}`")
    else:
        await update.message.reply_text(
            f"❌ نموذج غير صالح. النماذج المتاحة:\n" +
            "\n".join([f"- `{m}`" for m in ALLOWED_MODELS])
        )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_contexts.pop(chat_id, None)
    await update.message.reply_text("🧹 تم مسح سجل المحادثة.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    reply = await call_ai(chat_id, user_text)
    if len(reply) > 4096:
        for i in range(0, len(reply), 4096):
            await update.message.reply_text(reply[i:i+4096])
    else:
        await update.message.reply_text(reply)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print(f"Update {update} caused error {context.error}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("model", set_model))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    print("🤖 البوت يعمل...")
    app.run_polling()

if __name__ == "__main__":
    main()