import g4f
import disnake
import random
import re
import os
import json
import logging
import time
from datetime import datetime
from dotenv import load_dotenv
import asyncio
from typing import Tuple, List, Dict, Any
from disnake.ext import commands
from openai import OpenAI
import aiohttp

# ============================================================================
# 🔧 RAILWAY-ОПТИМИЗАЦИИ
# ============================================================================

IS_RAILWAY = os.getenv('RAILWAY', '').lower() == 'true'
DEFAULT_MAX_CONCURRENT = 2 if IS_RAILWAY else 10
DEFAULT_REQUESTS_PER_COMBO = 1 if IS_RAILWAY else 2

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_errors.log', encoding='utf-8', delay=True)
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

intents = disnake.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="псинка ", intents=intents)

# ============================================================================
# 🛡️ БЕЗОПАСНАЯ ЗАПИСЬ ФАЙЛОВ
# ============================================================================

def safe_write_file(filepath: str, content: str, max_size_mb: int = 5):
    try:
        if os.path.exists(filepath):
            size_mb = os.path.getsize(filepath) / 1024 / 1024
            if size_mb > max_size_mb:
                logger.warning(f"⚠️ Файл {filepath} слишком большой ({size_mb:.1f} МБ), пропускаем запись")
                return False
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception as e:
        logger.warning(f"⚠️ Не удалось записать {filepath}: {e} (это нормально на Railway)")
        return False

def safe_read_json(filepath: str, default: Any = None):
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"⚠️ Не удалось прочитать {filepath}: {e}")
    return default

# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

async def make_g4f_request(provider_name: str, model: str, prompt: str,
                           timeout: float = 40.0, system_prompt: str = None) -> Tuple[bool, str, float]:
    elapsed = 0.0
    start = time.time()
    try:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        try:
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
                    logger.debug(f"✅ g4f {provider_name}/{model} — {elapsed:.2f}s")
                    return True, answer.strip(), elapsed
            elapsed = time.time() - start
            logger.debug(f"⚠️ g4f {provider_name}/{model} — пустой ответ")
            return False, "Пустой ответ", elapsed
        except asyncio.TimeoutError:
            elapsed = time.time() - start
            logger.debug(f"⏰ g4f {provider_name}/{model} — таймаут {timeout}с")
            return False, f"Таймаут {timeout}с", elapsed
        except Exception as e:
            elapsed = time.time() - start
            error_msg = str(e)[:100]
            logger.debug(f"❌ g4f {provider_name}/{model} — ошибка: {type(e).__name__}: {error_msg}")
            return False, error_msg, elapsed
    except Exception as e:
        elapsed = time.time() - start
        error_msg = str(e)[:100]
        logger.error(f"❌ g4f критическая ошибка {provider_name}/{model}: {type(e).__name__}: {error_msg}")
        return False, error_msg, elapsed

async def get_openrouter_free_models() -> List[str]:
    openrouter_token = os.getenv('OPENR_TOKEN')
    if not openrouter_token:
        logger.warning("⚠️ OPENR_TOKEN не найден — используем статический список")
        return OPENROUTER_FREE_MODELS
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://openrouter.ai/api/v1/models", headers={"Authorization": f"Bearer {openrouter_token}"}) as response:
                if response.status == 200:
                    data = await response.json()
                    free_models = []
                    for model in data.get('data', []):
                        pricing = model.get('pricing', {})
                        if pricing.get('prompt', '0') == '0' or pricing.get('prompt', 0) == 0:
                            model_id = model.get('id', '')
                            if model_id and ':free' in model_id:
                                free_models.append(model_id)
                    if free_models:
                        logger.info(f"🌐 Получено {len(free_models)} бесплатных моделей от OpenRouter API")
                        return free_models[:15]
                    else:
                        logger.warning("⚠️ Не найдено бесплатных моделей через API")
                        return OPENROUTER_FREE_MODELS
                else:
                    logger.warning(f"⚠️ OpenRouter API вернул статус {response.status}")
                    return OPENROUTER_FREE_MODELS
    except Exception as e:
        logger.warning(f"⚠️ Не удалось получить модели OpenRouter: {e}")
        return OPENROUTER_FREE_MODELS

