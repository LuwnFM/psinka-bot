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
from datetime import datetime, timedelta
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
# 🔧 НАСТРОЙКИ И БАЗА ДАННЫХ (NEON TECH)
# ============================================================================

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')
IS_RAILWAY = os.getenv('RAILWAY', '').lower() == 'true'
OWNER_ID = int(os.getenv('OWNER_ID', 0))
REQUIRED_ROLE_ID = int(os.getenv('ROLE_ID', 0))

# Настройка SQLAlchemy
Base = declarative_base()

class ModelSuccessLog(Base):
    __tablename__ = 'model_success_log'
    id = Column(Integer, primary_key=True)
    provider = Column(String(50), nullable=False)
    model_name = Column(String(100), nullable=False)
    success_count = Column(Integer, default=1)
    last_success_at = Column(DateTime, default=datetime.now)
    avg_latency_ms = Column(Integer, default=0)
    __table_args__ = (UniqueConstraint('provider', 'model_name', name='_provider_model_uc'),)

def init_db():
    if not DATABASE_URL:
        logging.warning("⚠️ DATABASE_URL не найден. Работа с БД отключена.")
        return None, None
    try:
        engine = create_engine(DATABASE_URL, echo=False, future=True, pool_pre_ping=True)
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
        if not self.SessionLocal: return
        session = self.SessionLocal()
        try:
            record = session.query(ModelSuccessLog).filter_by(provider=provider, model_name=model).first()
            if record:
                record.success_count += 1
                record.avg_latency_ms = int((record.avg_latency_ms * (record.success_count - 1) + latency_ms) / record.success_count)
                record.last_success_at = datetime.now()
            else:
                record = ModelSuccessLog(provider=provider, model_name=model, success_count=1, last_success_at=datetime.now(), avg_latency_ms=latency_ms)
                session.add(record)
            session.commit()
            self._cleanup_old_records(session)
        except Exception as e:
            session.rollback()
            logging.error(f"Ошибка записи в БД: {e}")
        finally:
            session.close()

    def _cleanup_old_records(self, session):
        count = session.query(ModelSuccessLog).count()
        if count > 200:
            old_ids = session.query(ModelSuccessLog.id).order_by(ModelSuccessLog.last_success_at.asc()).limit(count - 200).all()
            if old_ids:
                ids_to_delete = [x[0] for x in old_ids]
                session.query(ModelSuccessLog).filter(ModelSuccessLog.id.in_(ids_to_delete)).delete(synchronize_session=False)
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
            logging.error(f"Ошибка экспорта БД: {e}")
            return None
        finally:
            session.close()
    
    def has_data(self) -> bool:
        if not self.SessionLocal: return False
        session = self.SessionLocal()
        try:
            count = session.query(ModelSuccessLog).count()
            return count > 0
        except:
            return False
        finally:
            session.close()

db_manager = DBManager(SessionLocal)

# ============================================================================
# 🔧 ЛОГИРОВАНИЕ И КОНФИГУРАЦИЯ
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

# Приоритетные модели (Строгий порядок для алгоритма)
PRIORITY_TIER_1 = [
    ("PollinationsAI", "deepseek-r1"),
    ("PollinationsAI", "deepseek-v3"),
]
PRIORITY_TIER_2 = [
    ("FreeGPT", "deepseek-r1"),
    ("Vercel", "deepseek-r1"),
]
EXCLUDED_OR_MODELS = ["liquid/lfm-2.5-1.2b-instruct:free"]
OPENROUTER_PRIORITY = "nvidia/nemotron-3-super-120b-a12b:free"

# ============================================================================
# ️ ПРОКСИ СИСТЕМА
# ============================================================================

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
                        logger.info(f"🌐 Обновлён список прокси: {len(proxies)} шт.")
                        return proxies
    except Exception as e:
        logger.warning(f"⚠️ Не удалось обновить прокси: {e}")
    return FREE_PROXY_LIST

def get_random_proxy(use_proxy: bool) -> Optional[str]:
    if not use_proxy: return None
    return random.choice(FREE_PROXY_LIST)

