"""RP-текстовые команды модерации без префикса и slash-команд.

Модуль намеренно изолирован от игровых механик в ``psinkamain.py``.
Темница (роль ``Спит``) остаётся в основном модуле, потому что там хранится
её БД/таймерная логика. Здесь находятся Карцер (Discord timeout), изгнание,
возвращение из бана, управление обычными ролями и служебная справка.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import Optional, Tuple

import disnake
from disnake.ext import commands

logger = logging.getLogger(__name__)

MAX_TIMEOUT_MINUTES = 28 * 24 * 60
DEFAULT_REASON = "Причина не указана"

USER_MENTION_RE = re.compile(r"<@!?(\d{15,25})>")
ROLE_MENTION_RE = re.compile(r"<@&(\d{15,25})>")

GUARD_ROLE_NAMES = {
    "гвардеец",
    "старший гвардеец",
}
SENIOR_CARCER_ROLE_NAMES = {
    "старший гвардеец",
    "глава гвардии фаервелла",
}
HEAD_GUARD_ROLE_NAMES = {
    "глава гвардии фаервелла",
}
STAFF_HELP_ROLE_NAMES = GUARD_ROLE_NAMES | HEAD_GUARD_ROLE_NAMES

# RP-фразы намеренно достаточно длинные и точные, чтобы не цеплять обычный чат.
KICK_RE = re.compile(
    r"^\s*"
    r"(?:(?P<mention><@!?\d{15,25}>)\s*[,—–-]?\s*)?"
    r"ты\s+изгоняешься\s+из\s+фаервелла"
    r"\s+за\s+(?P<reason>.+?)"
    r"\s*[.!]?\s*$",
    flags=re.IGNORECASE,
)

CARCER_RE = re.compile(
    r"^\s*"
    r"(?:(?P<mention><@!?\d{15,25}>)\s*[,—–-]?\s*)?"
    r"ты\s+отправляешься\s+в\s+карцер\s+на\s+"
    r"(?P<amount>\d{1,5})\s*"
    r"(?P<unit>мин(?:ут(?:у|ы)?|\.)?|час(?:а|ов)?|ч|д(?:ень|ня|ней)?|сут(?:ки|ок)?)"
    r"\s+за\s+(?P<reason>.+?)"
    r"\s*[.!]?\s*$",
    flags=re.IGNORECASE,
)

CARCER_RELEASE_RE = re.compile(
    r"^\s*"
    r"(?:(?P<mention><@!?\d{15,25}>)\s*[,—–-]?\s*)?"
    r"ты\s+освобождаешься\s+из\s+карцера"
    r"\s+за\s+(?P<reason>.+?)"
    r"\s*[.!]?\s*$",
    flags=re.IGNORECASE,
)

UNBAN_RE = re.compile(
    r"^\s*"
    r"врата\s+фаервелла\s+вновь\s+открыты\s+для\s+"
    r"(?P<user_id>\d{15,25})"
    r"\s+за\s+(?P<reason>.+?)"
    r"\s*[.!]?\s*$",
    flags=re.IGNORECASE,
)

ROLE_GRANT_RE = re.compile(
    r"^\s*"
    r"(?:(?P<mention><@!?\d{15,25}>)\s*[,—–-]?\s*)?"
    r"на\s+тебя\s+возлагается\s+знак\s+"
    r"(?P<role><@&\d{15,25}>)"
    r"\s+за\s+(?P<reason>.+?)"
    r"\s*[.!]?\s*$",
    flags=re.IGNORECASE,
)

ROLE_REMOVE_RE = re.compile(
    r"^\s*"
    r"(?:(?P<mention><@!?\d{15,25}>)\s*[,—–-]?\s*)?"
    r"с\s+тебя\s+снимается\s+знак\s+"
    r"(?P<role><@&\d{15,25}>)"
    r"\s+за\s+(?P<reason>.+?)"
    r"\s*[.!]?\s*$",
    flags=re.IGNORECASE,
)

HELP_TRIGGER = "огласи устав гвардии"


def _reason(value: Optional[str]) -> str:
    value = (value or "").strip()
    return value[:450] if value else DEFAULT_REASON


def _role_names(member: disnake.Member) -> set[str]:
    return {role.name.strip().casefold() for role in member.roles}


def _is_admin(member: object) -> bool:
    return isinstance(member, disnake.Member) and bool(member.guild_permissions.administrator)


def _has_named_role(member: object, allowed_names: set[str]) -> bool:
    return isinstance(member, disnake.Member) and bool(_role_names(member) & allowed_names)


def _has_carcer_access(member: object) -> bool:
    """Карцер: Administrator либо Старший Гвардеец / Глава Гвардии Фаервелла."""
    return _is_admin(member) or _has_named_role(member, SENIOR_CARCER_ROLE_NAMES)


def _has_unban_access(member: object) -> bool:
    """Возвращение из бана: Administrator либо Глава Гвардии Фаервелла."""
    return _is_admin(member) or _has_named_role(member, HEAD_GUARD_ROLE_NAMES)


def _has_help_access(member: object) -> bool:
    """Справка доступна всем штатным модераторским уровням."""
    return _is_admin(member) or _has_named_role(member, STAFF_HELP_ROLE_NAMES)


def _bot_member(guild: disnake.Guild, bot: commands.Bot) -> Optional[disnake.Member]:
    if guild.me is not None:
        return guild.me
    if bot.user is None:
        return None
    return guild.get_member(bot.user.id)


def _member_by_mention(guild: disnake.Guild, mention: Optional[str]) -> Optional[disnake.Member]:
    if not mention:
        return None
    match = USER_MENTION_RE.fullmatch(mention.strip())
    if not match:
        return None
    return guild.get_member(int(match.group(1)))


async def _reply_target(message: disnake.Message) -> Optional[disnake.Member]:
    ref = message.reference
    if ref is None:
        return None

    resolved = getattr(ref, "resolved", None)
    if isinstance(resolved, disnake.Message) and isinstance(resolved.author, disnake.Member):
        return resolved.author

    message_id = getattr(ref, "message_id", None)
    if message_id is None:
        return None

    try:
        referenced = await message.channel.fetch_message(message_id)
    except (disnake.NotFound, disnake.Forbidden, disnake.HTTPException):
        return None

    return referenced.author if isinstance(referenced.author, disnake.Member) else None


async def _resolve_target(message: disnake.Message, mention: Optional[str]) -> Optional[disnake.Member]:
    if message.guild is None:
        return None
    target = _member_by_mention(message.guild, mention)
    if target is not None:
        return target
    if mention is None:
        return await _reply_target(message)
    return None


def _hierarchy_problem(
    actor: disnake.Member,
    target: disnake.Member,
    bot_member: Optional[disnake.Member],
) -> Optional[str]:
    guild = actor.guild

    if target.id == guild.owner_id:
        return "владельца сервера этой командой затронуть нельзя"
    if target.id == actor.id:
        return "этот приказ нельзя применить к самому себе"
    if bot_member is None:
        return "не удалось определить положение бота в иерархии сервера"
    if target.id == bot_member.id:
        return "бот не может применить приказ к самому себе"

    if actor.id != guild.owner_id and target.top_role >= actor.top_role:
        return "роль цели находится не ниже вашей высшей роли"
    if target.top_role >= bot_member.top_role:
        return "роль цели находится не ниже высшей роли бота"

    return None


def _role_problem(
    actor: disnake.Member,
    target: disnake.Member,
    role: disnake.Role,
    bot_member: Optional[disnake.Member],
) -> Optional[str]:
    base = _hierarchy_problem(actor, target, bot_member)
    if base:
        return base
    if role.is_default():
        return "знак @everyone нельзя выдавать или снимать"
    if role.managed:
        return "этим знаком управляет интеграция Discord"
    if bot_member is None or role >= bot_member.top_role:
        return "роль находится не ниже высшей роли бота"
    if actor.id != actor.guild.owner_id and role >= actor.top_role:
        return "роль находится не ниже вашей высшей роли"
    return None


def _timeout_minutes(amount: int, unit: str) -> int:
    unit_cf = unit.casefold()
    if unit_cf.startswith("ч") or unit_cf.startswith("час"):
        return amount * 60
    if unit_cf.startswith("д") or unit_cf.startswith("сут"):
        return amount * 24 * 60
    return amount


class TextAdminCog(commands.Cog):
    """Служебная модерация обычными RP-фразами без ``/`` и ``!``."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _deny(self, message: disnake.Message, text: str) -> bool:
        await message.reply(f"🛡️ {text}", mention_author=False)
        return True

    async def _target_or_error(
        self,
        message: disnake.Message,
        mention: Optional[str],
    ) -> Optional[disnake.Member]:
        target = await _resolve_target(message, mention)
        if target is None:
            await message.reply(
                "❌ Приказу не хватает адресата. Поставь настоящее упоминание перед фразой "
                "или ответь этой фразой на сообщение нужного участника.",
                mention_author=False,
            )
        return target

    async def _check_target(
        self,
        message: disnake.Message,
        target: disnake.Member,
    ) -> Tuple[Optional[disnake.Member], Optional[str]]:
        assert message.guild is not None
        bot_member = _bot_member(message.guild, self.bot)
        problem = _hierarchy_problem(message.author, target, bot_member)  # type: ignore[arg-type]
        if problem:
            await message.reply(f"❌ Приказ не может быть исполнен: {problem}.", mention_author=False)
            return bot_member, problem
        return bot_member, None

    @commands.Cog.listener("on_message")
    async def text_admin_listener(self, message: disnake.Message) -> None:
        if message.author.bot or message.guild is None:
            return

        content = (message.content or "").strip()
        if not content:
            return

        # Точный RP-триггер справки: обычная разговорная фраза его не вызовет.
        if content.casefold().rstrip(".! ") == HELP_TRIGGER:
            if not _has_help_access(message.author):
                await self._deny(
                    message,
                    "Служебный устав открыт только Администраторам, Гвардейцам, "
                    "Старшим Гвардейцам и Главе Гвардии Фаервелла.",
                )
                return
            await self._send_help(message)
            return

        kick_match = KICK_RE.fullmatch(content)
        if kick_match:
            if not _is_admin(message.author):
                await self._deny(message, "Изгнание из Фаервелла доступно только Администраторам сервера.")
                return
            await self._handle_kick(message, kick_match)
            return

        unban_match = UNBAN_RE.fullmatch(content)
        if unban_match:
            if not _has_unban_access(message.author):
                await self._deny(
                    message,
                    "Открывать врата изгнанным могут только Администраторы и Глава Гвардии Фаервелла.",
                )
                return
            await self._handle_unban(message, unban_match)
            return

        carcer_match = CARCER_RE.fullmatch(content)
        if carcer_match:
            if not _has_carcer_access(message.author):
                await self._deny(
                    message,
                    "Ключи от Карцера доверены только Администраторам, Старшим Гвардейцам "
                    "и Главе Гвардии Фаервелла. Обычному Гвардейцу доступна Темница, но не Карцер.",
                )
                return
            await self._handle_carcer(message, carcer_match)
            return

        carcer_release_match = CARCER_RELEASE_RE.fullmatch(content)
        if carcer_release_match:
            if not _has_carcer_access(message.author):
                await self._deny(
                    message,
                    "Ключи от Карцера доверены только Администраторам, Старшим Гвардейцам "
                    "и Главе Гвардии Фаервелла. Обычному Гвардейцу снимать Discord timeout нельзя.",
                )
                return
            await self._handle_carcer_release(message, carcer_release_match)
            return

        role_grant_match = ROLE_GRANT_RE.fullmatch(content)
        if role_grant_match:
            if not _is_admin(message.author):
                await self._deny(message, "Возлагать служебные знаки могут только Администраторы сервера.")
                return
            await self._handle_role(message, role_grant_match, grant=True)
            return

        role_remove_match = ROLE_REMOVE_RE.fullmatch(content)
        if role_remove_match:
            if not _is_admin(message.author):
                await self._deny(message, "Снимать служебные знаки могут только Администраторы сервера.")
                return
            await self._handle_role(message, role_remove_match, grant=False)
            return

    async def _send_help(self, message: disnake.Message) -> None:
        await message.reply(
            "**📜 Служебный устав Гвардии Фаервелла**\n"
            "Все приказы произносятся обычным сообщением — без `/` и `!`.\n"
            "Для команд над участником можно поставить `@упоминание` перед фразой или ответить фразой на его сообщение.\n\n"
            "**🔒 Темница — роль `Спит`**\n"
            "`Ты отправляешься в темницу на 15 минут за 2.14`\n"
            "`Ты освобождаешься из темницы за наказание снято`\n"
            "Доступ: **Администратор / Гвардеец / Старший Гвардеец**.\n\n"
            "**⛓️ Карцер — Discord timeout**\n"
            "`Ты отправляешься в карцер на 15 минут за флуд`\n"
            "`Ты освобождаешься из карцера за наказание снято`\n"
            "Доступ: **Администратор / Старший Гвардеец / Глава Гвардии Фаервелла**.\n"
            "Обычный Гвардеец **не может** выдавать или снимать Карцер.\n\n"
            "**🚪 Изгнание с сервера — kick**\n"
            "`Ты изгоняешься из Фаервелла за нарушение устава`\n"
            "Доступ: **только Администратор**.\n\n"
            "**🏰 Возвращение из бана**\n"
            "`Врата Фаервелла вновь открыты для 123456789012345678 за апелляция принята`\n"
            "Доступ: **Администратор / Глава Гвардии Фаервелла**.\n"
            "Отдельной команды для выдачи бана **нет**.\n\n"
            "**🎖️ Служебные знаки — роли**\n"
            "`На тебя возлагается знак @Роль за назначение`\n"
            "`С тебя снимается знак @Роль за снятие полномочий`\n"
            "Доступ: **только Администратор**.\n\n"
            "Команд очистки сообщений в служебном наборе **нет**.",
            mention_author=False,
            allowed_mentions=disnake.AllowedMentions.none(),
        )

    async def _handle_kick(self, message: disnake.Message, match: re.Match[str]) -> None:
        target = await self._target_or_error(message, match.group("mention"))
        if target is None:
            return

        bot_member, problem = await self._check_target(message, target)
        if problem or bot_member is None:
            return
        if not bot_member.guild_permissions.kick_members:
            await message.reply("❌ У бота нет права **Выгонять участников**.", mention_author=False)
            return

        reason = _reason(match.group("reason"))
        audit_reason = f"Изгнание из Фаервелла: {reason}; модератор: {message.author} ({message.author.id})"

        try:
            target_name = str(target)
            target_id = target.id
            await target.kick(reason=audit_reason)
            await message.reply(
                f"🚪 **{target_name}** (`{target_id}`) изгнан за пределы Фаервелла.\n**Причина:** {reason}",
                mention_author=False,
                allowed_mentions=disnake.AllowedMentions.none(),
            )
        except disnake.Forbidden:
            await message.reply(
                "❌ Стража не смогла исполнить изгнание: проверь право бота **Выгонять участников** и иерархию ролей.",
                mention_author=False,
            )
        except disnake.HTTPException as exc:
            logger.warning("RP admin kick failed: %s", exc, exc_info=True)
            await message.reply(f"❌ Discord вернул ошибку изгнания: `{str(exc)[:250]}`", mention_author=False)

    async def _handle_carcer(self, message: disnake.Message, match: re.Match[str]) -> None:
        target = await self._target_or_error(message, match.group("mention"))
        if target is None:
            return

        bot_member, problem = await self._check_target(message, target)
        if problem or bot_member is None:
            return
        if not bot_member.guild_permissions.moderate_members:
            await message.reply("❌ У бота нет права **Модерировать участников** (`moderate_members`).", mention_author=False)
            return

        amount = int(match.group("amount"))
        minutes = _timeout_minutes(amount, match.group("unit"))
        if not 1 <= minutes <= MAX_TIMEOUT_MINUTES:
            await message.reply(
                "❌ Срок Карцера должен быть от 1 минуты до 28 суток.",
                mention_author=False,
            )
            return

        reason = _reason(match.group("reason"))
        audit_reason = f"Карцер на {minutes} мин.; причина: {reason}; модератор: {message.author} ({message.author.id})"

        try:
            await target.timeout(duration=timedelta(minutes=minutes), reason=audit_reason)
            release_at = disnake.utils.utcnow() + timedelta(minutes=minutes)
            release_timestamp = int(release_at.timestamp())
            await message.reply(
                f"⛓️ {target.mention} отправляется в Карцер на **{minutes} мин.**\n"
                f"**Причина:** {reason}\n"
                f"**Освобождение:** <t:{release_timestamp}:F> (<t:{release_timestamp}:R>)",
                mention_author=False,
                allowed_mentions=disnake.AllowedMentions(
                    everyone=False,
                    roles=False,
                    users=True,
                    replied_user=False,
                ),
            )
        except disnake.Forbidden:
            await message.reply(
                "❌ Дверь Карцера не закрылась: проверь право бота **Модерировать участников** и иерархию ролей.",
                mention_author=False,
            )
        except disnake.HTTPException as exc:
            logger.warning("RP admin carcer failed: %s", exc, exc_info=True)
            await message.reply(f"❌ Discord вернул ошибку Карцера: `{str(exc)[:250]}`", mention_author=False)

    async def _handle_carcer_release(self, message: disnake.Message, match: re.Match[str]) -> None:
        target = await self._target_or_error(message, match.group("mention"))
        if target is None:
            return

        bot_member, problem = await self._check_target(message, target)
        if problem or bot_member is None:
            return
        if not bot_member.guild_permissions.moderate_members:
            await message.reply("❌ У бота нет права **Модерировать участников** (`moderate_members`).", mention_author=False)
            return

        reason = _reason(match.group("reason"))
        audit_reason = f"Досрочное освобождение из Карцера: {reason}; модератор: {message.author} ({message.author.id})"

        try:
            await target.timeout(duration=None, reason=audit_reason)
            await message.reply(
                f"🔓 Дверь Карцера открыта для {target.mention}. Discord timeout снят.\n**Причина:** {reason}",
                mention_author=False,
                allowed_mentions=disnake.AllowedMentions(
                    everyone=False,
                    roles=False,
                    users=True,
                    replied_user=False,
                ),
            )
        except disnake.Forbidden:
            await message.reply(
                "❌ Дверь Карцера не открылась: проверь право бота **Модерировать участников** и иерархию ролей.",
                mention_author=False,
            )
        except disnake.HTTPException as exc:
            logger.warning("RP admin carcer release failed: %s", exc, exc_info=True)
            await message.reply(f"❌ Discord вернул ошибку освобождения: `{str(exc)[:250]}`", mention_author=False)

    async def _handle_unban(self, message: disnake.Message, match: re.Match[str]) -> None:
        assert message.guild is not None
        bot_member = _bot_member(message.guild, self.bot)
        if bot_member is None or not bot_member.guild_permissions.ban_members:
            await message.reply(
                "❌ У бота нет права **Банить участников** — Discord использует это же право для снятия бана.",
                mention_author=False,
            )
            return

        user_id = int(match.group("user_id"))
        reason = _reason(match.group("reason"))
        audit_reason = f"Врата Фаервелла вновь открыты: {reason}; модератор: {message.author} ({message.author.id})"

        try:
            await message.guild.unban(disnake.Object(id=user_id), reason=audit_reason)
            await message.reply(
                f"🏰 Врата Фаервелла вновь открыты для пользователя ID `{user_id}`.\n**Причина:** {reason}",
                mention_author=False,
            )
        except disnake.NotFound:
            await message.reply("❌ Этого ID нет среди изгнанных (бан-лист сервера).", mention_author=False)
        except disnake.Forbidden:
            await message.reply("❌ Discord не позволил открыть врата. Проверь право бота на снятие бана.", mention_author=False)
        except disnake.HTTPException as exc:
            logger.warning("RP admin unban failed: %s", exc, exc_info=True)
            await message.reply(f"❌ Discord вернул ошибку снятия бана: `{str(exc)[:250]}`", mention_author=False)

    async def _handle_role(
        self,
        message: disnake.Message,
        match: re.Match[str],
        *,
        grant: bool,
    ) -> None:
        assert message.guild is not None
        target = await self._target_or_error(message, match.group("mention"))
        if target is None:
            return

        role_match = ROLE_MENTION_RE.fullmatch(match.group("role"))
        role = message.guild.get_role(int(role_match.group(1))) if role_match else None
        if role is None:
            await message.reply("❌ Не удалось распознать служебный знак — укажи настоящее упоминание роли.", mention_author=False)
            return

        bot_member = _bot_member(message.guild, self.bot)
        problem = _role_problem(message.author, target, role, bot_member)  # type: ignore[arg-type]
        if problem:
            await message.reply(f"❌ Этот знак нельзя изменить: {problem}.", mention_author=False)
            return
        if bot_member is None or not bot_member.guild_permissions.manage_roles:
            await message.reply("❌ У бота нет права **Управлять ролями**.", mention_author=False)
            return

        reason = _reason(match.group("reason"))
        audit_reason = f"Служебный знак: {reason}; модератор: {message.author} ({message.author.id})"

        try:
            if grant:
                if role in target.roles:
                    await message.reply(
                        f"ℹ️ На {target.mention} уже возложен знак {role.mention}.",
                        mention_author=False,
                        allowed_mentions=disnake.AllowedMentions.none(),
                    )
                    return
                await target.add_roles(role, reason=audit_reason)
                text = f"🎖️ На {target.mention} возложен знак {role.mention}.\n**Причина:** {reason}"
            else:
                if role not in target.roles:
                    await message.reply(
                        f"ℹ️ На {target.mention} нет знака {role.mention}.",
                        mention_author=False,
                        allowed_mentions=disnake.AllowedMentions.none(),
                    )
                    return
                await target.remove_roles(role, reason=audit_reason)
                text = f"🎖️ С {target.mention} снят знак {role.mention}.\n**Причина:** {reason}"

            await message.reply(
                text,
                mention_author=False,
                allowed_mentions=disnake.AllowedMentions.none(),
            )
        except disnake.Forbidden:
            await message.reply(
                "❌ Discord не позволил изменить знак. Проверь право **Управлять ролями** и иерархию.",
                mention_author=False,
            )
        except disnake.HTTPException as exc:
            logger.warning("RP admin role action failed: %s", exc, exc_info=True)
            await message.reply(f"❌ Discord вернул ошибку роли: `{str(exc)[:250]}`", mention_author=False)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(TextAdminCog(bot))
