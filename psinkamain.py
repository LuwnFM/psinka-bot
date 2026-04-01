import g4f
import disnake
import random
import re
import os
import logging
import time
import math
import csv
import io
import asyncio
import traceback
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from typing import Tuple, List, Dict, Any, Optional
from disnake.ext import commands
from openai import OpenAI
import aiohttp
from groq import Groq
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, UniqueConstraint, func
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError

# ============================================================================
# 🔧 НАСТРОЙКИ И БАЗА ДАННЫХ (NEON TECH OPTIMIZED)
# ============================================================================

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')
IS_RAILWAY = os.getenv('RAILWAY', '').lower() == 'true'
OWNER_ID = int(os.getenv('OWNER_ID', 0))
REQUIRED_ROLE_ID = int(os.getenv('ROLE_ID', 0))

Base = declarative_base()

class ModelSuccessLog(Base):
    __tablename__ = 'model_success_log'
    id = Column(Integer, primary_key=True)
    provider = Column(String(50), nullable=False)
    model_name = Column(String(100), nullable=False)
    success_count = Column(Integer, default=1)
    last_success_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    avg_latency_ms = Column(Integer, default=0)
    __table_args__ = (UniqueConstraint('provider', 'model_name', name='_provider_model_uc'),)

def init_db():
    if not DATABASE_URL:
        logging.warning("⚠️ DATABASE_URL не найден. Работа с БД отключена (экономия ресурсов).")
        return None, None
    try:
        engine = create_engine(DATABASE_URL, echo=False, future=True, pool_pre_ping=True, pool_size=5, max_overflow=10)
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        logging.info("✅ База данных Neon подключена.")
        return engine, SessionLocal
    except Exception as e:
        logging.error(f"❌ Ошибка подключения к БД: {e}")
        return None, None

db_engine, SessionLocal = init_db()

class DBManager:
    def __init__(self, session_factory):
        self.SessionLocal = session_factory

    def log_success(self, provider: str, model: str, latency_ms: int):
        """Записывает успех ТОЛЬКО после реального ответа пользователю. Никакой разминки."""
        if not self.SessionLocal: 
            return
        session = self.SessionLocal()
        try:
            record = session.query(ModelSuccessLog).filter_by(provider=provider, model_name=model).first()
            if record:
                record.success_count += 1
                record.avg_latency_ms = int((record.avg_latency_ms * (record.success_count - 1) + latency_ms) / record.success_count)
                record.last_success_at = datetime.now(timezone.utc)
            else:
                record = ModelSuccessLog(provider=provider, model_name=model, success_count=1, 
                                         last_success_at=datetime.now(timezone.utc), avg_latency_ms=latency_ms)
                session.add(record)
            session.commit()
            self._cleanup_old_records(session)
        except Exception as e:
            session.rollback()
            logging.error(f"Ошибка записи в БД: {e}")
        finally:
            session.close()

    def _cleanup_old_records(self, session):
        """Оставляет только последние 200 записей для экономии места и скорости"""
        try:
            count = session.query(ModelSuccessLog).count()
            if count > 200:
                old_ids = session.query(ModelSuccessLog.id).order_by(ModelSuccessLog.last_success_at.asc()).limit(count - 200).all()
                if old_ids:
                    session.query(ModelSuccessLog).filter(ModelSuccessLog.id.in_([x[0] for x in old_ids])).delete(synchronize_session=False)
                    session.commit()
        except:
            pass

    def get_top_models(self, limit: int = 10) -> List[Tuple[str, str, int]]:
        if not self.SessionLocal: return []
        session = self.SessionLocal()
        try:
            results = session.query(ModelSuccessLog.provider, ModelSuccessLog.model_name, ModelSuccessLog.avg_latency_ms)\
                             .order_by(ModelSuccessLog.success_count.desc(), ModelSuccessLog.avg_latency_ms.asc())\
                             .limit(limit).all()
            return [(r.provider, r.model_name, r.avg_latency_ms) for r in results]
        except:
            return []
        finally:
            session.close()
    
    def export_to_csv(self) -> Optional[str]:
        if not self.SessionLocal: return None
        session = self.SessionLocal()
        try:
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['ID', 'Provider', 'Model', 'Success Count', 'Avg Latency (ms)', 'Last Success'])
            records = session.query(ModelSuccessLog).order_by(ModelSuccessLog.success_count.desc()).all()
            for r in records:
                writer.writerow([r.id, r.provider, r.model_name, r.success_count, r.avg_latency_ms, r.last_success_at])
            return output.getvalue()
        except Exception as e:
            logging.error(f"Ошибка экспорта CSV: {e}")
            return None
        finally:
            session.close()
    
    def has_data(self) -> bool:
        if not self.SessionLocal: return False
        session = self.SessionLocal()
        try:
            return session.query(ModelSuccessLog).count() > 0
        except:
            return False
        finally:
            session.close()

db_manager = DBManager(SessionLocal)

# ============================================================================
# 🔧 ЛОГИРОВАНИЕ (ИСПРАВЛЕНО ДЛЯ СКАЧИВАНИЯ)
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_errors.log', encoding='utf-8', delay=True)
    ]
)
logger = logging.getLogger(__name__)

ANALYSIS_LOG_FILE = "analysis_debug.log"
analysis_logger = logging.getLogger("analysis_debug")
analysis_logger.setLevel(logging.INFO)
if not analysis_logger.handlers:
    fh = logging.FileHandler(ANALYSIS_LOG_FILE, mode='w', encoding='utf-8')
    fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    analysis_logger.addHandler(fh)

def log_analysis(msg: str, level: str = "INFO"):
    getattr(analysis_logger, level.lower())(msg)

intents = disnake.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

PRIORITY_TIER_1 = [("PollinationsAI", "deepseek-r1"), ("PollinationsAI", "deepseek-v3")]
PRIORITY_TIER_2 = [("FreeGPT", "deepseek-r1"), ("Vercel", "deepseek-r1")]
EXCLUDED_OR_MODELS = ["liquid/lfm-2.5-1.2b-instruct:free"]
OPENROUTER_PRIORITY = "nvidia/nemotron-3-super-120b-a12b:free"

