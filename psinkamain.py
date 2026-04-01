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
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import asyncio
from typing import Tuple, List, Dict, Any, Optional
from disnake.ext import commands
from openai import OpenAI
import aiohttp
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
        logging.warning("⚠️ DATABASE_URL не найден.")
        return None, None
    try:
        engine = create_engine(DATABASE_URL, echo=False, future=True, pool_pre_ping=True)
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        logging.info("✅ База данных подключена.")
        return engine, SessionLocal
    except Exception as e:
        logging.error(f"❌ Ошибка БД: {e}")
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
                record = ModelSuccessLog(provider=provider, model_name=model, success_count=1, last_success_at=datetime.now(timezone.utc), avg_latency_ms=latency_ms)
                session.add(record)
            session.commit()
            self._cleanup_old_records(session)
        except Exception as e:
            session.rollback()
        finally:
            session.close()

    def _cleanup_old_records(self, session):
        count = session.query(ModelSuccessLog).count()
        if count > 200:
            old_ids = session.query(ModelSuccessLog.id).order_by(ModelSuccessLog.last_success_at.asc()).limit(count - 200).all()
            if old_ids:
                session.query(ModelSuccessLog).filter(ModelSuccessLog.id.in_([x[0] for x in old_ids])).delete(synchronize_session=False)
                session.commit()

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

intents = disnake.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

PRIORITY_TIER_1 = [("PollinationsAI", "deepseek-r1"), ("PollinationsAI", "deepseek-v3")]
PRIORITY_TIER_2 = [("FreeGPT", "deepseek-r1"), ("Vercel", "deepseek-r1")]
EXCLUDED_OR_MODELS = ["liquid/lfm-2.5-1.2b-instruct:free"]
OPENROUTER_PRIORITY = "nvidia/nemotron-3-super-120b-a12b:free"

ANALYSIS_SYSTEM_PROMPT = """
Ты — модератор RP сервера. Найди ТОЛЬКО явный оффтоп.
ИГНОРИРУЙ: описания действий (**текст**), диалоги, ролевые пинги.
ФИКСИРУЙ: флуд, OOC обсуждения, попрошайничество, спам пингами.
ФОРМАТ: Верни только ID сообщений через запятую (например: 5, 12) или NONE. Без пояснений.
"""

