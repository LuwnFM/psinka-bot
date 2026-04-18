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
# 🛡️ БАЗА НАЁМНИКОВ, НАВЫКОВ И СПЕЦИАЛИЗАЦИЙ
# ============================================================================

MERCENARY_SKILL_PROBABILITIES = {
    "Новичок": 10,
    "Опытный": 30,
    "Ветеран": 50,
    "Мастер": 8,
    "Легендарный Мастер": 2
}

# Специализации для профессий с широким профилем
MERCENARY_SPECIALIZATIONS = {
    "Кузнец": [
    {"name": "Оружейник", "skills": ["Оружейное дело", "Кузнец"]},
    {"name": "Бронник", "skills": ["Бронник", "Кузнец"]},
    {"name": "Гравёр-ювелир", "skills": ["Гравировка", "Ювелирное дело"]},
    ],
    "Ремесленник": [
        {"name": "Гравёр", "skills": ["Гравировка", "Резьба по камню"]},
        {"name": "Резчик по дереву", "skills": ["Резьба по дереву", "Деревообработка"]},
        {"name": "Гончар", "skills": ["Гончарное дело", "Рисование"]},
        {"name": "Стеклодув", "skills": ["Стеклодув", "Гравировка"]},
        {"name": "Красильщик", "skills": ["Красильщик", "Пошив"]},
        {"name": "Мыловар", "skills": ["Мыловарение", "Травничество"]},
        {"name": "Ювелир", "skills": ["Ювелирное дело", "Гравировка"]},
        {"name": "Оружейник", "skills": ["Оружейное дело", "Кузнец"]},
        {"name": "Бронник", "skills": ["Бронник", "Кузнец"]},
    ],
    "Оружейник": [
        {"name": "Мастер клинков", "skills": ["Оружейное дело", "Кузнец"]},
        {"name": "Мастер луков", "skills": ["Оружейное дело", "Деревообработка"]},
        {"name": "Гравёр оружия", "skills": ["Оружейное дело", "Гравировка"]},
    ],
    "Столяр": [
        {"name": "Резчик", "skills": ["Резьба по дереву", "Деревообработка"]},
        {"name": "Мебельщик", "skills": ["Деревообработка", "Строительство"]},
        {"name": "Мастер инструментов", "skills": ["Деревообработка", "Гравировка"]},
    ],
    "Каменщик": [
        {"name": "Резчик по камню", "skills": ["Резьба по камню", "Строительство"]},
        {"name": "Кладчик", "skills": ["Строительство", "Механика"]},
        {"name": "Скульптор", "skills": ["Резьба по камню", "Рисование"]},
    ],
    "Ткач": [
        {"name": "Портной", "skills": ["Пошив", "Красильщик"]},
        {"name": "Красильщик тканей", "skills": ["Красильщик", "Пошив"]},
        {"name": "Гобеленщик", "skills": ["Пошив", "Рисование"]},
    ],
    "Охотник": [
        {"name": "Зверолов", "skills": ["Охота", "Разделка и съём шкур"]},
        {"name": "Лучник", "skills": ["Охота", "Луки"]},
        {"name": "Следопыт", "skills": ["Охота", "Скрытность"]},
    ],
    "Рыбак": [
        {"name": "Рыболов", "skills": ["Рыбная ловля", "Плавание"]},
        {"name": "Торговец рыбой", "skills": ["Рыбная ловля", "Торговля"]},
        {"name": "Переработчик", "skills": ["Рыбная ловля", "Разделка и съём шкур"]},
    ],
    "Шахтер": [
        {"name": "Добытчик руды", "skills": ["Шахтёрское дело", "Сила"]},
        {"name": "Камнерез", "skills": ["Шахтёрское дело", "Резьба по камню"]},
        {"name": "Геолог", "skills": ["Шахтёрское дело", "Оценка"]},
    ],
    "Мечник": [
        {"name": "Дуэлянт", "skills": ["Колюще-режущее оружие", "Ловкость"]},
        {"name": "Рыцарь", "skills": ["Колюще-режущее оружие", "Щиты"]},
        {"name": "Наёмник", "skills": ["Колюще-режущее оружие", "Выносливость"]},
    ],
    "Лучник": [
        {"name": "Снайпер", "skills": ["Луки", "Восприятие"]},
        {"name": "Охотник", "skills": ["Луки", "Охота"]},
        {"name": "Воин", "skills": ["Луки", "Скрытность"]},
    ],
    "Стражник": [
        {"name": "Городовой", "skills": ["Колюще-режущее оружие", "Восприятие"]},
        {"name": "Тюремщик", "skills": ["Колюще-режущее оружие", "Пытки"]},
        {"name": "Дворцовый страж", "skills": ["Колюще-режущее оружие", "Щиты"]},
    ],
    "Винодел": [
        {"name": "Виноградарь", "skills": ["Виноделие", "Садоводство"]},
        {"name": "Мастер погреба", "skills": ["Виноделие", "Оценка"]},
        {"name": "Торговец вином", "skills": ["Виноделие", "Торговля"]},
    ],
    "Повар": [
        {"name": "Шеф-повар", "skills": ["Кулинария", "Травничество"]},
        {"name": "Пекарь", "skills": ["Кулинария", "Пивоварение"]},
        {"name": "Мясник", "skills": ["Кулинария", "Разделка и съём шкур"]},
    ],
    "Аптекарь": [
        {"name": "Травник", "skills": ["Алхимия", "Травничество"]},
        {"name": "Зельевар", "skills": ["Алхимия", "Врачевание"]},
        {"name": "Ядовед", "skills": ["Алхимия", "Пытки"]},
    ],
    "Священник": [
        {"name": "Проповедник", "skills": ["Теология", "Ораторство"]},
        {"name": "Целитель", "skills": ["Теология", "Врачевание"]},
        {"name": "Инквизитор", "skills": ["Теология", "Пытки"]},
    ],
    "Бард": [
        {"name": "Музыкант", "skills": ["Музыка", "Пение"]},
        {"name": "Сказитель", "skills": ["Музыка", "Ораторство"]},
        {"name": "Придворный артист", "skills": ["Музыка", "Харизма"]},
    ],
    "Торговец": [
        {"name": "Оценщик", "skills": ["Торговля", "Оценка"]},
        {"name": "Перекупщик", "skills": ["Торговля", "Ораторство"]},
        {"name": "Лавочник", "skills": ["Торговля", "Восприятие"]},
    ],
}

# Профессии без специализаций (уже узкие)
NO_SPECIALIZATION_PROFESSIONS = [
    "Ювелир", "Гончар", "Стеклодув", "Пивовар", "Красильщик",
    "Мыловар", "Археолог", "Алхимик", "Артофактор", "Големостроитель",
    "Инженер", "Механик", "Строитель", "Картограф", "Писатель",
    "Наездник", "Приручитель", "Рабовладелец", "Лидер", "Управленец",
    "Обучающий", "Оратор", "Пытатель", "Харизматик", "Акробат",
    "Воспринимающий", "Выносливый", "Ловкий", "Пловец", "Сильный",
    "Скрытный", "Ловкач", "Секс-работник", "Рыболов", "Бронник",
    "Рисовальщик", "Садовод", "Животновод", "Травник", "Охотник",
    "Рунолог", "Теолог", "Мореход", "Взломщик", "Оценщик", "Тактик",
    "Врачеватель", "Хирург", "Ловушечник", "Маскировщик", "Кулинар",
    "Рукопашник", "Лучник", "Арбалетчик", "Ударник", "Колющий",
    "Рубящий", "Колюще-рубящий", "Колюще-режущий", "Метательный",
    "Огнестрельный", "Взрывчатый", "Щитовик", "Цепной",
]

