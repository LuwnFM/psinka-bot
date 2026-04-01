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
        logging.warning("️ DATABASE_URL не найден. Работа с БД отключена.")
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

# Приоритетные модели на основе исторических отчетов (Hardcoded Fallbacks)
# Включает лучшие связки из ваших тестов: PollinationsAI, FreeGPT, Vercel, Blackbox, DuckDuckGo
PRIORITY_CANDIDATES = [
    ("PollinationsAI", "deepseek-r1"),
    ("PollinationsAI", "sonar"),
    ("PollinationsAI", "deepseek-v3"),
    ("FreeGPT", "deepseek-r1"),
    ("Vercel", "deepseek-r1"),
    ("Blackbox", "deepseek-v3"),
    ("Blackbox", "sonar"),
    ("Blackbox", "llama-3-70b"),
    ("DuckDuckGo", "deepseek-r1"),
    ("DuckDuckGo", "llama-3-70b"),
    ("OpenRouter", "nvidia/nemotron-3-super-120b-a12b:free"),
    ("OpenRouter", "meta-llama/llama-3.3-70b-instruct:free"),
]

EXCLUDED_OR_MODELS = ["liquid/lfm-2.5-1.2b-instruct:free"]

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
# 🔒 ПРОВЕРКА ДОСТУПА
# ============================================================================

async def check_access(interaction: disnake.CommandInteraction) -> bool:
    if interaction.author.id == OWNER_ID: return True
    if REQUIRED_ROLE_ID == 0:
        logger.warning("⚠️ ROLE_ID не настроен. Доступ открыт всем.")
        return True
    if not interaction.author.guild_roles:
        try: await interaction.author.fetch_roles()
        except: pass
    if any(role.id == REQUIRED_ROLE_ID for role in interaction.author.roles):
        return True
    await interaction.response.send_message("❌ У вас нет доступа к этой команде.", ephemeral=True)
    return False

# ============================================================================
# 🤖 ЗАПРОСЫ К МОДЕЛЯМ
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
                elapsed = time.time() - start
                return True, answer.strip(), elapsed
        return False, "Пустой ответ", time.time() - start
    except asyncio.TimeoutError:
        return False, f"Таймаут {timeout}с", time.time() - start
    except Exception as e:
        return False, str(e)[:100], time.time() - start

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
# 🔥 ФАЗА РАЗМИНКИ (OPTIMIZED WARM-UP)
# ============================================================================

async def run_warmup_phase(ctx, progress_msg, duration_seconds: int, use_proxy: bool):
    logger.info(f" Начало оптимизированной разминки...")
    start_time = time.time()
    test_prompt = "ok"
    system_prompt = "Reply only with 'ok'."
    
    # Смешиваем приоритетные кандидаты с данными из БД
    candidates = list(PRIORITY_CANDIDATES)
    db_top = db_manager.get_top_models(limit=5)
    for p, m, _ in db_top:
        if (p, m) not in candidates:
            candidates.insert(0, (p, m)) 
    
    requests_made = 0
    idx = 0
    current_proxy = get_random_proxy(use_proxy)
    successful_warmups = 0

    while (time.time() - start_time) < duration_seconds:
        cycle_start = time.time()
        if idx >= len(candidates): 
            idx = 0

        provider, model = candidates[idx]
        success = False
        latency_ms = 0

        try:
            if provider == "OpenRouter":
                if model in EXCLUDED_OR_MODELS:
                    idx += 1; continue
                success, _, lat = await test_openrouter_single(model, test_prompt, timeout=10.0, system_prompt=system_prompt, proxy_url=current_proxy)
            else:
                success, _, lat = await make_g4f_request(provider, model, test_prompt, timeout=10.0, system_prompt=system_prompt, proxy_url=current_proxy)
                latency_ms = int(lat * 1000) if success else 0

            if success:
                db_manager.log_success(provider, model, latency_ms if latency_ms > 0 else 100)
                successful_warmups += 1
        except:
            pass

        idx += 1
        requests_made += 1

        elapsed = int(time.time() - start_time)
        if progress_msg and elapsed % 10 == 0:
            try:
                remaining = duration_seconds - elapsed
                proxy_status = "🟢 ВКЛ" if use_proxy else "🔴 ВЫКЛ"
                await progress_msg.edit(
                    content=f"🔥 **Разминка моделей...**\nПрошло: {elapsed}с / Осталось: {remaining}с\nНайдено рабочих: {successful_warmups}\nПрокси: {proxy_status}")
            except:
                pass

        delay = 0.5 - (time.time() - cycle_start)
        if delay > 0: await asyncio.sleep(delay)

    logger.info(f"🏁 Разминка завершена. Успешных коннектов: {successful_warmups}")
    return successful_warmups

