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
# 🔧 НАСТРОЙКИ И БАЗА ДАННЫХ
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
# 🔧 ЛОГИРОВАНИЕ
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

# ============================================================================
# 🤖 КОНФИГУРАЦИЯ МОДЕЛЕЙ
# ============================================================================

PRIORITY_TIER_1 = [("PollinationsAI", "deepseek-r1"), ("PollinationsAI", "deepseek-v3")]
PRIORITY_TIER_2 = [("FreeGPT", "deepseek-r1"), ("Vercel", "deepseek-r1")]
EXCLUDED_OR_MODELS = ["liquid/lfm-2.5-1.2b-instruct:free"]
OPENROUTER_PRIORITY = "nvidia/nemotron-3-super-120b-a12b:free"

GROQ_PRIORITY_MODELS = [
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "qwen/qwen3-32b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "moonshotai/kimi-k2-instruct-0905",
]

OR_PRIORITY_MODELS = [
    OPENROUTER_PRIORITY,
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-3-27b-it:free",
    "qwen/qwen3-32b:free",
]

FREE_PROXY_LIST = [
    "http://103.152.112.162:80", "http://185.217.136.234:8080",
    "http://47.88.29.109:8080", "http://103.167.135.110:80", "http://185.162.230.55:80",
]

TEST_PROMPT = "Ответь только словом ок"

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

# ============================================================================
# 🛠 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

async def fetch_free_proxies(count: int = 20) -> List[str]:
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=http&timeout=10000&limit={count}"
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
    if interaction.author.id == OWNER_ID:
        return True
    
    if REQUIRED_ROLE_ID != 0:
        if any(role.id == REQUIRED_ROLE_ID for role in interaction.author.roles):
            return True
        await interaction.response.send_message("❌ Гав! Нет доступа (нужна роль по ID).", ephemeral=True)
        return False
    
    user_role_names = [role.name for role in interaction.author.roles]
    if any(role_name in user_role_names for role_name in allowed_role_names):
        return True
    
    await interaction.response.send_message(f"❌ Гав! Нет доступа (нужна роль: {', '.join(allowed_role_names)}).", ephemeral=True)
    return False

def create_progress_bar(current: int, total: int, length: int = 10) -> str:
    if total == 0: return "░" * length
    filled = int(length * current / total)
    return "█" * filled + "░" * (length - filled)

# ============================================================================
# 🌐 ЗАПРОСЫ К МОДЕЛЯМ
# ============================================================================

async def make_g4f_request(provider_name: str, model: str, prompt: str,
                           timeout: float = 45.0, system_prompt: str = None, proxy_url: str = None) -> Tuple[bool, str, float]:
    start = time.time()
    messages = []
    if system_prompt: messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    providers_to_try = [provider_name] if provider_name else [None]
    fallback_providers = ["PollinationsAI", "MyShell", "Perplexity"]
    
    for prov_name in providers_to_try + fallback_providers:
        try:
            provider_arg = getattr(g4f.Provider, prov_name, None) if prov_name else None
            
            def sync_call():
                return g4f.ChatCompletion.create(
                    model=model,
                    messages=messages,
                    provider=provider_arg,
                    timeout=int(timeout)
                )

            response = await asyncio.wait_for(
                asyncio.to_thread(sync_call),
                timeout=timeout + 5
            )
            
            if response:
                answer = str(response).strip()
                if "The model does not exist" in answer or "api.airforce" in answer or "Add a" in answer:
                    raise Exception(f"Provider Error: {answer[:50]}")
                
                if answer:
                    elapsed = time.time() - start
                    logger.debug(f"✅ G4F {prov_name}/{model} — {elapsed:.2f}s")
                    return True, answer, elapsed
            
            raise Exception("Пустой ответ")

        except Exception as e:
            err_str = str(e).lower()
            if "api_key" in err_str or "key" in err_str or "unauthorized" in err_str:
                logger.debug(f"⚠️ G4F {prov_name} требует ключ, пробуем следующий...")
                continue
            if "timeout" in err_str:
                return False, f"Таймаут {timeout}с", time.time() - start
            
            if prov_name == fallback_providers[-1]:
                return False, f"G4F Error: {str(e)[:80]}", time.time() - start

    return False, "Все провайдеры G4F недоступны", time.time() - start

async def test_openrouter_single(models: list, prompt: str, timeout: float = 45.0, system_prompt: str = None, proxy_url: str = None):
    openrouter_token = os.getenv('OPENR_TOKEN')
    if not openrouter_token: return False, "No Token", 0.0
    
    if isinstance(models, str): models = [models]
    
    start = time.time()
    messages = []
    if system_prompt: messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=openrouter_token)
    
    for model in models:
        try:
            def sync_call():
                return client.chat.completions.create(
                    model=model, 
                    messages=messages, 
                    timeout=int(timeout),
                    extra_headers={"HTTP-Referer": "https://github.com/psiiinka-bot", "X-OpenRouter-Title": "PsIInka Bot"}
                )

            response = await asyncio.wait_for(
                asyncio.to_thread(sync_call),
                timeout=timeout + 5
            )
            
            if response.choices and len(response.choices) > 0:
                answer = response.choices[0].message.content
                if answer and answer.strip():
                    elapsed = time.time() - start
                    logger.debug(f"✅ OpenRouter/{model} — {elapsed:.2f}s")
                    return True, answer.strip(), elapsed
            
            raise Exception("Пустой ответ")

        except Exception as e:
            err_str = str(e).lower()
            if "400" in err_str or "invalid model" in err_str:
                logger.debug(f"⚠️ OR/{model} не подошла, пробуем следующую...")
                continue
            if "timeout" in err_str:
                return False, f"Таймаут {timeout}с", time.time() - start
            
            if model == models[-1]:
                return False, f"OR Error: {str(e)[:80]}", time.time() - start

    return False, "Все модели OpenRouter недоступны", time.time() - start

