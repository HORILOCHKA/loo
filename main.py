# ============================================================================
# TELEGRAM MONITOR BOT - Моніторинг груп з пересиланням повідомлень
# ============================================================================
# Цей скрипт підключається до вашого Telegram акаунту та моніторить всі групи/канали
# на наявність ключових слів, після чого пересилає знайдені повідомлення вам

import asyncio
import logging
from telethon import TelegramClient, events
from telethon.tl.types import PeerChannel, PeerChat, PeerUser
import json
import os
from datetime import datetime, timedelta, timezone

# Налаштування системи логування (для відображення інформації про роботу скрипта)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TelegramMonitor:
    """
    🤖 Основний клас для моніторингу Telegram груп

    Цей клас відповідає за:
    - Підключення до Telegram API
    - Завантаження ключових слів з файлу
    - Моніторинг повідомлень у всіх групах/каналах
    - Пересилання знайдених повідомлень
    """

    def __init__(self, api_id, api_hash, phone_number, target_user_id, keywords_file='keywords.json'):
        """
        🔧 Ініціалізація Telegram монітора

        Args:
            api_id: API ID з my.telegram.org (число)
            api_hash: API Hash з my.telegram.org (рядок)
            phone_number: Номер телефону для авторизації (формат: +380XXXXXXXXX)
            target_user_id: ID користувача, якому надсилати повідомлення (число)
            keywords_file: Файл з ключовими словами (за замовчуванням: keywords.json)
        """
        # 💾 Збереження налаштувань
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone_number = phone_number
        self.target_user_id = target_user_id
        self.keywords_file = keywords_file

        # 📝 Завантаження ключових слів з файлу keywords.json
        self.keywords = self.load_keywords()

        # 🔗 Створення Telegram клієнта
        # 'session_name' - файл для збереження сесії (щоб не авторизуватися щоразу)
        self.client = TelegramClient('session_name', api_id, api_hash)
        
        # ⏰ Час останньої перевірки повідомлень (з timezone)
        self.last_check_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        
        # 📊 Час останнього статус повідомлення
        self.last_status_time = datetime.now(timezone.utc)
        
        # 📈 Статистика роботи бота
        self.stats = {
            'total_checks': 0,
            'total_messages_found': 0,
            'start_time': datetime.now(timezone.utc)
        }

    def load_keywords(self):
        """
        📂 Завантаження ключових слів з файлу keywords.json

        Якщо файл не існує - створює його з прикладами ключових слів
        Повертає список ключових слів у нижньому регістрі для пошуку
        """
        try:
            if os.path.exists(self.keywords_file):
                # 📖 Читання існуючого файлу з ключовими словами
                with open(self.keywords_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return [keyword.lower() for keyword in data.get('keywords', [])]
            else:
                # 📝 Створення файлу з прикладами ключових слів (якщо файл не існує)
                default_keywords = {
                    "keywords": [
                        "важливо",  # Приклади ключових слів
                        "терміново",  # Ви можете змінити їх у файлі keywords.json
                        "робота",  # після першого запуску
                        "проект",
                        "зустріч",
                        "дедлайн"
                    ]
                }
                with open(self.keywords_file, 'w', encoding='utf-8') as f:
                    json.dump(default_keywords, f, ensure_ascii=False, indent=2)
                logger.info(f"📝 Створено файл {self.keywords_file} з прикладами ключових слів")
                return [keyword.lower() for keyword in default_keywords['keywords']]
        except Exception as e:
            logger.error(f"❌ Помилка завантаження ключових слів: {e}")
            return []

    def check_keywords(self, message_text):
        """
        🔍 Перевірка наявності ключових слів у повідомленні

        Args:
            message_text: Текст повідомлення для перевірки

        Returns:
            list: Список знайдених ключових слів або порожній список
        """
        if not message_text:
            return []

        # 🔤 Переведення тексту в нижній регістр для пошуку
        message_lower = message_text.lower()
        found_keywords = []

        # 🔎 Пошук кожного ключового слова в тексті
        for keyword in self.keywords:
            if keyword in message_lower:
                found_keywords.append(keyword)

        return found_keywords

    async def start(self):
        """
        🚀 Запуск клієнта та авторизація в Telegram

        Цей метод:
        1. Авторизується у Telegram (може запитати SMS код)
        2. Отримує список всіх груп/каналів
        3. Запускає моніторинг повідомлень
        4. Працює до зупинки (Ctrl+C)
        """
        try:
            # 🔐 Авторизація в Telegram (може запитати SMS код при першому запуску)
            await self.client.start(phone=self.phone_number)
            logger.info("✅ Успішна авторизація в Telegram")

            # 👤 Отримання інформації про поточного користувача
            me = await self.client.get_me()
            logger.info(f"👤 Авторизовано як: {me.first_name} {me.last_name or ''} (@{me.username or 'без username'})")

            # 📋 Отримання списку всіх груп та каналів для моніторингу
            await self.get_all_chats()

            logger.info("🎯 Моніторинг розпочато. Перевірка кожні 5 хвилин...")
            logger.info("⏹️  Для зупинки натисніть Ctrl+C")

            # 🔄 Безкінечний цикл моніторингу з перевіркою кожні 5 хвилин
            await self.periodic_check_loop()

        except Exception as e:
            logger.error(f"❌ Помилка запуску: {e}")

    async def get_all_chats(self):
        """
        📋 Отримання списку всіх груп та каналів для моніторингу

        Показує всі групи/канали, де ви є учасником
        Скрипт буде моніторити повідомлення тільки в цих чатах
        """
        try:
            # 📞 Отримання всіх діалогів (чатів) користувача
            dialogs = await self.client.get_dialogs()
            groups = []

            # 🔍 Фільтрація тільки груп та каналів (пропускаємо приватні чати)
            for dialog in dialogs:
                if dialog.is_group or dialog.is_channel:
                    groups.append({
                        'id': dialog.id,
                        'title': dialog.title,
                        'type': 'канал' if dialog.is_channel else 'група'
                    })

            # 📊 Виведення статистики знайдених груп/каналів
            logger.info(f"📊 Знайдено {len(groups)} груп/каналів для моніторингу:")
            for group in groups:
                logger.info(f"  📌 {group['title']} ({group['type']}) [ID: {group['id']}]")

        except Exception as e:
            logger.error(f"❌ Помилка отримання списку чатів: {e}")

    async def periodic_check_loop(self):
        """
        🔄 Основний цикл періодичної перевірки повідомлень кожні 5 хвилин
        з відправкою статусу кожні 10 хвилин
        """
        while True:
            try:
                logger.info("🔍 Початок перевірки нових повідомлень...")
                messages_found = await self.check_recent_messages()
                self.stats['total_checks'] += 1
                self.stats['total_messages_found'] += messages_found
                
                logger.info("✅ Перевірка завершена. Очікування 5 хвилин...")
                
                # 📊 Перевірка чи потрібно відправити статус (кожні 10 хвилин)
                await self.check_and_send_status()
                
                # ⏰ Очікування 5 хвилин (300 секунд)
                await asyncio.sleep(300)
                
            except Exception as e:
                logger.error(f"❌ Помилка в циклі перевірки: {e}")
                # Відправка повідомлення про помилку
                await self.send_error_notification(str(e))
                # Очікування 1 хвилину перед повторною спробою при помилці
                await asyncio.sleep(60)

    async def check_recent_messages(self):
        """
        🔍 Перевірка повідомлень за останні 5 хвилин у всіх групах/каналах
        Повертає кількість знайдених повідомлень з ключовими словами
        """
        total_found = 0
        try:
            # 📞 Отримання всіх діалогів (чатів) користувача
            dialogs = await self.client.get_dialogs()
            current_time = datetime.now(timezone.utc)
            
            # 🔍 Перевірка кожної групи/каналу
            for dialog in dialogs:
                if dialog.is_group or dialog.is_channel:
                    found_in_chat = await self.check_chat_messages(dialog, current_time)
                    total_found += found_in_chat
            
            # 📅 Оновлення часу останньої перевірки
            self.last_check_time = current_time
            
            return total_found
            
        except Exception as e:
            logger.error(f"❌ Помилка перевірки повідомлень: {e}")
            return 0

    async def check_chat_messages(self, dialog, current_time):
        """
        📋 Перевірка повідомлень в конкретному чаті за останні 5 хвилин
        Повертає кількість знайдених повідомлень з ключовими словами
        """
        messages_with_keywords = 0
        try:
            # 📥 Отримання останніх повідомлень (збільшуємо ліміт для надійності)
            messages = await self.client.get_messages(
                dialog,
                limit=200  # Збільшений ліміт для кращого покриття
            )
            
            messages_checked = 0
            
            # 🔎 Перевірка кожного повідомлення
            for message in messages:
                # ⏰ Перевірка чи повідомлення новіше за час останньої перевірки
                if message.date <= self.last_check_time:
                    continue
                    
                messages_checked += 1
                
                # 🚫 Пропускаємо власні повідомлення
                if message.sender_id == (await self.client.get_me()).id:
                    continue
                
                # 📄 Перевірка тексту повідомлення
                if message.message:
                    found_keywords = self.check_keywords(message.message)
                    
                    if found_keywords:
                        messages_with_keywords += 1
                        # 📤 Пересилання повідомлення з ключовими словами
                        await self.forward_message_from_history(message, dialog, found_keywords)
            
            if messages_checked > 0:
                logger.info(f"📊 {dialog.title}: перевірено {messages_checked} повідомлень, знайдено {messages_with_keywords} з ключовими словами")
            
            return messages_with_keywords
                
        except Exception as e:
            logger.error(f"❌ Помилка перевірки чату {dialog.title}: {e}")
            return 0

    async def forward_message_from_history(self, message, dialog, keywords):
        """
        📤 Пересилання повідомлення з історії з ключовими словами
        """
        try:
            # 👤 Отримання інформації про відправника
            sender = await message.get_sender()
            
            # 📝 Формування інформації про повідомлення
            chat_name = getattr(dialog, 'title', 'Невідомий чат')
            sender_name = f"{getattr(sender, 'first_name', '')} {getattr(sender, 'last_name', '') or ''}".strip()
            sender_username = getattr(sender, 'username', '')

            # 👤 Формування інформації про відправника
            if sender_username:
                sender_info = f"{sender_name} (@{sender_username})"
            else:
                sender_info = sender_name or "Невідомий користувач"

            # 📋 Створення детального сповіщення
            notification_text = f"""
🔔 ЗНАЙДЕНО КЛЮЧОВІ СЛОВА: {', '.join(keywords)}

📍 Група/Канал: {chat_name}
👤 Відправник: {sender_info}
📅 Час: {message.date.strftime('%Y-%m-%d %H:%M:%S')}

💬 Повідомлення:
{message.message}

---
ID повідомлення: {message.id}
ID чату: {dialog.id}
            """.strip()

            # 📨 Надсилання сповіщення цільовому користувачу
            await self.client.send_message(self.target_user_id, notification_text)

            logger.info(f"✅ Переслано повідомлення з ключовими словами {keywords} з чату '{chat_name}'")

        except Exception as e:
            logger.error(f"❌ Помилка пересилання повідомлення: {e}")

    async def check_and_send_status(self):
        """
        📊 Перевірка чи потрібно відправити статус повідомлення (кожні 10 хвилин)
        """
        try:
            current_time = datetime.now(timezone.utc)
            time_since_last_status = current_time - self.last_status_time
            
            # 🕙 Якщо пройшло 10 хвилин або більше - відправляємо статус
            if time_since_last_status >= timedelta(minutes=10):
                await self.send_status_message()
                self.last_status_time = current_time
                
        except Exception as e:
            logger.error(f"❌ Помилка перевірки статусу: {e}")

    async def send_status_message(self):
        """
        📈 Відправка статус повідомлення про роботу бота
        """
        try:
            current_time = datetime.now(timezone.utc)
            uptime = current_time - self.stats['start_time']
            
            # 📊 Формування статистики
            hours = int(uptime.total_seconds() // 3600)
            minutes = int((uptime.total_seconds() % 3600) // 60)
            
            status_text = f"""
🤖 СТАТУС БОТА - БОТ ПРАЦЮЄ

⏰ Час роботи: {hours}г {minutes}хв
🔍 Всього перевірок: {self.stats['total_checks']}
📨 Знайдено повідомлень: {self.stats['total_messages_found']}
📅 Останнє оновлення: {current_time.strftime('%Y-%m-%d %H:%M:%S')}

✅ Бот активний та моніторить групи кожні 5 хвилин
🔑 Ключових слів у базі: {len(self.keywords)}

---
Наступний статус через 10 хвилин
            """.strip()

            # 📨 Відправка статус повідомлення
            await self.client.send_message(self.target_user_id, status_text)
            logger.info("📊 Відправлено статус повідомлення")
            
        except Exception as e:
            logger.error(f"❌ Помилка відправки статусу: {e}")

    async def send_error_notification(self, error_message):
        """
        ⚠️ Відправка повідомлення про помилку
        """
        try:
            error_text = f"""
⚠️ ПОМИЛКА В РОБОТІ БОТА

❌ Опис помилки: {error_message}
📅 Час помилки: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}

🔄 Бот спробує відновити роботу через 1 хвилину
            """.strip()

            await self.client.send_message(self.target_user_id, error_text)
            logger.info("⚠️ Відправлено повідомлення про помилку")
            
        except Exception as e:
            logger.error(f"❌ Помилка відправки повідомлення про помилку: {e}")


async def main():
    """Головна функція"""
    # ========================================================================
    # 🔧 НАЛАШТУВАННЯ - ОБОВ'ЯЗКОВО ЗАМІНІТЬ НА СВОЇ ДАНІ!
    # ========================================================================

    # 1️⃣ API_ID та API_HASH - отримайте на https://my.telegram.org
    # Інструкція:
    # - Перейдіть на https://my.telegram.org
    # - Увійдіть у свій Telegram акаунт
    # - Натисніть "API development tools"
    # - Створіть нову аплікацію (назва може бути будь-якою)
    # - Скопіюйте api_id (число) та api_hash (рядок)
    API_ID = 21851272  # ✅ Ваш API ID (число)
    API_HASH = '8278e92db1f324db822ed1e7a1d5a9ec'  # ✅ Ваш API Hash (рядок у лапках)

    # 2️⃣ Номер телефону - ваш номер, прив'язаний до Telegram акаунту
    # Формат: +380XXXXXXXXX (з кодом країни)
    PHONE_NUMBER = '+33652536163'  # ✅ Ваш номер телефону

    # 3️⃣ ID користувача для отримання сповіщень
    # Як отримати:
    # - Напишіть боту @userinfobot в Telegram
    # - Він надішле вам ваш User ID (число)
    # - Або використайте @getmyid_bot
    TARGET_USER_ID = 927144138  # ✅ Ваш User ID (число)

    # ✅ Перевірка правильності налаштувань перед запуском
    if not API_ID or not API_HASH:
        print("❌ ПОМИЛКА: Необхідно вказати API_ID та API_HASH")
        print("📝 Отримайте їх на https://my.telegram.org")
        return

    if not PHONE_NUMBER or PHONE_NUMBER == '+380XXXXXXXXX':
        print("❌ ПОМИЛКА: Необхідно вказати номер телефону")
        return

    if not TARGET_USER_ID:
        print("❌ ПОМИЛКА: Необхідно вказати ID цільового користувача")
        print("📝 Отримайте його через @userinfobot в Telegram")
        return

    print("✅ Налаштування перевірено успішно!")
    print(f"📱 Номер телефону: {PHONE_NUMBER}")
    print(f"🆔 User ID: {TARGET_USER_ID}")
    print(f"🔑 API ID: {API_ID}")

    # 🚀 Створення та запуск монітора з вашими налаштуваннями
    monitor = TelegramMonitor(
        api_id=API_ID,
        api_hash=API_HASH,
        phone_number=PHONE_NUMBER,
        target_user_id=TARGET_USER_ID
    )

    # 🎯 Запуск моніторингу
    await monitor.start()


# ============================================================================
# 🎯 ТОЧКА ВХОДУ - ТУТ ПОЧИНАЄТЬСЯ ВИКОНАННЯ ПРОГРАМИ
# ============================================================================
if __name__ == '__main__':
    print("🚀 Запуск Telegram Monitor...")
    print("📋 Переконайтеся, що ви вказали правильні налаштування у коді")
    print("🔑 Ключові слова завантажуються з файлу keywords.json")
    print("📱 При першому запуску може запитати SMS код")
    print("⏹️  Для зупинки натисніть Ctrl+C")
    print("-" * 50)

    try:
        # 🏃 Запуск асинхронної головної функції
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️  Моніторинг зупинено користувачем")
    except Exception as e:
        print(f"\n❌ Критична помилка: {e}")
        print("💡 Перевірте правильність налаштувань та підключення до інтернету")