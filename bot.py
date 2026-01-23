import logging
import sqlite3
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# ================= DB =================
conn = sqlite3.connect("orders.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name TEXT,
    address TEXT,
    phone TEXT,
    product TEXT,
    status TEXT
)
""")
conn.commit()

# ================= KEYBOARDS =================
def main_menu():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("🍔 Buyurtma berish", callback_data="menu_order"),
        InlineKeyboardButton("📦 Buyurtmalarim", callback_data="menu_my_orders")
    )
    return kb

def admin_kb(order_id):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Qabul qilindi", callback_data=f"accept:{order_id}"),
        InlineKeyboardButton("🍳 Tayyorlanmoqda", callback_data=f"cook:{order_id}"),
        InlineKeyboardButton("🛵 Kuryerga berildi", callback_data=f"courier:{order_id}"),
        InlineKeyboardButton("❌ Bekor qilindi", callback_data=f"cancel:{order_id}")
    )
    return kb

def admin_kb_by_status(order_id, status):
    kb = InlineKeyboardMarkup(row_width=2)
    if status == "Yangi" or status == "✅ Buyurtma qabul qilindi":
        kb.add(
            InlineKeyboardButton("🍳 Tayyorlanmoqda", callback_data=f"cook:{order_id}"),
            InlineKeyboardButton("❌ Bekor qilindi", callback_data=f"cancel:{order_id}")
        )
    elif status == "🍳 Buyurtma tayyorlanmoqda":
        kb.add(
            InlineKeyboardButton("🛵 Kuryerga berildi", callback_data=f"courier:{order_id}"),
            InlineKeyboardButton("❌ Bekor qilindi", callback_data=f"cancel:{order_id}")
        )
    return kb

# ================= USER FLOW =================
user_data = {}

@dp.message_handler(commands=["start"])
async def start(msg: types.Message):
    # Rasmi yuboramiz
    photo = InputFile("images.jpeg")  # Loyiha papkasida bo'lishi kerak
    await bot.send_photo(
        msg.chat.id,
        photo=photo,
        caption="👋 Salom! FastFood yetkazib berish botiga xush kelibsiz!\n\nQuyidagi menyudan tanlang:",
        reply_markup=main_menu()
    )

@dp.callback_query_handler(lambda c: c.data == "menu_order")
async def menu_order(call: types.CallbackQuery):
    await call.message.answer("🍔 Buyurtma berish uchun mahsulot nomini yozing:")
    user_data[call.from_user.id] = {}
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "menu_my_orders")
async def menu_my_orders(call: types.CallbackQuery):
    cursor.execute("SELECT id, product, status FROM orders WHERE user_id=?", (call.from_user.id,))
    orders = cursor.fetchall()
    if not orders:
        await call.message.answer("📦 Sizda hozircha buyurtmalar yo‘q.")
    else:
        text = "📦 Sizning buyurtmalaringiz:\n\n"
        for o in orders:
            text += f"#{o[0]} 🍔 {o[1]} - {o[2]}\n"
        await call.message.answer(text)
    await call.answer()

@dp.message_handler(lambda msg: msg.from_user.id in user_data and "product" not in user_data[msg.from_user.id])
async def get_product(msg: types.Message):
    user_data[msg.from_user.id]["product"] = msg.text
    await msg.answer("📍 Manzilni kiriting:")

@dp.message_handler(lambda msg: msg.from_user.id in user_data and "address" not in user_data[msg.from_user.id])
async def get_address(msg: types.Message):
    user_data[msg.from_user.id]["address"] = msg.text
    await msg.answer("📞 Telefon raqamingizni kiriting:")

@dp.message_handler(lambda msg: msg.from_user.id in user_data and "phone" not in user_data[msg.from_user.id])
async def get_phone(msg: types.Message):
    data = user_data[msg.from_user.id]
    data["phone"] = msg.text

    cursor.execute(
        "INSERT INTO orders (user_id, name, address, phone, product, status) VALUES (?, ?, ?, ?, ?, ?)",
        (
            msg.from_user.id,
            msg.from_user.full_name,
            data["address"],
            data["phone"],
            data["product"],
            "Yangi"
        )
    )
    conn.commit()
    order_id = cursor.lastrowid

    await msg.answer("✅ Buyurtmangiz qabul qilindi. Admin ko‘rib chiqyapti.")
    user_data.pop(msg.from_user.id)

    # Adminga xabar
    await bot.send_message(
        ADMIN_ID,
        f"""📦 YANGI BUYURTMA #{order_id}

👤 {msg.from_user.full_name}
🍔 {data['product']}
📍 {data['address']}
📞 {data['phone']}
""",
        reply_markup=admin_kb(order_id)
    )

# ================= ADMIN ACTIONS =================
@dp.callback_query_handler(lambda c: ":" in c.data)
async def admin_actions(call: types.CallbackQuery):
    action, order_id = call.data.split(":")
    order_id = int(order_id)

    cursor.execute("SELECT user_id, status FROM orders WHERE id=?", (order_id,))
    user_row = cursor.fetchone()
    user_id = user_row[0]
    current_status = user_row[1]

    status_map = {
        "accept": "✅ Buyurtma qabul qilindi",
        "cook": "🍳 Buyurtma tayyorlanmoqda",
        "courier": "🛵 Buyurtma kuryerga berildi",
        "cancel": "❌ Buyurtma bekor qilindi"
    }

    status_text = status_map[action]

    cursor.execute(
        "UPDATE orders SET status=? WHERE id=?",
        (status_text, order_id)
    )
    conn.commit()

    await bot.send_message(user_id, f"📦 #{order_id}\n{status_text}")
    await call.answer("Status yangilandi")

    # Tugmalarni yangilash faqat kerakli holatlarda
    kb = admin_kb_by_status(order_id, status_text)
    await call.message.edit_reply_markup(reply_markup=kb if kb.inline_keyboard else None)

# ================= RUN =================
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