async def test_groq_single(models: list, prompt: str, timeout: float = 45.0, system_prompt: str = None):
    groq_token = os.getenv('GROQ_TOKEN')
    if not groq_token: return False, "No GROQ Token", 0.0
    
    if isinstance(models, str): models = [models]
    
    client = Groq(api_key=groq_token)
    start = time.time()
    messages = []
    if system_prompt: messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    for model in models:
        try:
            def sync_call():
                return client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.5,
                    max_tokens=256,
                    timeout=int(timeout)
                )
            
            response = await asyncio.wait_for(
                asyncio.to_thread(sync_call),
                timeout=timeout + 5
            )
            
            if response.choices and len(response.choices) > 0:
                elapsed = time.time() - start
                content = response.choices[0].message.content
                if len(content) > 150: content = content[:147] + "..."
                logger.debug(f"✅ Groq/{model} — {elapsed:.2f}s")
                return True, f"{model}: {content}", elapsed
            
        except Exception as e:
            err_str = str(e).lower()
            if "timeout" in err_str:
                return False, f"Таймаут {timeout}с", time.time() - start
            logger.debug(f"⚠️ Groq/{model} ошибка: {str(e)[:50]}")
            continue
            
    elapsed = time.time() - start
    return False, "Все модели Groq недоступны", elapsed

async def heartbeat_keeper():
    while True:
        await asyncio.sleep(60)
        logger.debug("💓 Heartbeat OK")

# ============================================================================
# 🎲 ДВИЖОК КУБИКОВ
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
        self.rerolled = False
        self.successes: int = 0
        self.failures: int = 0
        self.botches: int = 0

class DiceParser:
    def __init__(self):
        self.aliases = {
            "dndstats": "6 4d6 k3", 
            "attack": "1d20", 
            "+d20": "2d20 d1", 
            "-d20": "2d20 kl1",
            "stat": "4d6 k3",
            "save": "1d20 + 5"
        }
    
    def parse(self, command_str: str) -> List[DiceResult]:
        results = []
        if not command_str or not command_str.strip():
            return results
        
        command_str = command_str.strip()
        parts = command_str.split()
        
        if parts and parts[0].lower() in self.aliases:
            command_str = self.aliases[parts[0].lower()] + " " + " ".join(parts[1:])
        
        sets = command_str.split(';')
        
        for s in sets[:4]:
            s = s.strip()
            if not s:
                continue
            
            result = self._parse_single_roll(s)
            if result:
                results.append(result)
        
        return results
    
    def _parse_single_roll(self, roll_str: str) -> Optional[DiceResult]:
        res = DiceResult()
        original_str = roll_str
        
        if '!' in roll_str:
            parts = roll_str.split('!', 1)
            roll_str = parts[0].strip()
            res.comment = parts[1].strip()
        
        flags = []
        flag_pattern = r'\b([a-z]{1,2})\b'
        potential_flags = re.findall(flag_pattern, roll_str.lower())
        for flag in potential_flags:
            if flag in ['s', 'nr', 'p', 'ul', 'e', 'ie', 'k', 'kl', 'd', 'dl', 'r', 'ir', 't', 'f', 'b']:
                flags.append(flag)
        
        clean_str = roll_str
        for flag in flags:
            clean_str = re.sub(r'\b' + flag + r'\b', '', clean_str, flags=re.IGNORECASE)
        
        num_sets = 1
        set_match = re.match(r'^(\d+)\s+(.+)$', clean_str.strip())
        if set_match:
            num_sets = min(int(set_match.group(1)), 20)
            clean_str = set_match.group(2)
        
        dice_match = re.search(r'(\d*)d(\d+)', clean_str, re.IGNORECASE)
        if not dice_match:
            num_match = re.match(r'^(\d+)$', clean_str.strip())
            if num_match:
                res.total = float(num_match.group(1))
                res.details = f"Статическое значение: {res.total}"
                return res
            return None
        
        num_dice = int(dice_match.group(1) or 1)
        num_sides = int(dice_match.group(2))
        
        if num_sides > 100: num_sides = 100
        if num_dice > 100: num_dice = 100
        
        rolls = [random.randint(1, num_sides) for _ in range(num_dice)]
        res.dice_rolls = rolls.copy()
        
        if 'e' in flags or 'ie' in flags:
            explode_val = num_sides
            infinite = 'ie' in flags
            
            explode_match = re.search(r'(i?e)(\d+)', roll_str, re.IGNORECASE)
            if explode_match:
                infinite = explode_match.group(1).lower() == 'ie'
                explode_val = int(explode_match.group(2))
            
            rolls_to_process = list(enumerate(rolls))
            exploded_count = 0
            max_explodes = 100 if infinite else len(rolls)
            
            while rolls_to_process and exploded_count < max_explodes:
                new_rolls_to_process = []
                for idx, val in rolls_to_process:
                    if val >= explode_val:
                        new_roll = random.randint(1, num_sides)
                        res.dice_rolls.append(new_roll)
                        res.exploded_rolls.append(new_roll)
                        exploded_count += 1
                        if infinite and new_roll >= explode_val and exploded_count < max_explodes:
                            new_rolls_to_process.append((len(res.dice_rolls)-1, new_roll))
                rolls_to_process = new_rolls_to_process
            
            res.details.append(f"💥 Взрывы: +{len(res.exploded_rolls)}")
        
        if any(f in flags for f in ['k', 'kl', 'd', 'dl']):
            keep_val = None
            for flag in ['k', 'kl', 'd', 'dl']:
                match = re.search(flag + r'(\d+)', roll_str, re.IGNORECASE)
                if match:
                    keep_val = int(match.group(1))
                    break
            
            if keep_val is not None and keep_val < len(res.dice_rolls):
                sorted_rolls = sorted(res.dice_rolls, reverse=True)
                if 'k' in flags or 'kl' in flags:
                    if 'kl' in flags:
                        sorted_rolls = sorted(res.dice_rolls)
                    res.kept_dice = sorted_rolls[:keep_val]
                    res.dice_rolls = res.kept_dice
                    res.details.append(f"📌 Оставлено {keep_val}")
                elif 'd' in flags or 'dl' in flags:
                    if 'dl' in flags:
                        sorted_rolls = sorted(res.dice_rolls)
                    res.dropped_dice = sorted_rolls[:keep_val]
                    res.kept_dice = sorted_rolls[keep_val:]
                    res.dice_rolls = res.kept_dice
                    res.details.append(f"🗑 Сброшено {keep_val}")
        
        modifier_match = re.search(r'([+\-*/])\s*(\d+(?:\.\d+)?)$', clean_str)
        if modifier_match:
            op = modifier_match.group(1)
            val = float(modifier_match.group(2))
            if op == '+': res.total += val
            elif op == '-': res.total -= val
            elif op == '*': res.total *= val
            elif op == '/':
                if val != 0: res.total /= val
            res.details.append(f"{op}{int(val) if val == int(val) else val}")
        
        res.total = sum(res.dice_rolls)
        
        if not res.details:
            res.details = [f"🎲 Бросок: {res.dice_rolls}"]
        else:
            res.details.insert(0, f"🎲 Бросок: {res.dice_rolls}")
        
        return res
    
    def get_help_text(self) -> str:
        return """
🎲 **Команда `/кубик` — Продвинутая система бросков**

**Базовые команды:**
• `XdY` — Бросить X кубиков с Y гранями (пример: `2d6`)
• `XdY + Z` — С модификатором (пример: `1d20 + 5`)
• `N XdY` — N наборов по XdY (пример: `6 4d6`)

**Модификаторы:**
• `eZ` — Взрывающиеся кубики на Z (пример: `3d6 e6`)
• `kZ` — Оставить Z лучших (пример: `4d6 k3`)
• `dZ` — Сбросить Z худших
• `rZ` — Перебросить ≤ Z
• `tZ` — Успехи при ≥ Z

**Алиасы:**
• `dndstats` — 6 наборов 4d6 k3 (статы D&D)
• `attack` — 1d20 (атака)
• `stat` — 4d6 k3 (один стат)

**Ограничения:** макс. 100 граней, 100 кубиков, 20 наборов, 4 броска
"""