# ============================================================================
# 💬 СЛЭШ-КОМАНДА "/скажи" (CASCADE LOGIC)
# ============================================================================

@bot.slash_command(name="скажи", description="Запрос к ИИ с умным каскадом и прогревом")
async def slash_say(
        interaction: disnake.CommandInteraction,
        вопрос: str = commands.Param(description="Ваш вопрос к боту", min_length=1),
        прокси: str = commands.Param(description="Использовать прокси?", choices=["Да", "Нет"], default="Нет")
):
    if not await check_access(interaction): return

    use_proxy = (прокси == "Да")
    proxy_status_text = "с прокси 🟢" if use_proxy else "без прокси 🔴"

    await interaction.response.defer()
    msg = await interaction.edit_original_response(
        content=f"🐕 ПсИИнка готовится ({proxy_status_text})...\n Запуск диагностики и прогрева (~45 сек)...")

    try:
        # 1. Быстрый прогрев (45 сек)
        await run_warmup_phase(interaction, msg, duration_seconds=45, use_proxy=use_proxy)

        await msg.edit(content=f"✅ **Диагностика завершена!** ({proxy_status_text})\n Выбираю лучшую модель...\n Генерирую ответ...")

        # 2. Получаем топ моделей из БД
        best_candidates = db_manager.get_top_models(limit=5)
        if not best_candidates:
            best_candidates = [(p, m, 0) for p, m in PRIORITY_CANDIDATES[:5]] 

        final_response = None
        final_provider = None
        final_model = None
        current_proxy = get_random_proxy(use_proxy)
        system_prompt = "Ты помощник по имени Псинка. Отвечай ТОЛЬКО на русском языке, кратко и по делу."

        # 3. Каскадный запрос
        for prov, mod, _ in best_candidates:
            logger.info(f"🔄 Попытка через {prov} / {mod}")
            try:
                if prov == "OpenRouter":
                    if mod in EXCLUDED_OR_MODELS: continue
                    success, answer, _ = await test_openrouter_single(mod, вопрос, timeout=45.0, system_prompt=system_prompt, proxy_url=current_proxy)
                else:
                    success, answer, _ = await make_g4f_request(prov, mod, вопрос, timeout=45.0, system_prompt=system_prompt, proxy_url=current_proxy)
                
                if success and answer:
                    final_response = answer
                    final_provider = prov
                    final_model = mod
                    break
            except Exception as e:
                logger.warning(f"Ошибка при запросе {prov}/{mod}: {e}")
                continue
        
        # 4. Финальный фолбэк
        if not final_response:
            logger.warning("⚠️ Каскад G4F не сработал, пробуем OpenRouter fallback...")
            fallback_models = ["meta-llama/llama-3.3-70b-instruct:free", "openrouter/free"]
            for or_m in fallback_models:
                try:
                    success, answer, _ = await test_openrouter_single(or_m, вопрос, timeout=45.0, system_prompt=system_prompt, proxy_url=current_proxy)
                    if success and answer:
                        final_response = answer
                        final_provider = "OpenRouter"
                        final_model = or_m
                        break
                except:
                    continue

        if not final_response:
            await msg.edit(content="️ Не удалось получить ответ ни от одной модели. Попробуйте позже или измените вопрос.")
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
        logger.error(f"Ошибка в команде /скажи: {e}", exc_info=True)
        await interaction.followup.send(f"️ Критическая ошибка: {str(e)[:100]}", ephemeral=True)

