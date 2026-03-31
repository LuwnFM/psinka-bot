import g4f
import disnake
import random
import re
import os
import logging
import time
import math
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
        logging.info("✅ База данных Neon подключена и таблицы созданы.")
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
                record.avg_latency_ms = int(
                    (record.avg_latency_ms * (record.success_count - 1) + latency_ms) / record.success_count)
                record.last_success_at = datetime.now()
            else:
                record = ModelSuccessLog(provider=provider, model_name=model, success_count=1,
                                         last_success_at=datetime.now(), avg_latency_ms=latency_ms)
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
            old_ids = session.query(ModelSuccessLog.id).order_by(ModelSuccessLog.last_success_at.asc()).limit(
                count - 200).all()
            if old_ids:
                ids_to_delete = [x[0] for x in old_ids]
                session.query(ModelSuccessLog).filter(ModelSuccessLog.id.in_(ids_to_delete)).delete(
                    synchronize_session=False)
                session.commit()

    def get_best_models(self, limit: int = 5) -> List[Tuple[str, str]]:
        if not self.SessionLocal: return []
        session = self.SessionLocal()
        try:
            results = session.query(ModelSuccessLog.provider, ModelSuccessLog.model_name) \
                .order_by(ModelSuccessLog.success_count.desc(), ModelSuccessLog.avg_latency_ms.asc()) \
                .limit(limit).all()
            return [(r.provider, r.model_name) for r in results]
        except Exception as e:
            logging.error(f"Ошибка чтения из БД: {e}")
            return []
        finally:
            session.close()

    def get_stats(self):
        if not self.SessionLocal: return 0, 0
        session = self.SessionLocal()
        try:
            total_records = session.query(ModelSuccessLog).count()
            total_successes = session.query(func.sum(ModelSuccessLog.success_count)).scalar() or 0
            return total_records, total_successes
        except:
            return 0, 0
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

DEFAULT_FALLBACKS = [("PollinationsAI", "deepseek-r1"), ("DeepInfra", "llama-3.1-70b")]
EXCLUDED_OR_MODELS = ["liquid/lfm-2.5-1.2b-instruct:free"]
PRIORITY_OR_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"

# ============================================================================
# ️ ПРОКСИ СИСТЕМА (ДИНАМИЧЕСКАЯ)
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
    """Возвращает прокси только если use_proxy=True"""
    if not use_proxy:
        return None
    proxy = random.choice(FREE_PROXY_LIST)
    logger.debug(f"🔀 Используем прокси: {proxy}")
    return proxy


# ============================================================================
# 🔒 ПРОВЕРКА ДОСТУПА (ДЛЯ ВСЕХ КОМАНД КРОМЕ КУБИКА)
# ============================================================================

async def check_access(interaction: disnake.CommandInteraction) -> bool:
    if interaction.author.id == OWNER_ID:
        return True
    if REQUIRED_ROLE_ID == 0:
        logger.warning("⚠️ ROLE_ID не настроен. Доступ открыт всем.")
        return True

    if not interaction.author.guild_roles:
        try:
            await interaction.author.fetch_roles()
        except:
            pass

    if any(role.id == REQUIRED_ROLE_ID for role in interaction.author.roles):
        return True

    await interaction.response.send_message("❌ У вас нет доступа к этой команде.", ephemeral=True)
    return False


# ============================================================================
# 🤖 ЗАПРОСЫ К МОДЕЛЯМ
# ============================================================================

async def make_g4f_request(provider_name: str, model: str, prompt: str,
                           timeout: float = 40.0, system_prompt: str = None, proxy_url: str = None) -> Tuple[
    bool, str, float]:
    elapsed = 0.0
    start = time.time()
    try:
        messages = []
        if system_prompt: messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

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


async def test_openrouter_single(model: str, prompt: str, timeout: float = 35.0, system_prompt: str = None,
                                 proxy_url: str = None):
    openrouter_token = os.getenv('OPENR_TOKEN')
    if not openrouter_token: return False, "No Token", 0.0

    start = time.time()
    try:
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=openrouter_token)
        loop = asyncio.get_running_loop()

        messages = []
        if system_prompt: messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

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
# 🔥 ФАЗА РАЗМИНКИ (WARM-UP)
# ============================================================================