ANALYSIS_SYSTEM_PROMPT = """
Ты — модератор RP сервера Discord. Твоя задача — найти ТОЛЬКО явный оффтоп, спам и нарушения формата постов.

📋 ЧТО ИГНОРИРОВАТЬ (НЕ отмечать):
- Любые ролевые действия, описания в **звёздочках**, __подчёркиваниях__ или `код`е.
- Диалоги персонажей, сюжетные повороты (даже жестокие, романтические или драматичные).
- Ролевые пинги (@персонаж, @должность) внутри контекста игры.
- Системные сообщения о переходе между локациями (если это часть сюжета).
- Эмоции и реакции персонажей (страх, боль, слезы).
- ВАЖНО: Не оценивай содержание роли (мораль, жестокость, этику), если это не реальный спам/оффтоп.

🚨 ЧТО ФИКСИРОВАТЬ (отмечать ID):
1. Оффтоп/Спам:
   - Флуд (короткие бессмысленные сообщения подряд: "а", "лол", смайлы без текста).
   - OOC обсуждения ((вне роли), //комментарии, обсуждение механик вне игры).
   - Попрошайничество (просьбы дать ресурсы/деньги вне игрового контекста).
   - Спам пингами (@everyone, @here, массовые упоминания не по делу).
   - Личные оскорбления игроков (не персонажей).
   - Реклама сторонних ресурсов.

2. Нарушение длины поста (Too Short):
   - Пост слишком короткий, если он занимает МЕНЕЕ 4 строк на компьютере ИЛИ МЕНЕЕ 6 строк на телефоне.
   - Ориентир: Если сообщение состоит из 1-2 предложений, одной фразы или просто "@user - Ссылка" без дополнительного описания действий/мыслей — это нарушение.
   - Исключение: Короткие реплики в быстром диалоге допустимы, если они часть плотной переписки, но одиночные сообщения типа "Привет", "Ок", "@user" — фиксируй.

📤 ФОРМАТ ОТВЕТА:
Верни ТОЛЬКО номера сообщений (ID) через запятую (например: 5, 12, 28) или NONE если нарушений нет.
Никаких пояснений, текста, кавычек или форматирования кроме списка цифр.

Пример правильного ответа: 3, 7, 15
Пример правильного ответа при отсутствии нарушений: NONE
"""

FREE_PROXY_LIST = [
    "http://103.152.112.162:80", "http://185.217.136.234:8080",
    "http://47.88.29.109:8080", "http://103.167.135.110:80", "http://185.162.230.55:80",
]

# GROQ модели с приоритетами (отсортировано по предпочтению на основе лимитов)
# Tier 1: Лучшие по балансу скорость/качество/лимиты
# - meta-llama/llama-4-scout-17b-16e-instruct: 30 RPM, 1K RPD, 30K TPM, 500K TPD
# - qwen/qwen3-32b: 60 RPM, 1K RPD, 6K TPM, 500K TPD (лучший TPM лимит)
# - llama-3.3-70b-versatile: 30 RPM, 1K RPD, 12K TPM, 100K TPD
GROQ_PRIORITY_MODELS = [
    # Tier 1: Топ модели
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "qwen/qwen3-32b",
    "llama-3.3-70b-versatile",
    # Tier 2: Быстрые легкие модели с высокими лимитами
    "llama-3.1-8b-instant",       # 30 RPM, 14.4K RPD, 6K TPM, 500K TPD
    "groq/compound-mini",         # 30 RPM, 250 RPD, 70K TPM, No limit TPD
    # Tier 3: Специализированные модели
    "groq/compound",              # 30 RPM, 250 RPD, 70K TPM, No limit TPD
    "allam-2-7b",                 # 30 RPM, 7K RPD, 6K TPM, 500K TPD
    "moonshotai/kimi-k2-instruct",# 60 RPM, 1K RPD, 10K TPM, 300K TPD
    "moonshotai/kimi-k2-instruct-0905",
]

async def fetch_free_proxies(count: int = 20) -> List[str]:
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all&limit={count}"
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    text = await response.text()
                    proxies = [f"http://{p.strip()}" for p in text.split('\n') if p.strip() and ':' in p]
                    if proxies:
                        logger.info(f"🌐 Обновлён список прокси: {len(proxies)} шт.")
                        return proxies
    except Exception as e:
        logger.warning(f"⚠️ Не удалось обновить прокси: {e}")
    return FREE_PROXY_LIST

def get_random_proxy(use_proxy: bool) -> Optional[str]:
    if not use_proxy: return None
    return random.choice(FREE_PROXY_LIST)

async def check_access(interaction: disnake.CommandInteraction, allowed_role_names: List[str] = ["Псарь"]) -> bool:
    if interaction.author.id == OWNER_ID: return True
    if REQUIRED_ROLE_ID != 0:
        if any(role.id == REQUIRED_ROLE_ID for role in interaction.author.roles): return True
        await interaction.response.send_message("❌ Нет роли (по ID).", ephemeral=True)
        return False
    user_role_names = [role.name for role in interaction.author.roles]
    if any(role_name in user_role_names for role_name in allowed_role_names): return True
    if REQUIRED_ROLE_ID == 0 and any(role_name in user_role_names for role_name in allowed_role_names): return True
    
    await interaction.response.send_message(f"❌ Нет доступа.", ephemeral=True)
    return False

# ============================================================================
# 🤖 ЗАПРОСЫ К МОДЕЛЯМ
# ============================================================================

async def make_g4f_request(provider_name: str, model: str, prompt: str,
                           timeout: float = 40.0, system_prompt: str = None, proxy_url: str = None) -> Tuple[bool, str, float]:
    start = time.time()
    messages = []
    if system_prompt: messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    provider_arg = getattr(g4f.Provider, provider_name, None) if provider_name else None
    
    def sync_call():
        return g4f.ChatCompletion.create(
            model=model,
            messages=messages,
            provider=provider_arg,
            timeout=int(timeout)
        )

    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(sync_call),
            timeout=timeout
        )
        
        if response:
            answer = str(response).strip()
            if "The model does not exist" in answer or "api.airforce" in answer:
                return False, "Model Not Found", time.time() - start
            if answer:
                return True, answer, time.time() - start
        return False, "Пустой ответ", time.time() - start
    except asyncio.TimeoutError:
        return False, f"Таймаут {timeout}с", time.time() - start
    except Exception as e:
        return False, str(e)[:100], time.time() - start

