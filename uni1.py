import sqlite3
import logging
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters
)
 
logging.basicConfig(level=logging.INFO)
 
BOT_TOKEN = "8601897406:AAHvq31880IRCgeEx2CZBp1kdwbHfEpul4I"
MINI_APP_URL = "https://mariarubtsova.github.io/StudyAbroad/"
DB_PATH = "universities.db"
 
STEP_FIELD, STEP_COUNTRY, STEP_IELTS, STEP_GPA, STEP_BUDGET = range(5)
 
FIELDS    = ["Компьютерные науки", "Медицина", "Экономика", "Инженерия", "Юриспруденция", "Бизнес"]
COUNTRIES = ["Германия", "Чехия", "Венгрия", "Австрия", "Нидерланды", "Финляндия", "Канада", "Австралия", "Любая страна"]
BUDGETS   = ["Бесплатно", "до $5000", "до $15000", "до $30000", "Любой"]
 
 
#загрузка базы вузов с SQL(теперь оно sql запросы фигачит)
 
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
 
 
#фильтр
 
def find_unis(field, country, ielts, gpa, budget_max):
    conn = get_conn()
    cur = conn.cursor()
 
    query = """
        SELECT DISTINCT u.name, c.name AS country, u.city,
               u.ielts_min, u.gpa_min, u.tuition_usd, u.scholarship, u.url
        FROM universities u
        JOIN countries c ON u.country_id = c.id
        JOIN university_fields uf ON uf.university_id = u.id
        JOIN fields f ON f.id = uf.field_id
        WHERE f.name = ?
          AND u.ielts_min <= ?
          AND u.gpa_min   <= ?
    """
    params = [field, ielts, gpa]
 
    if country != "Любая страна":
        query += " AND c.name = ?"
        params.append(country)
 
    if budget_max is not None:
        query += " AND u.tuition_usd <= ?"
        params.append(budget_max)
 
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]
 
 
#helpers 
 
def make_keyboard(options):
    buttons = [InlineKeyboardButton(o, callback_data=o) for o in options]
    rows = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(rows)
 
def budget_to_number(label):
    mapping = {
        "Бесплатно": 0,
        "до $5000": 5000,
        "до $15000": 15000,
        "до $30000": 30000,
        "Любой": None
    }
    return mapping.get(label)
 
def uni_card(uni):
    cost  = "Бесплатно" if uni["tuition_usd"] == 0 else f"${uni['tuition_usd']}/год"
    grant = "✅ Есть стипендии" if uni["scholarship"] else "❌ Стипендий нет"
    return (
        f"🏛 *{uni['name']}*\n"
        f"📍 {uni['city']}, {uni['country']}\n"
        f"🗣 IELTS ≥ {uni['ielts_min']} | GPA ≥ {uni['gpa_min']}\n"
        f"💰 {cost}\n"
        f"{grant}\n"
        f"🔗 {uni['url']}"
    )
 
 
#обработчики 
 
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    btn = KeyboardButton(
        "🎓 Открыть UniSearch",
        web_app=WebAppInfo(url=MINI_APP_URL)
    )
    markup = ReplyKeyboardMarkup([[btn]], resize_keyboard=True)
    await update.message.reply_text(
        "Привет! Нажми кнопку ниже чтобы найти университет 👇",
        reply_markup=markup
    )
 
async def start_classic(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Шаг 1 — выбери направление:", reply_markup=make_keyboard(FIELDS))
    return STEP_FIELD
 
async def step_field(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["field"] = query.data
    await query.edit_message_text(f"✅ {query.data}\n\nШаг 2 — выбери страну:", reply_markup=make_keyboard(COUNTRIES))
    return STEP_COUNTRY
 
async def step_country(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["country"] = query.data
    await query.edit_message_text(f"✅ {query.data}\n\nШаг 3 — введи IELTS (например 6.5):")
    return STEP_IELTS
 
async def step_ielts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.replace(',', '.'))
        if not 0 <= val <= 9: raise ValueError
    except ValueError:
        await update.message.reply_text("Введи число от 0 до 9")
        return STEP_IELTS
    ctx.user_data["ielts"] = val
    await update.message.reply_text("Шаг 4 — введи GPA (от 0 до 4, например 3.5):")
    return STEP_GPA
 
async def step_gpa(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.replace(',', '.'))
        if not 0 <= val <= 4: raise ValueError
    except ValueError:
        await update.message.reply_text("Введи число от 0 до 4")
        return STEP_GPA
    ctx.user_data["gpa"] = val
    await update.message.reply_text("Шаг 5 — бюджет:", reply_markup=make_keyboard(BUDGETS))
    return STEP_BUDGET
 
async def step_budget(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
 
    budget_max = budget_to_number(query.data)
    d = ctx.user_data
    results = find_unis(d.get("field"), d.get("country"), d.get("ielts", 0), d.get("gpa", 0), budget_max)
 
    await query.edit_message_text(f"🎉 Нашла {len(results)} вариантов:")
    for uni in results[:10]:
        await ctx.bot.send_message(
            chat_id=update.effective_chat.id,
            text=uni_card(uni),
            parse_mode="Markdown"
        )
    return ConversationHandler.END
 
async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменила. Напиши /start заново.")
    return ConversationHandler.END
 
 
#пуск 
 
def main():
    app = Application.builder().token(BOT_TOKEN).build()
 
    app.add_handler(CommandHandler("start", cmd_start))
 
    conv = ConversationHandler(
        entry_points=[CommandHandler("classic", start_classic)],
        states={
            STEP_FIELD:   [CallbackQueryHandler(step_field)],
            STEP_COUNTRY: [CallbackQueryHandler(step_country)],
            STEP_IELTS:   [MessageHandler(filters.TEXT & ~filters.COMMAND, step_ielts)],
            STEP_GPA:     [MessageHandler(filters.TEXT & ~filters.COMMAND, step_gpa)],
            STEP_BUDGET:  [CallbackQueryHandler(step_budget)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)]
    )
 
    app.add_handler(conv)
    app.run_polling()
 
if __name__ == "__main__":
    main()
 
