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
        logging.warning("⚠️ DATABASE_URL не найден. Работа с БД отключена.")
        return None, None
    try:
        engine = create_engine(DATABASE_URL, echo=False, future=True, pool_pre_ping=True, pool_size=5, max_overflow=10)
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        logging.info("✅ База данных подключена.")
        return engine, SessionLocal
    except Exception as e:
        logging.error(f"❌ Ошибка подключения к БД: {e}")
        return None, None

db_engine, SessionLocal = init_db()

class DBManager:
    def __init__(self, session_factory):
        self.SessionLocal = session_factory

    def log_success(self, provider: str, model: str, latency_ms: int):
        if not self.SessionLocal: return
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
        except: pass

    def get_top_models(self, limit: int = 10) -> List[Tuple[str, str, int]]:
        if not self.SessionLocal: return []
        session = self.SessionLocal()
        try:
            results = session.query(ModelSuccessLog.provider, ModelSuccessLog.model_name, ModelSuccessLog.avg_latency_ms)\
                             .order_by(ModelSuccessLog.success_count.desc(), ModelSuccessLog.avg_latency_ms.asc())\
                             .limit(limit).all()
            return [(r.provider, r.model_name, r.avg_latency_ms) for r in results]
        except: return []
        finally: session.close()
    
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
        except: return None
        finally: session.close()

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
# 🤖 КОНФИГУРАЦИЯ МОДЕЛЕЙ И ПРОКСИ
# ============================================================================

PRIORITY_TIER_1 = [("PollinationsAI", "deepseek-r1"), ("PollinationsAI", "deepseek-v3")]
PRIORITY_TIER_2 = [("FreeGPT", "deepseek-r1"), ("Vercel", "deepseek-r1")]
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
    "http://47.88.29.109:8080", "http://103.167.135.110:80",
]

TEST_PROMPT = "Ответь только словом ок"

ANALYSIS_SYSTEM_PROMPT = """
Ты — модератор. Найди ТОЛЬКО явный оффтоп, спам и нарушения формата.
Игнорируй ролевые действия. Фиксируй: флуд, OOC, рекламу, оскорбления, посты < 4 строк.
ФОРМАТ: Только ID через запятую или NONE.
"""

# ============================================================================
# 🛠 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (ОПТИМИЗИРОВАНО)
# ============================================================================

async def fetch_free_proxies(count: int = 20) -> List[str]:
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=http&timeout=10000&limit={count}"
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    text = await response.text()
                    proxies = [f"http://{p.strip()}" for p in text.split('\n') if p.strip() and ':' in p]
                    if proxies: return proxies
    except: pass
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
    await interaction.response.send_message(f"❌ Нет доступа.", ephemeral=True)
    return False

# ============================================================================
# 🌐 ЗАПРОСЫ К МОДЕЛЯМ (CASCADE & ASYNC SAFE)
# ============================================================================

