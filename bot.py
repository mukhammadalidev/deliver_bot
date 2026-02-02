import logging
import sqlite3
import os
import re
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputFile,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# ================= DB =================
conn = sqlite3.connect("orders.db")
cursor = conn.cursor()

# Jadvalni tekshirish va kerak bo'lsa yaratish
cursor.execute("""
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name TEXT,
    phone TEXT,
    products TEXT,
    total INTEGER,
    latitude REAL,
    longitude REAL,
    status TEXT
)
""")
conn.commit()

# ================= DATA =================
PRODUCTS = {
    "Burger": 25000,
    "Pizza": 45000,
    "Hot-dog": 20000,
    "Fri": 15000,
    "Cola": 10000
}

user_data = {}

# ================= KEYBOARDS =================
def main_menu():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("🍔 Buyurtma berish", callback_data="order"),
        InlineKeyboardButton("📦 Buyurtmalarim", callback_data="my_orders")
    )
    return kb


def products_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    for name, price in PRODUCTS.items():
        kb.insert(
            InlineKeyboardButton(
                f"{name} - {price} so'm",
                callback_data=f"add:{name}"
            )
        )
    kb.add(
        InlineKeyboardButton("🛒 Savatchani ko‘rish", callback_data="cart"),
        InlineKeyboardButton("✅ Buyurtmani yakunlash", callback_data="finish")
    )
    return kb


def location_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("📍 Lokatsiyani yuborish", request_location=True))
    return kb


def admin_kb(order_id):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🍳 Tayyorlanmoqda", callback_data=f"cook:{order_id}"),
        InlineKeyboardButton("🛵 Kuryerga berildi", callback_data=f"courier:{order_id}"),
        InlineKeyboardButton("❌ Bekor qilindi", callback_data=f"cancel:{order_id}")
    )
    return kb

# ================= START =================
@dp.message_handler(commands=["start"])
async def start(msg: types.Message):
    photo = InputFile("images.jpeg")
    await bot.send_photo(
        msg.chat.id,
        photo=photo,
        caption="👋 FastFood botga xush kelibsiz!",
        reply_markup=main_menu()
    )

# ================= ORDER =================
@dp.callback_query_handler(lambda c: c.data == "order")
async def order(call: types.CallbackQuery):
    user_data[call.from_user.id] = {
        "cart": [],
        "total": 0
    }
    await call.message.answer("🍔 Mahsulotni tanlang:", reply_markup=products_kb())
    await call.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("add:"))
async def add_product(call: types.CallbackQuery):
    product = call.data.split(":")[1]
    user_data[call.from_user.id]["cart"].append(product)
    user_data[call.from_user.id]["total"] += PRODUCTS[product]
    await call.answer(f"{product} qo‘shildi")


@dp.callback_query_handler(lambda c: c.data == "cart")
async def view_cart(call: types.CallbackQuery):
    data = user_data.get(call.from_user.id)
    if not data or not data["cart"]:
        await call.message.answer("🛒 Savatcha bo‘sh")
        return

    text = "🛒 Savatcha:\n\n"
    for p in data["cart"]:
        text += f"- {p}\n"
    text += f"\n💰 Jami: {data['total']} so‘m"

    await call.message.answer(text)
    await call.answer()


@dp.callback_query_handler(lambda c: c.data == "finish")
async def finish_order(call: types.CallbackQuery):
    await call.message.answer(
        "📍 Iltimos, lokatsiyani yuboring:",
        reply_markup=location_kb()
    )
    await call.answer()

# ================= LOCATION =================
@dp.message_handler(content_types=types.ContentType.LOCATION)
async def get_location(msg: types.Message):
    user_data[msg.from_user.id]["lat"] = msg.location.latitude
    user_data[msg.from_user.id]["lon"] = msg.location.longitude

    await msg.answer(
        "📞 Telefon raqamingizni kiriting:",
        reply_markup=types.ReplyKeyboardRemove()
    )

# ================= PHONE WITH VALIDATION =================
@dp.message_handler(lambda m: m.from_user.id in user_data and "phone" not in user_data[m.from_user.id])
async def get_phone(msg: types.Message):
    phone = msg.text.strip()
    
    # Oddiy validatsiya: faqat raqamlar, 10-13 belgi
    if not re.fullmatch(r"\d{10,13}", phone):
        await msg.answer("❌ Iltimos, to‘g‘ri telefon raqamini kiriting (faqat raqamlar, masalan: 998901234567)")
        return  # foydalanuvchi qayta yuboradi
    
    data = user_data[msg.from_user.id]
    data["phone"] = phone

    # Buyurtmani DB ga yozish
    cursor.execute(
        """INSERT INTO orders
        (user_id, name, phone, products, total, latitude, longitude, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            msg.from_user.id,
            msg.from_user.full_name,
            data["phone"],
            ", ".join(data["cart"]),
            data["total"],
            data["lat"],
            data["lon"],
            "Yangi"
        )
    )
    conn.commit()
    order_id = cursor.lastrowid

    await msg.answer("✅ Buyurtma qabul qilindi!")

    # Adminga yuborish
    await bot.send_message(
        ADMIN_ID,
        f"""📦 BUYURTMA #{order_id}
👤 {msg.from_user.full_name}
📞 {data['phone']}
🍔 {', '.join(data['cart'])}
💰 {data['total']} so‘m""",
        reply_markup=admin_kb(order_id)
    )

    await bot.send_location(
        ADMIN_ID,
        data["lat"],
        data["lon"],
        reply_markup=admin_kb(order_id)
    )

    user_data.pop(msg.from_user.id)

# ================= MY ORDERS =================
@dp.callback_query_handler(lambda c: c.data == "my_orders")
async def my_orders(call: types.CallbackQuery):
    cursor.execute(
        "SELECT id, products, total, status FROM orders WHERE user_id=?",
        (call.from_user.id,)
    )
    rows = cursor.fetchall()

    if not rows:
        await call.message.answer("📦 Buyurtmalar yo‘q")
    else:
        text = "📦 Buyurtmalar:\n\n"
        for r in rows:
            text += f"#{r[0]} | {r[1]} | {r[2]} so‘m | {r[3]}\n"
        await call.message.answer(text)

    await call.answer()

# ================= ADMIN =================
@dp.callback_query_handler(lambda c: c.data.startswith(("cook", "courier", "cancel")))
async def admin_actions(call: types.CallbackQuery):
    action, order_id = call.data.split(":")
    order_id = int(order_id)

    status_map = {
        "cook": "🍳 Tayyorlanmoqda",
        "courier": "🛵 Kuryerga berildi",
        "cancel": "❌ Bekor qilindi"
    }

    cursor.execute("UPDATE orders SET status=? WHERE id=?", (status_map[action], order_id))
    conn.commit()

    cursor.execute("SELECT user_id FROM orders WHERE id=?", (order_id,))
    user_id = cursor.fetchone()[0]

    await bot.send_message(user_id, f"📦 Buyurtma #{order_id}\n{status_map[action]}")
    await call.answer("Status yangilandi")

# ================= RUN =================
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