FREE_PROXY_LIST = [
    "http://103.152.112.162:80", "http://185.217.136.234:8080",
    "http://47.88.29.109:8080", "http://103.167.135.110:80", "http://185.162.230.55:80",
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
                        logger.info(f" Обновлён список прокси: {len(proxies)} шт.")
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
    await interaction.response.send_message(f"❌ Нет роли ({', '.join(allowed_role_names)}).", ephemeral=True)
    return False

# ============================================================================
#  ЗАПРОСЫ К МОДЕЛЯМ
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

async def heartbeat_keeper():
    while True:
        await asyncio.sleep(15)
        logger.debug("💓 Heartbeat OK")

async def run_passive_warmup(ctx, duration_seconds: int = 30):
    logger.info(" Warmup start...")
    start_time = time.time()
    candidates = PRIORITY_TIER_1 + PRIORITY_TIER_2
    idx = 0
    while (time.time() - start_time) < duration_seconds and idx < len(candidates):
        prov, mod = candidates[idx]
        try:
            success, _, _ = await make_g4f_request(prov, mod, "ok", timeout=10.0, system_prompt="Reply ok.")
            if success: db_manager.log_success(prov, mod, 100)
        except: pass
        idx += 1
        await asyncio.sleep(0.5)

# ============================================================================
# 🎲 ДВИЖОК КУБИКОВ (ВОЗВРАЩЕН КЛАСС DiceResult)
# ============================================================================

class DiceResult:
    def __init__(self):
        self.total = 0.0
        self.dice_rolls: List[int] = []
        self.details: List[str] = []
        self.successes = 0
        self.failures = 0
        self.botches = 0
        self.is_private = False
        self.comment = ""
        self.simplified = False
        self.no_results = False
        self.unsorted = False
        self.set_results: List[float] = []

class DiceParser:
    def __init__(self):
        self.aliases = {"dndstats": "6 4d6 k3", "attack": "1d20", "+d20": "2d20 d1", "-d20": "2d20 kl1"}
    
    def parse(self, command_str: str) -> List[DiceResult]:
        results = []
        if not command_str.strip(): return results
        parts = command_str.split()
        if parts and parts[0].lower() in self.aliases:
            command_str = self.aliases[parts[0].lower()] + " " + " ".join(parts[1:])
        
        sets = command_str.split(';')
        for s in sets[:4]:
            res = DiceResult()
            match = re.search(r'(\d*)d(\d+)', s)
            if match:
                n = int(match.group(1) or 1)
                y = int(match.group(2))
                rolls = [random.randint(1, y) for _ in range(n)]
                res.dice_rolls = rolls
                res.total = sum(rolls)
                res.details = f"Бросок: {rolls}"
                results.append(res)
        return results

dice_engine = DiceParser()

# ============================================================================
# 💬 КОМАНДЫ
# ============================================================================

@bot.slash_command(name="скажи", description="Запрос к ИИ")
async def slash_say(interaction: disnake.CommandInteraction, вопрос: str = commands.Param(min_length=1), прокси: str = commands.Param(choices=["Да", "Нет"], default="Нет")):
    if not await check_access(interaction): return
    try:
        await interaction.response.defer()
        msg = await interaction.edit_original_response(content=" Обработка...")
        
        queue = PRIORITY_TIER_1 + PRIORITY_TIER_2
        queue.append(("OpenRouter", OPENROUTER_PRIORITY))
        queue.append(("g4f-default", "deepseek-r1"))
        queue.append(("g4f-default", "deepseek-v3"))
        
        system_prompt = "Ты Псинка. Отвечай кратко на русском."
        final_response = None
        final_prov = "?"
        final_mod = "?"
        
        for prov, mod in queue:
            try:
                if prov == "OpenRouter":
                    ok, ans, _ = await test_openrouter_single(mod, вопрос, timeout=45.0, system_prompt=system_prompt)
                else:
                    ok, ans, _ = await make_g4f_request(prov, mod, вопрос, timeout=45.0, system_prompt=system_prompt)
                
                if ok and ans:
                    final_response = ans
                    final_prov, final_mod = prov, mod
                    db_manager.log_success(prov, mod, 0)
                    break
            except Exception as e:
                logger.warning(f"Error {prov}/{mod}: {e}")

        if not final_response:
            await msg.edit(content="❌ Не удалось получить ответ.")
            return
        
        await msg.edit(content=f"🐕 Ответ ({final_prov}/{final_mod}):\n{final_response[:1900]}")
    except Exception as e:
        logger.error(f"Critical error in /say: {e}", exc_info=True)
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Ошибка: {str(e)[:100]}", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Ошибка: {str(e)[:100]}", ephemeral=True)

@bot.slash_command(name="кубик", description="Бросок кубиков")
async def slash_cube(interaction: disnake.CommandInteraction, формула: str = None):
    try:
        if not формула:
            await interaction.response.send_message("ℹ️ Использование: `/кубик 2d6+5` или алиасы `dndstats`")
            return
        await interaction.response.defer()
        results = dice_engine.parse(формула)
        if not results: raise ValueError("Не удалось разобрать.")
        txt = "\n".join([f"**{r.total}** `({', '.join(map(str, r.dice_rolls))})`" for r in results])
        await interaction.followup.send(f" Результат:\n{txt}")
    except Exception as e:
        logger.error(f"Error in /cube: {e}", exc_info=True)
        await interaction.followup.send(f"❌ Ошибка: {str(e)[:100]}", ephemeral=True)