# ============================================================================
# 🎲 ДВИЖОК КУБИКОВ (DICE ENGINE - FULL IMPLEMENTATION)
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
        self.aliases: Dict[str, str] = {
            "dndstats": "6 4d6 k3",
            "attack": "1d20",
            "skill": "1d20",
            "save": "1d20",
            "+d20": "2d20 d1",
            "-d20": "2d20 kl1",
            "+d%": "((2d10kl1-1)*10)+1d10",
            "-d%": "((2d10k1-1)*10)+1d10",
            "dd34": "(1d3*10)+1d4",
            "cod": "d10 t8 ie10",
            "wod": "d10 t8 f1 ie10",
            "sr6": "d6 t5",
            "ex5": "d10 t7",
            "wh4+": "d6 t4",
            "age": "3d6",
            "df": "3d3 t3 f1",
            "snm5": "d6 ie6 t4",
            "d6s4": "5d6 ie",
            "sp4": "d10 t8 ie10",
            "yz": "d6 t6",
            "gb": "d12",
            "hsn": "2d6",
            "hsk1": "2d6",
            "hsh": "3d6",
        }

    def parse(self, command_str: str) -> List[DiceResult]:
        results = []
        original_command = command_str.strip()
        if not original_command: return results

        parts = original_command.split()
        if parts:
            first_word = parts[0].lower()
            if first_word in self.aliases:
                expansion = self.aliases[first_word]
                rest_of_command = " ".join(parts[1:])
                command_str = f"{expansion} {rest_of_command}".strip()
            else:
                command_str = original_command
        else:
            command_str = original_command

        roll_sets_raw = command_str.split(';')
        for roll_set_raw in roll_sets_raw:
            roll_set_raw = roll_set_raw.strip()
            if not roll_set_raw: continue
            result = self.process_single_roll_set(roll_set_raw)
            if result:
                results.append(result)
            if len(results) >= 4: break
        return results

    def process_single_roll_set(self, roll_str: str) -> Optional[DiceResult]:
        result = DiceResult()
        flags = re.findall(r'\b(s|nr|p|ul)\b', roll_str, re.IGNORECASE)
        for f in flags:
            f_low = f.lower()
            if f_low == 's': result.simplified = True
            elif f_low == 'nr': result.no_results = True
            elif f_low == 'p': result.is_private = True
            elif f_low == 'ul': result.unsorted = True

        comment_match = re.search(r'!\s*(.+)$', roll_str)
        if comment_match:
            result.comment = comment_match.group(1).strip()
            roll_str = roll_str[:comment_match.start()]

        clean_roll = re.sub(r'\b(s|nr|p|ul)\b', '', roll_str, flags=re.IGNORECASE)
        clean_roll = re.sub(r'!.+$', '', clean_roll).strip()
        if not clean_roll: return None

        set_count = 1
        set_match = re.match(r'^(\d+)\s+(.+)', clean_roll)
        if set_match:
            try:
                set_count = int(set_match.group(1))
                if set_count < 2 or set_count > 20: raise ValueError("Количество наборов (N) должно быть от 2 до 20.")
                clean_roll = set_match.group(2)
            except ValueError as e: raise ValueError(str(e))

        tokens = re.split(r'(\+|\-|\*|\/)', clean_roll)
        tokens = [t for t in tokens if t.strip()]
        if not tokens: return None

        try:
            val, logs = self.evaluate_term(tokens[0].strip(), result)
            current_total = val
            all_logs = logs

            for i in range(1, len(tokens), 2):
                if i + 1 >= len(tokens): break
                op = tokens[i]
                term_str = tokens[i + 1].strip()
                val, logs = self.evaluate_term(term_str, result)
                if op == '+': current_total += val
                elif op == '-': current_total -= val
                elif op == '*': current_total *= val
                elif op == '/':
                    if val == 0: raise ZeroDivisionError("Деление на ноль!")
                    current_total /= val
                all_logs.extend(logs)

            if set_count > 1:
                result.set_results = []
                total_sum = 0.0
                for k in range(set_count):
                    temp_res = DiceResult()
                    sub_val, sub_logs = self._calculate_expression(clean_roll, temp_res)
                    result.set_results.append(sub_val)
                    total_sum += sub_val
                    if k == 0:
                        result.details = temp_res.details
                        result.dice_rolls = temp_res.dice_rolls
                        result.successes = temp_res.successes
                        result.failures = temp_res.failures
                        result.botches = temp_res.botches
                result.total = total_sum
                result.details.insert(0, f"Выполнено наборов: {set_count}. Показан детальный лог первого набора.")
            else:
                result.total = current_total
                result.dice_rolls = all_logs
            return result
        except Exception as e:
            raise e

    def _calculate_expression(self, expr: str, res_obj: DiceResult) -> Tuple[float, List]:
        tokens = re.split(r'(\+|\-|\*|\/)', expr)
        tokens = [t for t in tokens if t.strip()]
        if not tokens: return 0, []
        val, logs = self.evaluate_term(tokens[0].strip(), res_obj)
        current = val
        all_logs = logs
        for i in range(1, len(tokens), 2):
            if i + 1 >= len(tokens): break
            op = tokens[i]
            term = tokens[i + 1].strip()
            val, logs = self.evaluate_term(term, res_obj)
            if op == '+': current += val
            elif op == '-': current -= val
            elif op == '*': current *= val
            elif op == '/':
                if val == 0: raise ZeroDivisionError("Деление на ноль")
                current /= val
            all_logs.extend(logs)
        return current, all_logs

    def evaluate_term(self, term: str, res_obj: DiceResult) -> Tuple[float, List]:
        if not term: return 0, []
        try:
            val = float(term)
            return val, [val]
        except ValueError:
            pass
        match = re.match(r'^(\d*)d(\d+)(.*)$', term, re.IGNORECASE)
        if not match:
            raise ValueError(f"Непонятный формат: '{term}'. Используйте формат NdY (напр. 2d6).")
        num_dice = int(match.group(1)) if match.group(1) else 1
        sides = int(match.group(2))
        modifiers_str = match.group(3).strip()
        if sides > 1000: raise ValueError("Максимум 1000 граней!")
        if num_dice > 100: raise ValueError("Слишком много кубиков (макс 100)!")
        rolls = [random.randint(1, sides) for _ in range(num_dice)]
        rolls = self.apply_rerolls(rolls, sides, modifiers_str, res_obj)
        rolls = self.apply_exploding(rolls, sides, modifiers_str, res_obj)
        rolls = self.apply_keep_drop(rolls, modifiers_str, res_obj)
        if re.search(r'\bt\d+', modifiers_str, re.IGNORECASE) or re.search(r'\bf\d+', modifiers_str, re.IGNORECASE):
            successes, failures, botches = self.calculate_successes(rolls, modifiers_str, sides)
            res_obj.successes = successes
            res_obj.failures = failures
            res_obj.botches = botches
            final_val = successes - failures
            return final_val, rolls
        return float(sum(rolls)), rolls

    def apply_rerolls(self, rolls: List[int], sides: int, mods: str, res: DiceResult) -> List[int]:
        new_rolls = rolls.copy()
        patterns = [(r'ir(\d+)', True), (r'r(\d+)', False)]
        for pattern, is_infinite in patterns:
            match = re.search(pattern, mods, re.IGNORECASE)
            if match:
                threshold = int(match.group(1))
                iterations = 0
                while True:
                    changed = False
                    for i, val in enumerate(new_rolls):
                        if val <= threshold:
                            new_val = random.randint(1, sides)
                            res.details.append(f"Переброс {val} -> {new_val} (<= {threshold})")
                            new_rolls[i] = new_val
                            changed = True
                            if not is_infinite: break
                    if not changed or not is_infinite: break
                    iterations += 1
                    if iterations > 100: break
        return new_rolls

    def apply_exploding(self, rolls: List[int], sides: int, mods: str, res: DiceResult) -> List[int]:
        final_rolls = rolls.copy()
        patterns = [(r'ie(\d+)?', True), (r'e(\d+)?', False)]
        for pattern, is_infinite in patterns:
            match = re.search(pattern, mods, re.IGNORECASE)
            if match:
                threshold = int(match.group(1)) if match.group(1) else sides
                i = 0
                limit = 1000
                count = 0
                while i < len(final_rolls) and count < limit:
                    val = final_rolls[i]
                    if val >= threshold:
                        extra = random.randint(1, sides)
                        res.details.append(f"Взрыв ({val}) -> +{extra}")
                        final_rolls.append(extra)
                    i += 1
                    count += 1
        return final_rolls

    def apply_keep_drop(self, rolls: List[int], mods: str, res: DiceResult) -> List[int]:
        working_rolls = rolls.copy()
        match_d = re.search(r'd(\d+)', mods, re.IGNORECASE)
        if match_d:
            count = int(match_d.group(1))
            if count > 0:
                working_rolls.sort()
                dropped = working_rolls[:count]
                working_rolls = working_rolls[count:]
                res.details.append(f"Сброшено низких ({count}): {dropped}")
        match_k = re.search(r'k(\d+)', mods, re.IGNORECASE)
        if match_k:
            count = int(match_k.group(1))
            if count > 0:
                working_rolls.sort(reverse=True)
                kept = working_rolls[:count]
                working_rolls = kept
                res.details.append(f"Оставлено высоких ({count}): {kept}")
        match_kl = re.search(r'kl(\d+)', mods, re.IGNORECASE)
        if match_kl:
            count = int(match_kl.group(1))
            if count > 0:
                working_rolls.sort()
                kept = working_rolls[:count]
                working_rolls = kept
                res.details.append(f"Оставлено низких ({count}): {kept}")
        return working_rolls

    def calculate_successes(self, rolls: List[int], mods: str, sides: int) -> Tuple[int, int, int]:
        successes = 0
        failures = 0
        botches = 0
        target_match = re.search(r't(\d+)', mods, re.IGNORECASE)
        fail_match = re.search(r'f(\d+)', mods, re.IGNORECASE)
        botch_match = re.search(r'b(\d+)?', mods, re.IGNORECASE)
        target = int(target_match.group(1)) if target_match else (sides + 1)
        fail_thresh = int(fail_match.group(1)) if fail_match else 0
        botch_thresh = int(botch_match.group(1)) if botch_match and botch_match.group(1) else 1
        for val in rolls:
            if val >= target: successes += 1
            if fail_thresh > 0 and val <= fail_thresh: failures += 1
            if val <= botch_thresh: botches += 1
        return successes, failures, botches