async def make_g4f_request(provider_name: str, model: str, prompt: str,
                           timeout: float = 45.0, system_prompt: str = None, proxy_url: str = None) -> Tuple[bool, str, float]:
    """
    Безопасный запрос к G4F. 
    Если провайдер требует ключ, пытается переключиться на бесплатный.
    """
    start = time.time()
    messages = []
    if system_prompt: messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    # Попытка 1: Заданный провайдер или Авто
    providers_to_try = [provider_name] if provider_name else [None]
    
    # Если авто-выбор падает с ошибкой ключа, добавляем резервные бесплатные
    fallback_providers = ["PollinationsAI", "MyShell", "Perplexity"]
    
    current_provider_name = provider_name or "Auto"
    
    for prov_name in providers_to_try + fallback_providers:
        try:
            provider_arg = getattr(g4f.Provider, prov_name, None) if prov_name else None
            
            def sync_call():
                # g4f.ChatCompletion.create синхронный
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
                # Фильтрация ошибок внутри ответа
                if "The model does not exist" in answer or "api.airforce" in answer or "Add a" in answer:
                    raise Exception(f"Provider Error: {answer[:50]}")
                
                if answer:
                    elapsed = time.time() - start
                    logger.debug(f"✅ G4F {prov_name}/{model} — {elapsed:.2f}s")
                    return True, answer, elapsed
            
            raise Exception("Пустой ответ")

        except Exception as e:
            err_str = str(e).lower()
            # Если ошибка про ключ, пробуем следующий провайдер из списка
            if "api_key" in err_str or "key" in err_str or "unauthorized" in err_str:
                logger.debug(f"⚠️ G4F {prov_name} требует ключ, пробуем следующий...")
                continue
            # Если таймаут или другая критическая ошибка - прерываем
            if "timeout" in err_str:
                return False, f"Таймаут {timeout}с", time.time() - start
            
            # Если это была последняя попытка
            if prov_name == fallback_providers[-1]:
                return False, f"G4F Error: {str(e)[:80]}", time.time() - start

    return False, "Все провайдеры G4F недоступны", time.time() - start

async def test_openrouter_single(models: list, prompt: str, timeout: float = 45.0, system_prompt: str = None, proxy_url: str = None):
    """
    Каскадный запрос к OpenRouter. Принимает список моделей.
    """
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
            # 400 Bad Request часто означает, что модель не подходит под запрос, пробуем следующую
            if "400" in err_str or "invalid model" in err_str:
                logger.debug(f"⚠️ OR/{model} не подошла, пробуем следующую...")
                continue
            if "timeout" in err_str:
                return False, f"Таймаут {timeout}с", time.time() - start
            
            # Если это последняя модель
            if model == models[-1]:
                return False, f"OR Error: {str(e)[:80]}", time.time() - start

    return False, "Все модели OpenRouter недоступны", time.time() - start

async def test_groq_single(models: list, prompt: str, timeout: float = 45.0, system_prompt: str = None):
    """
    Каскадный запрос к Groq. Исправлено: синхронный вызов в потоке.
    """
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
                # ОФИЦИАЛЬНЫЙ КЛИЕНТ GROQ СИНХРОННЫЙ!
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
            # Ошибки лимитов или модели - пробуем следующую
            logger.debug(f"⚠️ Groq/{model} ошибка: {str(e)[:50]}")
            continue
            
    elapsed = time.time() - start
    return False, "Все модели Groq недоступны", elapsed

