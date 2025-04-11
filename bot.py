import os
import sqlite3
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv
from openpyxl import Workbook

load_dotenv("token.env")

bot_token = os.getenv("BOT_TOKEN")
bot = Bot(token=bot_token)
dp = Dispatcher()

# Категории для разных бланков
BLANKS = {
    "bar": [
        "БАР - ПРОЧЕЕ товар",
        "БЕЗАЛКОГОЛЬНЫЕ НАПИТКИ**",
        "ЧАЙ/КОФЕ товар",
        "КОНДИТЕРКА/ВЫПЕЧКА",
        "КОНСЕРВАЦИЯ",
        "СОУСЫ",
        "СПЕЦИИ",
        "СЫПУЧИЕ",
        "ЧАЙ, КОФЕ",
        "ЗЕЛЕНЬ",
        "МОЛОЧНЫЕ ПРОДУКТЫ",
        "ОВОЩИ СВЕЖИЕ",
        "ФРУКТЫ",
        "ЯГОДЫ С/М",
        "НАПИТКИ БЛ ПФ"
    ],
    "alcohol": [
        "ВИНО БЕЛОЕ",
        "ВИНО КРАСНОЕ",
        "ВИНО ОРАНЖЕВОЕ",
        "ВЕРМУТ",
        "ШАМПАНСКОЕ/ИГРИСТОЕ",
        "ВИСКИ",
        "ВОДКА",
        "ГОРЬКИЕ НАСТОЙКИ",
        "ДЖИН",
        "КАЛЬВАДОС",
        "КОНЬЯК/АРМАНЬЯК",
        "ЛИКЕРЫ",
        "ПИВО РАЗЛИВНОЕ",
        "ПОРТВЕЙН",
        "ПОРТО/ХЕРЕС",
        "РОМ",
        "ТЕКИЛА",
        "ПИВО БУТЫЛКА",
        "БЕЗАЛКОГОЛЬНОЕ ПИВО"
    ]
}

# База данных
conn = sqlite3.connect("inventory.db", check_same_thread=False)
cursor = conn.cursor()

# Удаляем старую таблицу (если существует)
cursor.execute("DROP TABLE IF EXISTS inventory")

# Создаем новую таблицу с нужной структурой
cursor.execute('''
CREATE TABLE IF NOT EXISTS inventory (
    user_id INTEGER,
    username TEXT,
    category TEXT,
    name TEXT,
    quantity REAL,
    UNIQUE(user_id, category, name)
    )
''')
conn.commit()

class InventoryState(StatesGroup):
    waiting_for_blank = State()
    waiting_for_category = State()
    waiting_for_item_data = State()

@dp.message(F.text == "/start")
async def start(message: types.Message, state: FSMContext):
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(text="🍸 Бар", callback_data="blank_bar")
    builder.button(text="🥃 Алкоголь", callback_data="blank_alcohol")
    builder.button(text="📊 Excel", callback_data="generate_excel")
    builder.button(text="🧹 Очистить", callback_data="clear_data")
    builder.button(text="📖 Инструкция", callback_data="instruction")
    builder.adjust(2, 2)
    await message.answer("Выберите тип инвентаризации:", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "instruction")
async def show_instruction(callback: types.CallbackQuery):
    instruction_text = (
        "📚 *Инструкция по работе с ботом*\n\n"
        "1. Выберите тип инвентаризации (Бар или Алкоголь)\n"
        "2. Выберите нужную категорию из списка\n"
        "3. Вводите данные в формате:\n"
        "   `<Название товара> <Количество>`\n"
        "   Например: _Виски Джек Дэниелс 3.5_\n"
        "4. В одном сообщении МОЖНО вводить несколько товаров\n"
        "5. Используйте кнопку 📊 для генерации Excel-отчета\n"
        "6. Кнопка 🧹 очистит все ваши данные\n\n"
        "⚠️ *Важно:*\n"
        "- Дробные числа сохраняются как есть (например: 1.5 или 3,75)\n"
        "- Ваше имя будет отображаться в отчетах\n"
        "- Данные сохраняются автоматически после ввода!"
    )

    await callback.message.answer(
        instruction_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardBuilder()
        .button(text="◀️ Назад", callback_data="back_to_main")
        .as_markup()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("blank_"))