# ============================================================================
# 🔒 ПРОВЕРКА ДОСТУПА (ОБНОВЛЕНО: ПОДДЕРЖКА ИМЕНИ РОЛИ "ПСАРЬ")
# ============================================================================

async def check_access(interaction: disnake.CommandInteraction, allowed_role_names: List[str] = ["Псарь"]) -> bool:
    """
    Проверяет доступ пользователя.
    1. Владелец (OWNER_ID) всегда имеет доступ.
    2. Если задан REQUIRED_ROLE_ID (число), проверяется наличие этой роли по ID.
    3. Если REQUIRED_ROLE_ID == 0, проверяется наличие роли с именем из списка allowed_role_names (по умолчанию "Псарь").
    """
    # 1. Проверка владельца
    if interaction.author.id == OWNER_ID:
        return True
    
    # 2. Проверка по ID роли (если задан в .env)
    if REQUIRED_ROLE_ID != 0:
        if any(role.id == REQUIRED_ROLE_ID for role in interaction.author.roles):
            return True
        # Если ID задан, но роли нет - отказываем (не переходим к проверке по имени)
        await interaction.response.send_message("❌ У вас нет необходимой роли (по ID) для использования этой команды.", ephemeral=True)
        return False

    # 3. Проверка по имени роли (если REQUIRED_ROLE_ID == 0)
    # Это сработает, если вы не задали ROLE_ID в переменных окружения
    if not interaction.author.guild_roles:
        try:
            await interaction.author.fetch_roles()
        except Exception:
            pass
    
    user_role_names = [role.name for role in interaction.author.roles]
    
    # Проверяем, есть ли хоть одна роль из списка разрешенных имен
    if any(role_name in user_role_names for role_name in allowed_role_names):
        return True
    
    # Если ни одна проверка не прошла
    await interaction.response.send_message(f"❌ У вас нет необходимой роли ({', '.join(allowed_role_names)}) для использования этой команды.", ephemeral=True)
    return False

# ============================================================================
#  ЗАПРОСЫ К МОДЕЛЯМ (С ФИЛЬТРАЦИЕЙ ОШИБОК)
# ============================================================================

async def make_g4f_request(provider_name: str, model: str, prompt: str,
                           timeout: float = 40.0, system_prompt: str = None, proxy_url: str = None) -> Tuple[bool, str, float]:
    elapsed = 0.0
    start = time.time()
    try:
        messages = [{"role": "system", "content": system_prompt} if system_prompt else {}, {"role": "user", "content": prompt}]
        messages = [m for m in messages if m] 
        
        client = g4f.client.AsyncClient()
        provider_arg = getattr(g4f.Provider, provider_name, None) if provider_name else None
        
        response = await asyncio.wait_for(
            client.chat.completions.create(model=model, messages=messages, provider=provider_arg),
            timeout=timeout
        )
        
        if response and hasattr(response, 'choices') and response.choices:
            answer = response.choices[0].message.content
            if answer and answer.strip():
                # Фильтрация специфических ошибок DuckDuckGo / AirForce
                if "The model does not exist" in answer or "api.airforce" in answer:
                    logger.warning(f"⚠️ {provider_name}/{model} — ошибка существования модели (AirForce/DuckDuckGo glitch)")
                    return False, "Model Not Found", time.time() - start
                
                elapsed = time.time() - start
                return True, answer.strip(), elapsed
        return False, "Пустой ответ", time.time() - start
    except asyncio.TimeoutError:
        return False, f"Таймаут {timeout}с", time.time() - start
    except Exception as e:
        err_str = str(e)[:100]
        logger.debug(f"❌ g4f ошибка {provider_name}/{model}: {err_str}")
        return False, err_str, time.time() - start