async def test_openrouter_model(model: str, prompt: str, timeout: float = 35.0):
    openrouter_token = os.getenv('OPENR_TOKEN')
    if not openrouter_token:
        return False, "OPENR_TOKEN не найден в .env", 0.0
    elapsed = 0.0
    start = time.time()
    try:
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=openrouter_token)
        loop = asyncio.get_running_loop()
        google_models = ["gemma", "google/"]
        is_google_model = any(g in model.lower() for g in google_models)
        def make_request():
            messages = []
            if not is_google_model:
                messages.append({"role": "system", "content": "Отвечай максимально кратко. Если это тест — просто напиши 'ок'."})
            messages.append({"role": "user", "content": prompt})
            return client.chat.completions.create(model=model, messages=messages, timeout=timeout, extra_headers={"HTTP-Referer": "https://github.com/psiiinka-bot", "X-OpenRouter-Title": "PsIInka Bot"})
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await asyncio.wait_for(loop.run_in_executor(None, make_request), timeout=timeout)
                if response.choices and len(response.choices) > 0:
                    answer = response.choices[0].message.content
                    elapsed = time.time() - start
                    if answer and answer.strip():
                        answer_lower = answer.lower().strip()
                        if 'ок' in answer_lower or 'ok' in answer_lower or len(answer) < 50:
                            logger.info(f"✅ OpenRouter/{model} — {elapsed:.2f}s: {answer[:30]}")
                            return True, answer.strip(), elapsed
                        else:
                            return True, answer.strip(), elapsed
                    elapsed = time.time() - start
                    return False, "Пустой ответ", elapsed
                else:
                    elapsed = time.time() - start
                    return False, "Нет choices в ответе", elapsed
            except Exception as e:
                error_str = str(e).lower()
                if '429' in error_str or 'rate limit' in error_str:
                    wait_time = 2 ** attempt
                    logger.warning(f"⚠️ OpenRouter 429 — ожидание {wait_time}с (попытка {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                    continue
                elif '404' in error_str or 'not found' in error_str:
                    logger.warning(f"⚠️ OpenRouter 404 — модель {model} не найдена (пропускаем)")
                    return False, "Модель недоступна", elapsed
                elif '400' in error_str or 'invalid' in error_str:
                    logger.warning(f"⚠️ OpenRouter 400 — модель {model} не поддерживает запрос (пропускаем)")
                    return False, "Модель не поддерживает запрос", elapsed
                else:
                    raise
        elapsed = time.time() - start
        return False, "Превышено количество попыток", elapsed
    except asyncio.TimeoutError:
        elapsed = time.time() - start
        logger.warning(f"⏰ OpenRouter/{model} — таймаут {timeout}с")
        return False, f"Таймаут {timeout}с", elapsed
    except Exception as e:
        elapsed = time.time() - start
        logger.error(f"❌ OpenRouter/{model} — ошибка: {type(e).__name__}: {e}")
        return False, str(e)[:100], elapsed

def get_g4f_providers():
    providers = []
    skip = {'Provider', 'BaseProvider', 'RetryProvider', 'RetryUntilSuccessful', 'CustomProvider', 'OpenaiChat', 'FlowAI', 'Vercel', 'Yqcloud'}
    for attr_name in dir(g4f.Provider):
        if attr_name.startswith('_') or attr_name in skip:
            continue
        try:
            attr = getattr(g4f.Provider, attr_name)
            if isinstance(attr, type) and hasattr(attr, 'working_url'):
                providers.append(attr_name)
        except:
            continue
    if not providers:
        providers = ["PollinationsAI", "Perplexity", "PollinationsAI", "DeepInfra", "Together", "Qwen", "Grok", "Copilot"]
        logger.info("⚠️ Используем резервный список провайдеров")
    return providers

def get_g4f_models():
    models = []
    try:
        if hasattr(g4f, 'Model'):
            for attr_name in dir(g4f.Model):
                if not attr_name.startswith('_'):
                    try:
                        attr = getattr(g4f.Model, attr_name)
                        if isinstance(attr, str):
                            models.append(attr)
                    except:
                        continue
        if not models and hasattr(g4f, 'models'):
            try:
                for model in g4f.models:
                    if hasattr(model, 'name'):
                        models.append(model.name)
                    elif isinstance(model, str):
                        models.append(model)
            except:
                pass
    except Exception as e:
        logger.warning(f"Не удалось получить модели автоматически: {e}")
    if not models:
        models = ["gpt-4o", "gpt-4o-mini", "gpt-4", "llama-3-70b", "llama-3.1-70b", "qwen-2.5-72b", "deepseek-v3", "deepseek-r1", "gemini-2.0-flash", "mistral-7b", "mixtral-8x7b", "sonar", "sonar-pro"]
        logger.info("⚠️ Используем резервный список моделей")
    return list(set(models))

def save_test_results(results, total_combinations, elapsed_total, test_mode_name="unknown"):
    successful = [r for r in results if r['success']]
    successful_sorted = sorted(successful, key=lambda x: x['time'] if x['time'] else 999)
    top_50 = []
    for idx, r in enumerate(successful_sorted[:50]):
        top_50.append({'provider': r['provider'], 'model': r['model'], 'time': r['time'], 'rank': idx + 1})
    test_record = {'timestamp': datetime.now().isoformat(), 'test_mode_name': test_mode_name, 'total_combinations': total_combinations, 'successful_count': len(successful), 'elapsed_seconds': elapsed_total, 'top_combinations': top_50}
    history_file = 'test_history.json'
    history = safe_read_json(history_file, [])
    history.append(test_record)
    history = history[-10:]
    safe_write_file(history_file, json.dumps(history, ensure_ascii=False, indent=2))
    txt_file = 'test_latest_report.txt'
    txt_content = f"=== ТЕСТ ЗАВЕРШЁН {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n\n"
    txt_content += f"Всего комбинаций: {total_combinations}\n"
    txt_content += f"Успешно: {len(successful)}\n"
    txt_content += f"Время теста: {elapsed_total:.0f}с\n\n"
    txt_content += "ТОП-50 САМЫХ БЫСТРЫХ:\n"
    txt_content += "-" * 60 + "\n"
    for r in top_50:
        txt_content += f"{r['rank']:3}. {r['provider']:<16} {r['model']:<20} {r['time']:.2f}s\n"
    safe_write_file(txt_file, txt_content)
    logger.info(f"💾 Результаты теста сохранены (или пропущены на Railway)")
    return top_50

def get_default_candidates() -> List[Tuple[str, str]]:
    return [("PollinationsAI", "deepseek-v3"), ("PollinationsAI", "deepseek-r1"), ("PollinationsAI", "sonar"), ("DeepInfra", "llama-3.1-70b"), ("Together", "qwen-2.5-72b"), ("Perplexity", "sonar"), ("Perplexity", "sonar-pro"), ("HuggingSpace", "deepseek-v3")]

def get_best_combinations_from_history(max_combinations: int = 5) -> List[Tuple[str, str]]:
    history_file = 'test_history.json'
    history = safe_read_json(history_file, [])
    if not history:
        logger.warning("📁 История тестов пуста — используем резервный список")
        return get_default_candidates()
    last_3_tests = history[-3:]
    logger.info(f"📊 Анализирую последние {len(last_3_tests)} тестов...")
    combination_scores = {}
    for test in last_3_tests:
        for combo in test.get('top_combinations', []):
            key = (combo['provider'], combo['model'])
            if key[0] in ["Yqcloud", "Grok", "Copilot", "Qwen"]:
                continue
            time_val = combo['time']
            if key not in combination_scores:
                combination_scores[key] = {'times': [], 'ranks': []}
            combination_scores[key]['times'].append(time_val)
            combination_scores[key]['ranks'].append(combo['rank'])
    scored_combinations = []
    for (provider, model), data in combination_scores.items():
        avg_time = sum(data['times']) / len(data['times'])
        avg_rank = sum(data['ranks']) / len(data['ranks'])
        stability_bonus = len(data['times']) * 0.1
        scored_combinations.append({'provider': provider, 'model': model, 'avg_time': avg_time, 'avg_rank': avg_rank, 'appearances': len(data['times']), 'score': avg_time - stability_bonus})
    scored_combinations.sort(key=lambda x: x['score'])
    top_combos = scored_combinations[:max_combinations]
    logger.info(f"🏆 Выбрано {len(top_combos)} лучших комбинаций из истории тестов")
    return [(c['provider'], c['model']) for c in top_combos]

def generate_test_report(results, total_tests):
    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]
    report = f"📊 **ПОЛНЫЙ ОТЧЁТ ТЕСТИРОВАНИЯ** ({total_tests} комбинаций)\n"
    report += f"✅ **Успешно:** {len(successful)} | ❌ **Ошибок:** {len(failed)}\n\n"
    if successful:
        successful_sorted = sorted(successful, key=lambda x: x['time'] if x['time'] else 999)
        report += "**✅ ВСЕ РАБОЧИЕ КОМБИНАЦИИ:**\n"
        report += "```\n"
        report += f"{'№':<4} {'Провайдер':<16} {'Модель':<20} {'Время':<8}\n"
        report += "-" * 52 + "\n"
        for idx, r in enumerate(successful_sorted, 1):
            model_short = r['model'][:20] if len(r['model']) > 20 else r['model']
            provider_short = r['provider'][:16] if len(r['provider']) > 16 else r['provider']
            time_str = f"{r['time']:.2f}s" if r['time'] else "N/A"
            report += f"{idx:<4} {provider_short:<16} {model_short:<20} {time_str:<8}\n"
        report += "```\n"
    else:
        report += "❌ **Нет успешных комбинаций.**\n\n"
    if failed:
        error_groups = {}
        for r in failed:
            prov = r['provider']
            err = r['error'] if r['error'] else "Unknown"
            if prov not in error_groups:
                error_groups[prov] = {'errors': {}, 'count': 0}
            error_groups[prov]['count'] += 1
            if err not in error_groups[prov]['errors']:
                error_groups[prov]['errors'][err] = 0
            error_groups[prov]['errors'][err] += 1
        report += "\n**❌ ОШИБКИ ПО ПРОВАЙДЕРАМ:**\n```\n"
        for prov, data in sorted(error_groups.items(), key=lambda x: -x[1]['count']):
            report += f"{prov}: {data['count']} неудач\n"
            err_items = list(data['errors'].items())[:3]
            for err, count in err_items:
                short_err = err[:40] + "..." if len(err) > 40 else err
                report += f"  └─ {short_err} ({count}x)\n"
        report += "```\n"
        report += "⚠️ **Полные логи ошибок:** файл `bot_errors.log`"
    return report