MERCENARIES_DB = {
    # Ремесло и производство
    "Ремесленник": ["Гравировка", "Ловкость рук", "Выносливость", "Восприятие"],
    "Кузнец": ["Кузнец", "Сила", "Выносливость"],
    "Оружейник": ["Оружейное дело", "Гравировка", "Восприятие", "Кузнец"],
    "Ткач": ["Пошив", "Ловкость рук", "Восприятие", "Красильщик"],
    "Сапожник": ["Пошив", "Ловкость рук", "Резьба по дереву", "Восприятие"],
    "Каменщик": ["Строительство", "Сила", "Выносливость", "Резьба по камню"],
    "Плотник": ["Деревообработка", "Резьба по дереву", "Ловкость рук", "Строительство"],
    "Столяр": ["Деревообработка", "Резьба по дереву", "Ловкость рук", "Восприятие"],
    "Гончар": ["Гончарное дело", "Ловкость рук", "Рисование", "Восприятие"],
    "Мельник": ["Механика", "Выносливость", "Восприятие", "Управление"],
    "Повар": ["Кулинария", "Восприятие", "Ловкость рук", "Травничество"],
    "Мясник": ["Разделка и съём шкур", "Сила", "Восприятие", "Кулинария"],
    "Винодел": ["Виноделие", "Восприятие", "Травничество", "Садоводство"],
    "Табачник": ["Травничество", "Восприятие", "Торговля", "Ловкость рук"],
    "Ювелир": ["Ювелирное дело", "Ловкость рук", "Восприятие", "Гравировка"],
    "Медник": ["Кузнец", "Ловкость рук", "Гравировка", "Восприятие"],
    "Кухарь": ["Кулинария", "Восприятие", "Ловкость рук", "Травничество"],
    "Мастер": ["Управление", "Ловкость рук", "Восприятие", "Обучение"],
    "Мастер на мануфактуре": ["Управление", "Механика", "Восприятие", "Обучение"],
    "Управляющий на мельнице": ["Управление", "Механика", "Восприятие", "Торговля"],
    "Прораб": ["Управление", "Строительство", "Восприятие", "Лидерство"],
    "Надсмотрщик за общественными работами": ["Управление", "Восприятие", "Лидерство", "Сила"],
    "Рабочий на мельнице": ["Механика", "Выносливость", "Восприятие", "Сила"],
    "Рабочий на ферме": ["Садоводство", "Выносливость", "Сила", "Животноводство"],
    "Рабочий на верфи": ["Строительство", "Сила", "Выносливость", "Деревообработка"],
    "Рабочий на кирпичной заводе": ["Строительство", "Сила", "Выносливость", "Механика"],
    "Рабочий на ткацкой фабрике": ["Пошив", "Ловкость рук", "Выносливость", "Восприятие"],
    "Рабочий на мясокомбинате": ["Разделка и съём шкур", "Выносливость", "Сила", "Кулинария"],
    "Рабочий в порту": ["Мореходство", "Сила", "Выносливость", "Торговля"],
    "Чернорабочий": ["Сила", "Выносливость", "Восприятие", "Строительство"],
    "Ремонтник": ["Механика", "Ловкость рук", "Восприятие", "Инженерия"],
    "Ледочист": ["Сила", "Выносливость", "Восприятие", "Выносливость"],
    "Клепальщик": ["Кузнец", "Сила", "Ловкость рук", "Восприятие"],
    "Клиноковщик": ["Кузнец", "Сила", "Ловкость рук", "Оружейное дело"],
    "Железнодорожный техник": ["Механика", "Инженерия", "Восприятие", "Ловкость рук"],
    "Котлобойщик": ["Механика", "Сила", "Восприятие", "Выносливость"],
    "Сельхозтехник": ["Механика", "Садоводство", "Восприятие", "Инженерия"],
    "Пальцевщик": ["Ловкость рук", "Скрытность", "Ловкость", "Восприятие"],
    "Линотипист": ["Писательство", "Восприятие", "Ловкость рук", "Рисование"],
    "Писарь": ["Писательство", "Восприятие", "Ловкость рук", "Картография"],
    "Сиделец": ["Торговля", "Ораторство", "Восприятие", "Оценка"],
    "Продавец": ["Торговля", "Ораторство", "Восприятие", "Оценка"],
    "Продавец тканей": ["Торговля", "Ораторство", "Пошив", "Оценка"],
    
    # Сельское хозяйство и добыча
    "Фермер": ["Садоводство", "Выносливость", "Животноводство", "Травничество"],
    "Фермер-подневольный": ["Садоводство", "Выносливость", "Сила", "Животноводство"],
    "Лесоруб": ["Деревообработка", "Сила", "Выносливость", "Рубящее оружие"],
    "Дровосек": ["Деревообработка", "Сила", "Выносливость", "Рубящее оружие"],
    "Рыбак": ["Рыбная ловля", "Выносливость", "Ловкость", "Восприятие"],
    "Охотник": ["Охота", "Луки", "Выносливость", "Скрытность"],
    "Шахтер": ["Шахтёрское дело", "Сила", "Выносливость", "Восприятие"],
    "Жнец": ["Садоводство", "Выносливость", "Сила", "Ловкость рук"],
    "Сборщик ягод": ["Собирательство", "Восприятие", "Выносливость", "Травничество"],
    "Скотник": ["Животноводство", "Сила", "Приручение", "Выносливость"],
    "Конюх": ["Животноводство", "Наездник", "Приручение", "Сила"],
    "Кардер": ["Пошив", "Ловкость рук", "Восприятие", "Красильщик"],
    "Тесарь": ["Деревообработка", "Сила", "Ловкость рук", "Строительство"],
    "Косарь": ["Садоводство", "Сила", "Выносливость", "Рубящее оружие"],
    "Ловец зверей": ["Охота", "Ловкость", "Приручение", "Скрытность"],
    "Печник": ["Строительство", "Сила", "Восприятие", "Механика"],
    "Рабочий на свинарнике": ["Животноводство", "Сила", "Выносливость", "Приручение"],
    "Рабочий на лесопилке": ["Деревообработка", "Сила", "Выносливость", "Механика"],
    "Рабочий на винодельне": ["Виноделие", "Ловкость рук", "Выносливость", "Восприятие"],
    "Рабочий на шоколадной фабрике": ["Кулинария", "Ловкость рук", "Выносливость", "Восприятие"],
    "Рабочий на стекольной фабрике": ["Стеклодув", "Ловкость рук", "Восприятие", "Механика"],
    "Рабочий на холодильном заводе": ["Выносливость", "Сила", "Восприятие", "Механика"],
    "Рабочий на каменоломне": ["Резьба по камню", "Сила", "Выносливость", "Строительство"],
    
    # Рабы
    "Раб на руднике": ["Шахтёрское дело", "Выносливость", "Сила", "Восприятие"],
    "Раб на каменоломне": ["Резьба по камню", "Сила", "Выносливость", "Строительство"],
    "Раб на верфи": ["Строительство", "Сила", "Выносливость", "Мореходство"],
    "Раб на лесопилке": ["Деревообработка", "Сила", "Выносливость", "Рубящее оружие"],
    "Раб на винодельне": ["Виноделие", "Ловкость рук", "Выносливость", "Восприятие"],
    "Раб на шоколадной фабрике": ["Кулинария", "Ловкость рук", "Выносливость", "Восприятие"],
    "Раб на стекольной фабрике": ["Стеклодув", "Ловкость рук", "Восприятие", "Механика"],
    "Раб на холодильном заводе": ["Выносливость", "Сила", "Восприятие", "Механика"],
    "Раб на саванной": ["Выносливость", "Собирательство", "Охота", "Скрытность"],
    "Эльф раб дварфов": ["Ювелирное дело", "Ловкость рук", "Гравировка", "Восприятие"],
    
    # Военные и охрана
    "Стражник": ["Колюще-режущее оружие", "Сила", "Выносливость", "Восприятие"],
    "Страж": ["Колюще-режущее оружие", "Сила", "Выносливость", "Восприятие"],
    "Капитан стражи": ["Лидерство", "Тактика", "Сила", "Колюще-режущее оружие"],
    "Солдат": ["Колюще-режущее оружие", "Сила", "Выносливость", "Щиты"],
    "Пехотинец": ["Колюще-режущее оружие", "Сила", "Выносливость", "Щиты"],
    "Лучник": ["Луки", "Восприятие", "Ловкость", "Скрытность"],
    "Стрелок": ["Огнестрельное оружие", "Восприятие", "Ловкость", "Скрытность"],
    "Мечник": ["Колюще-режущее оружие", "Сила", "Ловкость", "Щиты"],
    "Копейщик": ["Колющее оружие", "Сила", "Выносливость", "Щиты"],
    "Рыцарь": ["Колюще-режущее оружие", "Сила", "Выносливость", "Наездник"],
    "Рыцарь-дуэлянт": ["Колющее оружие", "Ловкость", "Сила", "Акробатика"],
    "Рыцарь ордена": ["Колюще-режущее оружие", "Сила", "Выносливость", "Теология"],
    "Тевтонский рыцарь": ["Колюще-режущее оружие", "Сила", "Выносливость", "Теология"],
    "Наемник": ["Колюще-режущее оружие", "Сила", "Выносливость", "Тактика"],
    "Наймит": ["Колюще-режущее оружие", "Сила", "Выносливость", "Торговля"],
    "Гвардеец": ["Колюще-режущее оружие", "Сила", "Выносливость", "Восприятие"],
    "Городовой": ["Колюще-режущее оружие", "Сила", "Восприятие", "Ораторство"],
    "Караульный": ["Восприятие", "Выносливость", "Скрытность", "Колюще-режущее оружие"],
    "Ночной сторож": ["Восприятие", "Выносливость", "Скрытность", "Колюще-режущее оружие"],
    "Сторож": ["Восприятие", "Выносливость", "Сила", "Колюще-режущее оружие"],
    "Сторож-охотник": ["Охота", "Луки", "Восприятие", "Скрытность"],
    "Каратель": ["Пытки", "Сила", "Запугивание", "Колюще-режущее оружие"],
    "Палач": ["Пытки", "Сила", "Рубящее оружие", "Восприятие"],
    "Инквизитор": ["Пытки", "Теология", "Восприятие", "Ораторство"],
    "Разведчик": ["Скрытность", "Ловкость", "Восприятие", "Тактика"],
    "Гонец": ["Выносливость", "Ловкость", "Наездник", "Восприятие"],
    "Посланник": ["Ораторство", "Харизма", "Восприятие", "Торговля"],
    "Преследователь": ["Выносливость", "Восприятие", "Скрытность", "Охота"],
    "Оруженосец": ["Оружейное дело", "Сила", "Ловкость", "Колюще-режущее оружие"],
    "Оруженосец графа": ["Оружейное дело", "Сила", "Ловкость", "Наездник"],
    "Военный инженер": ["Инженерия", "Тактика", "Механика", "Строительство"],
    "Артиллерист": ["Взрывчатое оружие", "Восприятие", "Механика", "Сила"],
    "Бомбардир": ["Взрывчатое оружие", "Восприятие", "Сила", "Механика"],
    "Канонир": ["Взрывчатое оружие", "Восприятие", "Сила", "Механика"],
    "Главнокомандующий": ["Лидерство", "Тактика", "Харизма", "Управление"],
    "Командующий ополчением": ["Лидерство", "Тактика", "Харизма", "Колюще-режущее оружие"],
    "Командир корабля": ["Мореходство", "Лидерство", "Навигация", "Управление"],
    "Корабельник": ["Мореходство", "Сила", "Выносливость", "Строительство"],
    "Пират": ["Мореходство", "Сила", "Колюще-режущее оружие", "Торговля"],
    "Осадник": ["Строительство", "Сила", "Тактика", "Взрывчатое оружие"],
    "Гребец": ["Выносливость", "Сила", "Мореходство", "Ловкость"],
    "Тренер": ["Обучение", "Выносливость", "Лидерство", "Рукопашный бой"],
    "Фехтовальщик": ["Колющее оружие", "Ловкость", "Сила", "Акробатика"],
    "Турнирный борец": ["Рукопашный бой", "Сила", "Ловкость", "Выносливость"],
    "Ведьмак": ["Охота", "Алхимия", "Сила", "Выносливость"],
    
    # Магия и религия
    "Кудесник": ["Рунология", "Восприятие", "Алхимия", "Травничество"],
    "Чернокнижник": ["Рунология", "Восприятие", "Алхимия", "Травничество"],
    "Священник": ["Теология", "Ораторство", "Врачевание", "Харизма"],
    "Богослов": ["Теология", "Восприятие", "Писательство", "Обучение"],
    "Богослов-ученый": ["Теология", "Восприятие", "Писательство", "Археология"],
    "Паладин": ["Колюще-режущее оружие", "Сила", "Теология", "Щиты"],
    "Духовный чиновник": ["Теология", "Ораторство", "Управление", "Харизма"],
    "Работник местной церкви": ["Теология", "Восприятие", "Врачевание", "Харизма"],
    "Служитель церкви": ["Теология", "Восприятие", "Врачевание", "Харизма"],
    "Магистрат": ["Управление", "Ораторство", "Восприятие", "Торговля"],
    "Верховный лидер": ["Лидерство", "Харизма", "Тактика", "Управление"],
    "Надзиратель в тюрьме": ["Управление", "Сила", "Восприятие", "Пытки"],
    
    # Слуги и прислуга
    "Слуга": ["Ловкость рук", "Выносливость", "Восприятие", "Кулинария"],
    "Дворецкий": ["Управление", "Восприятие", "Харизма", "Торговля"],
    "Горничная": ["Ловкость рук", "Выносливость", "Восприятие", "Пошив"],
    "Комнатный слуга": ["Ловкость рук", "Выносливость", "Восприятие", "Врачевание"],
    "Лакеи": ["Ловкость рук", "Выносливость", "Восприятие", "Ораторство"],
    "Холоп": ["Выносливость", "Сила", "Восприятие", "Сила"],
    "Подмастерье": ["Обучение", "Ловкость рук", "Восприятие", "Выносливость"],
    "Ученик": ["Обучение", "Восприятие", "Ловкость рук", "Выносливость"],
    "Провизор": ["Алхимия", "Травничество", "Ловкость рук", "Восприятие"],
    "Аптекарь": ["Алхимия", "Травничество", "Ловкость рук", "Врачевание"],
    "Лекарь": ["Врачевание", "Травничество", "Ловкость рук", "Восприятие"],
    "Наставник": ["Обучение", "Восприятие", "Ораторство", "Харизма"],
    "Обучающий наставник": ["Обучение", "Восприятие", "Ораторство", "Харизма"],
    "Исследователь": ["Археология", "Восприятие", "Картография", "Писательство"],
    "Геодезист": ["Картография", "Восприятие", "Математика", "Инженерия"],
    "Водитель транспорта": ["Механика", "Восприятие", "Ловкость", "Наездник"],
    "Распространитель вестей": ["Ораторство", "Восприятие", "Выносливость", "Харизма"],
    
    # Искусство и развлечения
    "Бард": ["Музыка", "Ораторство", "Харизма", "Пение"],
    "Гулящий музыкант": ["Музыка", "Харизма", "Выносливость", "Пение"],
    "Голосистый артист": ["Пение", "Харизма", "Музыка", "Ораторство"],
    "Певец на королевском приеме": ["Пение", "Харизма", "Музыка", "Ораторство"],
    "Певец": ["Пение", "Харизма", "Музыка", "Восприятие"],
    "Актер в театре": ["Ораторство", "Харизма", "Пение", "Восприятие"],
    "Актер": ["Ораторство", "Харизма", "Пение", "Восприятие"],
    "Баянист": ["Музыка", "Ловкость рук", "Восприятие", "Пение"],
    "Фортепианщик": ["Музыка", "Ловкость рук", "Восприятие", "Пение"],
    "Дирижер": ["Музыка", "Лидерство", "Восприятие", "Харизма"],
    "Акробат": ["Акробатика", "Ловкость", "Выносливость", "Сила"],
    "Крылатый факир": ["Акробатика", "Ловкость рук", "Харизма", "Скрытность"],
    "Смотритель зоопарка": ["Приручение", "Животноводство", "Восприятие", "Выносливость"],
}