dice_engine = DiceParser()

@bot.slash_command(name="кубик", description="Бросок кубиков (D&D стиль)")
async def slash_cube(
        interaction: disnake.CommandInteraction,
        формула: str = commands.Param(description="Формула (2d6, 3d6+5, dndstats)", default=None)
):
    if not формула or формула.strip() == "":
        embed = disnake.Embed(title="🎲 Справка по кубикам", color=0x00FF88, description="Используйте `/кубик 2d6+5` или алиасы like `dndstats`")
        await interaction.response.send_message(embed=embed)
        return
    try:
        await interaction.response.defer()
        results = dice_engine.parse(формула)
        if not results: raise ValueError("Не удалось разобрать формулу.")
        main_embed = disnake.Embed(title=f" Бросок: {формула}", color=0xFFAA00)
        total_text = ""
        for i, res in enumerate(results):
            sum_val = res.total
            if res.successes != 0 or res.failures != 0:
                sum_display = f"**{res.successes} Усп.**"
                if res.failures > 0: sum_display += f" - {res.failures} Пров."
                if res.botches > 0: sum_display += f" | ️ {res.botches} Ботч"
            else:
                sum_display = f"**{int(sum_val) if isinstance(sum_val, float) and sum_val.is_integer() else round(sum_val, 2)}**"
            dice_str = ", ".join(map(str, res.dice_rolls[:25])) + ("..." if len(res.dice_rolls) > 25 else "")
            line = f"{'Результат ' + str(i+1) + ': ' if len(results)>1 else ''}{sum_display} `({dice_str})`"
            if res.comment: line += f" — _{res.comment}_"
            total_text += line + "\n\n"
        main_embed.description = total_text[:4096]
        if results[0].is_private:
            await interaction.followup.send(embed=main_embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=main_embed)
    except Exception as e:
        logger.error(f"Ошибка кубик: {e}")
        await interaction.followup.send(f"❌ Ошибка: {str(e)[:150]}", ephemeral=True)