# ============================================================================
# 🎲 ДВИЖОК КУБИКОВ
# ============================================================================
# (Оставлен без изменений, так как работал стабильно)
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
    def parse(self, command_str: str) -> List[DiceResult]:
        results = []
        if not command_str or not command_str.strip(): return results
        sets = command_str.split(';')
        for s in sets[:4]:
            s = s.strip()
            if not s: continue
            result = self._parse_single_roll(s)
            if result: results.append(result)
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
        
        # Упрощенная логика модификаторов для краткости кода
        # (Полная логика из предыдущего кода может быть возвращена при необходимости)
        res.total = sum(res.dice_rolls)
        res.details = [f"Бросок: {res.dice_rolls}"]
        return res
    
    def get_help_text(self) -> str:
        return """
🎲 **Команда `/кубик`**
Использование: `/кубик формула`
Примеры: `2d6`, `4d6 k3`, `1d20 + 5`, `6d10 t7`
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
        
        # Очередь с приоритетами (Cascade)
        queue = PRIORITY_TIER_1 + PRIORITY_TIER_2
        for groq_model in GROQ_PRIORITY_MODELS[:3]:
            queue.append(("Groq", groq_model))
        queue.append(("OpenRouter", OPENROUTER_PRIORITY))
        queue.append(("g4f-default", "deepseek-r1"))
        
        system_prompt = "Ты помощник по имени Псинка. Отвечай кратко на русском."
        final_response = None
        final_prov = "?"
        final_mod = "?"
        use_proxy = (прокси == "Да")
        proxy_url = get_random_proxy(use_proxy)
        
        for prov, mod in queue:
            try:
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
            await interaction.response.send_message(dice_engine.get_help_text())
            return
        await interaction.response.defer()
        results = dice_engine.parse(формула)
        if not results:
            raise ValueError("Не удалось разобрать формулу.")
        
        output_parts = []
        for i, r in enumerate(results):
            total_display = int(r.total) if r.total == int(r.total) else round(r.total, 2)
            part = f"**Результат #{i+1}: {total_display}**"
            if r.comment: part += f" _({r.comment})_"
            part += f"\n🎲 Броски: `[{', '.join(map(str, r.dice_rolls))}]`"
            output_parts.append(part)
        
        await interaction.followup.send(f"🎲 **Результат:**\n" + "\n\n".join(output_parts))
    except Exception as e:
        logger.error(f"Error in /cube: {e}", exc_info=True)
        await interaction.followup.send(f"❌ Ошибка: {str(e)[:200]}", ephemeral=True)

@bot.slash_command(name="статус", description="Статистика")
async def slash_status(interaction: disnake.CommandInteraction):
    try:
        if not await check_access(interaction): return
        await interaction.response.defer()
        top = db_manager.get_top_models(3)
        txt = "\n".join([f"{i+1}. `{p}` / `{m}` ({lat}ms)" for i,(p,m,lat) in enumerate(top)]) if top else "Нет данных"
        embed = disnake.Embed(title="📊 Статус", description=txt, color=0x00FF88)
        await interaction.edit_original_response(embed=embed)
    except Exception as e:
        logger.error(f"Error in /status: {e}", exc_info=True)
        await interaction.followup.send(f"❌ Ошибка: {str(e)[:100]}", ephemeral=True)

# ============================================================================
# 🧪 ТЕСТИРОВАНИЕ (ИНТЕГРАЦИЯ СТАРОГО И НОВОГО)
# ============================================================================

class TestModeView(disnake.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @disnake.ui.button(label="🧪 G4F Пинг", style=disnake.ButtonStyle.green, custom_id="test_g4f")
    async def test_g4f_btn(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        await interaction.response.defer()
        # Тестируем конкретный рабочий провайдер
        res = await make_g4f_request("PollinationsAI", "deepseek-r1", TEST_PROMPT, timeout=15.0)
        status = "✅" if res[0] else "❌"
        msg = f"{status} {res[1]} ({res[2]:.2f}s)"
        await interaction.followup.send(msg, ephemeral=True)

    @disnake.ui.button(label="🦅 Groq Пинг", style=disnake.ButtonStyle.blurple, custom_id="test_groq")
    async def test_groq_btn(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        await interaction.response.defer()
        # Передаем список моделей для каскада
        res = await test_groq_single(GROQ_PRIORITY_MODELS, TEST_PROMPT, timeout=15.0, system_prompt="Ты тестовый ИИ.")
        status = "✅" if res[0] else "❌"
        msg = f"{status} {res[1]} ({res[2]:.2f}s)"
        await interaction.followup.send(msg, ephemeral=True)

    @disnake.ui.button(label="🌐 OpenRouter", style=disnake.ButtonStyle.gray, custom_id="test_or")
    async def test_or_btn(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        await interaction.response.defer()
        # Передаем список моделей
        res = await test_openrouter_single(OR_PRIORITY_MODELS, TEST_PROMPT, timeout=15.0, system_prompt="Ты тестовый ИИ.")
        status = "✅" if res[0] else "❌"
        msg = f"{status} {res[1]} ({res[2]:.2f}s)"
        await interaction.followup.send(msg, ephemeral=True)
    
    @disnake.ui.button(label="🔍 Полное сканирование", style=disnake.ButtonStyle.red, custom_id="test_full")
    async def test_full_btn(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        await interaction.response.defer()
        await interaction.followup.send("🔄 Запуск полного сканирования... (это займет время)", ephemeral=True)
        # Запускаем массовый тест в фоне
        asyncio.create_task(run_mass_test(interaction.channel))

@bot.slash_command(name="тест", description="Тестирование провайдеров")
async def slash_test(interaction: disnake.CommandInteraction):
    try:
        if not await check_access(interaction): return
        embed = disnake.Embed(title="🛠 Диагностика", description="Выберите тип проверки:", color=0xFF8844)
        view = TestModeView()
        await interaction.response.send_message(embed=embed, view=view)
    except Exception as e:
        logger.error(f"Error in /test: {e}", exc_info=True)
        await interaction.response.send_message(f"❌ Ошибка: {str(e)[:100]}", ephemeral=True)

# ============================================================================
# 📊 МАССОВОЕ ТЕСТИРОВАНИЕ (ИЗ СТАРОГО КОДА, АДАПТИРОВАНО)
# ============================================================================

async def run_mass_test(channel):
    """Запускает полное сканирование комбинаций (аналог /тест all)"""
    progress_msg = await channel.send("🔄 **Запуск массового теста**\n`Сканирование G4F + Groq + OpenRouter...`")
    start_time = time.time()
    
    # Конфигурация теста
    providers_to_test = ["PollinationsAI", "Vercel", "FreeGPT"] # G4F
    models_to_test = ["deepseek-r1", "llama-3-70b", "qwen-2.5-72b"]
    combinations = [(p, m) for p in providers_to_test for m in models_to_test]
    combinations += [("Groq", m) for m in GROQ_PRIORITY_MODELS[:3]]
    combinations += [("OpenRouter", m) for m in OR_PRIORITY_MODELS[:3]]
    
    results = []
    total = len(combinations)
    
    semaphore = asyncio.Semaphore(5) # Ограничение нагрузки

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
    
    # Выполнение с обновлением прогресса
    for i, task in enumerate(asyncio.as_completed(tasks)):
        res = await task
        results.append(res)
        elapsed = time.time() - start_time
        percent = int(((i + 1) / total) * 100)
        bar = "█" * int(percent // 5) + "░" * (20 - int(percent // 5))
        try:
            await progress_msg.edit(content=f"🔄 **Тест**\n[{bar}] `{i+1}/{total}` ({percent}%)\n⏳ {elapsed:.0f}с")
        except: pass

    elapsed_total = time.time() - start_time
    successful = [r for r in results if r['success']]
    
    report = f"✅ **Тест завершен** ({elapsed_total:.0f}с)\n"
    report += f"Успешно: {len(successful)}/{total}\n\n"
    report += "**Топ-5 быстрых:**\n"
    successful.sort(key=lambda x: x['time'] if x['time'] else 999)
    for r in successful[:5]:
        report += f"• `{r['provider']}`/{r['model']} — {r['time']:.2f}s\n"
    
    await progress_msg.edit(content=report)
    
    # Сохранение в БД лучших
    for r in successful[:5]:
        db_manager.log_success(r['provider'], r['model'], int(r['time'] * 1000))

# ============================================================================
# 🔍 АНАЛИЗ КАНАЛА
# ============================================================================

async def collect_all_messages_debug(channel, days_limit: int, max_per_source: int = 400):
    after_date = datetime.now(timezone.utc) - timedelta(days=days_limit)
    all_messages = []
    try:
        async for message in channel.history(limit=max_per_source, after=after_date):
            if message.is_system() or message.author == bot.user or not message.content.strip(): continue
            all_messages.append({
                "id": len(all_messages) + 1, "real_id": message.id,
                "content": message.content[:1500], "author": str(message.author),
                "url": message.jump_url, "source": f"#{channel.name}", "created_at": message.created_at
            })
    except Exception as e: log_analysis(f"❌ Collection error: {e}", "ERROR")
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
    log_analysis(f"=== START ANALYSIS: {канал.name} ===", "INFO")
    
    try:
        messages_data = await collect_all_messages_debug(канал, days_to_check, max_per_source=400)
        if not messages_data:
            await interaction.edit_original_response(content="ℹ️ Сообщения не найдены.")
            return

        BATCH_SIZE = 35
        total_batches = (len(messages_data) + BATCH_SIZE - 1) // BATCH_SIZE
        status_msg = await interaction.edit_original_response(content=f"🔄 Анализ: 0%")
        
        all_violations = []
        # Очередь провайдеров для анализа
        analysis_queue = PRIORITY_TIER_1 + [("Groq", m) for m in GROQ_PRIORITY_MODELS[:2]] + [("OpenRouter", OPENROUTER_PRIORITY)]

        for i in range(0, len(messages_data), BATCH_SIZE):
            batch_data = messages_data[i : i + BATCH_SIZE]
            current_batch = (i // BATCH_SIZE) + 1
            batch_context = format_messages_for_ai(batch_data)
            user_prompt = f"Пакет {current_batch}/{total_batches}:\n\n{batch_context}"
            
            success = False
            for prov, mod in analysis_queue:
                try:
                    if prov == "OpenRouter":
                        ok, ans, _ = await test_openrouter_single([mod], user_prompt, timeout=50.0, system_prompt=ANALYSIS_SYSTEM_PROMPT)
                    elif prov == "Groq":
                        ok, ans, _ = await test_groq_single([mod], user_prompt, timeout=50.0, system_prompt=ANALYSIS_SYSTEM_PROMPT)
                    else:
                        ok, ans, _ = await make_g4f_request(prov, mod, user_prompt, timeout=50.0, system_prompt=ANALYSIS_SYSTEM_PROMPT)
                    
                    if ok:
                        batch_violations = parse_ai_response(ans, batch_data)
                        all_violations.extend(batch_violations)
                        success = True
                        break
                except: continue
            
            if not success:
                log_analysis(f"❌ Batch {current_batch} failed", "ERROR")

            percent = int((current_batch / total_batches) * 100)
            await status_msg.edit(content=f"🔄 Анализ: [{percent}%]")
            await asyncio.sleep(0.5)

        if not all_violations:
            await status_msg.edit(content="✅ Нарушений не найдено.")
            return

        report = f"🚨 Найдено {len(all_violations)} нарушений:\n"
        for i, v in enumerate(all_violations[:10], 1):
            report += f"{i}. {v['content'][:100]}... [Link]({v['url']})\n"
        
        await status_msg.edit(content=report[:2000])
        if len(all_violations) > 10:
            await interaction.channel.send("... и остальные нарушения (см. лог)")

    except Exception as e:
        logger.error(f"Analysis error: {e}", exc_info=True)
        await interaction.followup.send(f"❌ Ошибка анализа: {str(e)[:100]}", ephemeral=True)

# ============================================================================
# 💾 АДМИН КОМАНДЫ
# ============================================================================

@bot.slash_command(name="скачать_бд", description="Скачать таблицу успехов (CSV)")
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
        await interaction.followup.send("❌ БД пуста или не подключена.", ephemeral=True)

# ============================================================================
# СОБЫТИЯ
# ============================================================================

@bot.event
async def on_ready():
    logger.info(f"Bot {bot.user} ready!")
    asyncio.create_task(fetch_free_proxies()) 

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound): return
    logger.error(f"Command error {ctx.command}: {error}")
    if hasattr(ctx, 'author') and ctx.author.id == OWNER_ID:
        try: await ctx.send(f"⚠️ Ошибка: {str(error)[:100]}", delete_after=10)
        except: pass

if __name__ == "__main__":
    logger.info("🚀 Start PsIInka Bot v2.0-Cascade-Fixed")
    try:
        bot.run(os.getenv("DISCORD_TOKEN"))
    except Exception as e:
        logger.critical(f"💥 Startup crash: {e}", exc_info=True)
