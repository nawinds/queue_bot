from aiogram.types import user as user_type
from sqlalchemy import select, delete
import asyncio


from database import engine, async_session, Base
from models import Queue

db_lock = asyncio.Lock()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_queue(chat_id: int, message_id: int):
    async with db_lock:
        async with async_session() as session:
            async with session.begin():
                res = await session.execute(
                    select(Queue).where(
                        Queue.chat_id == chat_id, Queue.message_id == message_id
                    ).order_by(Queue.id.asc())
                )
                return res.scalars().all()


async def remove_queue(chat_id: int, message_id: int):
    async with db_lock:
        async with async_session() as session:
            async with session.begin():
                await session.execute(
                    delete(Queue).where(
                        Queue.chat_id == chat_id, Queue.message_id == message_id
                    )
                )

    return True


async def add_person(chat_id: int, message_id: int, user: user_type):
    async with db_lock:
        async with async_session() as session:
            async with session.begin():
                existing = await session.execute(
                    select(Queue).where(
                        Queue.chat_id == chat_id, Queue.message_id == message_id,
                        Queue.user_id == user.id
                    )
                )
                if existing.scalar() is not None:
                    return False

                queue_entry = Queue(
                    chat_id=chat_id,
                    message_id=message_id,
                    user_id=user.id,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    username=user.username,
                )
                session.add(queue_entry)

    return True


async def remove_person(chat_id: int, message_id: int, user: user_type):
    async with db_lock:
        async with async_session() as session:
            async with session.begin():
                existing = await session.execute(
                    select(Queue).where(
                        Queue.chat_id == chat_id, Queue.message_id == message_id,
                        Queue.user_id == user.id
                    )
                )
                if existing.scalar() is None:
                    return False

                await session.execute(
                    delete(Queue).where(
                        Queue.chat_id == chat_id, Queue.message_id == message_id,
                        Queue.user_id == user.id
                    )
                )
    return True
