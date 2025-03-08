import discord
from discord.ext import commands
import markovify
import random
import re
import requests
import os
import datetime
from tenacity import retry, stop_after_attempt, wait_fixed
import logging
from json_manager import JsonManager

# Настройка логирования
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("bot_logs.log"), 
                              logging.StreamHandler()])
logger = logging.getLogger('discord_bot')

class DiscordBot:
    """Класс для управления Discord ботом с интеграцией JsonManager"""
    
    def __init__(self):
        # Инициализация JsonManager
        self.json_manager = JsonManager()
        
        # Получение токенов из JsonManager
        self.DISCORD_TOKEN = self.json_manager.tokens.get("DISCORD_TOKEN", "")
        self.TELEGRAM_TOKEN = self.json_manager.tokens.get("TELEGRAM_TOKEN", "")
        self.TELEGRAM_CHAT_ID = self.json_manager.tokens.get("TELEGRAM_CHAT_ID", "")
        
        # Если токены отсутствуют, используем заглушки (только для разработки)
        if not all([self.DISCORD_TOKEN, self.TELEGRAM_TOKEN, self.TELEGRAM_CHAT_ID]):
            self.DISCORD_TOKEN = ''
            self.TELEGRAM_TOKEN = ''
            self.TELEGRAM_CHAT_ID = ''
            # Обновляем токены в JsonManager
            self.json_manager.tokens = {
                "DISCORD_TOKEN": self.DISCORD_TOKEN,
                "TELEGRAM_TOKEN": self.TELEGRAM_TOKEN,
                "TELEGRAM_CHAT_ID": self.TELEGRAM_CHAT_ID
            }
            self.json_manager._save_json(self.json_manager.tokens, self.json_manager.files["tokens"])
        
        # Получение данных бота из JsonManager
        self.text_corpus = self.json_manager.bot_data.get("text_corpus", "")
        self.static_images = self.json_manager.bot_data.get("static_images", [])
        self.gifs = self.json_manager.bot_data.get("gifs", [])
        
        # Настройка бота Discord
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        intents.messages = True
        intents.members = True
        intents.guilds = True
        self.bot = commands.Bot(command_prefix='!', intents=intents)
        
        # Список часто встречающихся шаблонов приветствий/прощаний для фильтрации
        self.common_patterns = [
            r'\bпривет\b', r'\bздравствуй\b', r'\bпока\b', r'\bдосвидания\b', 
            r'\bхай\b', r'\bхеллоу\b', r'\bбай\b', r'\bгудбай\b'
        ]
        
        # Настройка обработчиков событий
        self.setup_event_handlers()
        
        # Обновление статистики
        self.update_stats_on_start()
        
    def update_bot_data(self):
        """Обновление данных бота в JsonManager"""
        self.json_manager.bot_data["text_corpus"] = self.text_corpus
        self.json_manager.bot_data["static_images"] = self.static_images
        self.json_manager.bot_data["gifs"] = self.gifs
        self.json_manager._save_json(self.json_manager.bot_data, self.json_manager.files["bot_data"])
    
    def update_stats_on_start(self):
        """Обновление статистики при запуске бота"""
        # Увеличиваем счетчик перезапусков
        self.json_manager.stats["general"]["restarts"] += 1
        self.json_manager._save_json(self.json_manager.stats, self.json_manager.files["stats"])
    
    def update_message_stats(self, message_type="text", is_received=True):
        """Обновление статистики сообщений"""
        if is_received:
            self.json_manager.stats["messages"]["total_received"] += 1
        else:
            self.json_manager.stats["messages"]["total_sent"] += 1
        
        # Обновляем статистику по типу сообщений
        if message_type in self.json_manager.stats["messages"]["by_type"]:
            self.json_manager.stats["messages"]["by_type"][message_type] += 1
        
        # Обновляем статистику по дням
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        if today not in self.json_manager.stats["messages"]["by_day"]:
            self.json_manager.stats["messages"]["by_day"][today] = 0
        self.json_manager.stats["messages"]["by_day"][today] += 1
        
        # Сохраняем обновленную статистику
        self.json_manager._save_json(self.json_manager.stats, self.json_manager.files["stats"])
    
    def setup_event_handlers(self):
        """Настройка обработчиков событий Discord"""
        
        @self.bot.event
        async def on_ready():
            logger.info(f'{self.bot.user} has connected to Discord!')
            
        @self.bot.event
        async def on_message(message):
            if message.author == self.bot.user:
                return
            
            # Обрабатываем сообщение
            await self.process_message(message)
            
            # Обрабатываем команды
            await self.bot.process_commands(message)
        
        @self.bot.event
        async def on_message_delete(message):
            if not message.author.bot:
                log = f'Сообщение от {message.author.name} было удалено: {message.content}'
                self.send_to_telegram(log)
        
        @self.bot.event
        async def on_message_edit(before, after):
            if not before.author.bot:
                log = f'Сообщение от {before.author.name} было отредактировано.\nСтарое: {before.content}\nНовое: {after.content}'
                self.send_to_telegram(log)
        
        @self.bot.event
        async def on_voice_state_update(member, before, after):
            log = None
            if before.channel is None and after.channel is not None:
                log = f'{member.name} зашел в голосовой канал {after.channel.name}'
            elif before.channel is not None and after.channel is None:
                log = f'{member.name} вышел из голосового канала {before.channel.name}'
            elif before.channel != after.channel:
                log = f'{member.name} перешел из {before.channel.name} в {after.channel.name}'

            if log:
                self.send_to_telegram(log)
        
        @self.bot.event
        async def on_member_update(before, after):
            if before.nick != after.nick:
                old_nick = before.nick if before.nick else before.name
                new_nick = after.nick if after.nick else after.name
                log = f'Никнейм пользователя {before.name} изменен: {old_nick} -> {new_nick}'
                
                if after.guild.me.guild_permissions.view_audit_log:
                    async for entry in after.guild.audit_logs(limit=1, action=discord.AuditLogAction.member_update):
                        if entry.target.id == after.id and entry.before.nick != entry.after.nick:
                            log += f' (изменено пользователем {entry.user.name})'
                            break
                
                self.send_to_telegram(log)
        
        @self.bot.event
        async def on_guild_channel_update(before, after):
            if before.name != after.name:
                channel_type = "текстовый" if isinstance(after, discord.TextChannel) else "голосовой"
                log = f'{channel_type.capitalize()} канал изменен: {before.name} -> {after.name}'
                
                if after.guild.me.guild_permissions.view_audit_log:
                    async for entry in after.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_update):
                        if entry.target.id == after.id and entry.before.name != entry.after.name:
                            log += f' (изменено пользователем {entry.user.name})'
                            break
                
                self.send_to_telegram(log)
        
        @self.bot.event
        async def on_guild_channel_delete(channel):
            channel_type = "текстовый" if isinstance(channel, discord.TextChannel) else "голосовой"
            log = f'{channel_type.capitalize()} канал {channel.name} был удален'
            
            if channel.guild.me.guild_permissions.view_audit_log:
                async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
                    if entry.target.id == channel.id:
                        log += f' (удалено пользователем {entry.user.name})'
                        break
            
            self.send_to_telegram(log)
    
    async def process_message(self, message):
        """Обработка сообщений от пользователей"""
        
        if not message.author.bot:
            # Логирование сообщения
            log = f'Сообщение от {message.author.name}: {message.content}'
            self.send_to_telegram(log)
            self.update_message_stats(message_type="text", is_received=True)
            
            # Обработка вложений
            for attachment in message.attachments:
                if attachment.url.lower().endswith(('.png', '.jpg', '.jpeg')):
                    self.static_images.append(attachment.url)
                    if len(self.static_images) > 50:
                        self.static_images.pop(0)
                    image_path = f'./{attachment.filename}'
                    await attachment.save(image_path)
                    self.send_image_to_telegram(image_path)
                    os.remove(image_path)
                    self.update_message_stats(message_type="image", is_received=True)
                elif attachment.url.lower().endswith('.gif'):
                    self.gifs.append(attachment.url)
                    if len(self.gifs) > 50:
                        self.gifs.pop(0)
                    image_path = f'./{attachment.filename}'
                    await attachment.save(image_path)
                    self.send_image_to_telegram(image_path)
                    os.remove(image_path)
                    self.update_message_stats(message_type="gif", is_received=True)
                else:
                    self.send_to_telegram(f'Вложение от {message.author.name}: {attachment.url} (не изображение)')
        
        # Фильтрация и обработка входящего сообщения
        filtered_content = self.filter_emojis(message.content)
        
        # Проверяем, не содержит ли сообщение типичных шаблонов (приветствие/прощание)
        if filtered_content and not self.contains_common_pattern(filtered_content):
            normalized_content = self.normalize_text(filtered_content)
            # Добавляем новый текст в корпус, только если это не типичный шаблон
            self.text_corpus += normalized_content + " "
        
        words = self.text_corpus.split()
        if len(words) > 1000:
            self.text_corpus = ' '.join(words[-1000:])
        
        # Сохраняем обновленные данные
        self.update_bot_data()
        
        # Обработка упоминаний бота
        if self.bot.user in message.mentions:
            if len(words) < 10 and not self.static_images and not self.gifs:
                await message.channel.send("Недостаточно данных для генерации ответа.")
                return
            
            # Выбираем тип ответа: текст, изображение или GIF
            response_type = random.choice(
                ["text", "static_image", "gif"]
                if self.static_images and self.gifs else
                ["text", "static_image"] if self.static_images else
                ["text", "gif"] if self.gifs else
                ["text"]
            )
            
            if response_type == "text" and words:
                # Выбираем между генерацией через markovify и полностью случайными словами
                use_markov = random.choice([True, False])
                generated_message = self.generate_response(self.text_corpus, words, use_markov)
                await message.channel.send(generated_message)
                self.send_to_telegram(f'Бот ответил {message.author.name}: {generated_message}')
                self.update_message_stats(message_type="text", is_received=False)
            
            elif response_type == "static_image" and self.static_images:
                image_url = random.choice(self.static_images)
                await message.channel.send(image_url)
                self.send_to_telegram(f'Бот ответил {message.author.name} картинкой: {image_url}')
                self.update_message_stats(message_type="image", is_received=False)
            
            elif response_type == "gif" and self.gifs:
                gif_url = random.choice(self.gifs)
                await message.channel.send(gif_url)
                self.send_to_telegram(f'Бот ответил {message.author.name} GIF: {gif_url}')
                self.update_message_stats(message_type="gif", is_received=False)
    
    # Функция фильтрации эмодзи
    def filter_emojis(self, text):
        emoji_pattern = re.compile(r'[\U0001F000-\U0001FFFF]')
        return emoji_pattern.sub('', text).strip()
    
    # Нормализация текста
    def normalize_text(self, text):
        text = re.sub(r'\s+', ' ', text).strip()
        text = re.sub(r'([а-яА-Яa-zA-Z0-9])_([а-яА-Яa-zA-Z0-9])', r'\1 \2', text)
        return text
    
    # Функция, проверяющая содержит ли сообщение типичный шаблон
    def contains_common_pattern(self, message):
        for pattern in self.common_patterns:
            if re.search(pattern, message.lower()):
                return True
        return False
    
    # Функция генерации случайных слов из корпуса
    def generate_random_words(self, words, min_length=3, max_length=8):
        if len(words) < min_length:
            return "Недостаточно данных для генерации ответа."
        
        # Выбираем случайное количество слов
        word_count = random.randint(min_length, min(max_length, len(words)))
        
        # Выбираем случайные слова из корпуса
        selected_words = []
        for _ in range(word_count):
            # Берем случайное слово из корпуса
            selected_words.append(random.choice(words))
        
        # Соединяем слова в предложение
        return ' '.join(selected_words)
    
    # Модифицированная функция генерации ответа с использованием markovify
    def generate_response(self, text_corpus, words, use_markov=True):
        # Проверка на наличие достаточного количества слов в корпусе
        if len(words) < 10:
            return "Недостаточно данных для генерации ответа."
        
        # Пробуем использовать markovify для более осмысленных ответов
        if use_markov:
            try:
                text_model = markovify.Text(text_corpus, state_size=2)
                # Пробуем сгенерировать осмысленное предложение
                for _ in range(15):
                    generated_response = text_model.make_short_sentence(
                        max_chars=100,
                        max_words=10,
                        min_words=2,
                        tries=100
                    )
                    if generated_response and len(generated_response.split()) >= 2:
                        return generated_response
            except Exception as e:
                logger.error(f"Ошибка при генерации ответа через markovify: {e}")
        
        # Если markovify не справился или не используется, генерируем случайные слова
        return self.generate_random_words(words)
    
    # Функция отправки текстовых сообщений в Telegram с повторными попытками
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def send_to_telegram(self, message):
        try:
            url = f'https://api.telegram.org/bot{self.TELEGRAM_TOKEN}/sendMessage'
            payload = {'chat_id': self.TELEGRAM_CHAT_ID, 'text': message}
            response = requests.post(url, json=payload)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка отправки в Telegram: {e}")
            with open("error_log.txt", "a") as f:
                f.write(f"{datetime.datetime.now()} Ошибка отправки в Telegram: {e}\n")
            raise
    
    # Функция отправки изображений в Telegram с повторными попытками
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def send_image_to_telegram(self, image_path):
        try:
            url = f'https://api.telegram.org/bot{self.TELEGRAM_TOKEN}/sendPhoto'
            with open(image_path, 'rb') as image_file:
                files = {'photo': image_file}
                payload = {'chat_id': self.TELEGRAM_CHAT_ID}
                response = requests.post(url, data=payload, files=files)
                response.raise_for_status()
        except (requests.exceptions.RequestException, FileNotFoundError) as e:
            logger.error(f"Ошибка отправки изображения в Telegram: {e}")
            with open("error_log.txt", "a") as f:
                f.write(f"{datetime.datetime.now()} Ошибка отправки изображения в Telegram: {e}\n")
            raise
    
    def run(self):
        """Запуск бота"""
        logger.info("Запуск бота Discord...")
        self.bot.run(self.DISCORD_TOKEN)

# Функция для запуска бота
if __name__ == "__main__":
    discord_bot = DiscordBot()
    discord_bot.run()