dice_engine = DiceParser()

# ============================================================================
# 💬 КОМАНДЫ (СОБАЧИЙ СТИЛЬ)
# ============================================================================

@bot.slash_command(name="скажи", description="Запрос к ИИ")
async def slash_say(interaction: disnake.CommandInteraction, 
                    вопрос: str = commands.Param(min_length=1, description="Ваш вопрос или запрос"), 
                    прокси: str = commands.Param(choices=["Да", "Нет"], default="Нет", description="Использовать прокси")):
    if not await check_access(interaction): return
    try:
        await interaction.response.defer()
        
        # 🐕 СОБАЧИЙ СТИЛЬ: Начало обработки
        status_embed = disnake.Embed(
            title="🐕 ПсИИнка слушает...",
            description="*виляет хвостом* Сейчас прогавкаю ответ, хозяин! ⏳",
            color=0xFF8844,
            timestamp=datetime.now()
        )
        status_embed.add_field(name="📡 Статус", value="ПсИИнка принюхивается к нейросети...", inline=False)
        status_embed.set_footer(text="Может занять до 45 секунд 🐾")
        
        msg = await interaction.edit_original_response(embed=status_embed)
        
        queue = PRIORITY_TIER_1 + PRIORITY_TIER_2
        for groq_model in GROQ_PRIORITY_MODELS[:3]:
            queue.append(("Groq", groq_model))
        queue.append(("OpenRouter", OPENROUTER_PRIORITY))
        queue.append(("g4f-default", "deepseek-r1"))
        
        system_prompt = "Ты помощник по имени Псинка (мальчик). Отвечай кратко на русском и по делу, отвечай развёрнуто в случае нужды в глубинном анализе вопроса или при запросе пользователя."
        final_response = None
        final_prov = "?"
        final_mod = "?"
        use_proxy = (прокси == "Да")
        proxy_url = get_random_proxy(use_proxy)
        
        for idx, (prov, mod) in enumerate(queue):
            try:
                # 🐕 СОБАЧИЙ СТИЛЬ: Процесс перебора
                status_embed.description = f"*рычит на нейросети* Попытка {idx + 1}/{len(queue)}: `{prov}` / `{mod}`"
                status_embed.set_field_at(0, name="📡 Статус", value=f"ПсИИнка лает на **{prov}**... 🐕", inline=False)
                await msg.edit(embed=status_embed)
                
                if prov == "OpenRouter":
                    ok, ans, lat = await test_openrouter_single([mod], вопрос, timeout=45.0, system_prompt=system_prompt, proxy_url=proxy_url)
                elif prov == "Groq":
                    ok, ans, lat = await test_groq_single([mod], вопрос, timeout=45.0, system_prompt=system_prompt)
                else:
                    ok, ans, lat = await make_g4f_request(prov, mod, вопрос, timeout=45.0, system_prompt=system_prompt, proxy_url=proxy_url)
                
                if ok and ans:
                    final_response = ans
                    final_prov, final_mod = prov, mod
                    db_manager.log_success(prov, mod, int(lat * 1000))
                    break
            except Exception as e:
                logger.warning(f"Error {prov}/{mod}: {e}")
                continue

        if not final_response:
            # 🐕 СОБАЧИЙ СТИЛЬ: Ошибка
            error_embed = disnake.Embed(
                title="❌ ПсИИнка устал...",
                description="*повесил уши* Ни одна нейросеть не ответила, хозяин... 🐕",
                color=0xFF4444,
                timestamp=datetime.now()
            )
            error_embed.add_field(name="💡 Что делать?", value="• Проверь интернет 🌐\n• Попробуй позже, я отдохну 💤\n• Включи прокси 🔀", inline=False)
            await msg.edit(embed=error_embed)
            return
        
        # 🐕 СОБАЧИЙ СТИЛЬ: Успешный ответ
        response_embed = disnake.Embed(
            title="🐕 ПсИИнка прогавкал ответ!",
            description=f"*виляет хвостом* Держи, хозяин:\n\n{final_response[:4000]}",
            color=0x00FF88,
            timestamp=datetime.now()
        )
        response_embed.add_field(name="📊 Источник", value=f"**Прогавкал через:** `{final_prov}`\n**Модель:** `{final_mod}`\n**Время:** `{lat:.2f}с`", inline=True)
        response_embed.add_field(name="🔧 Информация", value=f"Длина ответа: `{len(final_response)} симв.`\nПрокси: `{прокси}`", inline=True)
        response_embed.set_footer(text="ПсИИнка бот | AI Assistant 🐾")
        
        await msg.edit(embed=response_embed)
        
    except Exception as e:
        logger.error(f"Critical error in /say: {e}", exc_info=True)
        err_msg = f"❌ Гав! Ошибка: {str(e)[:100]}"
        if interaction.response.is_done():
            await interaction.followup.send(err_msg, ephemeral=True)
        else:
            await interaction.response.send_message(err_msg, ephemeral=True)