async def test_openrouter_single(model: str, prompt: str, timeout: float = 35.0, system_prompt: str = None, proxy_url: str = None):
    openrouter_token = os.getenv('OPENR_TOKEN')
    if not openrouter_token: return False, "No Token", 0.0
    start = time.time()
    messages = []
    if system_prompt: messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=openrouter_token)
    
    def sync_call():
        return client.chat.completions.create(
            model=model, 
            messages=messages, 
            timeout=int(timeout),
            extra_headers={"HTTP-Referer": "https://github.com/psiiinka-bot", "X-OpenRouter-Title": "PsIInka Bot"}
        )

    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(sync_call),
            timeout=timeout
        )
        if response.choices and len(response.choices) > 0:
            answer = response.choices[0].message.content
            if answer and answer.strip():
                return True, answer.strip(), time.time() - start
        return False, "Пустой ответ", time.time() - start
    except Exception as e:
        return False, str(e)[:100], time.time() - start

async def test_groq_single(models: list, prompt: str, timeout: float = 35.0, system_prompt: str = None):
    groq_token = os.getenv('GROQ_TOKEN')
    if not groq_token: return False, "No GROQ Token", 0.0
    
    for model in models:
        start = time.time()
        messages = []
        if system_prompt: messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        client = Groq(api_key=groq_token)
        
        def sync_call():
            return client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.7,
                max_tokens=2048,
                timeout=int(timeout)
            )

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(sync_call),
                timeout=timeout
            )
            if response.choices and len(response.choices) > 0:
                answer = response.choices[0].message.content
                if answer and answer.strip():
                    return True, answer.strip(), time.time() - start
            logger.warning(f"Groq model {model} returned empty answer")
        except asyncio.TimeoutError:
            logger.warning(f"Groq model {model} timed out")
            continue
        except Exception as e:
            logger.warning(f"Groq model {model} error: {str(e)[:50]}")
            continue
    
    return False, "Все модели GROQ не ответили", time.time() - start

async def heartbeat_keeper():
    while True:
        await asyncio.sleep(60)
        logger.debug("💓 Heartbeat OK")

# ============================================================================
# 🎲 ДВИЖОК КУБИКОВ (Базовый из Кода 1)
# ============================================================================

class DiceResult:
    def __init__(self):
        self.total = 0.0
        self.dice_rolls: List[int] = []
        self.details: List[str] = []
        self.comment = ""
        self.exploded_rolls: List[int] = []
        self.kept_dice: List[int] = []
        self.dropped_dice: List[int] = []
        self.rerolled: bool = False
        self.successes: int = 0
        self.failures: int = 0
        self.botches: int = 0