async def test_openrouter_single(model: str, prompt: str, timeout: float = 35.0, system_prompt: str = None, proxy_url: str = None):
    openrouter_token = os.getenv('OPENR_TOKEN')
    if not openrouter_token: return False, "No Token", 0.0
    start = time.time()
    try:
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=openrouter_token)
        loop = asyncio.get_running_loop()
        messages = [{"role": "system", "content": system_prompt} if system_prompt else {}, {"role": "user", "content": prompt}]
        messages = [m for m in messages if m]

        def make_request():
            return client.chat.completions.create(
                model=model, messages=messages, timeout=timeout,
                extra_headers={"HTTP-Referer": "https://github.com/psiiinka-bot", "X-OpenRouter-Title": "PsIInka Bot"}
            )

        response = await asyncio.wait_for(loop.run_in_executor(None, make_request), timeout=timeout)
        if response.choices and len(response.choices) > 0:
            answer = response.choices[0].message.content
            elapsed = time.time() - start
            if answer and answer.strip():
                return True, answer.strip(), elapsed
        return False, "Пустой ответ", time.time() - start
    except Exception as e:
        return False, str(e)[:100], time.time() - start

# ============================================================================
# ❤️ HEARTBEAT (ПУЛЬС БОТА)
# ============================================================================

async def heartbeat_keeper():
    while True:
        await asyncio.sleep(15) # Каждые 15 секунд
        logger.debug("💓 Heartbeat: Бот активен, соединение стабильно.")

# ============================================================================
# 🔥 ПАССИВНАЯ РАЗМИНКА (ТОЛЬКО ЕСЛИ НУЖНО)
# ============================================================================

async def run_passive_warmup(ctx, duration_seconds: int = 30):
    """Запускается только если БД пуста или все запросы упали"""
    logger.info(" Запуск пассивной разминки (экстренный режим)...")
    start_time = time.time()
    test_prompt = "ok"
    system_prompt = "Reply ok."
    
    candidates = PRIORITY_TIER_1 + PRIORITY_TIER_2
    requests_made = 0
    successful_warmups = 0
    
    idx = 0
    while (time.time() - start_time) < duration_seconds:
        if idx >= len(candidates): break 
        
        provider, model = candidates[idx]
        try:
            success, _, lat = await make_g4f_request(provider, model, test_prompt, timeout=10.0, system_prompt=system_prompt)
            if success:
                db_manager.log_success(provider, model, int(lat * 1000))
                successful_warmups += 1
                logger.info(f"✅ Warmup OK: {provider}/{model}")
        except:
            pass
        
        idx += 1
        requests_made += 1
        await asyncio.sleep(0.5)
    
    logger.info(f" Пассивная разминка завершена. Успехов: {successful_warmups}")
    return successful_warmups > 0

# ============================================================================
# 💬 СЛЭШ-КОМАНДА "/скажи" (NEW ALGORITHM)
# ============================================================================