def generate_test_report_embed(results, total_tests, elapsed_total, test_mode_name):
    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]
    COLOR_SUCCESS = 0x00FF88
    COLOR_ERROR = 0xFF4444
    COLOR_WARNING = 0xFFAA00
    if len(successful) == 0:
        color = COLOR_ERROR
    elif len(successful) < total_tests * 0.3:
        color = COLOR_WARNING
    else:
        color = COLOR_SUCCESS
    embed = disnake.Embed(title="📊 Отчёт о тестировании моделей", description=f"**Режим:** `{test_mode_name}`\n**Время:** `{elapsed_total:.0f}с` ({elapsed_total / 60:.1f} мин)", color=color, timestamp=datetime.now())
    success_rate = (len(successful) / total_tests * 100) if total_tests > 0 else 0
    embed.add_field(name="📊 Статистика", value=f"**Всего:** `{total_tests}`\n**✅ Успешно:** `{len(successful)}`\n**❌ Ошибок:** `{len(failed)}`\n**📈 Успех:** `{success_rate:.0f}%`", inline=True)
    if successful:
        top_3 = sorted(successful, key=lambda x: x['time'] if x['time'] else 999)[:3]
        top_text = ""
        medals = ["🥇", "🥈", "🥉"]
        for i, r in enumerate(top_3):
            provider_short = r['provider'][:15] if len(r['provider']) > 15 else r['provider']
            model_short = r['model'][:18] if len(r['model']) > 18 else r['model']
            top_text += f"{medals[i]} `{provider_short}` / `{model_short}` — `{r['time']:.2f}с`\n"
        embed.add_field(name="🏆 Топ-3 быстрых", value=top_text if top_text else "❌ Нет данных", inline=True)
    else:
        embed.add_field(name="🏆 Топ-3 быстрых", value="❌ Нет успешных", inline=True)
    embed.add_field(name="📁 Файлы", value="📄 `test_latest_report.txt`\n💾 `test_history.json`", inline=True)
    if successful:
        successful_sorted = sorted(successful, key=lambda x: x['time'] if x['time'] else 999)[:10]
        table_header = f"{'№':<3} {'Провайдер':<16} {'Модель':<18} {'Время':<7}\n"
        table_separator = "—" * 48 + "\n"
        table_rows = ""
        for idx, r in enumerate(successful_sorted, 1):
            model_short = r['model'][:18] if len(r['model']) > 18 else r['model']
            provider_short = r['provider'][:16] if len(r['provider']) > 16 else r['provider']
            time_str = f"{r['time']:.2f}с" if r['time'] else "N/A"
            table_rows += f"{idx:<3} {provider_short:<16} {model_short:<18} {time_str:<7}\n"
        table_content = table_header + table_separator + table_rows
        embed.add_field(name="✅ Рабочие (Топ-10)", value=f"```\n{table_content}```" if len(table_content) < 1024 else "⚠️ Смотрите файл `test_latest_report.txt`", inline=False)
    if failed:
        error_groups = {}
        for r in failed:
            prov = r['provider']
            err = r['error'] if r['error'] else "Unknown"
            if prov not in error_groups:
                error_groups[prov] = {'count': 0, 'errors': {}}
            error_groups[prov]['count'] += 1
            if err not in error_groups[prov]['errors']:
                error_groups[prov]['errors'][err] = 0
            error_groups[prov]['errors'][err] += 1
        sorted_errors = sorted(error_groups.items(), key=lambda x: -x[1]['count'])[:3]
        error_text = ""
        for prov, data in sorted_errors:
            error_text += f"**🔴 {prov}** — `{data['count']}` неудач\n"
            err_items = list(data['errors'].items())[:1]
            for err, count in err_items:
                short_err = err[:30] + "..." if len(err) > 30 else err
                error_text += f"  └─ `{short_err}`\n"
        embed.add_field(name="❌ Ошибки", value=error_text if error_text else "❌ Нет данных", inline=False)
    is_openrouter_only = all(r['provider'] == 'OpenRouter' for r in results)
    if len(successful) == 0:
        if is_openrouter_only:
            recommendations = "🔴 **Все модели OpenRouter недоступны**\n• Проверьте API ключ OPENR_TOKEN 🔑\n• Проверьте интернет 🌐"
        else:
            recommendations = "🔴 **Все провайдеры недоступны**\n• Проверьте интернет 🌐\n• Обновите g4f: `pip install g4f --upgrade` 📦"
    elif len(successful) < 3:
        recommendations = "🟡 **Мало рабочих провайдеров**\n• Запустите `псинка тест quick` 🔍\n• Некоторые провайдеры временно недоступны ⏳"
    else:
        recommendations = "🟢 **Соединение в норме**\n• Используйте `псинка скажи` для запросов 💬\n• Лучшие комбинации сохранены в истории 💾"
    embed.add_field(name="💡 Рекомендации", value=recommendations, inline=False)
    embed.set_footer(text="ПсИИнка бот | g4f тестирование")
    return embed

# ============================================================================
# СПИСКИ МОДЕЛЕЙ И ПРОВАЙДЕРОВ
# ============================================================================

OPENROUTER_FREE_MODELS = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "stepfun/step-3.5-flash:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "meta-llama/llama-3-8b-instruct:free",
    "qwen/qwen-2.5-72b-instruct:free",
    "deepseek/deepseek-chat:free",
    "mistralai/mistral-7b-instruct:free",
]

EXPRESS_TEST_PROVIDERS = [
    ("PollinationsAI", "sonar"),
    ("PollinationsAI", "deepseek-r1"),
    ("DeepInfra", "llama-3.1-70b"),
    ("Perplexity", "sonar"),
    ("HuggingSpace", "deepseek-v3"),
]

QUICK_TEST_PROVIDERS = [
    "PollinationsAI", "HuggingSpace", "Qwen", "Blackbox",
    "DuckDuckGo", "FreeGPT", "Vercel",
]

QUICK_TEST_MODELS = [
    "gpt-4o", "gpt-4o-mini",
    "llama-3.1-70b", "llama-3-70b",
    "qwen-2.5-72b",
    "deepseek-v3", "deepseek-r1",
    "sonar", "sonar-pro",
    "mistral-7b", "mixtral-8x7b",
]