@bot.slash_command(name="кубик", description="Бросок кубиков")
async def slash_cube(interaction: disnake.CommandInteraction, 
                     формула: str = commands.Param(description="Формула броска (например: 2d6+5 или dndstats)", required=False)):
    try:
        if not формула:
            help_embed = disnake.Embed(
                title="🎲 ПсИИнка: Справка по кубикам",
                description=dice_engine.get_help_text(),
                color=0xFF8844,
                timestamp=datetime.now()
            )
            help_embed.set_footer(text="ПсИИнка бот | Dice Roller 🐾")
            await interaction.response.send_message(embed=help_embed)
            return
        
        await interaction.response.defer()
        results = dice_engine.parse(формула)
        
        if not results:
            raise ValueError("Не удалось разобрать формулу. Используйте `/кубик` для справки.")
        
        # 🐕 СОБАЧИЙ СТИЛЬ: Результат броска
        output_embed = disnake.Embed(
            title="🎲 ПсИИнка бросил кубики!",
            description=f"*подбрасывает лапой* Формула: `{формула}` 🐾",
            color=0x00AAFF,
            timestamp=datetime.now()
        )
        
        total_all = 0
        for i, r in enumerate(results):
            total_display = int(r.total) if r.total == int(r.total) else round(r.total, 2)
            total_all += r.total
            
            field_value = f"🎲 Выпало: `[{', '.join(map(str, r.dice_rolls))}]`\n"
            field_value += f"📊 **Сумма: {total_display}** *гав!*"
            
            if r.comment:
                field_value += f"\n💬 _{r.comment}_"
            
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
                field_value += "\n" + " | ".join(details_extra)
            
            output_embed.add_field(name=f"Бросок #{i+1}", value=field_value, inline=False)
        
        if len(results) > 1:
            output_embed.add_field(name="📈 Общая сумма", value=f"**{total_all}** *тяв!*", inline=False)
        
        output_embed.set_footer(text="ПсИИнка бот | Dice Roller 🐾")
        await interaction.followup.send(embed=output_embed)
        
    except Exception as e:
        logger.error(f"Error in /cube: {e}", exc_info=True)
        # 🐕 СОБАЧИЙ СТИЛЬ: Ошибка броска
        error_embed = disnake.Embed(
            title="❌ ПсИИнка не понял...",
            description=f"*склонил голову набок* Не могу разобрать: `{формула}` 🐕",
            color=0xFF4444,
            timestamp=datetime.now()
        )
        error_embed.add_field(name="💡 Помощь", value="*Гавкни* `/кубик` без параметров — я покажу справку!", inline=False)
        await interaction.followup.send(embed=error_embed, ephemeral=True)

@bot.slash_command(name="погавкай", description="Проверка пинга бота")
async def slash_bark(interaction: disnake.CommandInteraction):
    try:
        ping_ms = round(bot.latency * 1000)
        status = "🟢" if ping_ms < 100 else "🟡" if ping_ms < 300 else "🔴"
        
        # 🐕 СОБАЧИЙ СТИЛЬ: Пинг (как в старом коде, но мягче)
        embed = disnake.Embed(
            title="🐕 Гав! ПсИИнка на связи!",
            description=f"{status} **Пинг:** `{ping_ms} мс` *тяв!*",
            color=0x00FF88 if ping_ms < 100 else 0xFFAA00 if ping_ms < 300 else 0xFF4444,
            timestamp=datetime.now()
        )
        embed.add_field(name="📊 Статус", value="Бот работает нормально *виляет хвостом*", inline=False)
        embed.set_footer(text="ПсИИнка бот | Health Check 🐾")
        
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        logger.error(f"Error in /bark: {e}", exc_info=True)
        await interaction.response.send_message(f"❌ Гав! Ошибка: {str(e)[:100]}", ephemeral=True)

@bot.slash_command(name="статус", description="Статистика использования моделей")
async def slash_status(interaction: disnake.CommandInteraction):
    try:
        if not await check_access(interaction): return
        await interaction.response.defer()
        
        top = db_manager.get_top_models(10)
        
        # 🐕 СОБАЧИЙ СТИЛЬ: Статус системы
        embed = disnake.Embed(
            title="📊 ПсИИнка отчитывается",
            description="*виляет хвостом* Вот моя статистика, хозяин! 🐕",
            color=0x00FF88,
            timestamp=datetime.now()
        )
        
        if top:
            stats_text = ""
            for i, (p, m, lat) in enumerate(top, 1):
                medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i-1] if i <= 5 else f"{i}."
                stats_text += f"{medal} `{p}` / `{m}` — `{lat}мс`\n"
            
            embed.add_field(name="🏆 Топ-10 моделей", value=stats_text, inline=False)
        else:
            embed.add_field(name="📭 Данные", value="Нет записей. *Гавкни* `/скажи` для начала сбора статистики!", inline=False)
        
        embed.add_field(name="🔧 Режим", value="Экономия ресурсов (No Warmup)\nБД: " + ("✅ Подключена *гав!*" if db_manager.has_data() else "⚠️ Отключена *скулит*"), inline=False)
        embed.set_footer(text="ПсИИнка бот | Statistics 🐾")
        
        await interaction.edit_original_response(embed=embed)
        
    except Exception as e:
        logger.error(f"Error in /status: {e}", exc_info=True)
        await interaction.followup.send(f"❌ Гав! Ошибка: {str(e)[:100]}", ephemeral=True)