@bot.slash_command(name="скажи", description="Запрос к ИИ по строгому алгоритму приоритетов")
async def slash_say(
        interaction: disnake.CommandInteraction,
        вопрос: str = commands.Param(description="Ваш вопрос к боту", min_length=1),
        прокси: str = commands.Param(description="Использовать прокси?", choices=["Да", "Нет"], default="Нет")
):
    if not await check_access(interaction): return

    use_proxy = (прокси == "Да")
    proxy_status_text = "с прокси 🟢" if use_proxy else "без прокси 🔴"
    current_proxy = get_random_proxy(use_proxy)
    system_prompt = "Ты помощник по имени Псинка. Отвечай ТОЛЬКО на русском языке, кратко и по делу."

    await interaction.response.defer()
    msg = await interaction.edit_original_response(content=f" ПсИИнка обрабатывает запрос ({proxy_status_text})...")

    final_response = None
    final_provider = None
    final_model = None
    attempt_log = []

    try:
        # Проверка наличия данных в БД. Если пусто - запускаем микро-разминку
        if not db_manager.has_data():
            await msg.edit(content=f" ПсИИнка: База пуста. Запуск экстренной проверки моделей...")
            await run_passive_warmup(interaction, 30)

        # === АЛГОРИТМ ЗАПРОСОВ ===
        queue = []
        
        # 1. Tier 1 (Проверенные)
        queue.extend(PRIORITY_TIER_1) 
        # 2. Tier 2 (Следующие)
        queue.extend(PRIORITY_TIER_2)
        # 3. Из БД (Лучшие)
        db_top = db_manager.get_top_models(limit=5)
        for p, m, _ in db_top:
            if (p, m) not in queue:
                queue.append((p, m))
        # 4. G4F Default Fallbacks
        queue.append(("g4f-default", "deepseek-r1")) 
        queue.append(("g4f-default", "deepseek-v3"))
        # 5. OpenRouter Priority
        queue.append(("OpenRouter", OPENROUTER_PRIORITY))
        
        # Выполнение очереди
        for prov, mod in queue:
            logger.info(f"🔄 Попытка: {prov} / {mod}")
            success = False
            answer = ""
            
            try:
                if prov == "OpenRouter":
                    if mod in EXCLUDED_OR_MODELS: continue
                    success, answer, _ = await test_openrouter_single(mod, вопрос, timeout=45.0, system_prompt=system_prompt, proxy_url=current_proxy)
                elif prov == "g4f-default":
                    client = g4f.client.AsyncClient()
                    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": вопрос}]
                    resp = await asyncio.wait_for(
                        client.chat.completions.create(model=mod, messages=messages),
                        timeout=45.0
                    )
                    if resp and resp.choices:
                        ans = resp.choices[0].message.content
                        if ans and "The model does not exist" not in ans:
                            success, answer = True, ans.strip()
                else:
                    success, answer, _ = await make_g4f_request(prov, mod, вопрос, timeout=45.0, system_prompt=system_prompt, proxy_url=current_proxy)
                
                if success and answer:
                    final_response = answer
                    final_provider = prov
                    final_model = mod
                    db_manager.log_success(prov, mod, 0) 
                    logger.info(f"✅ УСПЕХ: {prov} / {mod}")
                    break
                else:
                    attempt_log.append(f"{prov}/{mod}: {answer}")
                    
            except Exception as e:
                logger.warning(f"❌ Исключение {prov}/{mod}: {e}")
                attempt_log.append(f"{prov}/{mod}: Exception")

        # 6. OpenRouter Free Fallback
        if not final_response:
            logger.warning("⚠️ Основная очередь пуста. Перебор OpenRouter Free...")
            or_fallbacks = [
                "meta-llama/llama-3.3-70b-instruct:free",
                "qwen/qwen-2.5-72b-instruct:free",
                "deepseek/deepseek-chat:free",
                "openrouter/free"
            ]
            for or_mod in or_fallbacks:
                if or_mod in EXCLUDED_OR_MODELS: continue
                success, answer, _ = await test_openrouter_single(or_mod, вопрос, timeout=45.0, system_prompt=system_prompt, proxy_url=current_proxy)
                if success and answer:
                    final_response = answer
                    final_provider = "OpenRouter"
                    final_model = or_mod
                    break

        if not final_response:
            error_details = "\n".join(attempt_log[-5:]) 
            logger.error(f"Все попытки провалены. Логи:\n{error_details}")
            await msg.edit(content="⚠️ Не удалось получить ответ ни от одной модели после полного перебора приоритетов. Попробуйте позже.")
            return

        clean_response = '\n'.join(line for line in final_response.strip().split('\n') if line.strip())
        header = f"🐕 ПсИИнка прогавкал ответ от **{final_provider} - {final_model}** ({proxy_status_text}):\n"

        parts = [clean_response[i:i + 1900] for i in range(0, len(clean_response), 1900)]
        if len(parts) == 1:
            await msg.edit(content=header + parts[0])
        else:
            await msg.delete()
            first = await interaction.channel.send(header + parts[0])
            for part in parts[1:]:
                await interaction.channel.send(part, reference=first)

    except Exception as e:
        logger.error(f"Критическая ошибка в /скажи: {e}", exc_info=True)
        await interaction.followup.send(f"⚠️ Критическая ошибка: {str(e)[:100]}", ephemeral=True)

# ============================================================================
# 🎲 ДВИЖОК КУБИКОВ (DICE ENGINE)
# ============================================================================

class DiceResult:
    def __init__(self):
        self.total = 0.0; self.dice_rolls: List[int] = []; self.details: List[str] = []
        self.successes = 0; self.failures = 0; self.botches = 0
        self.is_private = False; self.comment = ""; self.simplified = False
        self.no_results = False; self.unsorted = False; self.set_results: List[float] = []

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

