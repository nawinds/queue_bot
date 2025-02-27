import os

import asyncio
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, BotCommand, CallbackQuery
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest
from db_operations import init_db, get_queue, remove_queue, add_person, remove_person

API_TOKEN = os.getenv("TOKEN")

ADMINS = list(map(int, os.getenv("ADMINS", "").split(",")))
INCLUDE_CHAT_ADMINS = bool(os.getenv("INCLUDE_CHAT_ADMINS", 1))

bot = Bot(token=API_TOKEN)
dp = Dispatcher()


async def is_admin(user_id: int, chat_id: int) -> bool:
    if user_id not in ADMINS:
        chat_admins = await bot.get_chat_administrators(chat_id)
        if user_id not in map(lambda x: x.user.id, chat_admins) or not INCLUDE_CHAT_ADMINS:
            return False
    return True


async def get_queue_as_text(chat_id: int, message_id: int):
    queue = "Новая очередь:\n\n"

    res = await get_queue(chat_id, message_id)
    for i in range(len(res)):
        username_part = f"(@{res[i].username})" if res[i].username else ""
        queue += f"{i + 1}. {res[i].first_name or ''} {res[i].last_name or ''} {username_part}\n"

    return queue


queues = {}

class Queue:
    def __init__(self) -> None:
        self.to_update = False
        self.message = None
        self.delete = False

    async def queue_run_update_loop(self):
        while True:
            await asyncio.sleep(3.5)
            if self.to_update:
                self.to_update = False
                if self.message:
                    await self.update_message(self.message)
                else:
                    print("Queue has no message object")
            if self.delete:
                break
    
    def update(self, message=None) -> None:
        self.to_update = True
        if message:
            self.message = message

    async def update_message(self, message: Message):
        updated_text = await get_queue_as_text(message.chat.id, message.message_id)

        try:
            await bot.edit_message_text(
                text=updated_text,
                chat_id=message.chat.id,
                message_id=message.message_id,
                reply_markup=message.reply_markup
            )
        except TelegramRetryAfter as e:
            print(f"FLOOD!!! Waiting {e.retry_after + 0.1}s...")
            await asyncio.sleep(e.retry_after + 0.1)
            await bot.edit_message_text(
                text=updated_text,
                chat_id=message.chat.id,
                message_id=message.message_id,
                reply_markup=message.reply_markup
            )

        except TelegramBadRequest:
            print("Message not modified")

    def delete(self):
        self.delete = True


async def update_message(message: Message):
    if (message.chat.id, message.message_id) not in queues:
        queues[(message.chat.id, message.message_id)] = Queue()
        queues[(message.chat.id, message.message_id)].update(message)
        asyncio.create_task(queues[(message.chat.id, message.message_id)].queue_run_update_loop())
    else:
        queues[(message.chat.id, message.message_id)].update(message)


@dp.message(Command("start", "help"))
async def create_message_handler(message: Message):
    await message.answer("Привет! Это бот, позволяющий создавать очереди в группах. "
                         "Чтобы создать очередь, напишите /create.\n\n"
                         "Создатель бота: @nawinds")


@dp.message(Command(BotCommand(command="create", description="Create new queue")),)
async def create_message_handler(message: Message):

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Добавить себя", callback_data="add_me")],
        [InlineKeyboardButton(text="Удалить себя", callback_data="delete_me")],
        [InlineKeyboardButton(text="Удалить очередь", callback_data="delete_queue")],
    ])

    new_queue_message = await message.answer("Новая очередь:", reply_markup=keyboard)
    await new_queue_message.pin()


@dp.message(Command("update"))
async def create_message_handler(message: Message):
    if not message.reply_to_message:
        await message.reply("Не указано сообщение с очередью. Ответьте на него")
        return

    await update_message(message.reply_to_message)
    await message.delete()


@dp.callback_query(lambda c: c.data == "add_me")
async def add_me_callback_handler(callback_query: CallbackQuery):

    if await add_person(callback_query.message.chat.id, callback_query.message.message_id,
                        callback_query.from_user):
        await update_message(callback_query.message)

        await callback_query.answer("Ок, Вы добавлены в очередь")
    else:
        await callback_query.answer("Ошибка, Вы уже добавлены в очередь. "
                                    "Если нет, подождите, пока сообщение обновится", show_alert=True)



@dp.callback_query(lambda c: c.data == "delete_me")
async def delete_me_callback_handler(callback_query: CallbackQuery):

    if await remove_person(callback_query.message.chat.id, callback_query.message.message_id,
                        callback_query.from_user):
        await update_message(callback_query.message)

        await callback_query.answer("Ок, Вы удалены из очереди")
    else:
        await callback_query.answer("Ошибка, Вас уже не было в очереди. "
                                    "Если нет, подождите, пока сообщение обновится", show_alert=True)


@dp.callback_query(lambda c: c.data == "delete_queue")
async def delete_queue_callback_handler(callback_query: CallbackQuery):
    if not await is_admin(callback_query.from_user.id, callback_query.message.chat.id):
        await callback_query.answer("Удалять очередь может только админ", show_alert=True)
        return

    if await remove_queue(callback_query.message.chat.id, callback_query.message.message_id):
        await callback_query.message.delete()
        if (callback_query.message.chat.id, callback_query.message.message_id) in queues:
            queues[(callback_query.message.chat.id, callback_query.message.message_id)].delete()
        await callback_query.answer("Очередь удалена")
    else:
        await callback_query.answer("Не удалось удалить очередь")


async def main():
    await init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