# ============================================================================
# 🧪 ТЕСТИРОВАНИЕ (СОБАЧИЙ СТИЛЬ)
# ============================================================================

class TestModeView(disnake.ui.View):
    def __init__(self, ctx=None):
        super().__init__(timeout=None)
    
    @disnake.ui.button(label="⚡ Экспресс G4F", style=disnake.ButtonStyle.green, custom_id="test_express")
    async def express_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        log_analysis("TEST: Express G4F started", "INFO")
        start = time.time()
        ok, ans, lat = await make_g4f_request("PollinationsAI", "deepseek-r1", "ping", timeout=15.0)
        elapsed = time.time() - start
        
        status = "✅ Успех *гав!*" if ok else f"❌ Ошибка: {ans} *скулит*"
        color = 0x00FF88 if ok else 0xFF4444
        
        embed = disnake.Embed(
            title="🧪 ПсИИнка тестит G4F",
            description=f"*рычит* {status}",
            color=color,
            timestamp=datetime.now()
        )
        embed.add_field(name="⏱ Время", value=f"{elapsed:.2f}с", inline=True)
        embed.add_field(name="📡 Провайдер", value="PollinationsAI", inline=True)
        embed.add_field(name="🤖 Модель", value="deepseek-r1", inline=True)
        if ok:
            embed.add_field(name="💬 Ответ", value=f"```{ans[:100]}```", inline=False)
        
        log_analysis(f"TEST Result: {status}, Time: {elapsed:.2f}s", "INFO")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @disnake.ui.button(label="🦅 Groq Cloud", style=disnake.ButtonStyle.blurple, custom_id="test_groq")
    async def groq_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        log_analysis("TEST: Groq started", "INFO")
        start = time.time()
        ok, ans, lat = await test_groq_single(GROQ_PRIORITY_MODELS, "ping", timeout=15.0, system_prompt="Ты тестовый ИИ.")
        elapsed = time.time() - start
        
        status = "✅ Успех *гав!*" if ok else f"❌ Ошибка: {ans} *скулит*"
        color = 0x00FF88 if ok else 0xFF4444
        
        embed = disnake.Embed(
            title="🦅 ПсИИнка тестит Groq",
            description=f"*рычит* {status}",
            color=color,
            timestamp=datetime.now()
        )
        embed.add_field(name="⏱ Время", value=f"{elapsed:.2f}с", inline=True)
        embed.add_field(name="📡 Провайдер", value="Groq", inline=True)
        if ok:
            embed.add_field(name="💬 Ответ", value=f"```{ans[:100]}```", inline=False)
            embed.add_field(name="🏆 Модель", value=f"`{ans.split(':')[0]}`", inline=True)
        
        log_analysis(f"TEST Groq Result: {status}, Time: {elapsed:.2f}s", "INFO")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @disnake.ui.button(label="🌐 OpenRouter", style=disnake.ButtonStyle.gray, custom_id="test_openrouter")
    async def openrouter_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        log_analysis("TEST: OpenRouter started", "INFO")
        start = time.time()
        ok, ans, lat = await test_openrouter_single(OR_PRIORITY_MODELS, "ping", timeout=15.0, system_prompt="Ты тестовый ИИ.")
        elapsed = time.time() - start
        
        status = "✅ Успех *гав!*" if ok else f"❌ Ошибка: {ans} *скулит*"
        color = 0x00FF88 if ok else 0xFF4444
        
        embed = disnake.Embed(
            title="🌐 ПсИИнка тестит OpenRouter",
            description=f"*рычит* {status}",
            color=color,
            timestamp=datetime.now()
        )
        embed.add_field(name="⏱ Время", value=f"{elapsed:.2f}с", inline=True)
        embed.add_field(name="📡 Провайдер", value="OpenRouter", inline=True)
        if ok:
            embed.add_field(name="💬 Ответ", value=f"```{ans[:100]}```", inline=False)
        
        log_analysis(f"TEST OR Result: {status}, Time: {elapsed:.2f}s", "INFO")
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @disnake.ui.button(label="🔍 Полное сканирование", style=disnake.ButtonStyle.red, custom_id="test_full")
    async def all_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        await interaction.followup.send("🔄 ПсИИнка начинает полное сканирование... *нюхает* (это займёт время) 🐕", ephemeral=True)
        asyncio.create_task(run_mass_test(interaction.channel))

@bot.slash_command(name="тест", description="Тестирование провайдеров и моделей")
async def slash_test(interaction: disnake.CommandInteraction):
    try:
        if not await check_access(interaction): return
        
        # 🐕 СОБАЧИЙ СТИЛЬ: Меню теста
        embed = disnake.Embed(
            title="🛠 ПсИИнка: Проверка нейросетей",
            description="""**Выбери, что потестим, хозяин:** 🐕\n\n*виляет хвостом и ждёт команду*

⚡ **Экспресс G4F** — Быстрый тест (~5 сек)
🦅 **Groq Cloud** — Тест каскада Groq (~10 сек)
🌐 **OpenRouter** — Тест моделей OR (~15 сек)
🔍 **Полное сканирование** — Массовый тест (~2-5 мин)

ℹ️ Все тесты используют каскадный перебор для надёжности.
""",
            color=0xFF8844,
            timestamp=datetime.now()
        )
        embed.add_field(name="📊 Что тестируется", value="• Скорость ответа ⚡\n• Стабильность соединения 🌐\n• Работоспособность моделей 🤖", inline=False)
        embed.set_footer(text="ПсИИнка бот | Diagnostics 🐾")
        
        view = TestModeView()
        await interaction.response.send_message(embed=embed, view=view)
        
    except Exception as e:
        logger.error(f"Error in /test: {e}", exc_info=True)
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Гав! Ошибка: {str(e)[:100]}", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Гав! Ошибка: {str(e)[:100]}", ephemeral=True)