class DiceParser:
    def __init__(self):
        # Алиасы удалены - только продвинутая система кубиков
        pass
    
    def parse(self, command_str: str) -> List[DiceResult]:
        """Парсит команду кубиков с поддержкой модификаторов."""
        results = []
        if not command_str or not command_str.strip():
            return results
        
        command_str = command_str.strip()
        
        # Разделяем по точке с запятой для множественных бросков
        sets = command_str.split(';')
        
        for s in sets[:4]:  # Максимум 4 разных броска
            s = s.strip()
            if not s:
                continue
            
            result = self._parse_single_roll(s)
            if result:
                results.append(result)
        
        return results
    
    def _parse_single_roll(self, roll_str: str) -> Optional[DiceResult]:
        """Парсит одиночный бросок со всеми модификаторами."""
        res = DiceResult()
        original_str = roll_str
        
        # Извлекаем комментарий после !
        if '!' in roll_str:
            parts = roll_str.split('!', 1)
            roll_str = parts[0].strip()
            res.comment = parts[1].strip()
        
        # Проверяем флаги (s, nr, p, ul и т.д.)
        flags = []
        flag_pattern = r'\b([a-z]{1,2})\b'
        potential_flags = re.findall(flag_pattern, roll_str.lower())
        for flag in potential_flags:
            if flag in ['s', 'nr', 'p', 'ul', 'e', 'ie', 'k', 'kl', 'd', 'dl', 'r', 'ir', 't', 'f', 'b']:
                flags.append(flag)
        
        # Удаляем флаги из строки для парсинга
        clean_str = roll_str
        for flag in flags:
            clean_str = re.sub(r'\b' + flag + r'\b', '', clean_str, flags=re.IGNORECASE)
        
        # Парсим количество наборов (например "6 4d6" = 6 наборов по 4d6)
        num_sets = 1
        set_match = re.match(r'^(\d+)\s+(.+)$', clean_str.strip())
        if set_match:
            num_sets = min(int(set_match.group(1)), 20)  # Максимум 20 наборов
            clean_str = set_match.group(2)
        
        # Парсим основную формулу кубиков
        dice_match = re.search(r'(\d*)d(\d+)', clean_str, re.IGNORECASE)
        if not dice_match:
            # Пробуем найти просто число
            num_match = re.match(r'^(\d+)$', clean_str.strip())
            if num_match:
                res.total = float(num_match.group(1))
                res.details = f"Статическое значение: {res.total}"
                return res
            return None
        
        num_dice = int(dice_match.group(1) or 1)
        num_sides = int(dice_match.group(2))
        
        # Ограничиваем грани до 100
        if num_sides > 100:
            num_sides = 100
        
        # Ограничиваем количество кубиков
        if num_dice > 100:
            num_dice = 100
        
        # Бросаем кубики
        rolls = [random.randint(1, num_sides) for _ in range(num_dice)]
        res.dice_rolls = rolls.copy()
        
        # Обработка exploding dice (e)
        if 'e' in flags or 'ie' in flags:
            explode_val = num_sides  # По умолчанию взрывается на макс значении
            infinite = 'ie' in flags
            
            # Проверяем есть ли конкретное значение взрыва (e6)
            explode_match = re.search(r'(i?e)(\d+)', roll_str, re.IGNORECASE)
            if explode_match:
                infinite = explode_match.group(1).lower() == 'ie'
                explode_val = int(explode_match.group(2))
            
            original_rolls = rolls.copy()
            rolls_to_process = list(enumerate(rolls))
            exploded_count = 0
            max_explodes = 100 if infinite else len(rolls)
            
            while rolls_to_process and exploded_count < max_explodes:
                new_rolls_to_process = []
                for idx, val in rolls_to_process:
                    if val >= explode_val:
                        # Кубик взрывается - добавляем новый бросок
                        new_roll = random.randint(1, num_sides)
                        res.dice_rolls.append(new_roll)
                        res.exploded_rolls.append(new_roll)
                        exploded_count += 1
                        if infinite and new_roll >= explode_val and exploded_count < max_explodes:
                            new_rolls_to_process.append((len(res.dice_rolls)-1, new_roll))
                rolls_to_process = new_rolls_to_process
            
            res.details.append(f"Взрывы: +{len(res.exploded_rolls)} доп. бросков")
        
        # Обработка reroll (r, ir)
        if 'r' in flags or 'ir' in flags:
            reroll_val = None
            infinite = 'ir' in flags
            
            # Проверяем конкретное значение для reroll (r2)
            reroll_match = re.search(r'(i?r)(\d+)', roll_str, re.IGNORECASE)
            if reroll_match:
                infinite = reroll_match.group(1).lower() == 'ir'
                reroll_val = int(reroll_match.group(2))
            else:
                reroll_val = 1  # По умолчанию reroll единиц
            
            max_rerolls = 100 if infinite else len(res.dice_rolls)
            reroll_count = 0
            
            for i in range(len(res.dice_rolls)):
                while res.dice_rolls[i] <= reroll_val and reroll_count < max_rerolls:
                    res.dice_rolls[i] = random.randint(1, num_sides)
                    reroll_count += 1
                    res.rerolled = True
                    if not infinite:
                        break
            
            if reroll_count > 0:
                res.details.append(f"Перебросы: {reroll_count}")
        
        # Обработка keep/drop (k, kl, d, dl)
        kept_count = len(res.dice_rolls)
        if any(f in flags for f in ['k', 'kl', 'd', 'dl']):
            keep_val = None
            
            # Определяем сколько оставлять/сбрасывать
            for flag in ['k', 'kl', 'd', 'dl']:
                match = re.search(flag + r'(\d+)', roll_str, re.IGNORECASE)
                if match:
                    keep_val = int(match.group(1))
                    break
            
            if keep_val is not None and keep_val < len(res.dice_rolls):
                sorted_rolls = sorted(res.dice_rolls, reverse=True)
                
                if 'k' in flags or 'kl' in flags:
                    # Keep highest или keep lowest
                    if 'kl' in flags:
                        # Keep lowest - берём наименьшие
                        sorted_rolls = sorted(res.dice_rolls)
                        res.kept_dice = sorted_rolls[:keep_val]
                        res.dropped_dice = sorted_rolls[keep_val:]
                    else:
                        # Keep highest - берём наибольшие (по умолчанию)
                        res.kept_dice = sorted_rolls[:keep_val]
                        res.dropped_dice = sorted_rolls[keep_val:]
                    
                    res.dice_rolls = res.kept_dice
                    res.details.append(f"Оставлено {keep_val} лучших")
                
                elif 'd' in flags or 'dl' in flags:
                    # Drop lowest или drop highest
                    if 'dl' in flags:
                        # Drop lowest - сбрасываем наименьшие, оставляем лучшие
                        sorted_rolls = sorted(res.dice_rolls)
                        res.dropped_dice = sorted_rolls[:keep_val]
                        res.kept_dice = sorted_rolls[keep_val:]
                    else:
                        # Drop highest - сбрасываем наибольшие
                        res.dropped_dice = sorted_rolls[:keep_val]
                        res.kept_dice = sorted_rolls[keep_val:]
                    
                    res.dice_rolls = res.kept_dice
                    res.details.append(f"Сброшено {keep_val} худших")
        
        # Обработка success/failure (t, f)
        if 't' in flags:
            target_val = None
            failure_val = None
            
            t_match = re.search(r't(\d+)', roll_str, re.IGNORECASE)
            f_match = re.search(r'f(\d+)', roll_str, re.IGNORECASE)
            
            if t_match:
                target_val = int(t_match.group(1))
            if f_match:
                failure_val = int(f_match.group(1))
            
            if target_val is not None:
                for roll in res.dice_rolls:
                    if roll >= target_val:
                        res.successes += 1
                    elif failure_val is not None and roll <= failure_val:
                        res.failures += 1
                
                res.total = res.successes - res.failures
                res.details.append(f"Успехи: {res.successes}, Провалы: {res.failures}")
        
        # Обработка botches (b)
        if 'b' in flags:
            botch_val = 1
            b_match = re.search(r'b(\d+)', roll_str, re.IGNORECASE)
            if b_match:
                botch_val = int(b_match.group(1))
            
            for roll in res.dice_rolls:
                if roll <= botch_val:
                    res.botches += 1
            
            if res.botches > 0:
                res.details.append(f"Критические провалы: {res.botches}")
        
        # Вычисляем итоговую сумму
        if 't' not in flags:  # Если не было подсчёта успехов
            res.total = sum(res.dice_rolls)
        
        # Добавляем статические модификаторы (+5, -3, *2, /2)
        modifier_match = re.search(r'([+\-*/])\s*(\d+(?:\.\d+)?)$', clean_str)
        if modifier_match:
            op = modifier_match.group(1)
            val = float(modifier_match.group(2))
            old_total = res.total
            if op == '+':
                res.total += val
            elif op == '-':
                res.total -= val
            elif op == '*':
                res.total *= val
            elif op == '/':
                if val != 0:
                    res.total /= val
            
            if op in ['+', '-']:
                res.details.append(f"{op}{int(val) if val == int(val) else val}")
        
        # Формируем детальное описание
        if not res.details:
            res.details = [f"Бросок: {res.dice_rolls}"]
        elif isinstance(res.details, list):
            res.details.insert(0, f"Бросок: {res.dice_rolls}")
        else:
            res.details = [f"Бросок: {res.dice_rolls}", res.details]
        
        return res
    
    def get_help_text(self) -> str:
        """Возвращает справку по использованию кубиков."""
        return """
🎲 **Команда `/кубик` — Продвинутая система бросков**

**Использование:** `/кубик формула` или оставьте пустым для этой справки

📋 **Базовые команды:**
• `XdY` — Бросить X кубиков с Y гранями (пример: `2d6`)
• `XdY + Z` — С модификатором (пример: `1d20 + 5`)
• `XdY - Z` — Вычесть (пример: `3d8 - 2`)
• `XdY * Z` — Умножить (пример: `2d4 * 3`)
• `XdY / Z` — Разделить (пример: `4d6 / 2`)

🔢 **Несколько бросков:**
• `N XdY` — N наборов по XdY (пример: `6 4d6` — 6 наборов по 4к6)
• `A ; B ; C` — Разные броски через точку с запятой (макс. 4)

💥 **Взрывающиеся кубики:**
• `XdY eZ` — Взрыв на Z (пример: `3d6 e6`)
• `XdY e` — Взрыв на макс. значении
• `XdY ieZ` — Бесконечные взрывы (макс. 100)

📊 **Оставить/Сбросить:**
• `XdY kZ` — Оставить Z лучших (пример: `4d6 k3`)
• `XdY klZ` — Оставить Z худших
• `XdY dZ` — Сбросить Z худших
• `XdY dlZ` — Сбросить Z лучших

🔄 **Переброс:**
• `XdY rZ` — Перебросить ≤ Z (один раз)
• `XdY irZ` — Бесконечный переброс (макс. 100)

🎯 **Успехи/Провалы:**
• `XdY tZ` — Успехи при ≥ Z (пример: `6d10 t7`)
• `XdY tZ fW` — Успехи ≥Z, провалы ≤W

⚠️ **Критические провалы:**
• `XdY bZ` — Подсчитать ботчи (≤Z)

📝 **Дополнительно:**
• `! текст` — Добавить комментарий (пример: `4d6 ! Урон`)
• `s` — Упрощённый вывод
• `ul` — Не сортировать результаты

**Ограничения:** максимум 100 граней, 100 кубиков, 20 наборов, 4 броска в команде
"""