@bot.slash_command(name="погавкай", description="Пинг")
async def slash_bark(interaction: disnake.CommandInteraction):
    try:
        await interaction.response.send_message(f' Пинг: {round(bot.latency * 1000)} мс')
    except Exception as e:
        logger.error(f"Error in /bark: {e}", exc_info=True)

@bot.slash_command(name="статус", description="Статистика")
async def slash_status(interaction: disnake.CommandInteraction):
    try:
        if not await check_access(interaction): return
        await interaction.response.defer()
        top = db_manager.get_top_models(3)
        txt = "\n".join([f"{i+1}. `{p}` / `{m}`" for i,(p,m,_) in enumerate(top)]) if top else "Нет данных"
        embed = disnake.Embed(title=" Статус", description=txt, color=0x00FF88)
        await interaction.edit_original_response(embed=embed)
    except Exception as e:
        logger.error(f"Error in /status: {e}", exc_info=True)
        await interaction.followup.send(f"❌ Ошибка: {str(e)[:100]}", ephemeral=True)

# ============================================================================
# 🧪 ТЕСТ (ИСПРАВЛЕНЫ ЭМОДЗИ)
# ============================================================================

class TestModeView(disnake.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=300)
        self.ctx = ctx
    
    @disnake.ui.button(label="⚡ Экспресс", style=disnake.ButtonStyle.green, emoji="", custom_id="test_express")
    async def express_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        await interaction.channel.send("✅ Экспресс тест запущен.")

    @disnake.ui.button(label="⚡ Быстрый", style=disnake.ButtonStyle.green, emoji="⚡", custom_id="test_quick")
    async def quick_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        await interaction.channel.send("✅ Быстрый тест запущен.")

    @disnake.ui.button(label="🌐 OpenRouter", style=disnake.ButtonStyle.blurple, emoji="🔮", custom_id="test_openrouter")
    async def openrouter_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        await interaction.channel.send("✅ OpenRouter тест запущен.")

    @disnake.ui.button(label="🎯 Всё", style=disnake.ButtonStyle.red, emoji="🎲", custom_id="test_all")
    async def all_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        await interaction.channel.send("✅ Полный тест запущен.")

@bot.slash_command(name="тест", description="Тестирование")
async def slash_test(interaction: disnake.CommandInteraction):
    try:
        if not await check_access(interaction): return
        embed = disnake.Embed(title="Выбор режима", description="Нажмите кнопку:", color=0xFF8844)
        view = TestModeView(interaction)
        await interaction.response.send_message(embed=embed, view=view)
    except Exception as e:
        logger.error(f"Error in /test: {e}", exc_info=True)
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Ошибка: {str(e)[:100]}", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Ошибка: {str(e)[:100]}", ephemeral=True)

# ============================================================================
# 🔍 АНАЛИЗ (ПОЛНЫЙ ФУНКЦИОНАЛ + ПРОКСИ ФОЛЛБЕК)
# ============================================================================

ANALYSIS_LOG_FILE = "analysis_debug.log"
analysis_logger = logging.getLogger("analysis_debug")
analysis_logger.setLevel(logging.DEBUG)
if not analysis_logger.handlers:
    fh = logging.FileHandler(ANALYSIS_LOG_FILE, mode='w', encoding='utf-8')
    fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    analysis_logger.addHandler(fh)

def log_analysis(msg: str, level: str = "INFO"):
    getattr(analysis_logger, level.lower())(msg)

async def collect_all_messages_debug(channel, days_limit: int, max_per_source: int = 400):
    after_date = datetime.now(timezone.utc) - timedelta(days=days_limit)
    all_messages = []
    log_analysis(f"Старт сбора #{channel.name} за {days_limit} дней.", "INFO")
    
    # Основной канал
    try:
        async for message in channel.history(limit=max_per_source, after=after_date):
            if message.is_system() or message.author == bot.user or not message.content.strip(): continue
            all_messages.append({
                "id": len(all_messages) + 1, "real_id": message.id,
                "content": message.content[:1500], "author": str(message.author),
                "url": message.jump_url, "source": f"#{channel.name}", "created_at": message.created_at
            })
        log_analysis(f"✅ Основной канал: {len(all_messages)} сообщ.", "INFO")
    except Exception as e:
        log_analysis(f"❌ Ошибка основного канала: {e}", "ERROR")

    # Ветки
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
                log_analysis(f"✅ Ветка {thread.name}: {count} сообщ.", "INFO")
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