# ============================================================================
# ️ СЛЭШ-КОМАНДА "/погавкай"
# ============================================================================

@bot.slash_command(name="погавкай", description="Проверить пинг бота")
async def slash_bark(interaction: disnake.CommandInteraction):
    ping = round(bot.latency * 1000)
    await interaction.response.send_message(f'🐕 Иди нахуй! У меня пинг {ping} мс')

# ============================================================================
# 📊 СЛЭШ-КОМАНДА "/статус"
# ============================================================================

@bot.slash_command(name="статус", description="Показать статистику бота и БД")
async def slash_status(interaction: disnake.CommandInteraction):
    if not await check_access(interaction): return
    await interaction.response.defer()
    if not db_manager.SessionLocal:
        embed = disnake.Embed(title="⚠️ Статус системы", description="База данных не подключена.", color=0xFFAA00)
    else:
        rec_count = session.query(ModelSuccessLog).count() if (session := db_manager.SessionLocal()) else 0
        if session: session.close()
        top_models = db_manager.get_top_models(3)
        top_text = "\n".join([f"{i+1}. `{p}` / `{m}` ({l}мс)" for i, (p, m, l) in enumerate(top_models)]) if top_models else "Нет данных"
        embed = disnake.Embed(title="📊 Статус ПсИИнки", color=0x00FF88)
        embed.add_field(name="💾 База данных", value=f"Записей успехов: `{rec_count}`", inline=False)
        embed.add_field(name=" Топ моделей (прямо сейчас)", value=top_text, inline=False)
        embed.add_field(name="⚙️ Режим работы", value="Neon PostgreSQL" if IS_RAILWAY else "Локальный", inline=True)
    embed.set_footer(text=f"Версия: v0.4.0-Neon | Время: {datetime.now().strftime('%H:%M')}")
    await interaction.edit_original_response(embed=embed)