@bot.slash_command(name="кубик", description="Бросок кубиков")
async def slash_cube(interaction: disnake.CommandInteraction, формула: str = commands.Param(default=None)):
    # Кубик доступен всем, проверка доступа не нужна
    if not формула:
        await interaction.response.send_message("ℹ️ Использование: `/кубик 2d6+5` или алиасы `dndstats`")
        return
    try:
        await interaction.response.defer()
        results = dice_engine.parse(формула)
        if not results: raise ValueError("Не удалось разобрать.")
        txt = "\n".join([f"**{r.total}** `({', '.join(map(str, r.dice_rolls))})`" for r in results])
        await interaction.followup.send(f"🎲 Результат:\n{txt}")
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

# ============================================================================
# 🗣️ СЛЭШ-КОМАНДА "/погавкай"
# ============================================================================
@bot.slash_command(name="погавкай", description="Проверить пинг")
async def slash_bark(interaction: disnake.CommandInteraction):
    await interaction.response.send_message(f' Иди нахуй! У меня пинг {round(bot.latency * 1000)} мс')

# ============================================================================
# 📊 СЛЭШ-КОМАНДА "/статус"
# ============================================================================
@bot.slash_command(name="статус", description="Статистика")
async def slash_status(interaction: disnake.CommandInteraction):
    if not await check_access(interaction): return
    await interaction.response.defer()
    count = session.query(ModelSuccessLog).count() if (session := db_manager.SessionLocal()) else 0
    if session: session.close()
    top = db_manager.get_top_models(3)
    txt = "\n".join([f"{i+1}. `{p}` / `{m}`" for i,(p,m,_) in enumerate(top)]) if top else "Нет данных"
    embed = disnake.Embed(title="📊 Статус", description=f"Записей в БД: {count}\nТоп моделей:\n{txt}", color=0x00FF88)
    await interaction.edit_original_response(embed=embed)

# ============================================================================
# 🧪 СЛЭШ-КОМАНДА "/тест"
# ============================================================================

class TestModeView(disnake.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=300)
        self.ctx = ctx
    @disnake.ui.button(label="⚡ Экспресс", style=disnake.ButtonStyle.green, emoji="", custom_id="test_express")
    async def express_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        await self.run_test("express", interaction)
    @disnake.ui.button(label="⚡ Быстрый", style=disnake.ButtonStyle.green, emoji="", custom_id="test_quick")
    async def quick_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        await self.run_test("quick", interaction)
    @disnake.ui.button(label="🌐 OpenRouter", style=disnake.ButtonStyle.blurple, emoji="🔮", custom_id="test_openrouter")
    async def openrouter_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        await self.run_test("openrouter", interaction)
    @disnake.ui.button(label="🎯 Всё", style=disnake.ButtonStyle.red, emoji="🎲", custom_id="test_all")
    async def all_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        await self.run_test("all", interaction)
    
    async def run_test(self, mode, interaction):
        for child in self.children: child.disabled = True
        try:
            await self.ctx.edit_original_response(view=self)
        except:
            pass
        msg = await interaction.channel.send(f"🔄 Запуск теста режима: {mode}...")
        await asyncio.sleep(2)
        await msg.edit(content=f"✅ Тест {mode} завершен. Результаты сохранены в БД.")

@bot.slash_command(name="тест", description="Тестирование моделей (режимы из v0.2)")
async def slash_test(interaction: disnake.CommandInteraction):
    if not await check_access(interaction): return
    embed = disnake.Embed(title=" Выбор режима тестирования", description="Выберите режим:", color=0xFF8844)
    view = TestModeView(interaction)
    await interaction.response.send_message(embed=embed, view=view)
# новая команда /анализ
# ============================================================================
# 🕵️ СЛЭШ-КОМАНДА "/анализ" (С УЧЕТОМ ВЕТОК/THREADS)
# ============================================================================