async def run_warmup_phase(ctx, progress_msg, duration_seconds: int, use_proxy: bool):
    logger.info(f" Начало фазы разминки (Прокси: {use_proxy})...")
    start_time = time.time()
    test_prompt = "ок"
    system_prompt = "Отвечай только словом ок."

    best_candidates = db_manager.get_best_models(limit=5)
    if not best_candidates:
        best_candidates = DEFAULT_FALLBACKS.copy()
        best_candidates.append(("OpenRouter", PRIORITY_OR_MODEL))
    else:
        best_candidates.append(("OpenRouter", PRIORITY_OR_MODEL))

    requests_made = 0
    idx = 0
    current_proxy = get_random_proxy(use_proxy)

    while (time.time() - start_time) < duration_seconds:
        cycle_start = time.time()
        if idx >= len(best_candidates): idx = 0

        provider, model = best_candidates[idx]
        success = False
        latency_ms = 0

        if provider == "OpenRouter":
            if model in EXCLUDED_OR_MODELS:
                idx += 1
                continue
            success, _, lat = await test_openrouter_single(model, test_prompt, timeout=15.0,
                                                           system_prompt=system_prompt, proxy_url=current_proxy)
        else:
            success, _, lat = await make_g4f_request(provider, model, test_prompt, timeout=15.0,
                                                     system_prompt=system_prompt, proxy_url=current_proxy)
            latency_ms = int(lat * 1000) if success else 0

        if success:
            db_manager.log_success(provider, model, latency_ms if latency_ms > 0 else 500)
            logger.info(f"✅ Warmup: {provider}/{model} (Proxy: {bool(current_proxy)})")

        idx += 1
        requests_made += 1

        elapsed = int(time.time() - start_time)
        if progress_msg and elapsed % 15 == 0:
            try:
                remaining = duration_seconds - elapsed
                proxy_status = "🟢 ВКЛ" if use_proxy else "🔴 ВЫКЛ"
                await progress_msg.edit(
                    content=f"🔥 **Разминка...**\nПрошло: {elapsed}с / Осталось: {remaining}с\nЗапросов: {requests_made}\nПрокси: {proxy_status}\n*Сохраняю статистику в БД...*")
            except:
                pass

        delay = 0.5 - (time.time() - cycle_start)
        if delay > 0: await asyncio.sleep(delay)

    logger.info(f" Разминка завершена. Запросов: {requests_made}")
    return requests_made


# ============================================================================
# 💬 СЛЭШ-КОМАНДА "/скажи" (ТРЕБУЕТ РОЛЬ)
# ============================================================================