# ============================================================================
# 💾 АДМИН КОМАНДЫ: СКАЧАТЬ ФАЙЛЫ
# ============================================================================

@bot.slash_command(name="скачать_ошибки", description="Скачать файл логов ошибок (временный)")
async def slash_download_logs(interaction: disnake.CommandInteraction):
    if interaction.author.id != OWNER_ID:
        await interaction.response.send_message("❌ Доступ запрещён.", ephemeral=True)
        return
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
        logger.warning("⚠️ ВНИМАНИЕ: ROLE_ID не установлен. Доступ открыт всем.")
    else:
        logger.info(f" Ограничение доступа включено. Role ID: {REQUIRED_ROLE_ID}")
    asyncio.create_task(fetch_free_proxies())

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound): return
    logger.error(f"Ошибка команды {ctx.command}: {error}", exc_info=True)
    with open('bot_errors.log', 'a', encoding='utf-8') as f:
        f.write(f"\n[{datetime.now()}] ERROR: {error}\n")
    if hasattr(ctx, 'author'):
        if ctx.author.id == OWNER_ID:
            try: await ctx.send(f"⚠️ Произошла ошибка: {str(error)[:100]}", delete_after=10)
            except: pass

if __name__ == "__main__":
    try:
        logger.info("🚀 Запуск PsIInka Bot v0.4.0...")
        bot.run(os.getenv("DISCORD_TOKEN"))
    except Exception as e:
        logger.critical(f"💥 Критическая ошибка при запуске: {e}", exc_info=True)