async def select_blank(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    blank_type = callback.data.split("_")[1]
    await state.update_data(current_blank=blank_type)
    await show_categories(callback, blank_type)

async def show_categories(callback: types.CallbackQuery, blank_type: str):
    categories = BLANKS[blank_type]
    builder = InlineKeyboardBuilder()

    for category in categories:
        builder.button(text=category, callback_data=f"category_{category}")

    builder.button(text="🔙 Назад", callback_data="back_to_main")
    builder.adjust(1)

    new_text = f"Выберите категорию ({'Бар' if blank_type == 'bar' else 'Алкоголь'}):"
    new_markup = builder.as_markup()

    try:
        if (callback.message.text != new_text or
                callback.message.reply_markup.to_json() != new_markup.to_json()):
            await callback.message.edit_text(
                new_text,
                reply_markup=new_markup
            )
        else:
            await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка обновления меню: {e}")
        await callback.message.answer(
            new_text,
            reply_markup=new_markup
        )

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await start(callback.message, state)

@dp.callback_query(F.data == "clear_data")
async def clear_data(callback: types.CallbackQuery):
    cursor.execute("DELETE FROM inventory WHERE user_id = ?", (callback.from_user.id,))
    conn.commit()
    await callback.answer("Данные очищены!✅", show_alert=True)

@dp.callback_query(F.data.startswith("category_"))
async def select_category(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    category = callback.data.split("_", 1)[1]
    await state.update_data(
        category=category,
        callback_message_id=callback.message.message_id
    )
    await state.set_state(InventoryState.waiting_for_item_data)
    await callback.message.answer(
        f"Категория: {category}\n"
        "Введите данные в формате:\n"
        "<Название> <Количество>\n"
        "Пример: Ром 5\n"
        "Можно использовать дробные числа через . или , (например: 2.5 или 3,0)"
    )

@dp.message(InventoryState.waiting_for_item_data)
async def process_item_data(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        category = data["category"]
        username = message.from_user.username or message.from_user.full_name
        valid_count = 0

        items = message.text.strip().split('\n')

        for item in items:
            parts = item.rsplit(" ", 1)
            if len(parts) != 2:
                await message.answer(f"❌ Неверный формат: '{item}'")
                continue

            name, quantity_str = parts[0].strip(), parts[1].replace(',', '.')

            try:
                quantity = float(quantity_str)
            except ValueError:
                await message.answer(f"❌ Неверное количество: '{item}'")
                continue

            try:
                cursor.execute('''
                    INSERT INTO inventory (user_id, username, category, name, quantity)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, category, name) 
                    DO UPDATE SET quantity = quantity + excluded.quantity
                ''', (message.from_user.id, username, category, name, quantity))
                valid_count += 1
            except sqlite3.Error as e:
                logging.error(f"Ошибка БД: {e}")
                await message.answer(f"❌ Ошибка сохранения: {item}")

        conn.commit()

        if valid_count > 0:
            await message.answer(f"✅ Сохранено: {valid_count} позиций")
        else:
            await message.answer("❌ Нет валидных данных")

    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")

@dp.callback_query(F.data == "generate_excel")
async def generate_excel(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    cursor.execute(
        "SELECT username, category, name, quantity FROM inventory WHERE user_id = ?",
        (user_id,)
    )
    items = cursor.fetchall()

    if not items:
        return await callback.answer("Нет данных!", show_alert=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Инвентаризация"
    ws.append(["Пользователь", "Категория", "Наименование", "Количество"])

    current_username = None
    current_category = None
    start_user_row = 2
    start_category_row = 2

    for row, (username, category, name, qty) in enumerate(items, start=2):
        # Объединение ячеек для пользователя
        if username != current_username:
            if current_username is not None:
                ws.merge_cells(f"A{start_user_row}:A{row-1}")
            current_username = username
            start_user_row = row

        # Объединение ячеек для категории
        if category != current_category:
            if current_category is not None:
                ws.merge_cells(f"B{start_category_row}:B{row-1}")
            current_category = category
            start_category_row = row

        ws.append([username if row == start_user_row else "",
                   category if row == start_category_row else "",
                   name, qty])

    # Объединение последних групп
    if current_username:
        ws.merge_cells(f"A{start_user_row}:A{len(items)+1}")
    if current_category:
        ws.merge_cells(f"B{start_category_row}:B{len(items)+1}")

    # Настройка ширины столбцов
    ws.column_dimensions['A'].width = 20  # Пользователь
    ws.column_dimensions['B'].width = 25  # Категория
    ws.column_dimensions['C'].width = 35  # Наименование
    ws.column_dimensions['D'].width = 15  # Количество

    filename = f"inventory_{user_id}.xlsx"
    wb.save(filename)

    with open(filename, "rb") as file:
        await bot.send_document(
            callback.from_user.id,
            document=types.BufferedInputFile(file.read(), filename=filename),
            caption="✅ Ваш отчет готов!"
        )
    await callback.answer()

async def main():
    await bot.delete_webhook()
    await dp.start_polling(bot)

if __name__ == "__main__":
    print("Бот запущен!")
    asyncio.run(main())