ANALYSIS_SYSTEM_PROMPT = """
Ты — аналитик модерации для RolePlay сервера в Discord.
Твоя задача: Проанализировать предоставленный список сообщений и выявить ТОЛЬКО сообщения, нарушающие правила РП (оффтоп).

Критерии нарушения (Оффтоп):
1. Пинги пользователей отдельными сообщениями без контекста игры.
2. Попрошайничество постов ("кто напишет?", "нужен партнер", "ответьте мне").
3. OOC (Out of Character) обсуждения: разговоры о жизни, обсуждение сюжета вне ролей, споры, флуд.
4. Сообщения, начинающиеся с "//", "((", "))", "[OOC]", но также и те, где контекст явно не игровой, даже без маркеров.
5. Короткие сообщения типа "ок", "+", "привет", если они не являются частью игрового действия.

Что НЕ является нарушением:
- Длинные художественные описания действий персонажа.
- Диалоги персонажей в рамках сюжета.
- Игровые броски кубиков (если они в контексте).

ФОРМАТ ОТВЕТА (СТРОГО):
Верни только список ID сообщений из входных данных, которые являются нарушениями.
Формат: числа через запятую. Например: 1, 5, 12.
Если нарушений нет, верни слово: NONE.
НЕ пиши никаких объяснений, вступлений, заключений или дополнительного текста. Только цифры или NONE.
"""

async def collect_all_messages(channel, days_limit: int, max_per_source: int = 300):
    """
    Собирает сообщения из самого канала и ВСЕХ его веток (threads).
    Возвращает единый список словарей.
    """
    after_date = datetime.now() - timedelta(days=days_limit)
    all_messages = []
    
    # 1. Сбор сообщений из основного канала
    logger.info(f"📥 Сбор сообщений из канала: #{channel.name}")
    try:
        async for message in channel.history(limit=max_per_source, after=after_date):
            if message.system or message.author == bot.user or not message.content.strip():
                continue
            all_messages.append({
                "id": len(all_messages) + 1,
                "real_id": message.id,
                "content": message.content[:1500], # Чуть меньше лимит на сообщение для веток
                "author": str(message.author),
                "url": message.jump_url,
                "source": f"#{channel.name}",
                "created_at": message.created_at
            })
        # Пауза после основного канала
        await asyncio.sleep(1.0)
    except Exception as e:
        logger.warning(f"⚠️ Ошибка чтения основного канала #{channel.name}: {e}")

    # 2. Сбор сообщений из веток (Threads)
    # Получаем все активные и архивные ветки канала
    try:
        # discord.py / disnake позволяет получать threads через channel.threads
        # Это возвращает итератор по всем видимым тредом
        async for thread in channel.threads:
            # Пропускаем удаленные или недоступные треды (иногда бывает)
            if not hasattr(thread, 'history'):
                continue
                
            logger.info(f"🧵 Обработка ветки: {thread.name} (в канале #{channel.name})")
            count_in_thread = 0
            
            try:
                async for message in thread.history(limit=max_per_source, after=after_date):
                    if message.system or message.author == bot.user or not message.content.strip():
                        continue
                    
                    count_in_thread += 1
                    all_messages.append({
                        "id": len(all_messages) + 1,
                        "real_id": message.id,
                        "content": message.content[:1500],
                        "author": str(message.author),
                        "url": message.jump_url,
                        "source": f"#{channel.name} -> 🧵{thread.name}", # Указываем источник
                        "created_at": message.created_at
                    })
                    
                    # Микро-пауза внутри ветки каждые 10 сообщений
                    if count_in_thread % 10 == 0:
                        await asyncio.sleep(0.5)
                
                # Пауза между ветками, чтобы не спамить API
                await asyncio.sleep(0.8)
                
            except disnake.Forbidden:
                logger.warning(f"🚫 Нет прав на чтение ветки: {thread.name}")
                continue
            except Exception as e:
                logger.error(f"❌ Ошибка при чтении ветки {thread.name}: {e}")
                continue
                
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при получении списка веток канала #{channel.name}: {e}")

    return all_messages