# ============================================================================
# СОБЫТИЯ И КОМАНДЫ БОТА
# ============================================================================

@bot.event
async def on_ready():
    logger.info(f"🐍 Бот {bot.user} готов к работе! (Python {disnake.__version__})")
    logger.info(f"📦 g4f версия: {getattr(g4f, '__version__', 'unknown')}")
    if IS_RAILWAY:
        logger.info("🚂 Запущен на Railway — оптимизации активны")

@bot.command()
async def погавкай(ctx):
    try:
        await ctx.reply(f'Иди нахуй! У меня пинг {round(bot.latency * 1000)} мс')
    except Exception as e:
        logger.error(f"Ошибка в команде погавкай: {e}", exc_info=True)

# ============================================================================
# CLASS VIEW С КНОПКАМИ (БЕЗ ПОЛНОГО ТЕСТА)
# ============================================================================

class TestModeView(disnake.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.selected_mode = None

    @disnake.ui.button(label="⚡ Экспресс", style=disnake.ButtonStyle.green, emoji="🚀", custom_id="test_express")
    async def express_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        self.selected_mode = "express"
        await interaction.response.defer()
        await self.start_test("express")

    @disnake.ui.button(label="⚡ Быстрый", style=disnake.ButtonStyle.green, emoji="⚡", custom_id="test_quick")
    async def quick_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        self.selected_mode = "quick"
        await interaction.response.defer()
        await self.start_test("quick")

    @disnake.ui.button(label="🌐 OpenRouter", style=disnake.ButtonStyle.blurple, emoji="🔮", custom_id="test_openrouter")
    async def openrouter_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        self.selected_mode = "openrouter"
        await interaction.response.defer()
        await self.start_test("openrouter")

    @disnake.ui.button(label="🎯 Всё", style=disnake.ButtonStyle.red, emoji="🎲", custom_id="test_all")
    async def all_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        self.selected_mode = "all"
        await interaction.response.defer()
        await self.start_test("all")

    @disnake.ui.button(label="🤖 Авто", style=disnake.ButtonStyle.secondary, emoji="🔄", custom_id="test_auto")
    async def auto_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        self.selected_mode = "auto"
        await interaction.response.defer()
        await self.start_test("auto")

    async def start_test(self, mode: str):
        for child in self.children:
            child.disabled = True
        try:
            await self.ctx.message.edit(view=self)
        except:
            pass
        await run_test_command(self.ctx, mode)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            await self.ctx.message.edit(view=self)
        except:
            pass

# ============================================================================
# ФУНКЦИЯ ЗАПУСКА ТЕСТА (БЕЗ ПОЛНОГО ТЕСТА)
# ============================================================================

async def run_test_command(ctx, mode: str):
    try:
        progress_msg = await ctx.send("🔄 **Тестирование моделей запущено**\n`Определяю режим теста...`")
        logger.info("🚀 Начало тестирования моделей")
        start_time = time.time()
        test_prompt = "Ответь только словом \"ок\", если до тебя дошло моё сообщение"
        mode = mode.lower()

        if mode == "express":
            all_combinations = EXPRESS_TEST_PROVIDERS.copy()
            test_mode_name = "🟣 ЭКСПРЕСС ТЕСТ"
            test_openrouter = False
            MAX_CONCURRENT_REQUESTS = int(os.getenv('MAX_CONCURRENT', DEFAULT_MAX_CONCURRENT))
            REQUESTS_PER_COMBINATION = int(os.getenv('REQUESTS_PER_COMBO', DEFAULT_REQUESTS_PER_COMBO))
            REQUEST_TIMEOUT = 15.0
            BATCH_SIZE = 2
            timeout = 120.0
        elif mode == "quick":
            providers_to_test = QUICK_TEST_PROVIDERS
            all_models = QUICK_TEST_MODELS
            test_mode_name = "🟢 БЫСТРЫЙ ТЕСТ"
            test_openrouter = False
            MAX_CONCURRENT_REQUESTS = int(os.getenv('MAX_CONCURRENT', min(10, DEFAULT_MAX_CONCURRENT)))
            REQUESTS_PER_COMBINATION = int(os.getenv('REQUESTS_PER_COMBO', DEFAULT_REQUESTS_PER_COMBO))
            REQUEST_TIMEOUT = 25.0
            BATCH_SIZE = 5
            timeout = 300.0
        elif mode == "openrouter":
            await progress_msg.edit(content=f"🔄 **Тестирование моделей запущено**\n`Получаю актуальные бесплатные модели OpenRouter...`")
            all_models = await get_openrouter_free_models()
            providers_to_test = ["OpenRouter"]
            test_mode_name = "🟣 ТЕСТ OPENROUTER"
            test_openrouter = True
            MAX_CONCURRENT_REQUESTS = int(os.getenv('MAX_CONCURRENT', 2))
            REQUESTS_PER_COMBINATION = 1
            REQUEST_TIMEOUT = 35.0
            BATCH_SIZE = 2
            timeout = 400.0
        elif mode == "all":
            providers_to_test = QUICK_TEST_PROVIDERS
            all_models = QUICK_TEST_MODELS
            test_mode_name = "🔵 ТЕСТ ВСЕГО"
            test_openrouter = True
            MAX_CONCURRENT_REQUESTS = int(os.getenv('MAX_CONCURRENT', 5))
            REQUESTS_PER_COMBINATION = int(os.getenv('REQUESTS_PER_COMBO', DEFAULT_REQUESTS_PER_COMBO))
            REQUEST_TIMEOUT = 45.0
            BATCH_SIZE = 5
            timeout = 600.0
        else:  # auto
            providers_to_test = get_g4f_providers()
            all_models = get_g4f_models()
            test_mode_name = "🔵 АВТО-СКАНИРОВАНИЕ"
            test_openrouter = False
            MAX_CONCURRENT_REQUESTS = int(os.getenv('MAX_CONCURRENT', 8))
            REQUESTS_PER_COMBINATION = int(os.getenv('REQUESTS_PER_COMBO', DEFAULT_REQUESTS_PER_COMBO))
            REQUEST_TIMEOUT = 45.0
            BATCH_SIZE = 5
            timeout = 600.0

        if mode == "express":
            total_combinations = len(all_combinations)
        else:
            all_combinations = [(p, m) for p in providers_to_test for m in all_models]
            if test_openrouter and mode != "openrouter":
                for model in OPENROUTER_FREE_MODELS:
                    all_combinations.append(("OpenRouter", model))
            total_combinations = len(all_combinations)

        total_requests = total_combinations * REQUESTS_PER_COMBINATION
        logger.info(f"📋 Режим теста: {test_mode_name}")
        logger.info(f"🎯 Всего комбинаций: {total_combinations}")
        logger.info(f"🎯 Всего запросов: {total_requests}")
        await progress_msg.edit(content=f"🔄 **Тестирование моделей запущено**\n`Режим: {test_mode_name}`")

        results = []
        completed_count = 0
        combo_lock = asyncio.Lock()
        last_heartbeat = time.time()

        async def heartbeat_keeper():
            nonlocal last_heartbeat
            while True:
                await asyncio.sleep(25)
                last_heartbeat = time.time()
                logger.debug("💓 Heartbeat keeper активен")

        heartbeat_task = asyncio.create_task(heartbeat_keeper())

        async def update_progress(completed: int, total: int, status: str = "🔄", extra: str = ""):
            nonlocal progress_msg, last_heartbeat
            if not progress_msg:
                return
            try:
                percentage = (completed / total) * 100 if total > 0 else 0
                bar_len = 20
                filled = int(bar_len * completed / total) if total > 0 else 0
                bar = "█" * filled + "░" * (bar_len - filled)
                elapsed = time.time() - start_time
                eta = (elapsed / completed * (total - completed)) if completed > 0 else 0
                last_heartbeat = time.time()
                content = f"{status} **{test_mode_name}**\n[{bar}] `{completed}/{total}` ({percentage:.1f}%)\n📦 Готово: {len(results)}/{total_combinations}\n⏳ Прошло: {elapsed:.0f}с | ETA: {eta:.0f}с"
                if extra:
                    content += f"\n{extra}"
                await progress_msg.edit(content=content)
                await asyncio.sleep(0)
            except Exception:
                progress_msg = None

        async def test_single_request(provider: str, model: str) -> dict:
            if provider == "OpenRouter":
                success, answer_or_error, elapsed = await test_openrouter_model(model, test_prompt, REQUEST_TIMEOUT)
            else:
                success, answer_or_error, elapsed = await make_g4f_request(provider, model, test_prompt, REQUEST_TIMEOUT)
            return {'success': success, 'time': elapsed if success else None, 'answer_len': len(answer_or_error) if success else 0, 'error': answer_or_error if not success else None}

        async def process_combination(provider: str, model: str):
            nonlocal completed_count, last_heartbeat
            tasks = [test_single_request(provider, model) for _ in range(REQUESTS_PER_COMBINATION)]
            task_results = await asyncio.gather(*tasks, return_exceptions=True)
            success = False
            min_time = None
            errors = []
            for res in task_results:
                if isinstance(res, Exception):
                    errors.append(str(res)[:80])
                    continue
                if res.get('success'):
                    success = True
                    if min_time is None or res['time'] < min_time:
                        min_time = res['time']
                else:
                    errors.append(res.get('error', 'Unknown'))
            async with combo_lock:
                results.append({'provider': provider, 'model': model, 'time': min_time, 'success': success, 'response_length': 0 if not success else 100, 'error': errors[0] if errors and not success else None})
                completed_count += 1
                last_heartbeat = time.time()
                if completed_count % BATCH_SIZE == 0:
                    await update_progress(completed_count, total_requests)

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        async def limited_task(coro):
            async with semaphore:
                return await coro
        all_tasks = [limited_task(process_combination(p, m)) for p, m in all_combinations]

        try:
            await asyncio.wait_for(asyncio.gather(*all_tasks, return_exceptions=True), timeout=timeout)
        except asyncio.TimeoutError:
            await update_progress(completed_count, total_requests, "⚠️", f"Таймаут {int(timeout / 60)} минут")
            logger.warning("⏰ Таймаут тестирования")

        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

        elapsed_total = time.time() - start_time
        await update_progress(completed_count, total_requests, "✅", f"⏱ Всего: {elapsed_total:.0f}с ({elapsed_total / 60:.1f} мин)")
        save_test_results(results, total_combinations, elapsed_total, test_mode_name)
        txt_report = generate_test_report(results, total_combinations)
        txt_report += f"\n⏱ **Время теста:** {elapsed_total:.0f}с ({elapsed_total / 60:.1f} мин)\n"
        txt_report += f"🔧 **Режим:** {test_mode_name}\n"
        safe_write_file('test_full_report.txt', txt_report)
        embed = generate_test_report_embed(results, total_combinations, elapsed_total, test_mode_name)
        if progress_msg:
            try:
                await progress_msg.edit(content="✅ **Тест завершён!**", embed=embed)
                return
            except Exception as e:
                logger.warning(f"Не удалось отправить embed: {e}")
                progress_msg = None
        await ctx.send(embed=embed)
    except Exception as e:
        logger.error(f"Критическая ошибка в команде тест: {e}", exc_info=True)
        await ctx.send(f"[CRIT] {str(e)[:100]}")

# ============================================================================
# КОМАНДА "тест" С КНОПКАМИ (ОБНОВЛЁННОЕ ОПИСАНИЕ)
# ============================================================================

@bot.command(name="тест")
async def тест(ctx, mode: str = None):
    if mode:
        await run_test_command(ctx, mode.lower())
        return
    embed = disnake.Embed(
        title="🐕 ПсИИнка: Выбор режима тестирования",
        description=(
            "**Выберите режим тестирования моделей:**\n\n"
            "🚀 **Экспресс** — 5 провайдеров × 1 запрос (~15 сек)\n"
            "  `Быстрая диагностика перед командой `скажи`\n\n"
            "🚀 **Быстрый** — 8 провайдеров × 11 моделей (~5 мин)\n"
            "  `Идеально для быстрой проверки рабочих комбинаций`\n\n"
            "🔮 **OpenRouter** — бесплатные модели OpenRouter (~7 мин)\n"
            "  `Динамическое получение актуальных бесплатных моделей`\n\n"
            "🎲 **Всё** — g4f + OpenRouter вместе (~10 мин)\n"
            "  `Комбинированный тест всех доступных источников`\n\n"
            "🔄 **Авто** — автоматическое сканирование g4f (~10 мин)\n"
            "  `Бот сам определит доступные провайдеры и модели`\n\n"
            "⏱️ **Время на выбор:** 5 минут"
        ),
        color=0xFF8844,
        timestamp=datetime.now()
    )
    embed.add_field(name="📊 Что будет протестировано", value="• **Скорость ответа** каждой комбинации\n• **Стабильность соединения** с провайдерами\n• **Качество ответов** (проверка на русский язык)\n• **Работоспособность** моделей для команды `скажи`", inline=False)
    embed.add_field(name="💾 Результаты", value="• `test_history.json` — история для команды `скажи`\n• `test_latest_report.txt` — последний отчёт", inline=False)
    embed.set_footer(text="🐾 ПсИИнка бот | g4f тестирование моделей")
    embed.set_thumbnail(url="https://i.imgur.com/7Q8vK9L.png")
    view = TestModeView(ctx)
    await ctx.send(embed=embed, view=view)

@bot.command(name="кубик")
async def кубик(ctx, *, max_value: str):
    try:
        max_value = int(max_value)
        if max_value < 1:
            raise ValueError("Значение должно быть больше 0!")
        if max_value > 1000:
            max_value = 1000
        result = random.randint(1, max_value)
        await ctx.send(f"🎲 Выпало {result}")
    except ValueError:
        await ctx.send("❌ Введите корректное число")
    except Exception as e:
        logger.error(f"Ошибка в команде кубик: {e}", exc_info=True)
        await ctx.send("❌ Внутренняя ошибка")

@bot.command(name="лучшие")
async def лучшие(ctx, test_type: str = "all"):
    try:
        history_file = 'test_history.json'
        if not os.path.exists(history_file):
            await ctx.send("❌ История тестов пуста. Запустите `псинка тест quick` сначала.")
            return
        history = safe_read_json(history_file, [])
        if not history:
            await ctx.send("❌ История тестов пуста. Запустите `псинка тест quick` сначала.")
            return
        test_type = test_type.lower()
        type_keywords = {"all": ["🟢", "🟣", "🔵", "БЫСТРЫЙ", "OPENROUTER", "АВТО", "ВСЕГО"], "quick": ["🟢", "БЫСТРЫЙ"], "openrouter": ["🟣", "OPENROUTER"], "auto": ["🔵", "АВТО", "АВТО-СКАНИРОВАНИЕ"]}
        keywords = type_keywords.get(test_type, type_keywords["all"])
        filtered_tests = []
        type_counts = {"🟢": 0, "🟣": 0, "🔵": 0}
        for test in reversed(history):
            test_mode = test.get('test_mode_name', '')
            emoji = None
            for e in ["🟢", "🟣", "🔵"]:
                if e in test_mode:
                    emoji = e
                    break
            if not emoji:
                total = test.get('total_combinations', 0)
                if total <= 10:
                    emoji = "🟣"
                elif total <= 100:
                    emoji = "🟢"
                else:
                    emoji = "🔵"
            matches_type = any(kw in test_mode.upper() for kw in keywords) or emoji in keywords
            if matches_type:
                if emoji and emoji in type_counts:
                    if type_counts[emoji] < 5:
                        filtered_tests.append(test)
                        type_counts[emoji] += 1
                else:
                    filtered_tests.append(test)
                if len(filtered_tests) >= 20:
                    break
        if not filtered_tests:
            await ctx.send(f"❌ Нет тестов типа `{test_type}` в истории.")
            return
        combination_stats = {}
        for test in filtered_tests:
            for combo in test.get('top_combinations', []):
                key = (combo['provider'], combo['model'])
                if key not in combination_stats:
                    combination_stats[key] = {'times': [], 'ranks': [], 'test_count': 0, 'first_seen': test.get('timestamp', ''), 'last_seen': test.get('timestamp', '')}
                combination_stats[key]['times'].append(combo['time'])
                combination_stats[key]['ranks'].append(combo['rank'])
                combination_stats[key]['test_count'] += 1
                combination_stats[key]['last_seen'] = test.get('timestamp', '')
        aggregated_results = []
        for (provider, model), stats in combination_stats.items():
            avg_time = sum(stats['times']) / len(stats['times'])
            avg_rank = sum(stats['ranks']) / len(stats['ranks'])
            min_time = min(stats['times'])
            max_time = max(stats['times'])
            stability = (max_time - min_time) / avg_time if avg_time > 0 else 0
            aggregated_results.append({'provider': provider, 'model': model, 'avg_time': avg_time, 'min_time': min_time, 'max_time': max_time, 'avg_rank': avg_rank, 'test_count': stats['test_count'], 'stability': stability, 'first_seen': stats['first_seen'], 'last_seen': stats['last_seen']})
        aggregated_results.sort(key=lambda x: x['avg_time'])
        top_results = aggregated_results[:15]
        if not top_results:
            await ctx.send("❌ Нет успешных комбинаций в истории.")
            return
        embed = disnake.Embed(title="🏆 Лучшие комбинации (из test_history.json)", description=f"**Тип тестов:** `{test_type}`\n**Проанализировано тестов:** `{len(filtered_tests)}`\n**Всего комбинаций:** `{len(combination_stats)}`\n\n*Данные усреднены по последним 5 тестам каждого типа*", color=0x00FF88, timestamp=datetime.now())
        table_header = f"{'№':<3} {'Провайдер':<16} {'Модель':<18} {'Средн':<7} {'Мин':<7} {'Раз':<5}\n"
        table_separator = "—" * 62 + "\n"
        table_rows = ""
        for i, r in enumerate(top_results, 1):
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟", "1️⃣1️⃣", "1️⃣2️⃣", "1️⃣3️⃣", "1️⃣4️⃣", "1️⃣5️⃣"]
            medal = medals[i - 1] if i <= 15 else f"{i}."
            provider_short = r['provider'][:16] if len(r['provider']) > 16 else r['provider']
            model_short = r['model'][:18] if len(r['model']) > 18 else r['model']
            stability_icon = "🟢" if r['stability'] < 0.2 else "🟡" if r['stability'] < 0.5 else "🔴"
            spread = f"{((r['max_time'] - r['min_time']) * 1000):.0f}мс"
            table_rows += f"{medal} `{provider_short:<16}` `{model_short:<18}` `{r['avg_time']:.2f}с` `{r['min_time']:.2f}с` {spread:<5} {stability_icon}\n"
        embed.add_field(name="📊 Агрегированные результаты", value=f"```\n{table_header}{table_separator}{table_rows}```", inline=False)
        if top_results:
            best_combo = top_results[0]
            most_stable = min(top_results, key=lambda x: x['stability'])
            most_tested = max(top_results, key=lambda x: x['test_count'])
            provider_counts = {}
            for r in aggregated_results:
                p = r['provider']
                if p not in provider_counts:
                    provider_counts[p] = 0
                provider_counts[p] += 1
            best_provider = max(provider_counts.items(), key=lambda x: x[1])
            stats_text = f"🥇 **Лучшая:** `{best_combo['provider']}` / `{best_combo['model']}` — `{best_combo['avg_time']:.2f}с`\n🎯 **Стабильная:** `{most_stable['provider']}` / `{most_stable['model']}` (разброс: `{most_stable['stability']:.1%}`)\n📈 **Частая:** `{most_tested['provider']}` / `{most_tested['model']}` (`{most_tested['test_count']}` тестов)\n🏆 **Провайдер:** `{best_provider[0]}` (`{best_provider[1]}` комбинаций в топ-15)"
            embed.add_field(name="💡 Статистика", value=stats_text, inline=False)
        embed.set_footer(text="ПсИИнка бот | Данные из test_history.json")
        await ctx.send(embed=embed)
    except Exception as e:
        logger.error(f"Ошибка в команде лучшие: {e}", exc_info=True)
        await ctx.send(f"❌ Ошибка: {str(e)[:1900]}")

@bot.command(name="скажи")
async def скажи(ctx, *, prompt: str = None):
    try:
        if not prompt or prompt.isspace():
            await ctx.send("Введите ваш вопрос, хозяин?!")
            return
        msg = await ctx.send(f"Ответ от ПсИИнки...\n⏳ Загружаю ответ (Попытка 1/3)...")
        max_retries = 3
        retry_timeout = 60.0
        final_response = None
        final_provider = None
        final_model = None
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"🔄 Попытка {attempt}/{max_retries} получить ответ через g4f...")
                if attempt > 1:
                    await msg.edit(content=f"Ответ от ПсИИнки...\n⏳ Загружаю ответ (Попытка {attempt}/{max_retries})...")
                response_text, provider, model = await chat_with_model(prompt, timeout=retry_timeout, attempt=attempt)
                final_response = response_text
                final_provider = provider
                final_model = model
                break
            except TimeoutError as e:
                logger.warning(f"⏰ Попытка {attempt} завершилась таймаутом: {e}")
                if attempt == max_retries:
                    pass
                await asyncio.sleep(1)
                continue
            except Exception as e:
                logger.warning(f"⚠️ Попытка {attempt} неудачна: {type(e).__name__}: {e}")
                if attempt == max_retries:
                    pass
                await asyncio.sleep(1)
                continue
        if not final_response:
            logger.info("🔀 Все попытки g4f не удались, пробуем OpenRouter API...")
            await msg.edit(content=f"Ответ от ПсИИнки...\n⏳ Загружаю ответ через OpenRouter...")
            try:
                openrouter_response, openrouter_provider, openrouter_model = await chat_via_openrouter(prompt, timeout=40.0)
                final_response = openrouter_response
                final_provider = openrouter_provider
                final_model = openrouter_model
                logger.info(f"✅ OpenRouter успех: {openrouter_provider}/{openrouter_model}")
            except Exception as e:
                logger.error(f"❌ OpenRouter тоже не ответил: {type(e).__name__}: {e}")
                raise TimeoutError("Не удалось получить ответ ни от g4f, ни от OpenRouter")
        clean_response = final_response.strip()
        clean_response = '\n'.join(line for line in clean_response.split('\n') if line.strip())
        if not clean_response or clean_response.isspace():
            await msg.edit(content="⚠️ Модель вернула пустой ответ. Попробуйте другой вопрос.")
            return
        header = f"🐕 ПсИИнка прогавкал ответ от **{final_provider} - {final_model}**:\n"
        parts = [clean_response[i:i + 1900] for i in range(0, len(clean_response), 1900)]
        if len(parts) == 1:
            await msg.edit(content=header + parts[0])
        else:
            await msg.delete()
            first = await ctx.send(header + parts[0])
            for part in parts[1:]:
                await ctx.send(part, reference=first)
    except TimeoutError:
        await ctx.send("⚠️ Не удалось получить ответ ни от одной модели за ~3 минуты. Попробуйте позже.")
    except Exception as e:
        logger.error(f"Ошибка в команде скажи: {type(e).__name__}: {e}", exc_info=True)
        await ctx.send(f"⚠️ Ошибка: {str(e)[:1900]}")