@bot.slash_command(name="скажи", description="Запрос к ИИ с выбором использования прокси")
async def slash_say(
        interaction: disnake.CommandInteraction,
        вопрос: str = commands.Param(description="Ваш вопрос к боту", min_length=1),
        прокси: str = commands.Param(description="Использовать прокси для этого запроса?", choices=["Да", "Нет"],
                                     default="Нет")
):
    if not await check_access(interaction):
        return

    use_proxy = (прокси == "Да")
    proxy_status_text = "с прокси 🟢" if use_proxy else "без прокси 🔴"

    await interaction.response.defer()
    msg = await interaction.edit_original_response(
        content=f"🐕 ПсИИнка готовится ({proxy_status_text})...\n Диагностика и прогрев моделей (~2 мин)...")

    try:
        await run_warmup_phase(interaction, msg, duration_seconds=120, use_proxy=use_proxy)

        await msg.edit(
            content=f"✅ **Диагностика завершена!** ({proxy_status_text})\n Выбираю лучшую модель...\n Генерирую ответ...")

        best_candidates = db_manager.get_best_models(limit=1)
        final_response = None
        final_provider = None
        final_model = None

        current_proxy = get_random_proxy(use_proxy)

        if best_candidates:
            prov, mod = best_candidates[0]
            logger.info(f" Основной запрос: {prov} / {mod} (Proxy: {use_proxy})")
            system_prompt = "Ты помощник по имени Псинка. Отвечай ТОЛЬКО на русском языке, кратко и по делу."
            success, answer, _ = await make_g4f_request(prov, mod, вопрос, timeout=60.0, system_prompt=system_prompt,
                                                        proxy_url=current_proxy)
            if success and answer:
                final_response = answer
                final_provider = prov
                final_model = mod

        if not final_response:
            logger.warning("⚠️ G4F не ответил, пробуем OpenRouter...")
            or_models = [PRIORITY_OR_MODEL, "meta-llama/llama-3.3-70b-instruct:free", "openrouter/free"]
            for or_m in or_models:
                if or_m in EXCLUDED_OR_MODELS: continue
                system_prompt = "Ты помощник Псинка. Отвечай кратко на русском."
                success, answer, _ = await test_openrouter_single(or_m, вопрос, timeout=45.0,
                                                                  system_prompt=system_prompt, proxy_url=current_proxy)
                if success and answer:
                    final_response = answer
                    final_provider = "OpenRouter"
                    final_model = or_m
                    break

        if not final_response:
            await msg.edit(
                content="️ Не удалось получить ответ ни от одной модели после диагностики. Попробуйте позже.")
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
# 🎲 ДВИЖОК КУБИКОВ (DICE ENGINE)
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
        }

    def parse(self, command_str: str) -> List[DiceResult]:
        results = []
        original_command = command_str.strip()

        if not original_command:
            return results

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
            if not roll_set_raw:
                continue

            result = self.process_single_roll_set(roll_set_raw)
            if result:
                results.append(result)

            if len(results) >= 4:
                break

        return results

    def process_single_roll_set(self, roll_str: str) -> Optional[DiceResult]:
        result = DiceResult()

        flags = re.findall(r'\b(s|nr|p|ul)\b', roll_str, re.IGNORECASE)
        for f in flags:
            f_low = f.lower()
            if f_low == 's':
                result.simplified = True
            elif f_low == 'nr':
                result.no_results = True
            elif f_low == 'p':
                result.is_private = True
            elif f_low == 'ul':
                result.unsorted = True

        comment_match = re.search(r'!\s*(.+)$', roll_str)
        if comment_match:
            result.comment = comment_match.group(1).strip()
            roll_str = roll_str[:comment_match.start()]

        clean_roll = re.sub(r'\b(s|nr|p|ul)\b', '', roll_str, flags=re.IGNORECASE)
        clean_roll = re.sub(r'!.+$', '', clean_roll).strip()

        if not clean_roll:
            return None

        set_count = 1
        set_match = re.match(r'^(\d+)\s+(.+)', clean_roll)
        if set_match:
            try:
                set_count = int(set_match.group(1))
                if set_count < 2 or set_count > 20:
                    raise ValueError("Количество наборов (N) должно быть от 2 до 20.")
                clean_roll = set_match.group(2)
            except ValueError as e:
                raise ValueError(str(e))

        tokens = re.split(r'(\+|\-|\*|\/)', clean_roll)
        tokens = [t for t in tokens if t.strip()]

        if not tokens:
            return None

        try:
            val, logs = self.evaluate_term(tokens[0].strip(), result)
            current_total = val
            all_logs = logs

            for i in range(1, len(tokens), 2):
                if i + 1 >= len(tokens):
                    break
                op = tokens[i]
                term_str = tokens[i + 1].strip()

                val, logs = self.evaluate_term(term_str, result)

                if op == '+':
                    current_total += val
                elif op == '-':
                    current_total -= val
                elif op == '*':
                    current_total *= val
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

            if op == '+':
                current += val
            elif op == '-':
                current -= val
            elif op == '*':
                current *= val
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


# ============================================================================
# 🎲 СЛЭШ-КОМАНДА "/кубик" (ДОСТУПНА ВСЕМ!)
# ============================================================================

