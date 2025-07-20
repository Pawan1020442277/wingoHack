import os
import asyncio
import requests
import httpx
import nest_asyncio
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes

# --- CONFIG ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("OPENAI_API_KEY")
ACCESS_KEY = "mysecretkey"

PREDICTED_USERS = set()
LAST_SEEN_PERIOD = {}

nest_asyncio.apply()

# --- Fetch 200+ Results ---
async def fetch_latest_results():
    results = []
    try:
        for page in range(1, 40):  # Up to 2000 results
            url = "https://draw.ar-lottery01.com/WinGo/WinGo_1M/GetHistoryIssuePage.json"
            params = {"page": page, "pageSize": 100}
            res = requests.get(url, params=params, timeout=10)
            data = res.json()
            list_data = data.get("data", {}).get("list", [])
            if not list_data:
                break
            results.extend(list_data)
            if len(results) >= 300:
                break
        return results[:300]
    except Exception as e:
        print("❌ API Error:", e)
        return []

# --- GPT Prediction using Groq ---
async def predict_with_gpt(history_data):
    try:
        formatted_data = "\n".join([
            f"Period: {item['issueNumber']} | Number: {item['number']} | Color: {item['color']}"
            for item in history_data
        ])

        current_period = history_data[0]["issueNumber"]
        next_period = str(int(current_period) + 1)

        prompt = f"""
You're a master-level AI trained to analyze patterns in fast-paced lottery-style number games. You are given the last {len(history_data)} results from a game. Each result has:

- Period Number
- Winning Number (1–9)
- Color (Red, Green, Violet)
- Size (Big = 6-9, Small = 1-5)

Your job is to deeply analyze all possible patterns, including:
- Repeating and alternating numbers
- Color cycles and sudden shifts
- Hot vs cold numbers (most and least frequent)
- Big/Small streaks and breaking points
- Odd/Even transitions
- Time-based patterns
- Any combo sequences (like 2-5-8 loop or 3-6-9 triangle)
- Violet trap zones (where violet repeats or switches patterns)
- Hidden signals (like 1 always followed by 9, or 5 after red

🎯 Objective:
From this deep pattern logic, accurately predict the next result for:
{formatted_data}
Output strictly in this format:
Period: {next_period}
Number: <number>
Color: <color>
Size: <Big/Small>
Only give prediction — no extra text.
"""

        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }

        json_data = {
            "model": "llama3-70b-8192",  # You can also try "mixtral-8x7b-32768"
            "messages": [
                {"role": "system", "content": "You're an intelligent pattern prediction AI."},
                {"role": "user", "content": prompt}
            ]
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=json_data)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()

    except Exception as e:
        return f"❌ GPT Error: {e}"

# --- START Command ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args or args[0] != ACCESS_KEY:
        await update.message.reply_text("❌ Invalid access key.")
        return

    chat_id = update.effective_chat.id
    if chat_id in PREDICTED_USERS:
        await update.message.reply_text("🔄 Already running prediction.")
        return

    PREDICTED_USERS.add(chat_id)
    await update.message.reply_text("✅ Prediction started! You will now receive predictions...")

    async def monitor_results():
        global LAST_SEEN_PERIOD
        while chat_id in PREDICTED_USERS:
            results = await fetch_latest_results()
            if not results:
                await asyncio.sleep(5)
                continue

            current_period = results[0]['issueNumber']

            if LAST_SEEN_PERIOD.get(chat_id) != current_period:
                LAST_SEEN_PERIOD[chat_id] = current_period
                prediction = await predict_with_gpt(results)
                message = f"""🔮 *Kalyugi Gand Faad Prediction*
🕐 Period: `{int(current_period) + 1}`
📥 Results Fetched: *{len(results)}*
📊 {prediction}
"""
                await context.bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")

            await asyncio.sleep(5)

    asyncio.create_task(monitor_results())

# --- STOP Command ---
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in PREDICTED_USERS:
        PREDICTED_USERS.remove(chat_id)
        await update.message.reply_text("🛑 Prediction stopped.")
    else:
        await update.message.reply_text("😴 No prediction is running.")

# --- MAIN ---
async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))

    await app.bot.set_my_commands([
        BotCommand("start", "Start prediction"),
        BotCommand("stop", "Stop prediction")
    ])

    print("🤖 Bot is running...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