@bot.slash_command(name="анализ", description="Анализ канала")
async def slash_analyze(interaction: disnake.CommandInteraction, канал: disnake.TextChannel = commands.Param(), период: str = commands.Param(choices=["За последние 7 дней", "За последние 21 день"])):
    if interaction.author.id != OWNER_ID:
        await interaction.response.send_message("❌ Только владелец.", ephemeral=True)
        return

    days_to_check = 7 if "7 дней" in период else 21
    await interaction.response.defer()
    
    log_analysis(f"Начало анализа {канал.name} ({days_to_check} дн.)", "INFO")
    
    try:
        messages_data = await collect_all_messages_debug(канал, days_to_check, max_per_source=400)
        if not messages_data:
            await interaction.edit_original_response(content="ℹ️ Сообщения не найдены.")
            return

        BATCH_SIZE = 35
        total_batches = (len(messages_data) + BATCH_SIZE - 1) // BATCH_SIZE
        status_msg = await interaction.edit_original_response(content=f"🔄 Анализ: [░░░░░░░░░░] 0% (0/{total_batches})\nПодготовка...")
        
        all_violations = []
        
        # Очереди
        main_queue = PRIORITY_TIER_1 + PRIORITY_TIER_2
        or_fallback = [OPENROUTER_PRIORITY, "meta-llama/llama-3.3-70b-instruct:free", "qwen/qwen-2.5-72b-instruct:free"]
        g4f_fallback = [("g4f-default", "deepseek-r1"), ("g4f-default", "deepseek-v3")]
        
        # Полный список для прокси-фоллбека
        proxy_queue = main_queue + [("OpenRouter", m) for m in or_fallback] + g4f_fallback

        for i in range(0, len(messages_data), BATCH_SIZE):
            batch_data = messages_data[i : i + BATCH_SIZE]
            current_batch = (i // BATCH_SIZE) + 1
            batch_context = format_messages_for_ai(batch_data)
            user_prompt = f"Проанализируй пакет {current_batch}/{total_batches}:\n\n{batch_context}"
            
            final_answer = None
            success = False
            used_provider = "Unknown"
            use_proxy_mode = False

            # Helper for async execution in thread
            def run_async_in_thread(async_func, *args, **kwargs):
                return asyncio.run(async_func(*args, **kwargs))

            # Функция попытки запроса
            async def try_request(prov, mod, use_proxy=False):
                proxy_str = get_random_proxy(True) if use_proxy else None
                if prov == "OpenRouter":
                    return await test_openrouter_single(mod, user_prompt, timeout=50.0, system_prompt=ANALYSIS_SYSTEM_PROMPT)
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
                    log_analysis(f"Ошибка {prov}/{mod}: {e}", "DEBUG")
                    continue

            # 2. OpenRouter резерв
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

            # 3. G4F Default резерв
            if not success:
                for prov, mod in g4f_fallback:
                    try:
                        ok, ans, _ = await asyncio.wait_for(
                            asyncio.to_thread(run_async_in_thread, try_request, prov, mod, False),
                            timeout=55.0
                        )
                        if ok:
                            final_answer = ans
                            used_provider = f"{prov} ({mod})"
                            success = True
                            break
                    except: continue

            # 4. КРАЙНИЙ СЛУЧАЙ: ПРОКСИ РЕЖИМ
            if not success:
                log_analysis(f"️ Пакет {current_batch}: Все обычные методы failed. Активация PROXY MODE.", "WARNING")
                await status_msg.edit(content=f"🔄 Анализ: [{bar}] {percent}% ({current_batch-1}/{total_batches})\n⚠️ ОШИБКИ. ПОДКЛЮЧЕНИЕ ЧЕРЕЗ ПРОКСИ...")
                
                for prov, mod in proxy_queue:
                    try:
                        # Обновляем статус с указанием прокси
                        await status_msg.edit(content=f"🔄 Анализ: [{bar}] {percent}% ({current_batch-1}/{total_batches})\n Прокси: {prov}...")
                        
                        ok, ans, _ = await asyncio.wait_for(
                            asyncio.to_thread(run_async_in_thread, try_request, prov, mod, True), # True = use proxy
                            timeout=60.0 # Чуть больше таймаут для прокси
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
                log_analysis(f"❌ Пакет {current_batch}: Полностью неудачно даже с прокси.", "ERROR")

            batch_violations = parse_ai_response(final_answer, batch_data)
            all_violations.extend(batch_violations)
            log_analysis(f"Пакет {current_batch}: {used_provider}. Найдено: {len(batch_violations)}", "INFO")

            # Финиш пакета
            percent = int((current_batch / total_batches) * 100)
            bar = "█" * int(10 * current_batch // total_batches) + "░" * (10 - int(10 * current_batch // total_batches))
            await status_msg.edit(content=f"🔄 Анализ: [{bar}] {percent}% ({current_batch}/{total_batches})\n✅ Пакет #{current_batch} готов")
            await asyncio.sleep(1.0)

        await status_msg.edit(content=f"✅ Анализ завершен! [{'█'*10}] 100%\nФормирование отчета...")
        
        if not all_violations:
            await status_msg.edit(content="✅ Нарушений не найдено.")
            return

        # Отправка отчета
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

    except Exception as e:
        log_analysis(f"CRITICAL ERROR: {e}", "ERROR")
        import traceback
        log_analysis(traceback.format_exc(), "ERROR")
        logger.error(f"Critical error in /analyze: {e}", exc_info=True)
        await interaction.followup.send(f"❌ Критическая ошибка. Лог сохранен. `/скачать_анализ`\nОшибка: {str(e)[:100]}", ephemeral=True)

# ============================================================================
# 💾 АДМИН КОМАНДЫ: СКАЧАТЬ ФАЙЛЫ
# ============================================================================

@bot.slash_command(name="скачать_анализ", description="Скачать лог анализа")
async def slash_download_analysis_log(interaction: disnake.CommandInteraction):
    if interaction.author.id != OWNER_ID: return
    await interaction.response.defer()
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
    
    # Принудительная запись буфера
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.FileHandler):
            handler.flush()
    
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
    if REQUIRED_ROLE_ID == 0: 
        logger.info("Mode: Role 'Псарь' access.")
    else: 
        logger.info(f"Mode: Role ID {REQUIRED_ROLE_ID} access.")
    
    asyncio.create_task(fetch_free_proxies())
    asyncio.create_task(heartbeat_keeper()) 

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound): return
    
    # Логирование ошибки
    logger.error(f"Command error {ctx.command}: {error}", exc_info=True)
    
    # Запись в файл вручную, если basic_config не сработал мгновенно
    with open('bot_errors.log', 'a', encoding='utf-8') as f:
        f.write(f"\n[{datetime.now()}] ERROR: {type(error).__name__}: {error}\n")
    
    if hasattr(ctx, 'author') and ctx.author.id == OWNER_ID:
        try: 
            msg = f"⚠️ Ошибка команды: {str(error)[:100]}"
            if hasattr(ctx, 'response') and ctx.response.is_done():
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.send(msg, delete_after=10)
        except: pass

if __name__ == "__main__":
    logger.info("🚀 Start PsIInka Bot v0.4.7-FullRestore")
    try:
        bot.run(os.getenv("DISCORD_TOKEN"))
    except Exception as e:
        logger.critical(f"💥 Startup crash: {e}", exc_info=True)