async def chat_with_model(prompt: str, timeout: float = 40.0, attempt: int = 1):
    optimized_candidates = get_best_combinations_from_history(max_combinations=3)
    default_candidates = get_default_candidates()
    all_candidates = []
    seen = set()
    for p, m in optimized_candidates + default_candidates:
        if p == "Yqcloud":
            continue
        if (p, m) not in seen:
            all_candidates.append((p, m))
            seen.add((p, m))
    candidate_index = (attempt - 1) % len(all_candidates) if all_candidates else 0
    current_candidate = all_candidates[candidate_index] if all_candidates else ("PollinationsAI", "deepseek-r1")
    logger.info(f"🏎 Попытка {attempt}: 2 параллельных запроса (g4f-default + {current_candidate[0]}/{current_candidate[1]})")
    def is_russian(text: str) -> bool:
        if not text or len(text.strip()) < 3:
            return False
        cyrillic = len(re.findall(r'[а-яА-ЯёЁ]', text))
        total = len(re.findall(r'[а-яА-ЯёЁa-zA-Z]', text))
        return total > 0 and (cyrillic / total) >= 0.3
    def is_error_message(text: str) -> bool:
        error_keywords = ['limit', 'limited', 'rate limit', 'too many requests', 'ip 请求', '限流', '限制', 'error', 'errore', 'try again', 'попробуйте', 'через', 'минут', 'мин', 'https://', 'http://', 'wechat', '微信', 'chat19.aichatos', '60 次', '每小时', 'ip request', 'temporarily']
        text_lower = text.lower()
        return any(kw in text_lower for kw in error_keywords)
    async def fetch(provider_name: str, model: str):
        try:
            success, answer, elapsed = await make_g4f_request(provider_name, model, prompt, timeout=timeout, system_prompt="Ты помощник по имени Псинка. Отвечай ТОЛЬКО на русском языке, кратко и максимально по делу.")
            logger.info(f"📡 g4f запрос {provider_name}/{model}: success={success}, elapsed={elapsed:.2f}s, answer_len={len(answer) if answer else 0}")
            if not success or not answer:
                logger.warning(f"❌ {provider_name}/{model} — не успешен: {answer[:100] if answer else 'нет ответа'}")
                raise Exception(answer or "Пустой ответ")
            if is_error_message(answer):
                logger.warning(f"⚠️ {provider_name}/{model} — ошибка/лимит: {answer[:50]}...")
                raise Exception("Ошибка или лимит провайдера")
            if not is_russian(answer):
                logger.warning(f"⚠️ {provider_name}/{model} — не русский язык: {answer[:50]}...")
                raise Exception("Ответ не на русском языке")
            logger.info(f"✅ {provider_name}/{model} — {elapsed:.2f}s")
            return (answer, provider_name, model)
        except Exception as e:
            logger.error(f"❌ fetch() ошибка {provider_name}/{model}: {type(e).__name__}: {e}")
            raise
    async def fetch_default_g4f():
        try:
            logger.info("🎯 Приоритетный запрос: g4f deepseek-r1 (без провайдера)...")
            client = g4f.client.AsyncClient()
            messages = [{"role": "system", "content": "Ты помощник по имени Псинка. Отвечай ТОЛЬКО на русском языке, кратко и максимально по делу."}, {"role": "user", "content": prompt}]
            start = time.time()
            response = await asyncio.wait_for(client.chat.completions.create(model="deepseek-r1", messages=messages), timeout=timeout)
            if response and hasattr(response, 'choices') and response.choices:
                answer = response.choices[0].message.content
                if answer and answer.strip():
                    elapsed = time.time() - start
                    logger.info(f"📡 g4f-default запрос: success=True, elapsed={elapsed:.2f}s, answer_len={len(answer)}")
                    if is_error_message(answer):
                        logger.warning(f"⚠️ g4f-default/deepseek-r1 — ошибка: {answer[:50]}...")
                        raise Exception("Ошибка провайдера")
                    if not is_russian(answer):
                        logger.warning(f"⚠️ g4f-default/deepseek-r1 — не русский язык")
                        raise Exception("Ответ не на русском")
                    logger.info(f"✅ g4f-default/deepseek-r1 — {elapsed:.2f}s (g4f-default)")
                    return (answer, "g4f-default", "deepseek-r1")
            logger.warning(f"❌ g4f-default/deepseek-r1 — пустой ответ")
            raise Exception("Пустой ответ от g4f-default")
        except asyncio.TimeoutError:
            logger.error(f"⏰ g4f-default/deepseek-r1 — таймаут {timeout}с")
            raise
        except Exception as e:
            logger.error(f"❌ g4f-default/deepseek-r1 — ошибка: {type(e).__name__}: {e}")
            raise
    tasks = [asyncio.create_task(fetch_default_g4f()), asyncio.create_task(fetch(current_candidate[0], current_candidate[1]))]
    logger.info(f"🚀 Запущено 2 параллельных запроса (таймаут {timeout}с)...")
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED, timeout=timeout + 5.0)
        for task in pending:
            task.cancel()
        for task in done:
            try:
                result = task.result()
                if result:
                    logger.info(f"🏆 Победа в попытке {attempt}: {result[1]}/{result[2]}")
                    return result
            except Exception as e:
                logger.debug(f"Задача в попытке {attempt} не удалась: {type(e).__name__}: {e}")
                continue
        logger.error(f"❌ Попытка {attempt}: Оба запроса завершились ошибкой")
        raise Exception("Оба запроса в попытке завершились ошибкой")
    except asyncio.TimeoutError:
        logger.error(f"⏰ Таймаут попытки {attempt} ({timeout}с)")
        raise TimeoutError(f"Попытка {attempt} не удалась — таймаут")
    except Exception as e:
        logger.error(f"Ошибка в попытке {attempt}: {type(e).__name__}: {e}")
        raise TimeoutError(f"Попытка {attempt} не удалась: {str(e)}")