def normalize_mercenary_name(name: str) -> str:
    """Приводит название к стандартному виду для поиска в базе"""
    name = name.strip().lower()
    name = re.sub(r'\s*[-–—]\s*\d+\s*$', '', name)
    name = re.sub(r'\s+\d+\s*$', '', name)
    name = ' '.join(name.split())
    for key in MERCENARIES_DB.keys():
        if key.lower() == name:
            return key
    return None


def roll_specialization(profession: str) -> Optional[Dict]:
    """Роллит специализацию для профессии, если она есть в списке"""
    if profession not in MERCENARY_SPECIALIZATIONS:
        return None
    
    specializations = MERCENARY_SPECIALIZATIONS[profession]
    return random.choice(specializations)


def has_specialization(profession: str) -> bool:
    """Проверяет, есть ли у профессии специализации"""
    return profession in MERCENARY_SPECIALIZATIONS



# ============================================================================
# 🔧 НАСТРОЙКИ И БАЗА ДАННЫХ
# ============================================================================
# В начале файла, после импортов:
try:
    from g4f.errors import ProviderError, ModelNotFoundError, RequestLimitError, AuthenticationError
except ImportError:
    # Для совместимости со старыми версиями
    ProviderError = ModelNotFoundError = RequestLimitError = AuthenticationError = Exception

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')
IS_RAILWAY = os.getenv('RAILWAY', '').lower() == 'true' or os.getenv('IS_RAILWAY', '').lower() == 'true'
OWNER_ID = int(os.getenv('OWNER_ID', 0))
REQUIRED_ROLE_ID = int(os.getenv('REQUIRED_ROLE_ID', 0))
DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'
MAX_CONCURRENT = int(os.getenv('MAX_CONCURRENT', 5))
PROXY_REFRESH_HOURS = int(os.getenv('PROXY_REFRESH_HOURS', 6))
USE_PROXY = os.getenv('USE_PROXY', 'false').lower() == 'true'


# ✅ Проверка токенов при старте
def check_tokens():
    """Проверяет наличие всех необходимых токенов"""
    tokens = {
        'DISCORD_TOKEN': os.getenv('DISCORD_TOKEN'),
        'GROQ_TOKEN': os.getenv('GROQ_TOKEN'),
        'OPENR_TOKEN': os.getenv('OPENR_TOKEN'),
    }

    for name, value in tokens.items():
        if value:
            logger.info(f"✅ {name}: установлен")
        else:
            logger.warning(f"⚠️ {name}: НЕ НАЙДЕН (функционал будет ограничен)")

    return tokens

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
                record.avg_latency_ms = int(
                    (record.avg_latency_ms * (record.success_count - 1) + latency_ms) / record.success_count)
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
                old_ids = session.query(ModelSuccessLog.id).order_by(ModelSuccessLog.last_success_at.asc()).limit(
                    count - 200).all()
                if old_ids:
                    session.query(ModelSuccessLog).filter(ModelSuccessLog.id.in_([x[0] for x in old_ids])).delete(
                        synchronize_session=False)
                    session.commit()
        except:
            pass

    def get_top_models(self, limit: int = 10) -> List[Tuple[str, str, int]]:
        if not self.SessionLocal: return []
        session = self.SessionLocal()
        try:
            results = session.query(ModelSuccessLog.provider, ModelSuccessLog.model_name,
                                    ModelSuccessLog.avg_latency_ms) \
                .order_by(ModelSuccessLog.success_count.desc(), ModelSuccessLog.avg_latency_ms.asc()) \
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

    def get_all_models(self) -> List[Tuple[str, str]]:
        if not self.SessionLocal: return []
        session = self.SessionLocal()
        try:
            results = session.query(ModelSuccessLog.provider, ModelSuccessLog.model_name) \
                .order_by(ModelSuccessLog.success_count.desc()).all()
            return [(r.provider, r.model_name) for r in results]
        except:
            return []
        finally:
            session.close()


db_manager = DBManager(SessionLocal)

# ============================================================================
# 📂 МЕНЕДЖЕР ВРЕМЕННЫХ ЛОГОВ ТЕСТОВ
# ============================================================================

PENDING_TEST_LOG = "test_pending.csv"


class PendingTestManager:
    def __init__(self, filename: str):
        self.filename = filename
        if not os.path.exists(self.filename):
            with open(self.filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['provider', 'model', 'latency_ms', 'timestamp'])

    def log_success(self, provider: str, model: str, latency_ms: int):
        try:
            with open(self.filename, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([provider, model, latency_ms, datetime.now(timezone.utc).isoformat()])
        except Exception as e:
            logger.error(f"Ошибка записи во временный лог тестов: {e}")

    def read_and_clear(self) -> List[Tuple[str, str, int]]:
        results = []
        if not os.path.exists(self.filename):
            return results
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)
                for row in reader:
                    if len(row) >= 3:
                        results.append((row[0], row[1], int(row[2])))

            with open(self.filename, 'w', encoding='utf-8') as f:
                f.write('provider,model,latency_ms,timestamp\n')

            return results
        except Exception as e:
            logger.error(f"Ошибка чтения временного лога: {e}")
            return []

    def get_pending_models(self) -> List[Tuple[str, str]]:
        models = []
        if not os.path.exists(self.filename):
            return models
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)
                seen = set()
                for row in reader:
                    if len(row) >= 2:
                        key = (row[0], row[1])
                        if key not in seen:
                            models.append(key)
                            seen.add(key)
            return models
        except:
            return []


pending_test_manager = PendingTestManager(PENDING_TEST_LOG)

G4F_DEEP_SCAN_MODELS = {
    "PollinationsAI": ["deepseek-r1", "deepseek-v3", "llama-3.3-70b", "qwen-2.5-72b", "mistral-large"],
    "Vercel": ["deepseek-r1", "llama-3.3-70b", "qwen-2.5-72b"],
    "FreeGPT": ["deepseek-r1", "llama-3.3-70b", "gpt-3.5-turbo"],
    "MyShell": ["llama-3.3-70b", "mistral-large"],
    "Perplexity": ["llama-3.3-70b", "mixtral-8x7b"],
    "Default": ["gpt-3.5-turbo", "llama-3.3-70b", "deepseek-r1", "deepseek-v3"]
}


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

PRIORITY_TIER_1 = [("Default", "deepseek-r1"), ("Default", "deepseek-v3")]
PRIORITY_TIER_2 = [("PollinationsAI", "deepseek-r1"), ("Vercel", "deepseek-r1")]
EXCLUDED_OR_MODELS = ["liquid/lfm-2.5-1.2b-instruct:free"]
OPENROUTER_PRIORITY = "nvidia/nemotron-3-super-120b-a12b:free"