dice_engine = DiceParser()

# ============================================================================
# 💬 КОМАНДЫ
# ============================================================================

@bot.slash_command(name="скажи", description="Запрос к ИИ")
async def slash_say(interaction: disnake.CommandInteraction, вопрос: str = commands.Param(min_length=1), прокси: str = commands.Param(choices=["Да", "Нет"], default="Нет")):
    if not await check_access(interaction): return
    try:
        await interaction.response.defer()
        msg = await interaction.edit_original_response(content="⏳ Обработка...")
        
        queue = PRIORITY_TIER_1 + PRIORITY_TIER_2
        # Добавляем GROQ между g4f и OpenRouter
        for groq_model in GROQ_PRIORITY_MODELS[:3]:  # Топ-3 модели GROQ
            queue.append(("Groq", groq_model))
        queue.append(("OpenRouter", OPENROUTER_PRIORITY))
        queue.append(("g4f-default", "deepseek-r1"))
        
        system_prompt = "Ты помощник по имени Псинка (мальчик). Отвечай кратко на русском и по делу, отвечай развёрнуто в случае нужды в глубинном анализе вопроса или при запросе пользователя."
        final_response = None
        final_prov = "?"
        final_mod = "?"
        use_proxy = (прокси == "Да")
        proxy_url = get_random_proxy(use_proxy)
        
        for prov, mod in queue:
            try:
                if prov == "OpenRouter":
                    ok, ans, lat = await test_openrouter_single(mod, вопрос, timeout=45.0, system_prompt=system_prompt, proxy_url=proxy_url)
                elif prov == "Groq":
                    ok, ans, lat = await test_groq_single(mod, вопрос, timeout=45.0, system_prompt=system_prompt)
                else:
                    ok, ans, lat = await make_g4f_request(prov, mod, вопрос, timeout=45.0, system_prompt=system_prompt, proxy_url=proxy_url)
                
                if ok and ans:
                    final_response = ans
                    final_prov, final_mod = prov, mod
                    db_manager.log_success(prov, mod, int(lat * 1000))
                    break
            except Exception as e:
                logger.warning(f"Error {prov}/{mod}: {e}")

        if not final_response:
            await msg.edit(content="❌ Не удалось получить ответ ни от одной модели.")
            return
        
        await msg.edit(content=f"🐕 Ответ ({final_prov}/{final_mod}):\n{final_response[:1900]}")
    except Exception as e:
        logger.error(f"Critical error in /say: {e}", exc_info=True)
        err_msg = f"❌ Ошибка: {str(e)[:100]}"
        if interaction.response.is_done():
            await interaction.followup.send(err_msg, ephemeral=True)
        else:
            await interaction.response.send_message(err_msg, ephemeral=True)

@bot.slash_command(name="кубик", description="Бросок кубиков")
async def slash_cube(interaction: disnake.CommandInteraction, формула: str = None):
    try:
        if not формула:
            # Показываем справку при пустой команде
            help_text = dice_engine.get_help_text()
            await interaction.response.send_message(help_text)
            return
        
        await interaction.response.defer()
        results = dice_engine.parse(формула)
        
        if not results:
            raise ValueError("Не удалось разобрать формулу. Используйте `/кубик` для справки.")
        
        # Формируем красивый вывод
        output_parts = []
        for i, r in enumerate(results):
            result_num = i + 1
            total_display = int(r.total) if r.total == int(r.total) else round(r.total, 2)
            
            part = f"**Результат #{result_num}: {total_display}**"
            
            if r.comment:
                part += f" _({r.comment})_"
            
            part += f"\n🎲 Броски: `[{', '.join(map(str, r.dice_rolls))}]`"
            
            details_extra = []
            if r.exploded_rolls:
                details_extra.append(f"💥 Взрывы: +{len(r.exploded_rolls)}")
            if r.rerolled:
                details_extra.append("🔄 Был переброс")
            if r.successes > 0 or r.failures > 0:
                details_extra.append(f"✅ Успехи: {r.successes}, ❌ Провалы: {r.failures}")
            if r.botches > 0:
                details_extra.append(f"⚠️ Ботчи: {r.botches}")
            
            if details_extra:
                part += "\n" + " ".join(details_extra)
            
            output_parts.append(part)
        
        final_output = "\n\n".join(output_parts)
        await interaction.followup.send(f"🎲 **Результат броска:**\n{final_output}")
        
    except Exception as e:
        logger.error(f"Error in /cube: {e}", exc_info=True)
        error_msg = str(e)[:200]
        await interaction.followup.send(f"❌ Ошибка: {error_msg}\nИспользуйте `/кубик` для справки по командам.", ephemeral=True)

@bot.slash_command(name="погавкай", description="Пинг")
async def slash_bark(interaction: disnake.CommandInteraction):
    try:
        await interaction.response.send_message(f'🐕 Пинг: {round(bot.latency * 1000)} мс')
    except Exception as e:
        logger.error(f"Error in /bark: {e}", exc_info=True)