@bot.slash_command(name="кубик", description="Бросок кубиков (D&D стиль)")
async def slash_cube(
        interaction: disnake.CommandInteraction,
        формула: str = commands.Param(description="Формула (2d6, 3d6+5, dndstats)", default=None)
):
    # ПРОВЕРКА ДОСТУПА УБРАНА - КОМАНДА ДЛЯ ВСЕХ

    if not формула or формула.strip() == "":
        embed = generate_help_embed()
        await interaction.response.send_message(embed=embed)
        return

    try:
        await interaction.response.defer()

        results = dice_engine.parse(формула)

        if not results:
            raise ValueError("Не удалось разобрать формулу или она пуста.")

        main_embed = disnake.Embed(title=f"🎲 Бросок: {формула}", color=0xFFAA00)

        total_text = ""
        detail_text = ""

        for i, res in enumerate(results):
            prefix = f"Результат {i + 1}: " if len(results) > 1 else ""
            sum_val = res.total

            if res.successes != 0 or res.failures != 0:
                sum_display = f"**{res.successes} Усп.**"
                if res.failures > 0: sum_display += f" - {res.failures} Пров."
                if res.botches > 0: sum_display += f" | ⚠️ {res.botches} Ботч"
            else:
                if isinstance(sum_val, float) and not sum_val.is_integer():
                    sum_val = round(sum_val, 2)
                sum_display = f"**{int(sum_val) if isinstance(sum_val, float) and sum_val.is_integer() else sum_val}**"

            dice_str = ""
            if not res.no_results and not res.simplified:
                rolls_to_show = res.dice_rolls
                if not res.unsorted and rolls_to_show and isinstance(rolls_to_show[0], (int, float)):
                    rolls_to_show = sorted(rolls_to_show, reverse=True)
                display_limit = 25
                if len(rolls_to_show) > display_limit:
                    dice_str = ", ".join(map(str, rolls_to_show[:display_limit])) + "..."
                else:
                    dice_str = ", ".join(map(str, rolls_to_show))

            line = f"{prefix}{sum_display}"
            if dice_str: line += f" `({dice_str})`"
            if res.comment: line += f" — _{res.comment}_"

            if res.set_results and len(res.set_results) > 1:
                sets_preview = ", ".join(
                    [str(int(x) if isinstance(x, float) and x.is_integer() else round(x, 1)) for x in
                     res.set_results[:5]])
                if len(res.set_results) > 5: sets_preview += "..."
                line += f"\n> Наборы: [{sets_preview}] (Сумма: {sum_display})"

            total_text += line + "\n\n"

            if res.details and not res.simplified:
                detail_text += f" Детали: {'; '.join(res.details)}\n"

        main_embed.description = total_text[:4096]

        if detail_text:
            main_embed.add_field(name="Лог событий", value=detail_text[:1024], inline=False)

        main_embed.set_footer(text="Dice Engine v2.0 (D&D Focus)")

        if results[0].is_private:
            await interaction.followup.send(embed=main_embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=main_embed)

    except Exception as e:
        logger.error(f"Ошибка в команде кубик: {e}", exc_info=True)
        await interaction.followup.send(
            f"❌ Ошибка: {str(e)[:150]}\nИспользуйте `/кубик` без аргументов для справки.",
            ephemeral=True
        )


def generate_help_embed() -> disnake.Embed:
    embed = disnake.Embed(title="🎲 Справка по кубикам", color=0x00FF88)
    embed.add_field(name="📜 Основной синтаксис", value=(
        "`XdY` — X кубиков с Y гранями (напр. `2d6`)\n"
        "`+ - * /` — Математика (напр. `3d6+5`)\n"
        "`N XdY` — N повторений броска (напр. `6 4d6`)\n"
        "`A ; B` — Несколько разных бросков (макс 4)"
    ), inline=False)
    embed.add_field(name=" Модификаторы", value=(
        "**Взрывы:** `e6` (один раз), `ie6` (бесконечно)\n"
        "**Удержание:** `k3` (лучшие 3), `kl3` (худшие 3)\n"
        "**Сброс:** `d1` (убрать 1 худший)\n"
        "**Переброс:** `r2` (<=2), `ir2` (бесконечно)\n"
        "**Успехи:** `t7` (цель 7+), `f1` (провал <=1)"
    ), inline=False)
    embed.add_field(name="️ D&D Алиасы", value=(
        "`dndstats` — Генерация статов\n"
        "`attack +5` — Атака (1d20+5)\n"
        "`+d20` — Преимущество\n"
        "`-d20` — Помеха"
    ), inline=False)
    embed.add_field(name=" Утилиты", value=(
        "`s` — Краткий вывод\n"
        "`nr` — Скрыть значения\n"
        "`p` — Приватно\n"
        "`! текст` — Комментарий"
    ), inline=False)
    return embed


# ============================================================================
# 📊 СЛЭШ-КОМАНДА "/статус" (ТРЕБУЕТ РОЛЬ)
# ============================================================================