GROQ_PRIORITY_MODELS = [
    "llama-3.3-70b-versatile",
    "meta-llama/llama-4-scout-17b-16e-instruct",
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
Ты — аналитик-модератор RP сервера Discord. Твоя задача — найти ТОЛЬКО явный оффтоп, спам.

📋 ЧТО ИГНОРИРОВАТЬ (НЕ отмечать):
- Любые ролевые действия, описания в **звёздочках**, __подчёркиваниях__ или `код`е, когда они не аномально короткие (тогда проверяй их контекст).
- Диалоги персонажей, сюжетные повороты (даже жестокие, романтические или драматичные).
- Ролевые пинги (@персонаж, @должность) внутри контекста игры.
- Системные сообщения о переходе между локациями (если это часть сюжета).
- Эмоции и реакции персонажей (страх, боль, слезы).
- ВАЖНО: Не оценивай содержание роли (мораль, жестокость, этику), если это не реальный спам/оффтоп.

🚨 ЧТО ФИКСИРОВАТЬ (отмечать ID):
Оффтоп/Спам:
   - Флуд (короткие бессмысленные сообщения подряд: "а", "лол", смайлы без текста).
   - OOC обсуждения ((вне роли), //комментарии, обсуждение механик вне игры).
   - Попрошайничество (просьбы дать ресурсы/деньги вне игрового контекста).
   - Спам пингами (@everyone, @here, массовые упоминания не по делу).
   - Личные оскорбления игроков (не персонажей).
   - Реклама сторонних ресурсов.

📤 ФОРМАТ ОТВЕТА:
Верни ТОЛЬКО номера сообщений (ID) через запятую (например: 5, 12, 28) или NONE если нарушений нет.
Никаких пояснений, текста, кавычек или форматирования кроме списка цифр.

Пример правильного ответа: 3, 7, 15
Пример правильного ответа при отсутствии нарушений: NONE
"""

# ============================================================================
# 📚 ПОЛНЫЕ СПИСКИ МОДЕЛЕЙ ДЛЯ ТЕСТИРОВАНИЯ
# ============================================================================

# Все известные модели Groq (приоритетные + дополнительные)
GROQ_ALL_MODELS = GROQ_PRIORITY_MODELS + [
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
    "llama-3.2-1b-preview",
    "llama-3.2-3b-preview",
    "llama-3.2-11b-vision-preview",
    "llama-3.2-90b-vision-preview",
    "llama-guard-3-8b",
    "llama3-70b-8192",
    "llama3-8b-8192",
]

# Все известные бесплатные/доступные модели OpenRouter
OR_ALL_MODELS = OR_PRIORITY_MODELS + [
    "meta-llama/llama-3-8b-instruct:free",
    "meta-llama/llama-3-70b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
    "mistralai/mixtral-8x7b-instruct:free",
    "google/gemma-2-9b-it:free",
    "huggingfaceh4/zephyr-7b-beta:free",
    "nousresearch/hermes-2-pro-mistral-7b:free",
    "openchat/openchat-7b:free",
    "microsoft/phi-3-mini-128k-instruct:free",
    "microsoft/phi-3-medium-128k-instruct:free",
]


def get_all_g4f_combinations() -> List[Tuple[str, str]]:
    """
    Возвращает ВСЕ комбинации провайдер/модель для G4F:
    - Из конфигурации G4F_DEEP_SCAN_MODELS
    - Из БД (успешные истории)
    - Уникальные, без дубликатов
    """
    combos = []
    seen = set()
    EXCLUDED = ["flux-pro", "liquid/lfm-2.5-1.2b-instruct:free"]

    # 1. Из конфигурации бота
    for prov, models in G4F_DEEP_SCAN_MODELS.items():
        for mod in models:
            key = (prov, mod)
            if key not in seen and mod not in EXCLUDED:
                combos.append(key)
                seen.add(key)

    # 2. Из БД (если подключена) — добавляем успешные модели
    if SessionLocal:
        db_models = db_manager.get_all_models()
        for prov, mod in db_models:
            # Пропускаем не-G4F провайдеры и исключённые модели
            if prov in ["Groq", "OpenRouter"] or mod in EXCLUDED:
                continue
            key = (prov, mod)
            if key not in seen:
                combos.append(key)
                seen.add(key)

    return combos


def get_all_groq_combinations() -> List[Tuple[str, str]]:
    """Возвращает все известные модели Groq"""
    return [("Groq", mod) for mod in GROQ_ALL_MODELS if mod not in EXCLUDED_OR_MODELS]


def get_all_openrouter_combinations() -> List[Tuple[str, str]]:
    """Возвращает все известные модели OpenRouter"""
    return [("OpenRouter", mod) for mod in OR_ALL_MODELS if mod not in EXCLUDED_OR_MODELS]
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


# Добавьте эту функцию в вспомогательные:
def validate_proxy_format(proxy: str) -> bool:
    """Проверяет формат прокси согласно требованиям g4f [[33]]"""
    if not proxy:
        return False
    if not proxy.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
        return False
    try:
        host_port = proxy.split('://')[-1]
        host, port = host_port.rsplit(':', 1)
        return bool(host) and port.isdigit() and 1 <= int(port) <= 65535
    except:
        return False

# Обновите get_random_proxy:
def get_random_proxy(use_proxy: bool) -> Optional[str]:
    if not use_proxy:
        return None
    # Фильтруем только валидные прокси
    valid = [p for p in FREE_PROXY_LIST if validate_proxy_format(p)]
    return random.choice(valid) if valid else None


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

    await interaction.response.send_message(f"❌ Гав! Нет доступа (нужна роль: {', '.join(allowed_role_names)}).",
                                            ephemeral=True)
    return False


def create_progress_bar(current: int, total: int, length: int = 10) -> str:
    if total == 0: return "░" * length
    filled = int(length * current / total)
    return "█" * filled + "░" * (length - filled)


def strip_think_content(text: str) -> str:
    """Удаляет секции <think>...</think> из ответа модели"""
    if not text:
        return text

    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'</?think>', '', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.lstrip()

    return cleaned if cleaned.strip() else text


# ============================================================================
# 🌐 ЗАПРОСЫ К МОДЕЛЯМ (ИСПРАВЛЕНО)
# ============================================================================

async def make_g4f_request(provider_name: str, model: str, prompt: str,
                           timeout: float = 45.0, system_prompt: str = None,
                           proxy_url: str = None) -> Tuple[bool, str, float]:
    """
    Запрос к g4f с корректной обработкой провайдеров
    """
    start = time.time()

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    # Список провайдеров для перебора
    providers_to_try = []
    if provider_name and provider_name != "g4f-default":
        providers_to_try.append(provider_name)
    providers_to_try.extend(["PollinationsAI", "MyShell", "Perplexity", "Vercel"])

    for prov_name in providers_to_try:
        try:
            def sync_call():
                from g4f.client import Client as G4FClient
                client = G4FClient()

                kwargs = {
                    "model": model,
                    "messages": messages,
                    "stream": False,
                }

                # Прокси передаётся в клиент
                if proxy_url and validate_proxy_format(proxy_url):
                    kwargs["proxy"] = proxy_url

                # Провайдер указываем только если он существует
                try:
                    provider_class = getattr(g4f.Provider, prov_name, None)
                    if provider_class:
                        kwargs["provider"] = provider_class
                except:
                    pass

                return client.chat.completions.create(**kwargs)

            response = await asyncio.wait_for(
                asyncio.to_thread(sync_call),
                timeout=timeout + 10
            )

            if response is None:
                raise Exception("Пустой ответ (None)")

            if hasattr(response, 'choices') and response.choices:
                choice = response.choices[0]
                if hasattr(choice, 'message') and hasattr(choice.message, 'content'):
                    answer = choice.message.content
                    if answer and answer.strip():
                        answer = strip_think_content(answer.strip())
                        elapsed = time.time() - start
                        logger.debug(f"✅ G4F {prov_name}/{model} — {elapsed:.2f}s")
                        return True, answer, elapsed
                    else:
                        raise Exception("Пустой content")
                else:
                    raise Exception("Нет message.content")
            else:
                raise Exception(f"Некорректный ответ: {type(response)}")

        except asyncio.TimeoutError:
            logger.debug(f"⏰ G4F {prov_name} таймаут")
            continue
        except Exception as e:
            err_str = str(e).lower()

            if any(kw in err_str for kw in ["api_key", "unauthorized", "authentication", "401"]):
                logger.debug(f"⚠️ G4F {prov_name} требует авторизацию")
                continue

            if any(kw in err_str for kw in ["not found", "does not exist", "404"]):
                logger.debug(f"⚠️ G4F {prov_name}/{model} не найдена")
                continue

            logger.debug(f"⚠️ G4F {prov_name} ошибка: {str(e)[:60]}")
            continue

    elapsed = time.time() - start
    return False, "Все провайдеры G4F недоступны", elapsed


async def test_openrouter_single(models: list, prompt: str, timeout: float = 45.0,
                                 system_prompt: str = None, proxy_url: str = None) -> Tuple[bool, str, float]:
    """
    Запрос к OpenRouter с ВАШИМ именем переменной OPENR_TOKEN
    """
    openrouter_token = os.getenv('OPENR_TOKEN')  # ✅ ВАША переменная
    if not openrouter_token:
        return False, "No OPENR_TOKEN", 0.0

    if isinstance(models, str):
        models = [models]

    start = time.time()
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=openrouter_token,
        timeout=timeout
    )

    for model in models:
        try:
            def sync_call():
                return client.chat.completions.create(
                    model=model,
                    messages=messages,
                    extra_headers={
                        "HTTP-Referer": "https://github.com/psiiinka-bot",
                        "X-Title": "PsIInka Bot",
                    }
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

            raise Exception("Пустой ответ от OpenRouter")

        except Exception as e:
            err_str = str(e).lower()

            if "400" in err_str or "invalid model" in err_str or "not found" in err_str:
                logger.debug(f"⚠️ OR/{model} не подошла")
                continue

            if "timeout" in err_str:
                logger.debug(f"⏰ OR/{model} таймаут")
                continue

            if "429" in err_str or "rate limit" in err_str:
                logger.debug(f"🚫 OR/{model} rate limit")
                await asyncio.sleep(2)
                continue

            if model == models[-1]:
                elapsed = time.time() - start
                return False, f"OR Error: {str(e)[:80]}", elapsed

    elapsed = time.time() - start
    return False, "Все модели OpenRouter недоступны", elapsed


async def test_groq_single(models: list, prompt: str, timeout: float = 45.0,
                           system_prompt: str = None, return_model_name: bool = False) -> Tuple[bool, str, float]:
    """
    Запрос к Groq с ВАШИМ именем переменной GROQ_TOKEN
    """
    groq_token = os.getenv('GROQ_TOKEN')  # ✅ ВАША переменная
    if not groq_token:
        return False, "No GROQ_TOKEN", 0.0

    if isinstance(models, str):
        models = [models]

    client = Groq(api_key=groq_token, timeout=timeout)
    start = time.time()

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    for model in models:
        try:
            def sync_call():
                return client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.5,
                )

            response = await asyncio.wait_for(
                asyncio.to_thread(sync_call),
                timeout=timeout + 5
            )

            if response.choices and len(response.choices) > 0:
                elapsed = time.time() - start
                content = response.choices[0].message.content

                if content and content.strip():
                    logger.debug(f"✅ Groq/{model} — {elapsed:.2f}s")

                    if return_model_name:
                        return True, f"{model}: {content}", elapsed
                    else:
                        return True, content, elapsed

            raise Exception("Пустой ответ от Groq")

        except Exception as e:
            err_str = str(e).lower()

            if "timeout" in err_str:
                logger.debug(f"⏰ Groq/{model} таймаут")
                elapsed = time.time() - start
                return False, f"Таймаут {timeout}с", elapsed

            if "429" in err_str or "rate limit" in err_str:
                logger.debug(f"🚫 Groq/{model} rate limit")
                await asyncio.sleep(2)
                continue

            if "404" in err_str or "not found" in err_str:
                logger.debug(f"⚠️ Groq/{model} не найдена")
                continue

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
                            new_rolls_to_process.append((len(res.dice_rolls) - 1, new_roll))
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
            if op == '+':
                res.total += val
            elif op == '-':
                res.total -= val
            elif op == '*':
                res.total *= val
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

async def get_priority_queue():
    """
    Очередь для /скажи:
    1. Временный файл тестов
    2. Groq модели
    3. OpenRouter модели
    4. БД
    5. G4F модели (в конце)
    """
    queue = []
    seen = set()

    EXCLUDED_MODELS = ["flux-pro", "liquid/lfm-2.5-1.2b-instruct:free"]

    # 1. Временный файл тестов
    pending = pending_test_manager.get_pending_models()
    for prov, mod in pending:
        if (prov, mod) not in seen and mod not in EXCLUDED_MODELS:
            queue.append((prov, mod))
            seen.add((prov, mod))

    # 2. Groq модели
    for groq_model in GROQ_PRIORITY_MODELS:
        if ("Groq", groq_model) not in seen and groq_model not in EXCLUDED_MODELS:
            queue.append(("Groq", groq_model))
            seen.add(("Groq", groq_model))

    # 3. OpenRouter модели
    for or_model in OR_PRIORITY_MODELS:
        if ("OpenRouter", or_model) not in seen and or_model not in EXCLUDED_MODELS:
            queue.append(("OpenRouter", or_model))
            seen.add(("OpenRouter", or_model))

    # 4. Модели из БД
    if SessionLocal:
        db_models = db_manager.get_all_models()
        for prov, mod in db_models:
            if (prov, mod) not in seen and mod not in EXCLUDED_MODELS:
                queue.append((prov, mod))
                seen.add((prov, mod))

    # 5. G4F модели (в конце)
    if ("g4f-default", "deepseek-r1") not in seen:
        queue.append(("g4f-default", "deepseek-r1"))
        seen.add(("g4f-default", "deepseek-r1"))

    for prov, models in G4F_DEEP_SCAN_MODELS.items():
        for mod in models:
            if (prov, mod) not in seen and mod not in EXCLUDED_MODELS:
                queue.append((prov, mod))
                seen.add((prov, mod))

    return queue


async def get_analysis_priority_queue():
    """
    Очередь для /анализ:
    1. БД (самый высокий приоритет)
    2. Временный файл тестов
    3. Groq модели
    4. OpenRouter модели
    5. G4F модели (в конце)
    """
    queue = []
    seen = set()
    EXCLUDED_MODELS = ["flux-pro", "liquid/lfm-2.5-1.2b-instruct:free"]

    # 1. БД — самый высокий приоритет
    if SessionLocal:
        db_models = db_manager.get_all_models()
        for prov, mod in db_models:
            if (prov, mod) not in seen and mod not in EXCLUDED_MODELS:
                queue.append((prov, mod))
                seen.add((prov, mod))

    # 2. Временный файл тестов
    pending = pending_test_manager.get_pending_models()
    for prov, mod in pending:
        if (prov, mod) not in seen and mod not in EXCLUDED_MODELS:
            queue.append((prov, mod))
            seen.add((prov, mod))

    # 3. Groq модели
    for groq_model in GROQ_PRIORITY_MODELS:
        if ("Groq", groq_model) not in seen and groq_model not in EXCLUDED_MODELS:
            queue.append(("Groq", groq_model))
            seen.add(("Groq", groq_model))

    # 4. OpenRouter модели
    for or_model in OR_PRIORITY_MODELS:
        if ("OpenRouter", or_model) not in seen and or_model not in EXCLUDED_MODELS:
            queue.append(("OpenRouter", or_model))
            seen.add(("OpenRouter", or_model))

    # 5. G4F модели (в конце)
    if ("g4f-default", "deepseek-r1") not in seen:
        queue.append(("g4f-default", "deepseek-r1"))
        seen.add(("g4f-default", "deepseek-r1"))

    for prov, models in G4F_DEEP_SCAN_MODELS.items():
        for mod in models:
            if (prov, mod) not in seen and mod not in EXCLUDED_MODELS:
                queue.append((prov, mod))
                seen.add((prov, mod))

    return queue


@bot.slash_command(name="скажи", description="Запрос к ИИ")
async def slash_say(interaction: disnake.CommandInteraction,
                    вопрос: str = commands.Param(min_length=1, description="Ваш вопрос или запрос"),
                    прокси: str = commands.Param(choices=["Да", "Нет"], default="Нет",
                                                 description="Использовать прокси")):
    if not await check_access(interaction):
        return

    try:
        await interaction.response.defer()

        status_embed = disnake.Embed(
            title="🐕 ПсИИнка слушает...",
            description="*виляет хвостом* Сейчас прогавкаю ответ, хозяин! ⏳",
            color=0xFF8844,
            timestamp=datetime.now()
        )
        status_embed.add_field(name="📡 Статус", value="ПсИИнка принюхивается к нейросети...", inline=False)
        status_embed.set_footer(text="Может занять до 45 секунд 🐾")

        msg = await interaction.edit_original_response(embed=status_embed)

        queue = await get_priority_queue()

        system_prompt = "Ты помощник по имени Псинка (мальчик). Отвечай кратко на русском и по делу, отвечай развёрнуто в случае нужды в глубинном анализе вопроса или при запросе пользователя."
        final_response = None
        final_prov = "?"
        final_mod = "?"
        final_lat = 0.0
        use_proxy = (прокси == "Да") and USE_PROXY
        proxy_url = get_random_proxy(use_proxy) if use_proxy else None
        used_temp_file = False

        for idx, (prov, mod) in enumerate(queue):
            try:
                status_embed.description = f"*рычит на нейросети* Попытка {idx + 1}/{len(queue)}: `{prov}` / `{mod}`"
                status_embed.set_field_at(0, name="📡 Статус", value=f"ПсИИнка лает на **{prov}**... 🐕", inline=False)
                await msg.edit(embed=status_embed)

                if prov == "OpenRouter":
                    ok, ans, lat = await test_openrouter_single([mod], вопрос, timeout=45.0,
                                                                system_prompt=system_prompt, proxy_url=proxy_url)
                elif prov == "Groq":
                    ok, ans, lat = await test_groq_single([mod], вопрос, timeout=45.0, system_prompt=system_prompt,
                                                          return_model_name=False)
                else:
                    ok, ans, lat = await make_g4f_request(prov, mod, вопрос, timeout=45.0, system_prompt=system_prompt,
                                                          proxy_url=proxy_url)

                if ok and ans and len(ans.strip()) > 0:  # ✅ Проверка на пустой ответ
                    final_response = strip_think_content(ans)
                    final_prov, final_mod = prov, mod
                    final_lat = lat
                    pending_models = pending_test_manager.get_pending_models()
                    if (prov, mod) in pending_models:
                        used_temp_file = True
                    if not used_temp_file and SessionLocal:
                        db_manager.log_success(prov, mod, int(lat * 1000))
                    break

            except Exception as e:
                logger.warning(f"Error {prov}/{mod}: {e}", exc_info=True)
                continue

        if not final_response:
            error_embed = disnake.Embed(
                title="❌ ПсИИнка устал...",
                description="*повесил уши* Ни одна нейросеть не ответила, хозяин... 🐕",
                color=0xFF4444,
                timestamp=datetime.now()
            )
            error_embed.add_field(name="💡 Что делать?",
                                  value="• Проверь токены в .env 🔑\n• Проверь интернет 🌐\n• Попробуй позже 💤",
                                  inline=False)
            await msg.edit(embed=error_embed)
            return

        await msg.delete()

        header_text = f"🐕 **ПсИИнка прогавкал ответ!**\n"
        header_text += f"*виляет хвостом* Держи, хозяин:\n\n"
        header_text += f"📊 **Источник:** `{final_prov}` / `{final_mod}`\n"
        header_text += f"⏱ **Время:** `{final_lat:.2f}с` | 📏 **Длина:** `{len(final_response)} симв.`\n"
        header_text += f"🔀 **Прокси:** `{прокси}`\n"
        header_text += f"{'─' * 40}\n\n"

        MAX_CHUNK_SIZE = 1900
        chunks = []

        first_chunk = header_text + final_response[:MAX_CHUNK_SIZE - len(header_text)]
        chunks.append(first_chunk)

        remaining = final_response[MAX_CHUNK_SIZE - len(header_text):]
        while remaining:
            chunks.append(remaining[:MAX_CHUNK_SIZE])
            remaining = remaining[MAX_CHUNK_SIZE:]

        first_msg = await interaction.channel.send(chunks[0])

        for i in range(1, len(chunks)):
            await interaction.channel.send(chunks[i], reference=first_msg, mention_author=False)

    except Exception as e:
        logger.error(f"Critical error in /say: {e}", exc_info=True)
        err_msg = f"❌ Гав! Ошибка: {str(e)[:100]}"
        if interaction.response.is_done():
            await interaction.followup.send(err_msg, ephemeral=True)
        else:
            await interaction.response.send_message(err_msg, ephemeral=True)


@bot.slash_command(name="кубик", description="Бросок кубиков")
async def slash_cube(interaction: disnake.CommandInteraction,
                     формула: Optional[str] = commands.Param(
                         description="Формула броска (например: 2d6+5 или dndstats)", default=None)):
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

            output_embed.add_field(name=f"Бросок #{i + 1}", value=field_value, inline=False)

        if len(results) > 1:
            output_embed.add_field(name="📈 Общая сумма", value=f"**{total_all}** *тяв!*", inline=False)

        output_embed.set_footer(text="ПсИИнка бот | Dice Roller 🐾")
        await interaction.followup.send(embed=output_embed)

    except Exception as e:
        logger.error(f"Error in /cube: {e}", exc_info=True)
        error_embed = disnake.Embed(
            title="❌ ПсИИнка не понял...",
            description=f"*склонил голову набок* Не могу разобрать: `{формула}` 🐕",
            color=0xFF4444,
            timestamp=datetime.now()
        )
        error_embed.add_field(name="💡 Помощь", value="*Гавкни* `/кубик` без параметров — я покажу справку!",
                              inline=False)
        await interaction.followup.send(embed=error_embed, ephemeral=True)


@bot.slash_command(name="погавкай", description="Проверка пинга бота")
async def slash_bark(interaction: disnake.CommandInteraction):
    try:
        ping_ms = round(bot.latency * 1000)
        status = "🟢" if ping_ms < 100 else "🟡" if ping_ms < 300 else "🔴"

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

        embed = disnake.Embed(
            title="📊 ПсИИнка отчитывается",
            description="*виляет хвостом* Вот моя статистика, хозяин! 🐕",
            color=0x00FF88,
            timestamp=datetime.now()
        )

        if top:
            stats_text = ""
            for i, (p, m, lat) in enumerate(top, 1):
                medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i - 1] if i <= 5 else f"{i}."
                stats_text += f"{medal} `{p}` / `{m}` — `{lat}мс`\n"

            embed.add_field(name="🏆 Топ-10 моделей", value=stats_text, inline=False)
        else:
            embed.add_field(name="📭 Данные", value="Нет записей. *Гавкни* `/скажи` для начала сбора статистики!",
                            inline=False)

        embed.add_field(name="🔧 Режим", value="Экономия ресурсов (No Warmup)\nБД: " + (
            "✅ Подключена *гав!*" if db_manager.has_data() else "⚠️ Отключена *скулит*"), inline=False)
        embed.set_footer(text="ПсИИнка бот | Statistics 🐾")

        await interaction.edit_original_response(embed=embed)

    except Exception as e:
        logger.error(f"Error in /status: {e}", exc_info=True)
        await interaction.followup.send(f"❌ Гав! Ошибка: {str(e)[:100]}", ephemeral=True)


# ============================================================================
# 🧪 ТЕСТИРОВАНИЕ (ОБНОВЛЁННОЕ — МАССОВОЕ ПО ПРОВАЙДЕРАМ)
# ============================================================================

async def test_provider_models(provider: str, models: list, prompt: str = TEST_PROMPT,
                               timeout: float = 30.0, system_prompt: str = None,
                               use_proxy: bool = False) -> List[Dict]:
    """Универсальная функция для тестирования всех моделей провайдера"""
    results = []

    for model in models:
        start = time.time()
        try:
            proxy_url = get_random_proxy(use_proxy) if use_proxy else None

            if provider == "OpenRouter":
                ok, ans, lat = await test_openrouter_single([model], prompt, timeout=timeout,
                                                            system_prompt=system_prompt, proxy_url=proxy_url)
            elif provider == "Groq":
                ok, ans, lat = await test_groq_single([model], prompt, timeout=timeout,
                                                      system_prompt=system_prompt, return_model_name=False)
            else:  # G4F провайдеры
                ok, ans, lat = await make_g4f_request(provider, model, prompt, timeout=timeout,
                                                      system_prompt=system_prompt, proxy_url=proxy_url)

            result = {
                'model': model,
                'success': ok,
                'latency': round(lat, 2),
                'error': ans if not ok else None,
                'answer_preview': ans[:100] if ok and ans else None
            }

            # Логгируем успешные тесты
            if ok:
                pending_test_manager.log_success(provider, model, int(lat * 1000))

            results.append(result)
            await asyncio.sleep(0.3)  # Небольшая пауза между запросами

        except Exception as e:
            results.append({
                'model': model,
                'success': False,
                'latency': 0,
                'error': str(e)[:80],
                'answer_preview': None
            })

    return results


def format_test_results(provider: str, results: List[Dict], max_show: int = 10) -> str:
    """Форматирует результаты тестов для вывода в embed"""
    if not results:
        return "❌ Нет данных *скулит*"

    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]

    output = f"**Всего:** `{len(results)}` | ✅ Успешно: `{len(successful)}` | ❌ Ошибок: `{len(failed)}`\n\n"

    # Показываем топ быстрых успешных
    if successful:
        successful_sorted = sorted(successful, key=lambda x: x['latency'] if x['latency'] else 999)
        output += "**🏆 Топ быстрых:**\n"
        for r in successful_sorted[:max_show]:
            emoji = "🥇" if r == successful_sorted[0] else "•"
            output += f"{emoji} `{r['model']}` — `{r['latency']}с`\n"
        if len(successful) > max_show:
            output += f"_и ещё {len(successful) - max_show} успешных..._\n"
        output += "\n"

    # Показываем первые ошибки если есть
    if failed and len(failed) <= 3:
        output += "**❌ Ошибки:**\n"
        for r in failed[:3]:
            output += f"• `{r['model']}`: {r['error']}\n"
        if len(failed) > 3:
            output += f"_и ещё {len(failed) - 3} ошибок..._\n"

    return output.strip()


class TestModeView(disnake.ui.View):
    def __init__(self, ctx=None):
        super().__init__(timeout=None)

    @disnake.ui.button(label="⚡ Тест ВСЕ G4F", style=disnake.ButtonStyle.green, custom_id="test_all_g4f")
    async def all_g4f_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        log_analysis("TEST: All G4F providers started", "INFO")
        start = time.time()

        # ✅ Получаем ВСЕ комбинации G4F, а не только приоритетные
        all_combinations = get_all_g4f_combinations()

        if not all_combinations:
            await interaction.followup.send("❌ Гав! Нет моделей G4F для теста. *нюхает*", ephemeral=True)
            return

        progress_embed = disnake.Embed(
            title="🔄 ПсИИнка тестирует G4F...",
            description=f"*нюхает* Всего моделей: `{len(all_combinations)}` 🐕",
            color=0xFF8844,
            timestamp=datetime.now()
        )
        progress_embed.add_field(name="Прогресс", value="`[░░░░░░░░░░] 0%`", inline=False)
        progress_embed.add_field(name="Статус", value="Запуск тестов...", inline=False)
        progress_msg = await interaction.followup.send(embed=progress_embed, ephemeral=True)

        all_results = []
        semaphore = asyncio.Semaphore(3)  # Ограничение параллельных запросов

        async def test_single(prov, mod):
            async with semaphore:
                try:
                    ok, ans, lat = await make_g4f_request(prov, mod, TEST_PROMPT, timeout=45.0)
                    if ok:
                        pending_test_manager.log_success(prov, mod, int(lat * 1000))
                    return {
                        'provider': prov,
                        'model': mod,
                        'success': ok,
                        'latency': round(lat, 2) if lat else 0,
                        'error': ans if not ok else None
                    }
                except Exception as e:
                    return {
                        'provider': prov,
                        'model': mod,
                        'success': False,
                        'latency': 0,
                        'error': str(e)[:80]
                    }

        tasks = [test_single(p, m) for p, m in all_combinations]

        for i, task in enumerate(asyncio.as_completed(tasks)):
            res = await task
            all_results.append(res)
            percent = int(((i + 1) / len(tasks)) * 100)
            bar = create_progress_bar(i + 1, len(tasks))

            try:
                progress_embed.set_field_at(0, name="Прогресс", value=f"`[{bar}] {percent}%`", inline=False)
                succ = len([r for r in all_results if r['success']])
                progress_embed.set_field_at(1, name="Статус",
                                            value=f"*лает на* `{res['provider']}`/`{res['model']}` 🐕\n✅ Успешно: `{succ}`",
                                            inline=False)
                await progress_msg.edit(embed=progress_embed)
            except:
                pass  # Игнорируем ошибки обновления сообщения

        elapsed = time.time() - start
        successful = [r for r in all_results if r['success']]

        # Группируем результаты по провайдерам
        by_provider = {}
        for r in all_results:
            prov = r['provider']
            if prov not in by_provider:
                by_provider[prov] = []
            by_provider[prov].append(r)

        final_embed = disnake.Embed(
            title="✅ ПсИИнка закончил тест G4F!",
            description=f"*виляет хвостом* Общее время: `{elapsed:.0f}с` 🐕\n📊 **Итого:** `{len(successful)}/{len(all_results)}` успешных",
            color=0x00FF88 if successful else 0xFF4444,
            timestamp=datetime.now()
        )

        # Статистика по каждому провайдеру
        for prov, prov_results in sorted(by_provider.items()):
            succ = len([r for r in prov_results if r['success']])
            if succ > 0:
                avg_lat = round(sum(r['latency'] for r in prov_results if r['success']) / succ, 2)
                final_embed.add_field(
                    name=f"📡 {prov} ({succ}/{len(prov_results)})",
                    value=f"⏱ Ср. время: `{avg_lat}с`",
                    inline=True
                )
            else:
                final_embed.add_field(
                    name=f"📡 {prov} (0/{len(prov_results)})",
                    value="❌ Все неудачны",
                    inline=True
                )

        # Топ-5 самых быстрых моделей
        if successful:
            top_fast = sorted(successful, key=lambda x: x['latency'] if x['latency'] else 999)[:5]
            top_text = "\n".join([f"• `{r['provider']}`/`{r['model']}` — `{r['latency']}с`" for r in top_fast])
            final_embed.add_field(name="🏆 Топ-5 быстрых", value=top_text, inline=False)

        # Если есть ошибки — покажем первые 3
        failed = [r for r in all_results if not r['success']]
        if failed:
            err_text = "\n".join([f"• `{r['provider']}`/`{r['model']}`: {r['error']}" for r in failed[:3]])
            if len(failed) > 3:
                err_text += f"\n_и ещё {len(failed) - 3} ошибок..._"
            final_embed.add_field(name="❌ Ошибки", value=err_text, inline=False)

        await progress_msg.edit(embed=final_embed)
        log_analysis(f"TEST G4F All: {len(successful)}/{len(all_results)} success, {elapsed:.1f}s", "INFO")

    @disnake.ui.button(label="🦅 Тест ВСЕ Groq", style=disnake.ButtonStyle.blurple, custom_id="test_all_groq")
    async def all_groq_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        log_analysis("TEST: All Groq models started", "INFO")
        start = time.time()

        # ✅ Используем ВСЕ известные модели Groq, а не только приоритетные
        all_combinations = get_all_groq_combinations()

        if not all_combinations:
            await interaction.followup.send("❌ Гав! Нет моделей Groq для теста. *нюхает*", ephemeral=True)
            return

        progress_embed = disnake.Embed(
            title="🔄 ПсИИнка тестирует Groq...",
            description=f"*нюхает* Всего моделей: `{len(all_combinations)}` 🐕",
            color=0x5865F2,
            timestamp=datetime.now()
        )
        progress_embed.add_field(name="Прогресс", value="`[░░░░░░░░░░] 0%`", inline=False)
        progress_embed.add_field(name="Статус", value="Запуск тестов...", inline=False)
        progress_msg = await interaction.followup.send(embed=progress_embed, ephemeral=True)

        all_results = []

        for i, (prov, model) in enumerate(all_combinations):
            try:
                # ✅ Используем request_timeout вместо timeout для Groq SDK [[61]][[67]]
                ok, ans, lat = await test_groq_single(
                    [model],
                    TEST_PROMPT,
                    timeout=45.0,
                    system_prompt="Ты тестовый ИИ.",
                    return_model_name=False
                )

                if ok:
                    pending_test_manager.log_success(prov, model, int(lat * 1000))

                result = {
                    'model': model,
                    'success': ok,
                    'latency': round(lat, 2) if lat else 0,
                    'error': ans if not ok else None
                }
                all_results.append(result)

                # Обновляем прогресс
                percent = int(((i + 1) / len(all_combinations)) * 100)
                bar = create_progress_bar(i + 1, len(all_combinations))
                progress_embed.set_field_at(0, name="Прогресс", value=f"`[{bar}] {percent}%`", inline=False)
                status = "✅" if ok else "❌"
                progress_embed.set_field_at(1, name="Статус", value=f"*лает на* `{model}` {status} 🐕", inline=False)
                await progress_msg.edit(embed=progress_embed)

                await asyncio.sleep(0.3)  # Пауза между запросами

            except Exception as e:
                all_results.append({
                    'model': model,
                    'success': False,
                    'latency': 0,
                    'error': str(e)[:80]
                })

        elapsed = time.time() - start
        successful = [r for r in all_results if r['success']]

        final_embed = disnake.Embed(
            title="✅ ПсИИнка закончил тест Groq!",
            description=f"*виляет хвостом* Общее время: `{elapsed:.0f}с` 🐕\n📊 **Итого:** `{len(successful)}/{len(all_combinations)}` успешных",
            color=0x00FF88 if successful else 0xFF4444,
            timestamp=datetime.now()
        )

        # Детали по каждой модели (сортируем: успешные с быстрым временем вверху)
        details = ""
        for r in sorted(all_results, key=lambda x: (not x['success'], x['latency'] if x['success'] else 999)):
            emoji = "✅" if r['success'] else "❌"
            latency_str = f"`{r['latency']}с`" if r['success'] and r['latency'] > 0 else "—"
            details += f"{emoji} `{r['model']}` — {latency_str}\n"

        final_embed.add_field(name="📋 Результаты по моделям", value=details or "❌ Нет данных", inline=False)

        if successful:
            top_fast = sorted(successful, key=lambda x: x['latency'] if x['latency'] else 999)[:3]
            top_text = "\n".join([f"• `{r['model']}` — `{r['latency']}с`" for r in top_fast])
            final_embed.add_field(name="🏆 Топ-3 быстрых", value=top_text, inline=True)

        await progress_msg.edit(embed=final_embed)
        log_analysis(f"TEST Groq All: {len(successful)}/{len(all_combinations)} success, {elapsed:.1f}s", "INFO")

    @disnake.ui.button(label="🌐 Тест ВСЕ OpenRouter", style=disnake.ButtonStyle.gray, custom_id="test_all_openrouter")
    async def all_openrouter_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        log_analysis("TEST: All OpenRouter models started", "INFO")
        start = time.time()

        # ✅ Используем ВСЕ известные модели OpenRouter, а не только приоритетные
        all_combinations = get_all_openrouter_combinations()

        if not all_combinations:
            await interaction.followup.send("❌ Гав! Нет моделей OpenRouter для теста. *нюхает*", ephemeral=True)
            return

        progress_embed = disnake.Embed(
            title="🔄 ПсИИнка тестирует OpenRouter...",
            description=f"*нюхает* Всего моделей: `{len(all_combinations)}` 🐕",
            color=0x95A5A6,
            timestamp=datetime.now()
        )
        progress_embed.add_field(name="Прогресс", value="`[░░░░░░░░░░] 0%`", inline=False)
        progress_embed.add_field(name="Статус", value="Запуск тестов...", inline=False)
        progress_msg = await interaction.followup.send(embed=progress_embed, ephemeral=True)

        all_results = []

        for i, (prov, model) in enumerate(all_combinations):
            try:
                # ✅ Передаём правильные заголовки: X-Title вместо X-OpenRouter-Title [[51]]
                ok, ans, lat = await test_openrouter_single(
                    [model],
                    TEST_PROMPT,
                    timeout=45.0,
                    system_prompt="Ты тестовый ИИ."
                )

                if ok:
                    pending_test_manager.log_success(prov, model, int(lat * 1000))

                result = {
                    'model': model,
                    'success': ok,
                    'latency': round(lat, 2) if lat else 0,
                    'error': ans if not ok else None
                }
                all_results.append(result)

                # Обновляем прогресс
                percent = int(((i + 1) / len(all_combinations)) * 100)
                bar = create_progress_bar(i + 1, len(all_combinations))
                progress_embed.set_field_at(0, name="Прогресс", value=f"`[{bar}] {percent}%`", inline=False)
                status = "✅" if ok else "❌"
                progress_embed.set_field_at(1, name="Статус", value=f"*лает на* `{model}` {status} 🐕", inline=False)
                await progress_msg.edit(embed=progress_embed)

                await asyncio.sleep(0.3)  # Пауза между запросами

            except Exception as e:
                all_results.append({
                    'model': model,
                    'success': False,
                    'latency': 0,
                    'error': str(e)[:80]
                })

        elapsed = time.time() - start
        successful = [r for r in all_results if r['success']]

        final_embed = disnake.Embed(
            title="✅ ПсИИнка закончил тест OpenRouter!",
            description=f"*виляет хвостом* Общее время: `{elapsed:.0f}с` 🐕\n📊 **Итого:** `{len(successful)}/{len(all_combinations)}` успешных",
            color=0x00FF88 if successful else 0xFF4444,
            timestamp=datetime.now()
        )

        # Детали по каждой модели
        details = ""
        for r in sorted(all_results, key=lambda x: (not x['success'], x['latency'] if x['success'] else 999)):
            emoji = "✅" if r['success'] else "❌"
            latency_str = f"`{r['latency']}с`" if r['success'] and r['latency'] > 0 else "—"
            details += f"{emoji} `{r['model']}` — {latency_str}\n"

        final_embed.add_field(name="📋 Результаты по моделям", value=details or "❌ Нет данных", inline=False)

        if successful:
            top_fast = sorted(successful, key=lambda x: x['latency'] if x['latency'] else 999)[:3]
            top_text = "\n".join([f"• `{r['model']}` — `{r['latency']}с`" for r in top_fast])
            final_embed.add_field(name="🏆 Топ-3 быстрых", value=top_text, inline=True)

        await progress_msg.edit(embed=final_embed)
        log_analysis(f"TEST OpenRouter All: {len(successful)}/{len(all_combinations)} success, {elapsed:.1f}s", "INFO")

    @disnake.ui.button(label="🔍 Полное сканирование", style=disnake.ButtonStyle.red, custom_id="test_full")
    async def all_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        await interaction.followup.send("🔄 ПсИИнка начинает полное сканирование... *нюхает* (это займёт время) 🐕",
                                        ephemeral=True)
        asyncio.create_task(run_mass_test(interaction.channel))


@bot.slash_command(name="тест", description="Тестирование провайдеров и моделей")
async def slash_test(interaction: disnake.CommandInteraction):
    try:
        if not await check_access(interaction):
            return

        # ✅ Получаем актуальные количества моделей для отображения в описании
        g4f_count = len(get_all_g4f_combinations())
        groq_count = len(get_all_groq_combinations())
        or_count = len(get_all_openrouter_combinations())
        total_count = g4f_count + groq_count + or_count

        embed = disnake.Embed(
            title="🛠 ПсИИнка: Проверка нейросетей",
            description=f"""**Выбери, что потестим, хозяин:** 🐕

*виляет хвостом и ждёт команду*

⚡ **Тест ВСЕ G4F** — `{g4f_count}` моделей
   └─ Время: ~{max(40, g4f_count * 13)} сек (параллельно ×3)
   └─ ⚠️ Может занять до {(g4f_count * 40) // 60 + 1} мин при медленных провайдерах

🦅 **Тест ВСЕ Groq** — `{groq_count}` моделей
   └─ Время: ~{groq_count * 40} сек (последовательно)

🌐 **Тест ВСЕ OpenRouter** — `{or_count}` моделей
   └─ Время: ~{or_count * 40} сек (последовательно)

🔍 **Полное сканирование** — ВСЕ провайдеры (`{total_count}` моделей)
   └─ Время: ~10-20 минут (зависит от стабильности провайдеров)
   └─ Режим: параллельные запросы (×3 для G4F) + прогресс-бар

> ℹ️ Все тесты используют каскадный перебор, логируют успехи в БД 
> и поддерживают прокси для обхода ограничений.
""",
            color=0xFF8844,
            timestamp=datetime.now()
        )
        embed.add_field(
            name="📊 Что проверяется",
            value=(
                "• ⚡ Скорость ответа (латентность)\n"
                "• 🌐 Стабильность соединения\n"
                "• 🤖 Работоспособность моделей\n"
                "• 🔀 Обход блокировок (прокси)"
            ),
            inline=False
        )
        embed.add_field(
            name="💾 Сохранение результатов",
            value=(
                "✅ Успешные тесты → `test_pending.csv`\n"
                "🔧 Команда `/записать_тест` → БД Neon\n"
                "📈 Команда `/статус` → топ моделей"
            ),
            inline=False
        )
        embed.set_footer(text="ПсИИнка бот | Diagnostics 🐾")

        view = TestModeView()
        await interaction.response.send_message(embed=embed, view=view)

    except Exception as e:
        logger.error(f"Error in /test: {e}", exc_info=True)
        err_msg = f"❌ Гав! Ошибка: {str(e)[:100]}"
        if interaction.response.is_done():
            await interaction.followup.send(err_msg, ephemeral=True)
        else:
            await interaction.response.send_message(err_msg, ephemeral=True)


# ============================================================================
# 📊 МАССОВОЕ ТЕСТИРОВАНИЕ (СОБАЧИЙ СТИЛЬ)
# ============================================================================

async def run_mass_test(channel):
    progress_embed = disnake.Embed(
        title="🔄 ПсИИнка сканирует...",
        description="*нюхает* G4F (Deep) + Groq + OpenRouter... 🐕",
        color=0xFF8844,
        timestamp=datetime.now()
    )
    progress_embed.add_field(name="Прогресс", value="`[░░░░░░░░░░] 0%`", inline=False)
    progress_msg = await channel.send(embed=progress_embed)

    start_time = time.time()

    combinations = []

    for prov, models in G4F_DEEP_SCAN_MODELS.items():
        for mod in models:
            combinations.append((prov, mod))

    for m in GROQ_PRIORITY_MODELS:
        combinations.append(("Groq", m))

    for m in OR_PRIORITY_MODELS:
        combinations.append(("OpenRouter", m))

    results = []
    total = len(combinations)
    semaphore = asyncio.Semaphore(5)

    async def test_combo(provider, model):
        async with semaphore:
            start = time.time()
            try:
                if provider == "OpenRouter":
                    ok, ans, lat = await test_openrouter_single([model], TEST_PROMPT, timeout=45.0)
                elif provider == "Groq":
                    ok, ans, lat = await test_groq_single([model], TEST_PROMPT, timeout=45.0, return_model_name=False)
                else:
                    ok, ans, lat = await make_g4f_request(provider, model, TEST_PROMPT, timeout=45.0)

                if ok:
                    pending_test_manager.log_success(provider, model, int(lat * 1000))

                return {'provider': provider, 'model': model, 'success': ok, 'time': lat,
                        'error': ans if not ok else None}
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
            progress_embed.set_field_at(0, name="Прогресс", value=f"`[{bar}] {percent}%`\n⏳ Прошло: {elapsed:.0f}с",
                                        inline=False)

            success_count = len([r for r in results if r['success']])
            progress_embed.set_field_at(1, name="📊 Статистика",
                                        value=f"✅ Успешно: {success_count} *гав!*\n❌ Ошибок: {len(results) - success_count} *скулит*",
                                        inline=False)

            await progress_msg.edit(embed=progress_embed)
        except:
            pass

    elapsed_total = time.time() - start_time
    successful = [r for r in results if r['success']]

    final_embed = disnake.Embed(
        title="✅ ПсИИнка закончил тест!",
        description=f"*виляет хвостом* Общее время: `{elapsed_total:.0f}с` ({elapsed_total / 60:.1f} мин) 🐕",
        color=0x00FF88,
        timestamp=datetime.now()
    )
    final_embed.add_field(name="📊 Результаты",
                          value=f"✅ Успешно: `{len(successful)}/{total}` *гав!*\n📈 Процент: `{int(len(successful) / total * 100)}%`",
                          inline=False)

    if successful:
        successful.sort(key=lambda x: x['time'] if x['time'] else 999)
        top_text = ""
        for r in successful[:5]:
            top_text += f"• `{r['provider']}`/{r['model']} — `{r['time']:.2f}с`\n"
        final_embed.add_field(name="🏆 Топ-5 быстрых", value=top_text, inline=False)

    await progress_msg.edit(embed=final_embed)


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

        main_queue = await get_analysis_priority_queue()

        for i in range(0, len(messages_data), BATCH_SIZE):
            batch_data = messages_data[i: i + BATCH_SIZE]
            current_batch = (i // BATCH_SIZE) + 1
            batch_context = format_messages_for_ai(batch_data)
            user_prompt = f"Пакет {current_batch}/{total_batches}:\n\n{batch_context}"

            final_answer = None
            success = False
            used_provider = "Unknown"
            used_temp_file = False

            async def try_request(prov, mod, use_proxy=False):
                proxy_str = get_random_proxy(True) if use_proxy else None
                if prov == "OpenRouter":
                    return await test_openrouter_single(mod, user_prompt, timeout=50.0,
                                                        system_prompt=ANALYSIS_SYSTEM_PROMPT)
                elif prov == "Groq":
                    return await test_groq_single(mod, user_prompt, timeout=50.0, system_prompt=ANALYSIS_SYSTEM_PROMPT,
                                                  return_model_name=False)
                else:
                    return await make_g4f_request(prov, mod, user_prompt, timeout=50.0,
                                                  system_prompt=ANALYSIS_SYSTEM_PROMPT, proxy_url=proxy_str)

            for prov, mod in main_queue:
                try:
                    percent = int(((current_batch - 1) / total_batches) * 100)
                    bar = create_progress_bar(current_batch - 1, total_batches)

                    progress_embed.set_field_at(0, name="Прогресс", value=f"`[{bar}] {percent}%`", inline=False)
                    progress_embed.set_field_at(1, name="Статус", value=f"*лает на* `{prov}`... 🐕", inline=False)
                    await status_msg.edit(embed=progress_embed)

                    ok, ans, lat = await try_request(prov, mod, False)
                    if ok:
                        final_answer = ans
                        used_provider = f"{prov} ({mod})"
                        success = True
                        pending_models = pending_test_manager.get_pending_models()
                        if (prov, mod) in pending_models:
                            used_temp_file = True
                        if not used_temp_file:
                            db_manager.log_success(prov, mod, int(lat * 1000))
                        break
                except Exception as e:
                    log_analysis(f"Error {prov}/{mod}: {e}", "DEBUG")
                    continue

            if not success:
                log_analysis(f"⚠️ Batch {current_batch}: Activating PROXY MODE.", "WARNING")
                progress_embed.set_field_at(1, name="Статус", value="⚠️ ПРОКСИ РЕЖИМ... *нюхает* 🔀", inline=False)
                await status_msg.edit(embed=progress_embed)

                for prov, mod in main_queue:
                    try:
                        ok, ans, lat = await try_request(prov, mod, True)
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

        header_embed = disnake.Embed(
            title="🚨 ПсИИнка нашёл нарушения!",
            description=f"*рычит на нарушителей* Найдено **{len(all_violations)}** нарушений 🐕",
            color=0xFF4444,
            timestamp=datetime.now()
        )
        header_embed.add_field(name="Канал", value=f"#{канал.name}", inline=True)
        header_embed.add_field(name="Период", value=f"{days_to_check} дней", inline=True)
        header_embed.add_field(name="Сообщений проверено", value=f"`{len(messages_data)}`", inline=True)

        await status_msg.edit(content=None, embed=header_embed)

        for part in report_parts:
            await interaction.channel.send(part)

        await interaction.channel.send("✅ ПсИИнка закончил! *виляет хвостом* 🐕")
        log_analysis(f"Analysis finished: {len(all_violations)} violations reported.", "INFO")

    except Exception as e:
        error_trace = traceback.format_exc()
        log_analysis(f"CRITICAL ERROR: {e}\n{error_trace}", "ERROR")
        logger.error(f"Critical error in /analyze: {e}", exc_info=True)
        await interaction.followup.send(f"❌ ПсИИнка ошибся... *повесил уши*\nЛог сохранен.\nОшибка: {str(e)[:100]} 🐕",
                                        ephemeral=True)


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
        await interaction.followup.send("❌ Гав! Не удалось экспортировать данные или БД не подключена. *скулит*",
                                        ephemeral=True)


@bot.slash_command(name="очистить_бд", description="Полная очистка таблицы успехов в БД")
async def slash_clear_db(interaction: disnake.CommandInteraction):
    if interaction.author.id != OWNER_ID:
        await interaction.response.send_message("❌ Гав! Доступ запрещён.", ephemeral=True)
        return

    await interaction.response.defer()

    if not SessionLocal:
        await interaction.followup.send("❌ Гав! БД не подключена.", ephemeral=True)
        return

    session = SessionLocal()
    try:
        count = session.query(ModelSuccessLog).count()
        session.query(ModelSuccessLog).delete()
        session.commit()
        await interaction.followup.send(f"✅ ПсИИнка очистил БД! Удалено записей: `{count}` *виляет хвостом* 🐕",
                                        ephemeral=True)
    except Exception as e:
        session.rollback()
        logger.error(f"Error clearing DB: {e}")
        await interaction.followup.send(f"❌ Ошибка очистки: {str(e)[:100]}", ephemeral=True)
    finally:
        session.close()


@bot.slash_command(name="записать_тест", description="Перенос данных из временного лога тестов в БД")
async def slash_commit_tests(interaction: disnake.CommandInteraction):
    if interaction.author.id != OWNER_ID:
        await interaction.response.send_message("❌ Гав! Доступ запрещён.", ephemeral=True)
        return

    await interaction.response.defer()

    records = pending_test_manager.read_and_clear()
    if not records:
        await interaction.followup.send("ℹ️ ПсИИнка проверил временный лог — там пусто. *нюхает* 🐕", ephemeral=True)
        return

    count = 0
    if SessionLocal:
        session = SessionLocal()
        try:
            for prov, mod, lat in records:
                db_manager.log_success(prov, mod, lat)
                count += 1
            session.commit()
            await interaction.followup.send(f"✅ ПсИИнка записал `{count}` успешных тестов в БД! *виляет хвостом* 🐕",
                                            ephemeral=True)
        except Exception as e:
            session.rollback()
            logger.error(f"Error committing tests: {e}")
            await interaction.followup.send(f"❌ Ошибка записи: {str(e)[:100]}", ephemeral=True)
        finally:
            session.close()
    else:
        await interaction.followup.send("❌ Гав! БД не подключена, данные сохранены только в файле.", ephemeral=True)

# ============================================================================
# 🛡️ КОМАНДА: НАЁМНИК (ОБНОВЛЁННАЯ СО СПЕЦИАЛИЗАЦИЯМИ)
# ============================================================================

def roll_skill_level() -> str:
    """Роллит уровень навыка по заданным шансам"""
    roll = random.randint(1, 100)
    cumulative = 0
    for level, chance in MERCENARY_SKILL_PROBABILITIES.items():
        cumulative += chance
        if roll <= cumulative:
            return level
    return "Новичок"


def get_skill_level_emoji(level: str) -> str:
    """Возвращает эмодзи для уровня навыка"""
    emojis = {
        "Новичок": "🔰",
        "Опытный": "✅",
        "Ветеран": "⭐",
        "Мастер": "🏆",
        "Легендарный Мастер": "👑"
    }
    return emojis.get(level, "•")


@bot.slash_command(name="наёмник", description="Получить информацию о наёмнике")
async def slash_mercenary(interaction: disnake.CommandInteraction,
                          имя: str = commands.Param(min_length=1, description="Название наёмника (например: Гончар, Мечник)")):
    try:
        await interaction.response.defer()

        # Нормализуем имя для поиска
        mercenary_name = normalize_mercenary_name(имя)

        if not mercenary_name or mercenary_name not in MERCENARIES_DB:
            error_embed = disnake.Embed(
                title="❌ Ошибка",
                description=f"Наёмник **`{имя}`** не найден в базе.",
                color=0xFF4444,
                timestamp=datetime.now()
            )
            error_embed.set_footer(text="ПсИИнка бот | Mercenary System 🐾")
            await interaction.edit_original_response(embed=error_embed)
            return

        # Получаем пул навыков
        skill_pool = MERCENARIES_DB[mercenary_name]
        
        # Проверяем специализацию
        specialization = roll_specialization(mercenary_name)
        spec_skills = []
        
        if specialization:
            # Заменяем 1-2 навыка из пула на навыки специализации
            spec_skills = specialization["skills"][:2]  # Берём максимум 2 навыка из специализации
        
        # Роллим уровни для каждого навыка
        skills_with_levels = []
        for i, skill in enumerate(skill_pool):
            # Если есть специализация и это один из первых навыков — заменяем
            if specialization and i < len(spec_skills):
                skill = spec_skills[i]
            
            level = roll_skill_level()
            skills_with_levels.append((skill, level))

        # Сортируем по уровню (от высшего к низшему)
        level_order = ["Легендарный Мастер", "Мастер", "Ветеран", "Опытный", "Новичок"]
        skills_with_levels.sort(key=lambda x: level_order.index(x[1]) if x[1] in level_order else 999)

        # Формируем текст навыков
        skills_text = ""
        for skill, level in skills_with_levels:
            emoji = get_skill_level_emoji(level)
            skills_text += f"{emoji} **{skill}** — `{level}`\n"

        # Создаём embed
        embed = disnake.Embed(
            title=f"🛡️ Наёмник: {mercenary_name}",
            description=f"Карточка наёмника с навыками",
            color=0xFF8844,
            timestamp=datetime.now()
        )

        # Добавляем специализацию если есть
        if specialization:
            embed.add_field(
                name="🎯 Специализация",
                value=f"**{specialization['name']}**\n_Влияет на навыки: {', '.join(specialization['skills'])}_",
                inline=False
            )

        # Блок навыков
        embed.add_field(
            name="📚 Навыки",
            value=skills_text if skills_text else "❓ Навыки не определены",
            inline=False
        )

        # Блок снаряжения (пока пустой)
        embed.add_field(
            name="🎒 Снаряжение",
            value="*Ожидает заполнения...*",
            inline=False
        )

        embed.set_footer(text=f"ПсИИнка бот | Mercenary: {mercenary_name} 🐾")

        await interaction.edit_original_response(embed=embed)

    except Exception as e:
        logger.error(f"Error in /mercenary: {e}", exc_info=True)
        error_embed = disnake.Embed(
            title="❌ Ошибка",
            description=f"Произошла ошибка при генерации наёмника.\n\n`{str(e)[:200]}`",
            color=0xFF4444,
            timestamp=datetime.now()
        )
        error_embed.set_footer(text="ПсИИнка бот | Error 🐾")
        
        if interaction.response.is_done():
            await interaction.followup.send(embed=error_embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=error_embed, ephemeral=True)


# ============================================================================
# СОБЫТИЯ
# ============================================================================

@bot.event
async def on_ready():
    check_tokens()  # ✅ Проверка токенов
    logger.info(f"Bot {bot.user} ready! (Railway: {IS_RAILWAY})")
    logger.info("🚀 MODE: NO WARMUP (DB SAVING ENABLED)")

    if REQUIRED_ROLE_ID == 0:
        logger.info("Mode: Role 'Псарь' access.")
    else:
        logger.info(f"Mode: Role ID {REQUIRED_ROLE_ID} access.")

    if USE_PROXY:
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
        except:
            pass


if __name__ == "__main__":
    logger.info("🚀 Start PsIInka Bot v2.0-Full-Integrated")
    try:
        bot.run(os.getenv("DISCORD_TOKEN"))
    except Exception as e:
        logger.critical(f"💥 Startup crash: {e}", exc_info=True)