async def chat_via_openrouter(prompt: str, timeout: float = 45.0):
    openrouter_token = os.getenv('OPENR_TOKEN')
    if not openrouter_token:
        logger.error("❌ OPENR_TOKEN не найден в .env")
        raise Exception("OpenRouter API ключ не настроен")
    priority_models = get_openrouter_models_from_history(max_models=3)
    default_models = ["liquid/lfm-2.5-1.2b-instruct:free", "nvidia/nemotron-3-super-120b-a12b:free", "stepfun/step-3.5-flash:free", "arcee-ai/trinity-large-preview:free", "nvidia/nemotron-3-nano-30b-a3b:free"]
    models_to_try = []
    for m in priority_models:
        if m not in models_to_try:
            models_to_try.append(m)
    for m in default_models:
        if m not in models_to_try:
            models_to_try.append(m)
    models_to_try.append("openrouter/free")
    logger.info(f"🔀 OpenRouter fallback: {len(models_to_try)} моделей в очереди")
    for model in models_to_try:
        logger.info(f"🔀 Попытка OpenRouter: {model}...")
        try:
            client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=openrouter_token)
            loop = asyncio.get_running_loop()
            google_models = ["gemma", "google/"]
            is_google_model = any(g in model.lower() for g in google_models)
            def make_request():
                messages = []
                if not is_google_model:
                    messages.append({"role": "system", "content": "Ты помощник по имени Псинка. Отвечай ТОЛЬКО на русском языке, кратко и максимально по делу."})
                messages.append({"role": "user", "content": prompt})
                return client.chat.completions.create(model=model, messages=messages, timeout=timeout, extra_headers={"HTTP-Referer": "https://github.com/psiiinka-bot", "X-OpenRouter-Title": "PsIInka Bot"})
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    start = time.time()
                    response = await asyncio.wait_for(loop.run_in_executor(None, make_request), timeout=timeout)
                    if response.choices and len(response.choices) > 0:
                        answer = response.choices[0].message.content
                        elapsed = time.time() - start
                        if answer and answer.strip():
                            logger.info(f"✅ OpenRouter успех ({model}) за {elapsed:.2f}s")
                            return (answer.strip(), "OpenRouter", model)
                        else:
                            logger.warning(f"⚠️ OpenRouter пустой ответ ({model})")
                            break
                    else:
                        logger.warning(f"⚠️ OpenRouter нет choices ({model})")
                        break
                except Exception as e:
                    error_str = str(e).lower()
                    if '429' in error_str or 'rate limit' in error_str:
                        wait_time = 2 ** attempt
                        logger.warning(f"⚠️ OpenRouter 429 — ожидание {wait_time}с")
                        await asyncio.sleep(wait_time)
                        continue
                    elif '404' in error_str or '400' in error_str:
                        logger.warning(f"⚠️ OpenRouter ошибка {model}: {e}")
                        break
                    else:
                        raise
            logger.warning(f"⚠️ OpenRouter модель {model} не сработала")
            continue
        except Exception as e:
            logger.warning(f"⚠️ OpenRouter ошибка {model}: {e}")
            continue
    logger.error("❌ Все модели OpenRouter не ответили")
    raise Exception("OpenRouter: ни одна модель не ответила")

