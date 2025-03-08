import json
import os
import datetime
import logging
from typing import Dict, List, Any, Union, Optional, Tuple

# Настройка логирования
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("bot_logs.log"), 
                              logging.StreamHandler()])
logger = logging.getLogger('json_manager')

class JsonManager:
    """Класс для управления всеми JSON-файлами бота"""
    
    def __init__(self, config_dir: str = "config"):
        """Инициализация менеджера JSON-файлов
        
        Args:
            config_dir: Директория, в которой хранятся файлы конфигурации
        """
        self.config_dir = config_dir
        os.makedirs(config_dir, exist_ok=True)
        
        # Пути к файлам
        self.files = {
            "tokens": os.path.join(config_dir, "tokens.json"),
            "bot_data": os.path.join(config_dir, "bot_data.json"),
            "responses": os.path.join(config_dir, "responses.json"),
            "personality": os.path.join(config_dir, "personality.json"),
            "filters": os.path.join(config_dir, "filters.json"),
            "commands": os.path.join(config_dir, "commands.json"),
            "stats": os.path.join(config_dir, "stats.json"),
            "learning_config": os.path.join(config_dir, "learning_config.json"),
            "scheduler": os.path.join(config_dir, "scheduler.json")
        }
        
        # Загрузка всех файлов
        self.tokens = self._load_json(self.files["tokens"])
        self.bot_data = self._load_json(self.files["bot_data"])
        self.responses = self._load_json(self.files["responses"])
        self.personality = self._load_json(self.files["personality"])
        self.filters = self._load_json(self.files["filters"])
        self.commands = self._load_json(self.files["commands"])
        self.stats = self._load_json(self.files["stats"])
        self.learning_config = self._load_json(self.files["learning_config"])
        self.scheduler = self._load_json(self.files["scheduler"])
        
        # Инициализация недостающих файлов с значениями по умолчанию
        self._init_default_files()
        
    def _load_json(self, filepath: str) -> Dict:
        """Загрузка JSON-файла
        
        Args:
            filepath: Путь к файлу
            
        Returns:
            Словарь с данными из файла или пустой словарь, если файл не существует
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.info(f"Файл {filepath} не найден, будет создан при сохранении")
            return {}
        except json.JSONDecodeError:
            logger.error(f"Ошибка декодирования JSON в файле {filepath}")
            return {}
            
    def _save_json(self, data: Dict, filepath: str) -> bool:
        """Сохранение данных в JSON-файл
        
        Args:
            data: Данные для сохранения
            filepath: Путь к файлу
            
        Returns:
            True если сохранение прошло успешно, иначе False
        """
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения в файл {filepath}: {e}")
            return False
            
    def _init_default_files(self):
        """Инициализация файлов с значениями по умолчанию, если они отсутствуют"""
        # Проверка и инициализация bot_data.json
        if not self.bot_data:
            self.bot_data = {
                "text_corpus": "",
                "static_images": [],
                "gifs": []
            }
            self._save_json(self.bot_data, self.files["bot_data"])
            
        # Проверка и инициализация tokens.json
        if not self.tokens:
            self.tokens = {
                "DISCORD_TOKEN": "",
                "TELEGRAM_TOKEN": "",
                "TELEGRAM_CHAT_ID": ""
            }
            self._save_json(self.tokens, self.files["tokens"])
            
        # Проверка и инициализация stats.json
        if not self.stats:
            self.stats = {
                "general": {
                    "start_date": datetime.datetime.now().isoformat(),
                    "uptime": 0,
                    "restarts": 0,
                    "version": "1.0.0"
                },
                "messages": {
                    "total_received": 0,
                    "total_sent": 0,
                    "by_type": {
                        "text": 0,
                        "image": 0,
                        "gif": 0
                    },
                    "by_day": {},
                    "peak_time": None,
                    "slowest_time": None
                }
            }  # Added closing brace here
            self._save_json(self.stats, self.files["stats"])