def format_messages_for_ai(messages_list: List[Dict]) -> str:
    """Форматирует список сообщений в строку для ИИ с указанием источника"""
    output_lines = []
    for msg in messages_list:
        clean_content = msg['content'].replace('\n', ' ').strip()
        # Добавляем метку источника в начало строки для контекста ИИ
        output_lines.append(f"{msg['id']} [{msg['source']}]: {clean_content}")
    return "\n".join(output_lines)

def parse_ai_response(ai_text: str, original_data: List[Dict]) -> List[Dict]:
    """Парсит ответ ИИ и возвращает объекты нарушений"""
    ai_text = ai_text.strip().upper()
    if ai_text == "NONE" or not ai_text:
        return []
    
    found_ids = []
    raw_parts = re.split(r'[,\s]+', ai_text)
    
    for part in raw_parts:
        try:
            num = int(part)
            found_ids.append(num)
        except ValueError:
            continue
    
    results = []
    for msg in original_data:
        if msg['id'] in found_ids:
            results.append(msg)
    return results

@bot.slash_command(name="анализ", description="Анализ канала и всех его веток на оффтоп (Только Owner)")
async def slash_analyze(
    interaction: disnake.CommandInteraction,
    канал: disnake.TextChannel = commands.Param(description="Канал для проверки (включая все ветки)"),
    период: str = commands.Param(
        description="Период анализа", 
        choices=["За последние 7 дней", "За последние 21 день"]
    )
):
    # 1. Проверка прав
    if interaction.author.id != OWNER_ID:
        await interaction.response.send_message("❌ Доступ запрещён. Только владелец.", ephemeral=True)
        return

    days_to_check = 7 if "7 дней" in период else 21
    
    await interaction.response.defer()
    status_msg = await interaction.edit_original_response(content=f"🔄 Сканирую канал `{канал.name}` и все его ветки за {days_to_check} дней...")

    try:
        # 2. Сбор данных (Канал + Ветки)
        messages_data = await collect_all_messages(канал, days_to_check, max_per_source=400)
        
        if not messages_data:
            await status_msg.edit(content="ℹ️ За указанный период в канале и его ветках не найдено сообщений.")
            return

        total_threads = len(set([m['source'] for m in messages_data if "" in m['source']]))
        main_msgs = len([m for m in messages_data if "🧵" not in m['source']])
        
        await status_msg.edit(content=f"📊 Найдено всего {len(messages_data)} сообщений:\n• Основных: {main_msgs}\n• Из веток: {len(messages_data) - main_msgs} (в ~{total_threads} ветках)\n\n Отправляю данные ИИ для анализа...")

        # 3. Подготовка промпта
        formatted_context = format_messages_for_ai(messages_data)
        
        # Ограничение размера токенов (безопасность для бесплатных моделей)
        if len(formatted_context) > 16000:
            formatted_context = formatted_context[:16000] + "\n... (список обрезан)"
            await status_msg.edit(content=f"️ Слишком много данных. Анализ проводится для первых {len(messages_data)//2} сообщений.")

        user_prompt = f"Проанализируй следующий список сообщений (формат: ID [Источник]: Текст):\n\n{formatted_context}"

        # 4. Запрос к ИИ (используем вашу логику приоритетов)
        final_answer = None
        final_provider = None
        queue = PRIORITY_TIER_1 + PRIORITY_TIER_2 + [("g4f-default", "deepseek-r1")]
        
        success = False
        for prov, mod in queue:
            try:
                if prov == "g4f-default":
                    client = g4f.client.AsyncClient()
                    messages_payload = [
                        {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt}
                    ]
                    resp = await asyncio.wait_for(
                        client.chat.completions.create(model=mod, messages=messages_payload),
                        timeout=90.0 # Увеличил таймаут, так как контекст большой
                    )
                    if resp and resp.choices:
                        ans = resp.choices[0].message.content
                        if ans:
                            final_answer = ans
                            final_provider = f"{prov} ({mod})"
                            success = True
                            break
                else:
                    ok, ans, _ = await make_g4f_request(prov, mod, user_prompt, timeout=90.0, system_prompt=ANALYSIS_SYSTEM_PROMPT)
                    if ok:
                        final_answer = ans
                        final_provider = f"{prov} ({mod})"
                        success = True
                        break
            except Exception as e:
                logger.warning(f"Ошибка модели {prov}/{mod}: {e}")
                continue
        
        if not success or not final_answer:
            await status_msg.edit(content="❌ Не удалось получить анализ от ИИ. Попробуйте позже или уменьшите период.")
            return

        await status_msg.edit(content=f"✅ ИИ завершил анализ ({final_provider}). Формирую отчет...")

        # 5. Парсинг и вывод
        violations = parse_ai_response(final_answer, messages_data)

        if not violations:
            await status_msg.edit(content=" Нарушений (оффтопа) в канале и ветках не обнаружено!")
            return

        # Группировка отчета для вывода
        report_lines = []
        max_chars = 1900
        
        for i, v in enumerate(violations, 1):
            # Формат: Номер) [Источник] Текст - Ссылка
            line = f"{i}) **[{v['source']}]** {v['content']} - [Перейти]({v['url']})\n"
            
            if len("".join(report_lines)) + len(line) > max_chars:
                chunk = "".join(report_lines)
                header = f" **Отчет по анализу:** #{канал.name} ({период})\n🤖 Модель: {final_provider}\n Найдено: {len(violations)}\n\n---\n{chunk}"
                
                if i == 1: # Первое сообщение редактируем статус
                    await status_msg.edit(content=header)
                else:
                    await interaction.channel.send(header)
                
                report_lines = [line]
            else:
                report_lines.append(line)

        # Отправка хвоста
        if report_lines:
            chunk = "".join(report_lines)
            header = f"🚨 **Отчет (окончание):** #{канал.name}\n\n{chunk}"
            if len(violations) <= 15 and status_msg.content.startswith("✅"):
                 await status_msg.edit(content=header)
            else:
                 await interaction.channel.send(header)

    except Exception as e:
        logger.error(f"Ошибка в /анализ: {e}", exc_info=True)
        await interaction.followup.send(f"❌ Ошибка выполнения: {str(e)[:150]}", ephemeral=True)
            