@bot.slash_command(name="статус", description="Статистика")
async def slash_status(interaction: disnake.CommandInteraction):
    try:
        if not await check_access(interaction): return
        await interaction.response.defer()
        top = db_manager.get_top_models(3)
        txt = "\n".join([f"{i+1}. `{p}` / `{m}` (Lat: {lat}ms)" for i,(p,m,lat) in enumerate(top)]) if top else "Нет данных (используйте /скажи)"
        embed = disnake.Embed(title="📊 Статус", description=txt, color=0x00FF88)
        embed.add_field(name="Режим", value="Экономия ресурсов (No Warmup)", inline=False)
        await interaction.edit_original_response(embed=embed)
    except Exception as e:
        logger.error(f"Error in /status: {e}", exc_info=True)
        await interaction.followup.send(f"❌ Ошибка: {str(e)[:100]}", ephemeral=True)

# ============================================================================
# 🧪 ТЕСТ (ВОССТАНОВЛЕНО + ЛОГИРОВАНИЕ)
# ============================================================================

class TestModeView(disnake.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=300)
        self.ctx = ctx
    
    @disnake.ui.button(label="⚡ Экспресс G4F", style=disnake.ButtonStyle.green, custom_id="test_express")
    async def express_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        log_analysis("TEST: Express G4F started", "INFO")
        start = time.time()
        ok, ans, lat = await make_g4f_request("PollinationsAI", "deepseek-r1", "ответь \"ок\" если прочитал текст, не отвечай ничего другого", timeout=15.0)
        elapsed = time.time() - start
        status = "✅ Успех" if ok else f"❌ Ошибка: {ans}"
        log_analysis(f"TEST Result: {status}, Time: {elapsed:.2f}s", "INFO")
        await interaction.channel.send(f"✅ Экспресс тест G4F:\nСтатус: {status}\n⏱ Время: {elapsed:.2f}с\n📝 Ответ: {ans[:100]}")

    @disnake.ui.button(label="🦅 Groq Cloud", style=disnake.ButtonStyle.orange, custom_id="test_groq")
    async def groq_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        log_analysis("TEST: Groq Cloud started", "INFO")
        start = time.time()
        ok, ans, lat = await test_groq_single(GROQ_PRIORITY_MODELS, "ответь \"ок\" если прочитал текст, не отвечай ничего другого", timeout=15.0)
        elapsed = time.time() - start
        status = "✅ Успех" if ok else f"❌ Ошибка: {ans}"
        log_analysis(f"TEST Groq Result: {status}, Time: {elapsed:.2f}s", "INFO")
        await interaction.channel.send(f"✅ Тест Groq Cloud:\nСтатус: {status}\n⏱ Время: {elapsed:.2f}с\n📝 Ответ: {ans[:100] if ans else 'Нет ответа'}")

    @disnake.ui.button(label="🌐 OpenRouter", style=disnake.ButtonStyle.blurple, custom_id="test_openrouter")
    async def openrouter_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        log_analysis("TEST: OpenRouter started", "INFO")
        start = time.time()
        ok, ans, lat = await test_openrouter_single(OPENROUTER_PRIORITY, "ответь \"ок\" если прочитал текст, не отвечай ничего другого", timeout=15.0)
        elapsed = time.time() - start
        status = "✅ Успех" if ok else f"❌ Ошибка: {ans}"
        log_analysis(f"TEST OR Result: {status}, Time: {elapsed:.2f}s", "INFO")
        await interaction.channel.send(f"✅ Тест OpenRouter:\nСтатус: {status}\n⏱ Время: {elapsed:.2f}с\n📝 Ответ: {ans[:100] if ans else 'Нет ответа'}")

    @disnake.ui.button(label="🎯 Полный цикл", style=disnake.ButtonStyle.red, custom_id="test_all")
    async def all_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        await interaction.channel.send("✅ Запуск полного теста (G4F + Groq + OR)...")
        log_analysis("TEST: Full cycle started", "INFO")
        ok1, _, l1 = await make_g4f_request("PollinationsAI", "deepseek-r1", "ok", timeout=20.0)
        ok2, _, l2 = await test_groq_single(GROQ_PRIORITY_MODELS, "ok", timeout=20.0)
        ok3, _, l3 = await test_openrouter_single(OPENROUTER_PRIORITY, "ok", timeout=20.0)
        
        res = f"G4F: {'✅' if ok1 else '❌'} | Groq: {'✅' if ok2 else '❌'} | OR: {'✅' if ok3 else '❌'}"
        log_analysis(f"TEST Full Result: {res}", "INFO")
        await interaction.channel.send(res)

@bot.slash_command(name="тест", description="Тестирование провайдеров")
async def slash_test(interaction: disnake.CommandInteraction):
    try:
        if not await check_access(interaction): return
        embed = disnake.Embed(title="Выбор режима теста", description="Нажмите кнопку для проверки:\n\n📊 После теста будет показан топ моделей по скорости ответа!", color=0xFF8844)
        view = TestModeView(interaction)
        await interaction.response.send_message(embed=embed, view=view)
    except Exception as e:
        logger.error(f"Error in /test: {e}", exc_info=True)
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Ошибка: {str(e)[:100]}", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Ошибка: {str(e)[:100]}", ephemeral=True)

# ============================================================================
# 🔍 АНАЛИЗ (ПОЛНЫЙ ФУНКЦИОНАЛ + ЛОГИРОВАНИЕ В ФАЙЛ)
# ============================================================================

async def collect_all_messages_debug(channel, days_limit: int, max_per_source: int = 400):
    after_date = datetime.now(timezone.utc) - timedelta(days=days_limit)
    all_messages = []
    log_analysis(f"Start collecting #{channel.name} for {days_limit} days.", "INFO")
    
    try:
        async for message in channel.history(limit=max_per_source, after=after_date):
            if message.is_system() or message.author == bot.user or not message.content.strip(): continue
            all_messages.append({
                "id": len(all_messages) + 1, "real_id": message.id,
                "content": message.content[:1500], "author": str(message.author),
                "url": message.jump_url, "source": f"#{channel.name}", "created_at": message.created_at
            })
        log_analysis(f"✅ Main channel: {len(all_messages)} msgs.", "INFO")
    except Exception as e:
        log_analysis(f"❌ Main channel error: {e}", "ERROR")

    if hasattr(channel, 'threads'):
        for thread in channel.threads:
            if not hasattr(thread, 'history'): continue
            try:
                count = 0
                async for message in thread.history(limit=max_per_source, after=after_date):
                    if message.is_system() or message.author == bot.user or not message.content.strip(): continue
                    all_messages.append({
                        "id": len(all_messages) + 1, "real_id": message.id,
                        "content": message.content[:1500], "author": str(message.author),
                        "url": message.jump_url, "source": f"Thread: {thread.name}", "created_at": message.created_at
                    })
                    count += 1
                log_analysis(f"✅ Thread {thread.name}: {count} msgs.", "INFO")
                await asyncio.sleep(0.5)
            except: pass
    
    return all_messages