def get_openrouter_models_from_history(max_models: int = 3) -> List[str]:
    history_file = 'test_history.json'
    history = safe_read_json(history_file, [])
    if not history:
        logger.warning("📁 test_history.json не найден — используем дефолтные модели OpenRouter")
        return []
    model_stats = {}
    for test in history:
        for combo in test.get('top_combinations', []):
            if combo['provider'] == 'OpenRouter':
                model = combo['model']
                time_val = combo['time']
                if model not in model_stats:
                    model_stats[model] = {'times': [], 'appearances': 0}
                model_stats[model]['times'].append(time_val)
                model_stats[model]['appearances'] += 1
    if not model_stats:
        logger.warning("📁 Нет тестов OpenRouter в истории — используем дефолтные модели")
        return []
    scored_models = []
    for model, stats in model_stats.items():
        avg_time = sum(stats['times']) / len(stats['times'])
        min_time = min(stats['times'])
        max_time = max(stats['times'])
        stability = (max_time - min_time) / avg_time if avg_time > 0 else 0
        score = avg_time + (stability * 0.5) - (stats['appearances'] * 0.1)
        scored_models.append({'model': model, 'avg_time': avg_time, 'stability': stability, 'appearances': stats['appearances'], 'score': score})
    scored_models.sort(key=lambda x: x['score'])
    top_models = [m['model'] for m in scored_models[:max_models]]
    logger.info(f"🏆 Найдено {len(top_models)} стабильных моделей OpenRouter из истории:")
    for i, m in enumerate(top_models, 1):
        model_data = next(x for x in scored_models if x['model'] == m)
        logger.info(f"  #{i}: {m} — {model_data['avg_time']:.2f}с (стабильность: {model_data['stability']:.1%}, тестов: {model_data['appearances']})")
    return top_models

@bot.event
async def on_command_error(ctx, error):
    logger.error(f"Ошибка в команде {ctx.command}: {error}", exc_info=True)
    try:
        await ctx.send(f"⚠️ Ошибка: {str(error)}")
    except:
        pass

if __name__ == "__main__":
    try:
        logger.info("🚀 Запуск бота...")
        logger.info(f"📁 Рабочая директория: {os.getcwd()}")
        logger.info(f"🚂 Railway: {IS_RAILWAY}")
        bot.run(os.getenv("DISCORD_TOKEN"))
    except Exception as e:
        logger.critical(f"💥 Критическая ошибка при запуске: {e}", exc_info=True)