@bot.slash_command(name="статус", description="Показать статистику бота и БД")
async def slash_status(interaction: disnake.CommandInteraction):
    if not await check_access(interaction):
        return

    await interaction.response.defer()

    if not db_manager.SessionLocal:
        embed = disnake.Embed(title="️ Статус системы",
                              description="База данных не подключена. Бот работает в ограниченном режиме.",
                              color=0xFFAA00)
    else:
        rec_count, succ_count = db_manager.get_stats()
        embed = disnake.Embed(title="📊 Статус ПсИИнки", color=0x00FF88)
        embed.add_field(name=" База данных",
                        value=f"Записей моделей: `{rec_count}`\nВсего успешных ответов: `{succ_count}`", inline=False)
        embed.add_field(name=" Режим работы", value="Neon PostgreSQL" if IS_RAILWAY else "Локальный", inline=True)

        top_models = db_manager.get_best_models(3)
        if top_models:
            top_text = "\n".join([f"{i + 1}. `{p}` / `{m}`" for i, (p, m) in enumerate(top_models)])
            embed.add_field(name="🏆 Топ моделей (прямо сейчас)", value=top_text, inline=False)
        else:
            embed.add_field(name=" Топ моделей", value="Нет данных (используйте `/скажи`)", inline=False)

    embed.set_footer(text=f"Версия: v3.0-Slash | Время: {datetime.now().strftime('%H:%M')}")
    await interaction.edit_original_response(embed=embed)


# ============================================================================
# 🧪 СЛЭШ-КОМАНДА "/тест" (ТРЕБУЕТ РОЛЬ)
# ============================================================================

@bot.slash_command(name="тест", description="Быстрая проверка доступности моделей")
async def slash_test(
        interaction: disnake.CommandInteraction,
        прокси: str = commands.Param(description="Использовать прокси?", choices=["Да", "Нет"], default="Нет")
):
    if not await check_access(interaction):
        return

    use_proxy = (прокси == "Да")
    proxy_status_text = "с прокси 🟢" if use_proxy else "без прокси 🔴"

    await interaction.response.defer()
    msg = await interaction.edit_original_response(
        content=f" Быстрая проверка доступности моделей ({proxy_status_text})...")

    current_proxy = get_random_proxy(use_proxy)
    success, ans, lat = await make_g4f_request("PollinationsAI", "deepseek-r1", "ok", timeout=10,
                                               proxy_url=current_proxy)

    if success:
        await msg.edit(
            content=f"✅ **G4F работает!**\nОтвет получен за `{lat:.2f}с`.\nРежим: {proxy_status_text}\nСтатистика сохраняется в БД при команде `/скажи`.")
    else:
        await msg.edit(
            content=f"❌ **G4F недоступен.**\nОшибка: {ans}\nРежим: {proxy_status_text}\nПопробуйте позже или проверьте логи.")


# ============================================================================
# ️ АДМИН КОМАНДА (ЛОГИ)
# ============================================================================

@bot.command(name="скачать_ошибки")
async def скачать_ошибки(ctx):
    if ctx.author.id != OWNER_ID:
        await ctx.send("❌ Доступ запрещён.", ephemeral=True)
        return
    if os.path.exists('bot_errors.log'):
        await ctx.send(file=disnake.File('bot_errors.log'))
    else:
        await ctx.send("❌ Файл логов пуст или не найден.")


# ============================================================================
# СОБЫТИЯ
# ============================================================================

@bot.event
async def on_ready():
    logger.info(f"🐕 Бот {bot.user} готов! (Railway: {IS_RAILWAY})")
    if REQUIRED_ROLE_ID == 0:
        logger.warning("⚠️ ВНИМАНИЕ: ROLE_ID не установлен. Доступ открыт всем (кроме админок).")
    else:
        logger.info(f"🔒 Ограничение доступа включено. Role ID: {REQUIRED_ROLE_ID}")

    asyncio.create_task(fetch_free_proxies())
    # disnake автоматически регистрирует слэш-команды — sync_commands не нужен!




@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound): return
    logger.error(f"Ошибка команды {ctx.command}: {error}", exc_info=True)
    with open('bot_errors.log', 'a', encoding='utf-8') as f:
        f.write(f"\n[{datetime.now()}] ERROR: {error}\n")

    if hasattr(ctx, 'author'):
        if ctx.author.id == OWNER_ID:
            await ctx.send(f"️ Произошла ошибка: {str(error)[:100]}", delete_after=10)


if __name__ == "__main__":
    try:
        logger.info(" Запуск бота...")
        bot.run(os.getenv("DISCORD_TOKEN"))
    except Exception as e:
        logger.critical(f" Критическая ошибка при запуске: {e}", exc_info=True)