def format_messages_for_ai(messages_list: List[Dict]) -> str:
    return "\n".join([f"{msg['id']} [{msg['source']}]: {msg['content'].replace(chr(10), ' ')}" for msg in messages_list])

def parse_ai_response(ai_text: str, original_data: List[Dict]) -> List[Dict]:
    if not ai_text or ai_text.strip().upper() == "NONE": return []
    found_ids = []
    for part in re.split(r'[,\s]+', ai_text):
        try: found_ids.append(int(part))
        except: pass
    return [msg for msg in original_data if msg['id'] in found_ids]

@bot.slash_command(name="анализ", description="Анализ канала на нарушения")
async def slash_analyze(interaction: disnake.CommandInteraction, канал: disnake.TextChannel = commands.Param(), период: str = commands.Param(choices=["За последние 7 дней", "За последние 21 день"])):
    if interaction.author.id != OWNER_ID:
        await interaction.response.send_message("❌ Только владелец.", ephemeral=True)
        return

    days_to_check = 7 if "7 дней" in период else 21
    await interaction.response.defer()
    
    log_analysis(f"=== START ANALYSIS: {канал.name} ({days_to_check} days) ===", "INFO")
    
    try:
        messages_data = await collect_all_messages_debug(канал, days_to_check, max_per_source=400)
        if not messages_data:
            await interaction.edit_original_response(content="ℹ️ Сообщения не найдены.")
            return

        BATCH_SIZE = 35
        total_batches = (len(messages_data) + BATCH_SIZE - 1) // BATCH_SIZE
        status_msg = await interaction.edit_original_response(content=f"🔄 Анализ: [░░░░░░░░░░] 0% (0/{total_batches})\nПодготовка...")
        
        all_violations = []
        
        main_queue = PRIORITY_TIER_1 + PRIORITY_TIER_2
        # Добавляем GROQ модели в основную очередь
        groq_queue = [("Groq", m) for m in GROQ_PRIORITY_MODELS[:5]]  # Топ-5 моделей GROQ
        or_fallback = [OPENROUTER_PRIORITY, "meta-llama/llama-3.3-70b-instruct:free"]
        g4f_fallback = [("g4f-default", "deepseek-r1")]
        proxy_queue = main_queue + groq_queue + [("OpenRouter", m) for m in or_fallback] + g4f_fallback

        for i in range(0, len(messages_data), BATCH_SIZE):
            batch_data = messages_data[i : i + BATCH_SIZE]
            current_batch = (i // BATCH_SIZE) + 1
            batch_context = format_messages_for_ai(batch_data)
            user_prompt = f"Проанализируй пакет {current_batch}/{total_batches}:\n\n{batch_context}"
            
            final_answer = None
            success = False
            used_provider = "Unknown"

            def run_async_in_thread(async_func, *args, **kwargs):
                return asyncio.run(async_func(*args, **kwargs))

            async def try_request(prov, mod, use_proxy=False):
                proxy_str = get_random_proxy(True) if use_proxy else None
                if prov == "OpenRouter":
                    return await test_openrouter_single(mod, user_prompt, timeout=50.0, system_prompt=ANALYSIS_SYSTEM_PROMPT)
                elif prov == "Groq":
                    return await test_groq_single(mod, user_prompt, timeout=50.0, system_prompt=ANALYSIS_SYSTEM_PROMPT)
                else:
                    return await make_g4f_request(prov, mod, user_prompt, timeout=50.0, system_prompt=ANALYSIS_SYSTEM_PROMPT, proxy_url=proxy_str)

            # 1. Основная попытка
            for prov, mod in main_queue:
                try:
                    percent = int(((current_batch - 1) / total_batches) * 100)
                    bar = "█" * int(10 * (current_batch - 1) // total_batches) + "░" * (10 - int(10 * (current_batch - 1) // total_batches))
                    await status_msg.edit(content=f"🔄 Анализ: [{bar}] {percent}% ({current_batch-1}/{total_batches})\nПопытка: {prov}...")

                    ok, ans, _ = await asyncio.wait_for(
                        asyncio.to_thread(run_async_in_thread, try_request, prov, mod, False),
                        timeout=55.0
                    )
                    if ok:
                        final_answer = ans
                        used_provider = f"{prov} ({mod})"
                        success = True
                        break
                except Exception as e:
                    log_analysis(f"Error {prov}/{mod}: {e}", "DEBUG")
                    continue

            # 2. GROQ резерв (если не сработала основная очередь g4f)
            if not success:
                for groq_model in GROQ_PRIORITY_MODELS:
                    try:
                        ok, ans, _ = await asyncio.wait_for(
                            asyncio.to_thread(run_async_in_thread, try_request, "Groq", groq_model, False),
                            timeout=55.0
                        )
                        if ok:
                            final_answer = ans
                            used_provider = f"Groq ({groq_model})"
                            success = True
                            break
                    except: continue

            # 3. OpenRouter резерв
            if not success:
                for or_model in or_fallback:
                    try:
                        ok, ans, _ = await asyncio.wait_for(
                            asyncio.to_thread(run_async_in_thread, try_request, "OpenRouter", or_model, False),
                            timeout=55.0
                        )
                        if ok:
                            final_answer = ans
                            used_provider = f"OpenRouter ({or_model})"
                            success = True
                            break
                    except: continue

            # 4. ПРОКСИ РЕЖИМ (Крайний случай)
            if not success:
                log_analysis(f"⚠️ Batch {current_batch}: Normal failed. Activating PROXY MODE.", "WARNING")
                await status_msg.edit(content=f"🔄 Анализ: [{bar}] {percent}%\n⚠️ ОШИБКИ. ПОДКЛЮЧЕНИЕ ЧЕРЕЗ ПРОКСИ...")
                
                for prov, mod in proxy_queue:
                    try:
                        ok, ans, _ = await asyncio.wait_for(
                            asyncio.to_thread(run_async_in_thread, try_request, prov, mod, True),
                            timeout=60.0
                        )
                        if ok:
                            final_answer = ans
                            used_provider = f"{prov} ({mod}) [PROXY]"
                            success = True
                            break
                    except Exception as e:
                        log_analysis(f"Proxy Error {prov}/{mod}: {e}", "DEBUG")
                        continue

            if not success:
                final_answer = "NONE"
                used_provider = "NO_RESPONSE"
                log_analysis(f"❌ Batch {current_batch}: FAILED completely.", "ERROR")

            batch_violations = parse_ai_response(final_answer, batch_data)
            all_violations.extend(batch_violations)
            log_analysis(f"Batch {current_batch}: {used_provider}. Found: {len(batch_violations)}", "INFO")

            percent = int((current_batch / total_batches) * 100)
            bar = "█" * int(10 * current_batch // total_batches) + "░" * (10 - int(10 * current_batch // total_batches))
            await status_msg.edit(content=f"🔄 Анализ: [{bar}] {percent}% ({current_batch}/{total_batches})\n✅ Пакет #{current_batch} готов")
            await asyncio.sleep(1.0)

        await status_msg.edit(content=f"✅ Анализ завершен! [{'█'*10}] 100%\nФормирование отчета...")
        
        if not all_violations:
            await status_msg.edit(content="✅ Нарушений не найдено.")
            log_analysis("Analysis finished: No violations.", "INFO")
            return

        report_parts = []
        current_part = []
        current_len = 0
        
        for i, v in enumerate(all_violations, 1):
            clean_txt = re.sub(r'<@!?[0-9]+>', '@user', v['content'])[:400]
            line = f"{i}) **[{v['source']}]** {clean_txt} - [Ссылка]({v['url']})\n"
            if current_len + len(line) > 1800:
                report_parts.append("".join(current_part))
                current_part = [line]
                current_len = len(line)
            else:
                current_part.append(line)
                current_len += len(line)
        if current_part: report_parts.append("".join(current_part))

        header = f"🚨 Отчет по анализу ({len(all_violations)} нарушений):\n"
        await status_msg.edit(content=header + report_parts[0][:1800])
        for part in report_parts[1:]:
            await interaction.channel.send(part)
        await interaction.channel.send("✅ Анализ полностью завершен.")
        log_analysis(f"Analysis finished: {len(all_violations)} violations reported.", "INFO")

    except Exception as e:
        error_trace = traceback.format_exc()
        log_analysis(f"CRITICAL ERROR: {e}\n{error_trace}", "ERROR")
        logger.error(f"Critical error in /analyze: {e}", exc_info=True)
        await interaction.followup.send(f"❌ Критическая ошибка. Лог сохранен.\nОшибка: {str(e)[:100]}", ephemeral=True)

# ============================================================================
# 💾 АДМИН КОМАНДЫ: СКАЧАТЬ ФАЙЛЫ (ИСПРАВЛЕНО ЛОГГИРОВАНИЕ)
# ============================================================================

@bot.slash_command(name="скачать_анализ", description="Скачать лог анализа")
async def slash_download_analysis_log(interaction: disnake.CommandInteraction):
    if interaction.author.id != OWNER_ID: return
    await interaction.response.defer()
    for handler in analysis_logger.handlers:
        if isinstance(handler, logging.FileHandler):
            handler.flush()
            
    if os.path.exists(ANALYSIS_LOG_FILE):
        await interaction.followup.send(file=disnake.File(ANALYSIS_LOG_FILE))
    else:
        await interaction.followup.send("❌ Файл не найден.", ephemeral=True)

@bot.slash_command(name="скачать_ошибки", description="Скачать общий лог ошибок бота")
async def slash_download_logs(interaction: disnake.CommandInteraction):
    if interaction.author.id != OWNER_ID:
        await interaction.response.send_message("❌ Доступ запрещён.", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if isinstance(handler, logging.FileHandler):
            handler.flush()
    
    await asyncio.sleep(0.1)
    
    if os.path.exists('bot_errors.log'):
        await interaction.followup.send(file=disnake.File('bot_errors.log'))
    else:
        await interaction.followup.send("❌ Файл логов пуст или не найден.", ephemeral=True)

@bot.slash_command(name="скачать_бд", description="Скачать таблицу успехов из БД (CSV)")
async def slash_download_db(interaction: disnake.CommandInteraction):
    if interaction.author.id != OWNER_ID:
        await interaction.response.send_message("❌ Доступ запрещён.", ephemeral=True)
        return
    
    await interaction.response.defer()
    csv_data = db_manager.export_to_csv()
    
    if csv_data:
        file_obj = io.BytesIO(csv_data.encode('utf-8'))
        file_obj.name = "model_success_log.csv"
        await interaction.followup.send(file=disnake.File(file_obj))
    else:
        await interaction.followup.send("❌ Не удалось экспортировать данные или БД не подключена.", ephemeral=True)

# ============================================================================
# СОБЫТИЯ
# ============================================================================

@bot.event
async def on_ready():
    logger.info(f"Bot {bot.user} ready! (Railway: {IS_RAILWAY})")
    logger.info("🚀 MODE: NO WARMUP (DB SAVING ENABLED)")
    if REQUIRED_ROLE_ID == 0: 
        logger.info("Mode: Role 'Псарь' access.")
    else: 
        logger.info(f"Mode: Role ID {REQUIRED_ROLE_ID} access.")
    
    asyncio.create_task(fetch_free_proxies())
    asyncio.create_task(heartbeat_keeper()) 

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound): return
    
    logger.error(f"Command error {ctx.command}: {error}", exc_info=True)
    
    try:
        with open('bot_errors.log', 'a', encoding='utf-8') as f:
            f.write(f"\n[{datetime.now()}] ERROR: {type(error).__name__}: {error}\n")
            f.flush()
            os.fsync(f.fileno())
    except Exception as e:
        print(f"Failed to write to log file: {e}")
    
    if hasattr(ctx, 'author') and ctx.author.id == OWNER_ID:
        try: 
            msg = f"⚠️ Ошибка команды: {str(error)[:100]}"
            if hasattr(ctx, 'response') and ctx.response.is_done():
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.send(msg, delete_after=10)
        except: pass

if __name__ == "__main__":
    logger.info("🚀 Start PsIInka Bot v1.0-Optimized-NoWarmup")
    try:
        bot.run(os.getenv("DISCORD_TOKEN"))
    except Exception as e:
        logger.critical(f"💥 Startup crash: {e}", exc_info=True)
