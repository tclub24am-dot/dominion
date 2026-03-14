import asyncio
import os
from sqlalchemy import text, select
from app.database import SessionLocal
from app.models.all_models import User, UserRole
from app.services.auth import hash_password as get_password_hash

async def create_master_user():
    async with SessionLocal() as db:
        # Проверяем, существует ли уже пользователь master
        result = await db.execute(select(User.id).where(User.username == 'master'))
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            print("Пользователь master уже существует. Пропускаем создание.")
            return
            
        # Создаем пользователя master с правильными привилегиями
        master_password = os.getenv("MASTER_BOOTSTRAP_PASSWORD")
        if not master_password:
            print("ОШИБКА БЕЗОПАСНОСТИ: MASTER_BOOTSTRAP_PASSWORD не задан в .env! Создание мастера отменено.")
            return
        user = User(
            username='master',
            hashed_password=get_password_hash(master_password),
            full_name='Master Spartak',
            role=UserRole.MASTER,
            is_active=True,
            can_see_treasury=True,
            can_see_fleet=True,
            can_see_analytics=True,
            can_see_logistics=True,
            can_see_hr=True,
            can_edit_users=True
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f"Пользователь {user.username} успешно создан!")

if __name__ == "__main__":
    asyncio.run(create_master_user())