# ============================================================================
# 📊 МАССОВОЕ ТЕСТИРОВАНИЕ (СОБАЧИЙ СТИЛЬ)
# ============================================================================

async def run_mass_test(channel):
    """Запускает полное сканирование комбинаций"""
    progress_embed = disnake.Embed(
        title="🔄 ПсИИнка сканирует...",
        description="*нюхает* G4F + Groq + OpenRouter... 🐕",
        color=0xFF8844,
        timestamp=datetime.now()
    )
    progress_embed.add_field(name="Прогресс", value="`[░░░░░░░░░░] 0%`", inline=False)
    progress_msg = await channel.send(embed=progress_embed)
    
    start_time = time.time()
    
    providers_to_test = ["PollinationsAI", "Vercel", "FreeGPT"]
    models_to_test = ["deepseek-r1", "llama-3-70b", "qwen-2.5-72b"]
    combinations = [(p, m) for p in providers_to_test for m in models_to_test]
    combinations += [("Groq", m) for m in GROQ_PRIORITY_MODELS[:3]]
    combinations += [("OpenRouter", m) for m in OR_PRIORITY_MODELS[:3]]
    
    results = []
    total = len(combinations)
    
    semaphore = asyncio.Semaphore(5)

    async def test_combo(provider, model):
        async with semaphore:
            start = time.time()
            try:
                if provider == "OpenRouter":
                    ok, ans, lat = await test_openrouter_single([model], TEST_PROMPT, timeout=30.0)
                elif provider == "Groq":
                    ok, ans, lat = await test_groq_single([model], TEST_PROMPT, timeout=30.0)
                else:
                    ok, ans, lat = await make_g4f_request(provider, model, TEST_PROMPT, timeout=30.0)
                
                return {'provider': provider, 'model': model, 'success': ok, 'time': lat, 'error': ans if not ok else None}
            except Exception as e:
                return {'provider': provider, 'model': model, 'success': False, 'time': 0, 'error': str(e)[:50]}

    tasks = [test_combo(p, m) for p, m in combinations]
    
    for i, task in enumerate(asyncio.as_completed(tasks)):
        res = await task
        results.append(res)
        elapsed = time.time() - start_time
        percent = int(((i + 1) / total) * 100)
        bar = create_progress_bar(i + 1, total)
        
        try:
            progress_embed.description = f"*лает на* {i + 1}/{total}: `{res['provider']}` / `{res['model']}` 🐕"
            progress_embed.set_field_at(0, name="Прогресс", value=f"`[{bar}] {percent}%`\n⏳ Прошло: {elapsed:.0f}с", inline=False)
            
            success_count = len([r for r in results if r['success']])
            progress_embed.add_field(name="📊 Статистика", value=f"✅ Успешно: {success_count} *гав!*\n❌ Ошибок: {len(results) - success_count} *скулит*", inline=False)
            
            await progress_msg.edit(embed=progress_embed)
        except: pass

    elapsed_total = time.time() - start_time
    successful = [r for r in results if r['success']]
    
    final_embed = disnake.Embed(
        title="✅ ПсИИнка закончил тест!",
        description=f"*виляет хвостом* Общее время: `{elapsed_total:.0f}с` ({elapsed_total / 60:.1f} мин) 🐕",
        color=0x00FF88,
        timestamp=datetime.now()
    )
    final_embed.add_field(name="📊 Результаты", value=f"✅ Успешно: `{len(successful)}/{total}` *гав!*\n📈 Процент: `{int(len(successful) / total * 100)}%`", inline=False)
    
    if successful:
        successful.sort(key=lambda x: x['time'] if x['time'] else 999)
        top_text = ""
        for r in successful[:5]:
            top_text += f"• `{r['provider']}`/{r['model']} — `{r['time']:.2f}с`\n"
        final_embed.add_field(name="🏆 Топ-5 быстрых", value=top_text, inline=False)
    
    await progress_msg.edit(embed=final_embed)
    
    for r in successful[:5]:
        db_manager.log_success(r['provider'], r['model'], int(r['time'] * 1000))

# ============================================================================
# 🔍 АНАЛИЗ КАНАЛА (СОБАЧИЙ СТИЛЬ)
# ============================================================================

async def collect_all_messages_debug(channel, days_limit: int, max_per_source: int = 400):
    after_date = datetime.now(timezone.utc) - timedelta(days=days_limit)
    all_messages = []
    log_analysis(f"Start collecting #{channel.name} for {days_limit} days.", "INFO")
    
    try:
        async for message in channel.history(limit=max_per_source, after=after_date):
            if message.is_system() or message.author == bot.user or not message.content.strip(): 
                continue
            all_messages.append({
                "id": len(all_messages) + 1, 
                "real_id": message.id,
                "content": message.content[:1500], 
                "author": str(message.author),
                "url": message.jump_url, 
                "source": f"#{channel.name}", 
                "created_at": message.created_at
            })
        log_analysis(f"✅ Main channel: {len(all_messages)} msgs.", "INFO")
    except Exception as e:
        log_analysis(f"❌ Main channel error: {e}", "ERROR")

    if hasattr(channel, 'threads'):
        for thread in channel.threads:
            if not hasattr(thread, 'history'): 
                continue
            try:
                count = 0
                async for message in thread.history(limit=max_per_source, after=after_date):
                    if message.is_system() or message.author == bot.user or not message.content.strip(): 
                        continue
                    all_messages.append({
                        "id": len(all_messages) + 1, 
                        "real_id": message.id,
                        "content": message.content[:1500], 
                        "author": str(message.author),
                        "url": message.jump_url, 
                        "source": f"Thread: {thread.name}", 
                        "created_at": message.created_at
                    })
                    count += 1
                log_analysis(f"✅ Thread {thread.name}: {count} msgs.", "INFO")
                await asyncio.sleep(0.5)
            except: 
                pass
    
    return all_messages