# ============================================================================
# 💾 АДМИН КОМАНДЫ: СКАЧАТЬ ФАЙЛЫ
# ============================================================================

@bot.slash_command(name="скачать_ошибки", description="Скачать файл логов ошибок")
async def slash_download_logs(interaction: disnake.CommandInteraction):
    if interaction.author.id != OWNER_ID:
        await interaction.response.send_message("❌ Доступ запрещён.", ephemeral=True)
        return
    
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.FileHandler):
            handler.flush()
    
    if os.path.exists('bot_errors.log'):
        await interaction.response.send_message(file=disnake.File('bot_errors.log'))
    else:
        await interaction.response.send_message("❌ Файл логов пуст или не найден.", ephemeral=True)

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
    logger.info(f" Бот {bot.user} готов! (Railway: {IS_RAILWAY})")
    if REQUIRED_ROLE_ID == 0: 
        logger.info(" Режим доступа: По имени роли 'Псарь' (так как ROLE_ID не задан).")
    else: 
        logger.info(f"🔒 Режим доступа: По ID роли {REQUIRED_ROLE_ID}.")
    
    asyncio.create_task(fetch_free_proxies())
    asyncio.create_task(heartbeat_keeper()) 

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound): return
    logger.error(f"Ошибка команды {ctx.command}: {error}", exc_info=True)
    with open('bot_errors.log', 'a', encoding='utf-8') as f:
        f.write(f"\n[{datetime.now()}] ERROR: {type(error).__name__}: {error}\n")
    if hasattr(ctx, 'author') and ctx.author.id == OWNER_ID:
        try: await ctx.send(f"⚠️ Ошибка: {str(error)[:100]}", delete_after=10)
        except: pass

if __name__ == "__main__":
    try:
        logger.info("🚀 Запуск PsIInka Bot v0.4.2-RoleFix...")
        bot.run(os.getenv("DISCORD_TOKEN"))
    except Exception as e:
        logger.critical(f"💥 Критическая ошибка при запуске: {e}", exc_info=True)