def format_messages_for_ai(messages_list: List[Dict]) -> str:
    return "\n".join([
        f"{msg['id']} [{msg['source']}]: {msg['content'].replace(chr(10), ' ')}" 
        for msg in messages_list
    ])


def parse_ai_response(ai_text: str, original_data: List[Dict]) -> List[Dict]:
    if not ai_text or ai_text.strip().upper() == "NONE": 
        return []
    
    found_ids = []
    for part in re.split(r'[,\s\n]+', ai_text):
        try: 
            found_ids.append(int(part))
        except: 
            pass
    
    return [msg for msg in original_data if msg['id'] in found_ids]


@bot.slash_command(name="анализ", description="Анализ канала на нарушения")
async def slash_analyze(interaction: disnake.CommandInteraction, 
                        канал: disnake.TextChannel = commands.Param(description="Канал для анализа"), 
                        период: str = commands.Param(choices=["За последние 7 дней", "За последние 21 день"], 
                                                      description="Период анализа")):
    if interaction.author.id != OWNER_ID:
        if not await check_access(interaction, allowed_role_names=["Псарь"]):
            return

    days_to_check = 7 if "7 дней" in период else 21
    await interaction.response.defer()
    
    log_analysis(f"=== START ANALYSIS: {канал.name} ({days_to_check} days) ===", "INFO")
    
    try:
        messages_data = await collect_all_messages_debug(канал, days_to_check, max_per_source=400)
        if not messages_data:
            await interaction.edit_original_response(content="ℹ️ ПсИИнка не нашёл сообщений. *нюхает*")
            return

        BATCH_SIZE = 35
        total_batches = (len(messages_data) + BATCH_SIZE - 1) // BATCH_SIZE
        
        # 🐕 СОБАЧИЙ СТИЛЬ: Прогресс анализа
        progress_embed = disnake.Embed(
            title="🔍 ПсИИнка нюхает канал",
            description=f"*принюхивается* Канал: `#{канал.name}`\nПериод: `{days_to_check} дней` 🐕\nСообщений: `{len(messages_data)}`",
            color=0xFF8844,
            timestamp=datetime.now()
        )
        progress_embed.add_field(name="Прогресс", value="`[░░░░░░░░░░] 0%`", inline=False)
        progress_embed.add_field(name="Статус", value="ПсИИнка готовится...", inline=False)
        
        status_msg = await interaction.edit_original_response(embed=progress_embed)
        
        all_violations = []
        
        main_queue = PRIORITY_TIER_1 + PRIORITY_TIER_2
        groq_queue = [("Groq", m) for m in GROQ_PRIORITY_MODELS[:3]]
        or_fallback = [OPENROUTER_PRIORITY, "meta-llama/llama-3.3-70b-instruct:free"]
        proxy_queue = main_queue + groq_queue + [("OpenRouter", m) for m in or_fallback]

        for i in range(0, len(messages_data), BATCH_SIZE):
            batch_data = messages_data[i : i + BATCH_SIZE]
            current_batch = (i // BATCH_SIZE) + 1
            batch_context = format_messages_for_ai(batch_data)
            user_prompt = f"Пакет {current_batch}/{total_batches}:\n\n{batch_context}"
            
            final_answer = None
            success = False
            used_provider = "Unknown"

            async def try_request(prov, mod, use_proxy=False):
                proxy_str = get_random_proxy(True) if use_proxy else None
                if prov == "OpenRouter":
                    return await test_openrouter_single(mod, user_prompt, timeout=50.0, system_prompt=ANALYSIS_SYSTEM_PROMPT)
                elif prov == "Groq":
                    return await test_groq_single(mod, user_prompt, timeout=50.0, system_prompt=ANALYSIS_SYSTEM_PROMPT)
                else:
                    return await make_g4f_request(prov, mod, user_prompt, timeout=50.0, system_prompt=ANALYSIS_SYSTEM_PROMPT, proxy_url=proxy_str)

            for prov, mod in main_queue:
                try:
                    percent = int(((current_batch - 1) / total_batches) * 100)
                    bar = create_progress_bar(current_batch - 1, total_batches)
                    
                    progress_embed.set_field_at(0, name="Прогресс", value=f"`[{bar}] {percent}%`", inline=False)
                    progress_embed.set_field_at(1, name="Статус", value=f"*лает на* `{prov}`... 🐕", inline=False)
                    await status_msg.edit(embed=progress_embed)

                    ok, ans, _ = await try_request(prov, mod, False)
                    if ok:
                        final_answer = ans
                        used_provider = f"{prov} ({mod})"
                        success = True
                        break
                except Exception as e:
                    log_analysis(f"Error {prov}/{mod}: {e}", "DEBUG")
                    continue

            if not success:
                for groq_model in GROQ_PRIORITY_MODELS[:3]:
                    try:
                        ok, ans, _ = await try_request("Groq", groq_model, False)
                        if ok:
                            final_answer = ans
                            used_provider = f"Groq ({groq_model})"
                            success = True
                            break
                    except: 
                        continue

            if not success:
                for or_model in or_fallback:
                    try:
                        ok, ans, _ = await try_request("OpenRouter", or_model, False)
                        if ok:
                            final_answer = ans
                            used_provider = f"OpenRouter ({or_model})"
                            success = True
                            break
                    except: 
                        continue

            if not success:
                log_analysis(f"⚠️ Batch {current_batch}: Activating PROXY MODE.", "WARNING")
                progress_embed.set_field_at(1, name="Статус", value="⚠️ ПРОКСИ РЕЖИМ... *нюхает* 🔀", inline=False)
                await status_msg.edit(embed=progress_embed)
                
                for prov, mod in proxy_queue:
                    try:
                        ok, ans, _ = await try_request(prov, mod, True)
                        if ok:
                            final_answer = ans
                            used_provider = f"{prov} ({mod}) [PROXY]"
                            success = True
                            break
                    except: 
                        continue

            if not success:
                final_answer = "NONE"
                used_provider = "NO_RESPONSE"
                log_analysis(f"❌ Batch {current_batch}: FAILED.", "ERROR")

            batch_violations = parse_ai_response(final_answer, batch_data)
            all_violations.extend(batch_violations)
            log_analysis(f"Batch {current_batch}: {used_provider}. Found: {len(batch_violations)}", "INFO")

            percent = int((current_batch / total_batches) * 100)
            bar = create_progress_bar(current_batch, total_batches)
            progress_embed.set_field_at(0, name="Прогресс", value=f"`[{bar}] {percent}%`", inline=False)
            progress_embed.set_field_at(1, name="Статус", value=f"✅ Пакет #{current_batch} готов *гав!*", inline=False)
            progress_embed.add_field(name="Найдено нарушений", value=f"`{len(all_violations)}` *рычит*", inline=False)
            await status_msg.edit(embed=progress_embed)
            await asyncio.sleep(1.0)

        progress_embed.color = 0x00FF88
        progress_embed.set_field_at(1, name="Статус", value="✅ Анализ завершен! *виляет хвостом* 🐕", inline=False)
        await status_msg.edit(embed=progress_embed)
        
        if not all_violations:
            await status_msg.edit(content="✅ ПсИИнка проверил — всё чисто! *виляет хвостом* 🐕", embed=None)
            log_analysis("Analysis finished: No violations.", "INFO")
            return

        report_parts = []
        current_part = []
        current_len = 0
        
        for i, v in enumerate(all_violations, 1):
            clean_txt = re.sub(r'<@!?[0-9]+>', '@user', v['content'])[:400]
            line = f"{i}) **[{v['source']}]** {clean_txt}\n🔗 [Ссылка]({v['url']})\n\n"
            
            if current_len + len(line) > 1800:
                report_parts.append("".join(current_part))
                current_part = [line]
                current_len = len(line)
            else:
                current_part.append(line)
                current_len += len(line)
        
        if current_part: 
            report_parts.append("".join(current_part))

        # 🐕 СОБАЧИЙ СТИЛЬ: Отчёт по анализу
        header_embed = disnake.Embed(
            title="🚨 ПсИИнка нашёл нарушения!",
            description=f"*рычит на нарушителей* Найдено **{len(all_violations)}** нарушений 🐕",
            color=0xFF4444,
            timestamp=datetime.now()
        )
        header_embed.add_field(name="Канал", value=f"#{канал.name}", inline=True)
        header_embed.add_field(name="Период", value=f"{days_to_check} дней", inline=True)
        header_embed.add_field(name="Сообщений проверено", value=f"`{len(messages_data)}`", inline=True)
        
        await status_msg.edit(content=report_parts[0][:1800], embed=header_embed)
        
        for part in report_parts[1:]:
            await interaction.channel.send(part)
        
        await interaction.channel.send("✅ ПсИИнка закончил! *виляет хвостом* 🐕")
        log_analysis(f"Analysis finished: {len(all_violations)} violations reported.", "INFO")

    except Exception as e:
        error_trace = traceback.format_exc()
        log_analysis(f"CRITICAL ERROR: {e}\n{error_trace}", "ERROR")
        logger.error(f"Critical error in /analyze: {e}", exc_info=True)
        await interaction.followup.send(f"❌ ПсИИнка ошибся... *повесил уши*\nЛог сохранен.\nОшибка: {str(e)[:100]} 🐕", ephemeral=True)

# ============================================================================
# 💾 АДМИН КОМАНДЫ: СКАЧАТЬ ФАЙЛЫ
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
        await interaction.followup.send("❌ Гав! Файл не найден. *нюхает*", ephemeral=True)

@bot.slash_command(name="скачать_ошибки", description="Скачать общий лог ошибок бота")
async def slash_download_logs(interaction: disnake.CommandInteraction):
    if interaction.author.id != OWNER_ID:
        await interaction.response.send_message("❌ Гав! Доступ запрещён.", ephemeral=True)
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
        await interaction.followup.send("❌ Гав! Файл логов пуст или не найден. *скулит*", ephemeral=True)

@bot.slash_command(name="скачать_бд", description="Скачать таблицу успехов из БД (CSV)")
async def slash_download_db(interaction: disnake.CommandInteraction):
    if interaction.author.id != OWNER_ID:
        await interaction.response.send_message("❌ Гав! Доступ запрещён.", ephemeral=True)
        return
    
    await interaction.response.defer()
    csv_data = db_manager.export_to_csv()
    
    if csv_data:
        file_obj = io.BytesIO(csv_data.encode('utf-8'))
        file_obj.name = "model_success_log.csv"
        await interaction.followup.send(file=disnake.File(file_obj))
    else:
        await interaction.followup.send("❌ Гав! Не удалось экспортировать данные или БД не подключена. *скулит*", ephemeral=True)

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
            msg = f"⚠️ Гав! Ошибка команды: {str(error)[:100]}"
            if hasattr(ctx, 'response') and ctx.response.is_done():
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.send(msg, delete_after=10)
        except: pass

if __name__ == "__main__":
    logger.info("🚀 Start PsIInka Bot v2.0-Full-Integrated")
    try:
        bot.run(os.getenv("DISCORD_TOKEN"))
    except Exception as e:
        logger.critical(f"💥 Startup crash: {e}", exc_info=True)
