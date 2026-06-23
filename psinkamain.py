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
import zipfile
from xml.sax.saxutils import escape as xml_escape
import json
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


def normalize_lookup_text(text: str) -> str:
    """Единая нормализация: ё/е, дефисы, номера и лишние пробелы."""
    text = (text or "").strip().lower().replace("ё", "е")
    text = re.sub(r'\s*[-–—]\s*\d+\s*$', '', text)
    text = re.sub(r'\s+\d+\s*$', '', text)
    text = re.sub(r'[-–—]+', ' ', text)
    return ' '.join(text.split())


def normalize_mercenary_name(name: str) -> Optional[str]:
    """Приводит название к стандартному виду для поиска в базе."""
    normalized = normalize_lookup_text(name)
    aliases = {
        "шахтер": "Шахтер",
        "шахтерское дело": "Шахтер",
        "наемник": "Наемник",
        "наемник обычный": "Наемник",
    }
    if normalized in aliases and aliases[normalized] in MERCENARIES_DB:
        return aliases[normalized]
    for key in MERCENARIES_DB.keys():
        if normalize_lookup_text(key) == normalized:
            return key
    return None


def dedupe_preserve_order(items: List[str]) -> List[str]:
    """Убирает дубли, сохраняя порядок и исходное написание первого вхождения."""
    result = []
    seen = set()
    for item in items:
        key = normalize_lookup_text(item)
        if key and key not in seen:
            result.append(item)
            seen.add(key)
    return result


def get_known_skills() -> set:
    """Собирает список уже существующих навыков из MERCENARIES_DB."""
    skills = set()
    for pool in MERCENARIES_DB.values():
        skills.update(pool)
    return skills


def normalize_skill_name(skill: str, known_skills: set) -> Optional[str]:
    """Не добавляет новые названия навыков: приводит специализации к уже имеющимся навыкам."""
    key = normalize_lookup_text(skill)
    aliases = {
        "кузнец": "Кузнец",
        "стеклодув": "Стеклодув",
        "красильщик": "Красильщик",
        "бронник": "Бронник",
        "лечение": "Врачевание",
        "мореход": "Мореходство",
        "писатель": "Писательство",
        "наездник": "Наездник",
        "лучник": "Луки",
        "тактик": "Тактика",
        "теолог": "Теология",
        "рунолог": "Рунология",
        "взломщик": "Взлом",
        "оценщик": "Оценка",
        "пловец": "Плавание",
        "сильный": "Сила",
        "ловкий": "Ловкость",
        "выносливый": "Выносливость",
        "скрытный": "Скрытность",
    }
    if key in aliases and aliases[key] in known_skills:
        return aliases[key]
    for known in known_skills:
        if normalize_lookup_text(known) == key:
            return known
    return None


def sanitize_specialization(spec: Dict, known_skills: set) -> Optional[Dict]:
    """Чистит навыки специализации: только существующие навыки, без дублей."""
    if not spec:
        return None
    clean_skills = []
    for skill in spec.get("skills", []):
        normalized = normalize_skill_name(skill, known_skills)
        if normalized:
            clean_skills.append(normalized)
    clean_skills = dedupe_preserve_order(clean_skills)
    if not clean_skills:
        return None
    return {"name": spec.get("name", "Специализация"), "skills": clean_skills}


def roll_specialization(profession: str) -> Optional[Dict]:
    """Роллит специализацию для профессии, если она есть в списке."""
    if profession not in MERCENARY_SPECIALIZATIONS:
        return None
    known_skills = get_known_skills()
    clean_specs = []
    for spec in MERCENARY_SPECIALIZATIONS[profession]:
        clean = sanitize_specialization(spec, known_skills)
        if clean:
            clean_specs.append(clean)
    return random.choice(clean_specs) if clean_specs else None


def has_specialization(profession: str) -> bool:
    """Проверяет, есть ли у профессии специализации."""
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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler('bot_errors.log', encoding='utf-8', delay=True)],
    force=True
)
logger = logging.getLogger(__name__)

load_dotenv()


def safe_int_env(name: str, default: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        logger.warning(f"⚠️ {name}: ожидалось число, получено `{raw}`. Использую {default}.")
        return default


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "да", "on"}


DATABASE_URL = os.getenv('DATABASE_URL')
IS_RAILWAY = env_bool('RAILWAY') or env_bool('IS_RAILWAY')
OWNER_ID = safe_int_env('OWNER_ID', 0)
REQUIRED_ROLE_ID = safe_int_env('REQUIRED_ROLE_ID', 0)
DEBUG = env_bool('DEBUG', False)
MAX_CONCURRENT = max(1, safe_int_env('MAX_CONCURRENT', 5))
PROXY_REFRESH_HOURS = max(1, safe_int_env('PROXY_REFRESH_HOURS', 6))
USE_PROXY = env_bool('USE_PROXY', False)
ai_semaphore = asyncio.Semaphore(MAX_CONCURRENT)


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

    def is_connected(self) -> bool:
        return self.SessionLocal is not None

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

    def read_records(self) -> List[Tuple[str, str, int]]:
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
            return results
        except Exception as e:
            logger.error(f"Ошибка чтения временного лога: {e}")
            return []

    def clear(self):
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                f.write('provider,model,latency_ms,timestamp\n')
        except Exception as e:
            logger.error(f"Ошибка очистки временного лога: {e}")

    def read_and_clear(self) -> List[Tuple[str, str, int]]:
        results = self.read_records()
        if results:
            self.clear()
        return results

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
    ],
    force=True
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
EXCLUDED_OR_MODELS = ["liquid/lfm-2.5-1.2b-instruct:free", "llama-3.1-8b-instant"]
OPENROUTER_PRIORITY = "nvidia/nemotron-3-super-120b-a12b:free"

GROQ_PRIORITY_MODELS = [
    "llama-3.3-70b-versatile",
    "meta-llama/llama-4-scout-17b-16e-instruct",
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


def dedupe_combinations(combinations: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    result = []
    seen = set()
    for provider, model in combinations:
        if not provider or not model or model in EXCLUDED_OR_MODELS:
            continue
        key = (provider, model)
        if key not in seen:
            result.append(key)
            seen.add(key)
    return result


def get_db_combinations(provider: Optional[str] = None) -> List[Tuple[str, str]]:
    if not SessionLocal:
        return []
    combos = db_manager.get_all_models()
    if provider:
        combos = [(p, m) for p, m in combos if p == provider]
    return combos


async def fetch_groq_model_ids() -> List[str]:
    token = os.getenv('GROQ_TOKEN')
    if not token:
        return []
    try:
        headers = {"Authorization": f"Bearer {token}"}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get("https://api.groq.com/openai/v1/models", timeout=15) as response:
                if response.status != 200:
                    logger.warning(f"Groq models list status: {response.status}")
                    return []
                data = await response.json()
                return [item.get('id') for item in data.get('data', []) if item.get('id')]
    except Exception as e:
        logger.warning(f"Не удалось получить живой список Groq моделей: {e}")
        return []


async def fetch_openrouter_model_ids(free_only: bool = True) -> List[str]:
    headers = {}
    token = os.getenv('OPENR_TOKEN')
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get("https://openrouter.ai/api/v1/models", timeout=20) as response:
                if response.status != 200:
                    logger.warning(f"OpenRouter models list status: {response.status}")
                    return []
                data = await response.json()
                models = []
                for item in data.get('data', []):
                    model_id = item.get('id')
                    if not model_id:
                        continue
                    if free_only and not model_id.endswith(':free'):
                        pricing = item.get('pricing') or {}
                        prompt_price = str(pricing.get('prompt', ''))
                        completion_price = str(pricing.get('completion', ''))
                        if prompt_price not in {'0', '0.0'} or completion_price not in {'0', '0.0'}:
                            continue
                    models.append(model_id)
                return models
    except Exception as e:
        logger.warning(f"Не удалось получить живой список OpenRouter моделей: {e}")
        return []


async def get_all_groq_combinations_live() -> List[Tuple[str, str]]:
    live_models = await fetch_groq_model_ids()
    source_models = live_models if live_models else GROQ_ALL_MODELS
    combos = [("Groq", m) for m in GROQ_PRIORITY_MODELS]
    combos += get_db_combinations("Groq")
    combos += [("Groq", m) for m in source_models]
    return dedupe_combinations(combos)


async def get_all_openrouter_combinations_live() -> List[Tuple[str, str]]:
    live_models = await fetch_openrouter_model_ids(free_only=True)
    source_models = live_models if live_models else OR_ALL_MODELS
    combos = [("OpenRouter", m) for m in OR_PRIORITY_MODELS]
    combos += get_db_combinations("OpenRouter")
    combos += [("OpenRouter", m) for m in source_models]
    return dedupe_combinations(combos)


async def get_all_test_combinations_live() -> List[Tuple[str, str]]:
    combos = []
    combos.extend(get_all_g4f_combinations())
    combos.extend(await get_all_groq_combinations_live())
    combos.extend(await get_all_openrouter_combinations_live())
    return dedupe_combinations(combos)
# ============================================================================
# 🛠 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

async def fetch_free_proxies(count: int = 20) -> List[str]:
    """Загружает свежие HTTP-прокси. Не используется по умолчанию, только если /скажи прокси=Да."""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=http&timeout=10000&limit={count}"
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    text = await response.text()
                    proxies = [f"http://{p.strip()}" for p in text.split('\n') if p.strip() and ':' in p]
                    proxies = [p for p in proxies if validate_proxy_format(p)]
                    if proxies:
                        logger.info(f"🌐 Обновлён список прокси: {len(proxies)} шт.")
                        return proxies
    except Exception as e:
        logger.warning(f"⚠️ Не удалось обновить прокси: {e}")
    return [p for p in FREE_PROXY_LIST if validate_proxy_format(p)]


def validate_proxy_format(proxy: str) -> bool:
    """Проверяет формат прокси: http(s)/socks + host:port."""
    if not proxy:
        return False
    if not proxy.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
        return False
    try:
        host_port = proxy.split('://')[-1]
        host, port = host_port.rsplit(':', 1)
        return bool(host) and port.isdigit() and 1 <= int(port) <= 65535
    except Exception:
        return False


proxy_lock = asyncio.Lock()
proxy_last_refresh = 0.0


async def ensure_proxy_list(force: bool = False) -> List[str]:
    """Обновляет глобальный список прокси по требованию, а не при обычном старте."""
    global FREE_PROXY_LIST, proxy_last_refresh
    now = time.time()
    refresh_after = PROXY_REFRESH_HOURS * 3600
    valid_current = [p for p in FREE_PROXY_LIST if validate_proxy_format(p)]
    if valid_current and not force and now - proxy_last_refresh < refresh_after:
        return valid_current

    async with proxy_lock:
        now = time.time()
        valid_current = [p for p in FREE_PROXY_LIST if validate_proxy_format(p)]
        if valid_current and not force and now - proxy_last_refresh < refresh_after:
            return valid_current
        FREE_PROXY_LIST = await fetch_free_proxies()
        proxy_last_refresh = time.time()
        return [p for p in FREE_PROXY_LIST if validate_proxy_format(p)]


def get_random_proxy(use_proxy: bool) -> Optional[str]:
    if not use_proxy:
        return None
    valid = [p for p in FREE_PROXY_LIST if validate_proxy_format(p)]
    return random.choice(valid) if valid else None


async def get_random_proxy_async(use_proxy: bool) -> Optional[str]:
    if not use_proxy:
        return None
    proxies = await ensure_proxy_list()
    return random.choice(proxies) if proxies else None


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
        self.all_rolls: List[int] = []
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
        results: List[DiceResult] = []
        if not command_str or not command_str.strip():
            return results

        command_str = command_str.strip()
        parts = command_str.split(maxsplit=1)
        alias = parts[0].lower() if parts else ""
        if alias in self.aliases:
            tail = parts[1] if len(parts) > 1 else ""
            command_str = (self.aliases[alias] + " " + tail).strip()

        for expression in command_str.split(';')[:4]:
            expression = expression.strip()
            if not expression:
                continue
            parsed = self._parse_expression(expression)
            results.extend(parsed)

        return results[:80]

    def _parse_expression(self, expression: str) -> List[DiceResult]:
        comment = ""
        if '!' in expression:
            expression, comment = expression.split('!', 1)
            expression = expression.strip()
            comment = comment.strip()

        num_sets = 1
        set_match = re.match(r'^(\d+)\s+(.+)$', expression.strip())
        if set_match and 'd' in set_match.group(2).lower():
            num_sets = max(1, min(int(set_match.group(1)), 20))
            expression = set_match.group(2).strip()

        results = []
        for _ in range(num_sets):
            result = self._roll_once(expression)
            if result:
                result.comment = comment
                results.append(result)
        return results

    def _extract_modifier(self, expression: str) -> Tuple[str, Optional[Tuple[str, float]]]:
        modifier_match = re.search(r'(?<![a-zA-Z])([+\-*/])\s*(-?\d+(?:\.\d+)?)\s*$', expression)
        if not modifier_match:
            return expression, None
        op = modifier_match.group(1)
        value = float(modifier_match.group(2))
        return expression[:modifier_match.start()].strip(), (op, value)

    def _roll_once(self, expression: str) -> Optional[DiceResult]:
        res = DiceResult()
        expr_without_modifier, modifier = self._extract_modifier(expression.strip())

        dice_match = re.search(r'(\d*)d(\d+)', expr_without_modifier, re.IGNORECASE)
        if not dice_match:
            num_match = re.fullmatch(r'\s*(-?\d+(?:\.\d+)?)\s*', expression)
            if num_match:
                res.total = float(num_match.group(1))
                res.details = [f"Статическое значение: {res.total:g}"]
                return res
            return None

        num_dice = int(dice_match.group(1) or 1)
        num_sides = int(dice_match.group(2))
        num_dice = max(1, min(num_dice, 100))
        num_sides = max(2, min(num_sides, 100))

        tail = expr_without_modifier[dice_match.end():]

        def find_flag(names: List[str]) -> Optional[re.Match]:
            names_sorted = sorted(names, key=len, reverse=True)
            pattern = r'(?<![a-zA-Z])(' + '|'.join(map(re.escape, names_sorted)) + r')\s*(\d+)?\b'
            return re.search(pattern, tail, re.IGNORECASE)

        rolls = [random.randint(1, num_sides) for _ in range(num_dice)]
        res.all_rolls = rolls.copy()
        working_rolls = rolls.copy()

        reroll_match = find_flag(['ir', 'r'])
        if reroll_match:
            threshold = int(reroll_match.group(2) or 1)
            infinite = reroll_match.group(1).lower() == 'ir'
            threshold = max(1, min(threshold, num_sides))
            rerolled_count = 0
            for i, value in enumerate(working_rolls):
                safety = 0
                if value <= threshold:
                    new_value = random.randint(1, num_sides)
                    rerolled_count += 1
                    working_rolls[i] = new_value
                    res.all_rolls.append(new_value)
                    if infinite:
                        while working_rolls[i] <= threshold and safety < 100:
                            working_rolls[i] = random.randint(1, num_sides)
                            res.all_rolls.append(working_rolls[i])
                            rerolled_count += 1
                            safety += 1
            if rerolled_count:
                res.rerolled = True
                res.details.append(f"🔄 Перебросы ≤{threshold}: {rerolled_count}")

        explode_match = find_flag(['ie', 'e'])
        if explode_match:
            explode_val = int(explode_match.group(2) or num_sides)
            infinite = explode_match.group(1).lower() == 'ie'
            explode_val = max(1, min(explode_val, num_sides))
            to_check = list(working_rolls)
            exploded_count = 0
            max_explodes = 100 if infinite else len(to_check)
            while to_check and exploded_count < max_explodes:
                current = to_check.pop(0)
                if current >= explode_val:
                    new_roll = random.randint(1, num_sides)
                    working_rolls.append(new_roll)
                    res.all_rolls.append(new_roll)
                    res.exploded_rolls.append(new_roll)
                    exploded_count += 1
                    if infinite and new_roll >= explode_val:
                        to_check.append(new_roll)
            if res.exploded_rolls:
                res.details.append(f"💥 Взрывы ≥{explode_val}: +{len(res.exploded_rolls)}")

        selected_rolls = working_rolls.copy()
        keep_drop_match = find_flag(['kh', 'kl', 'k', 'dh', 'dl', 'd'])
        if keep_drop_match:
            flag = keep_drop_match.group(1).lower()
            amount = int(keep_drop_match.group(2) or 1)
            amount = max(0, min(amount, len(selected_rolls)))
            indexed = list(enumerate(selected_rolls))
            if amount > 0 and amount < len(selected_rolls):
                if flag in ('k', 'kh'):
                    keep_indexes = {idx for idx, _ in sorted(indexed, key=lambda x: x[1], reverse=True)[:amount]}
                    label = f"📌 Оставлено лучших: {amount}"
                elif flag == 'kl':
                    keep_indexes = {idx for idx, _ in sorted(indexed, key=lambda x: x[1])[:amount]}
                    label = f"📌 Оставлено худших: {amount}"
                elif flag in ('d', 'dl'):
                    drop_indexes = {idx for idx, _ in sorted(indexed, key=lambda x: x[1])[:amount]}
                    keep_indexes = {idx for idx, _ in indexed if idx not in drop_indexes}
                    label = f"🗑 Сброшено худших: {amount}"
                else:  # dh
                    drop_indexes = {idx for idx, _ in sorted(indexed, key=lambda x: x[1], reverse=True)[:amount]}
                    keep_indexes = {idx for idx, _ in indexed if idx not in drop_indexes}
                    label = f"🗑 Сброшено лучших: {amount}"

                res.kept_dice = [val for idx, val in indexed if idx in keep_indexes]
                res.dropped_dice = [val for idx, val in indexed if idx not in keep_indexes]
                selected_rolls = res.kept_dice.copy()
                res.details.append(label)
            elif amount >= len(selected_rolls) and flag.startswith('d'):
                res.dropped_dice = selected_rolls.copy()
                selected_rolls = []
                res.details.append(f"🗑 Сброшены все кубики: {amount}")

        target_match = find_flag(['t'])
        if target_match:
            target = int(target_match.group(2) or num_sides)
            target = max(1, min(target, num_sides))
            res.successes = sum(1 for value in selected_rolls if value >= target)
            res.failures = len(selected_rolls) - res.successes
            res.botches = sum(1 for value in selected_rolls if value == 1)
            res.total = float(res.successes)
            res.details.append(f"✅ Цель ≥{target}: успехов {res.successes}, провалов {res.failures}")
        else:
            res.total = float(sum(selected_rolls))

        if modifier:
            op, val = modifier
            old_total = res.total
            if op == '+':
                res.total += val
            elif op == '-':
                res.total -= val
            elif op == '*':
                res.total *= val
            elif op == '/' and val != 0:
                res.total /= val
            elif op == '/' and val == 0:
                res.details.append("⚠️ Деление на ноль пропущено")
            if not (op == '/' and val == 0):
                display_val = int(val) if val == int(val) else val
                res.details.append(f"🧮 Модификатор: {old_total:g} {op} {display_val} = {res.total:g}")

        res.dice_rolls = selected_rolls.copy()
        if res.dropped_dice:
            res.details.append(f"🗑 Сброшено: {res.dropped_dice}")
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
• `A; B; C` — несколько разных бросков одной командой

**Модификаторы:**
• `eZ` — Взрывающиеся кубики на Z один раз (пример: `3d6 e6`)
• `ieZ` — Взрывающиеся кубики с цепной реакцией
• `kZ` / `khZ` — Оставить Z лучших (пример: `4d6 k3`)
• `klZ` — Оставить Z худших
• `dZ` / `dlZ` — Сбросить Z худших
• `dhZ` — Сбросить Z лучших
• `rZ` — Один раз перебросить кубики ≤ Z
• `irZ` — Перебрасывать ≤ Z до успеха или лимита защиты
• `tZ` — Считать успехи при ≥ Z вместо суммы

**Алиасы:**
• `dndstats` — 6 наборов 4d6 k3 (статы D&D)
• `attack` — 1d20 (атака)
• `+d20` — преимущество, 2d20 d1
• `-d20` — помеха, 2d20 kl1
• `stat` — 4d6 k3 (один стат)
• `save` — 1d20 + 5

**Ограничения:** макс. 100 граней, 100 кубиков, 20 наборов, 4 формулы через `;`
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
        semaphore_acquired = False
        await ai_semaphore.acquire()
        semaphore_acquired = True

        queue = await get_priority_queue()

        system_prompt = "Ты помощник по имени Псинка (мальчик). Отвечай кратко на русском и по делу, отвечай развёрнуто в случае нужды в глубинном анализе вопроса или при запросе пользователя."
        final_response = None
        final_prov = "?"
        final_mod = "?"
        final_lat = 0.0
        use_proxy = (прокси == "Да")
        proxy_url = await get_random_proxy_async(use_proxy)
        proxy_display = "Да" if proxy_url else "Нет"
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

        if semaphore_acquired:
            ai_semaphore.release()
            semaphore_acquired = False

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
        header_text += f"🔀 **Прокси:** `{proxy_display}`\n"
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
        if 'semaphore_acquired' in locals() and semaphore_acquired:
            ai_semaphore.release()
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

            detail_lines = []
            for detail in r.details:
                if detail.startswith("🎲 Бросок:"):
                    continue
                if detail not in detail_lines:
                    detail_lines.append(detail)
            if details_extra:
                for detail in details_extra:
                    if detail not in detail_lines:
                        detail_lines.append(detail)
            if detail_lines:
                field_value += "\n" + "\n".join(f"• {d}" for d in detail_lines[:8])

            output_embed.add_field(name=f"Бросок #{i + 1}", value=field_value[:1024], inline=False)

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

        db_state = "✅ Подключена *гав!*" if db_manager.is_connected() else "⚠️ Отключена *скулит*"
        data_state = "✅ Есть записи" if db_manager.has_data() else "📭 Записей пока нет"
        embed.add_field(name="🔧 Режим", value=f"Экономия ресурсов (No Warmup)\nБД: {db_state}\nДанные: {data_state}", inline=False)
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
        all_combinations = await get_all_groq_combinations_live()

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
        all_combinations = await get_all_openrouter_combinations_live()

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
        groq_count = len(await get_all_groq_combinations_live())
        or_count = len(await get_all_openrouter_combinations_live())
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
    progress_embed.add_field(name="📊 Статистика", value="✅ Успешно: 0\n❌ Ошибок: 0", inline=False)
    progress_msg = await channel.send(embed=progress_embed)

    start_time = time.time()

    combinations = await get_all_test_combinations_live()

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

DISCORD_CHANNEL_LINK_RE = re.compile(
    r"https?://(?:canary\.|ptb\.)?discord(?:app)?\.com/channels/(?P<guild>\d+|@me)/(?P<channel>\d+)(?:/(?P<message>\d+))?",
    re.IGNORECASE,
)
DISCORD_CHANNEL_MENTION_RE = re.compile(r"^<#(?P<channel>\d+)>$")


def get_analysis_channel_types() -> List[Any]:
    """Типы каналов, которые можно выбрать в UI slash-команды."""
    wanted = ["text", "news", "forum", "public_thread", "private_thread", "news_thread"]
    return [getattr(disnake.ChannelType, name) for name in wanted if hasattr(disnake.ChannelType, name)]


ANALYSIS_CHANNEL_TYPES = get_analysis_channel_types()


def extract_channel_reference(raw: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    """
    Достаёт guild_id и channel/thread_id из ссылки Discord, упоминания <#id> или голого ID.
    Для message-link берётся второй ID — это канал или тред, где лежит сообщение.
    """
    if not raw:
        return None, None

    value = raw.strip()
    link_match = DISCORD_CHANNEL_LINK_RE.search(value)
    if link_match:
        guild_raw = link_match.group("guild")
        guild_id = int(guild_raw) if guild_raw.isdigit() else None
        return guild_id, int(link_match.group("channel"))

    mention_match = DISCORD_CHANNEL_MENTION_RE.match(value)
    if mention_match:
        return None, int(mention_match.group("channel"))

    if value.isdigit():
        return None, int(value)

    return None, None


async def find_thread_in_archives(guild, target_id: int):
    """Fallback для старых/архивных тредов, если cache/fetch_channel их не нашли."""
    if not guild:
        return None

    for channel in getattr(guild, "channels", []):
        for thread in getattr(channel, "threads", []):
            if getattr(thread, "id", None) == target_id:
                return thread

        archived_threads = getattr(channel, "archived_threads", None)
        if not archived_threads:
            continue

        for private_flag in (False, True):
            try:
                async for thread in channel.archived_threads(private=private_flag, limit=100):
                    if getattr(thread, "id", None) == target_id:
                        return thread
            except Exception as e:
                log_analysis(
                    f"Archive lookup skipped for {getattr(channel, 'name', '?')} private={private_flag}: {e}",
                    "DEBUG",
                )

    return None


async def resolve_analysis_target(interaction: disnake.CommandInteraction,
                                  selected_channel=None,
                                  ссылка: Optional[str] = None):
    """
    Возвращает канал/форум/тред для анализа.
    Приоритет: ссылка/ID/упоминание → выбранный канал → текущий канал.
    """
    if not getattr(interaction, "guild", None):
        return None, "❌ Гав! `/анализ` работает только внутри сервера."

    target = None
    link_guild_id, link_channel_id = extract_channel_reference(ссылка)

    if ссылка and not link_channel_id:
        return None, "❌ ПсИИнка не смог разобрать ссылку/ID канала. Дай ссылку Discord, `<#канал>` или числовой ID."

    if link_guild_id and link_guild_id != interaction.guild.id:
        return None, "❌ Эта ссылка ведёт на другой сервер. ПсИИнка нюхает только текущий сервер."

    if link_channel_id:
        guild = interaction.guild
        target = guild.get_channel(link_channel_id)

        if target is None and hasattr(guild, "get_thread"):
            target = guild.get_thread(link_channel_id)

        if target is None:
            target = bot.get_channel(link_channel_id)

        if target is None:
            try:
                target = await bot.fetch_channel(link_channel_id)
            except Exception as e:
                log_analysis(f"bot.fetch_channel({link_channel_id}) failed: {e}", "DEBUG")

        if target is None:
            try:
                target = await guild.fetch_channel(link_channel_id)
            except Exception as e:
                log_analysis(f"guild.fetch_channel({link_channel_id}) failed: {e}", "DEBUG")

        if target is None:
            target = await find_thread_in_archives(guild, link_channel_id)
    else:
        target = selected_channel or interaction.channel

    if target is None:
        return None, "❌ ПсИИнка не нашёл такой канал/форум/тред. Проверь ссылку и права бота."

    target_guild = getattr(target, "guild", None)
    if target_guild and getattr(target_guild, "id", None) != interaction.guild.id:
        return None, "❌ Этот канал не из текущего сервера."

    has_history = callable(getattr(target, "history", None))
    has_threads = hasattr(target, "threads") or callable(getattr(target, "archived_threads", None))
    if not has_history and not has_threads:
        return None, "❌ Это не текстовый канал, не форум и не тред. ПсИИнка там не сможет нюхать сообщения."

    return target, None


def analysis_target_name(channel) -> str:
    if hasattr(channel, "parent") and getattr(channel, "parent", None):
        return f"{channel.parent.name} / {channel.name}"
    return getattr(channel, "name", str(getattr(channel, "id", "unknown")))

async def collect_all_messages_debug(channel, days_limit: int, max_per_source: int = 400):
    after_date = datetime.now(timezone.utc) - timedelta(days=days_limit)
    all_messages = []
    target_label = analysis_target_name(channel)
    log_analysis(f"Start collecting #{target_label} for {days_limit} days.", "INFO")

    history_method = getattr(channel, "history", None)
    if callable(history_method):
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
                    "source": f"#{target_label}",
                    "created_at": message.created_at
                })
            log_analysis(f"✅ Main channel/thread: {len(all_messages)} msgs.", "INFO")
        except Exception as e:
            log_analysis(f"❌ Main channel/thread error: {e}", "ERROR")
    else:
        log_analysis(f"Main history skipped for {target_label}: no direct history method.", "INFO")

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

    # Архивные треды: добавлено без изменения основного механизма анализа.
    if hasattr(channel, 'archived_threads'):
        seen_thread_ids = {getattr(t, 'id', None) for t in getattr(channel, 'threads', [])}
        for private_flag in (False, True):
            try:
                async for thread in channel.archived_threads(private=private_flag, limit=100):
                    if getattr(thread, 'id', None) in seen_thread_ids or not hasattr(thread, 'history'):
                        continue
                    seen_thread_ids.add(getattr(thread, 'id', None))
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
                                "source": f"Archived Thread: {thread.name}",
                                "created_at": message.created_at
                            })
                            count += 1
                        log_analysis(f"✅ Archived thread {thread.name}: {count} msgs.", "INFO")
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        log_analysis(f"Archived thread {getattr(thread, 'name', '?')} error: {e}", "DEBUG")
            except Exception as e:
                log_analysis(f"Archived threads private={private_flag} unavailable: {e}", "DEBUG")

    return all_messages


def format_messages_for_ai(messages_list: List[Dict]) -> str:
    return "\n".join([
        f"{msg['id']} [{msg['source']}]: {msg['content'].replace(chr(10), ' ')}"
        for msg in messages_list
    ])


def parse_ai_response(ai_text: str, original_data: List[Dict]) -> List[Dict]:
    if not ai_text or ai_text.strip().upper() == "NONE":
        return []

    found_ids = [int(x) for x in re.findall(r'\d+', ai_text)]
    found_set = set(found_ids)
    return [msg for msg in original_data if msg['id'] in found_set]


@bot.slash_command(name="анализ", description="Анализ канала, форума или треда на нарушения")
async def slash_analyze(interaction: disnake.CommandInteraction,
                        канал: Optional[disnake.abc.GuildChannel] = commands.Param(
                            default=None,
                            description="Канал/форум/тред для анализа",
                            channel_types=ANALYSIS_CHANNEL_TYPES,
                        ),
                        ссылка: Optional[str] = commands.Param(
                            default=None,
                            description="Ссылка, ID или упоминание канала/форума/треда",
                        ),
                        период: str = commands.Param(
                            default="За последние 7 дней",
                            choices=["За последние 7 дней", "За последние 21 день"],
                            description="Период анализа",
                        )):
    if interaction.author.id != OWNER_ID:
        if not await check_access(interaction, allowed_role_names=["Псарь"]):
            return

    target_channel, target_error = await resolve_analysis_target(interaction, канал, ссылка)
    if target_error:
        await interaction.response.send_message(target_error, ephemeral=True)
        return

    days_to_check = 7 if "7 дней" in период else 21
    await interaction.response.defer()

    target_name = analysis_target_name(target_channel)
    log_analysis(f"=== START ANALYSIS: {target_name} ({days_to_check} days) ===", "INFO")

    try:
        messages_data = await collect_all_messages_debug(target_channel, days_to_check, max_per_source=400)
        if not messages_data:
            await interaction.edit_original_response(content="ℹ️ ПсИИнка не нашёл сообщений. *нюхает*")
            return

        BATCH_SIZE = 35
        total_batches = (len(messages_data) + BATCH_SIZE - 1) // BATCH_SIZE

        progress_embed = disnake.Embed(
            title="🔍 ПсИИнка нюхает канал",
            description=f"*принюхивается* Канал: `#{target_name}`\nПериод: `{days_to_check} дней` 🐕\nСообщений: `{len(messages_data)}`",
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
        header_embed.add_field(name="Канал", value=f"#{target_name}", inline=True)
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
# 💰 КОМАНДА: ЦЕНЫ АУКЦИОНА
# ============================================================================

# ============================================================================
# 💰 КОМАНДА: ЦЕНЫ АУКЦИОНА
# ============================================================================

AUCTIONEER_IDS = {839258901249523723, 754615336682127372}
AUCTIONEER_USERNAMES = {"aukcionistfirewell", "lagyshka22"}

NEW_AUCTION_LOT_RE = re.compile(
    r"(?:📦\s*)?(?:л\s*о\s*т|lot)\s*(?:№|#|n\s*o\.?|no\.?|nº|n°|номер)?\s*[:\-–—]?\s*(\d{1,8})",
    re.IGNORECASE,
)

ANCIENT_AUCTION_LOT_RE = re.compile(
    r"Номер\s+лота\s*:\s*(\d{1,8})",
    re.IGNORECASE,
)

AUCTION_LAST_BID_RE = re.compile(
    r"Последняя\s+ставка[^\d]{0,180}([0-9][0-9 \u00A0]*)",
    re.IGNORECASE | re.DOTALL,
)

AUCTION_START_PRICE_RE = re.compile(
    r"Начальная\s+стоимость[^\d]{0,120}([0-9][0-9 \u00A0]*)",
    re.IGNORECASE | re.DOTALL,
)


def get_auction_price_channel_types() -> List[Any]:
    wanted = ["text", "news", "public_thread", "private_thread", "news_thread"]
    return [getattr(disnake.ChannelType, name) for name in wanted if hasattr(disnake.ChannelType, name)]


AUCTION_PRICE_CHANNEL_TYPES = get_auction_price_channel_types()


def auction_money_to_int(raw: Optional[str]) -> Optional[int]:
    digits = re.sub(r"\D+", "", raw or "")
    return int(digits) if digits else None


def clean_auction_text(text: Any) -> str:
    text = "" if text is None else str(text)

    # Убираем невидимые символы, которые часто ломают regex.
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]", "", text)

    text = text.replace("\u00A0", " ")
    text = text.replace("Ｎ", "N")
    text = text.replace("ｏ", "o")
    text = text.replace("О", "О")

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def norm_auction_text(text: Any) -> str:
    return clean_auction_text(text).lower().replace("ё", "е")


def append_unique_text(parts: List[str], value: Any):
    if value is None:
        return

    text = clean_auction_text(value)
    if not text:
        return

    if text not in parts:
        parts.append(text)


def flatten_any_strings(value: Any) -> List[str]:
    result = []

    if value is None:
        return result

    if isinstance(value, str):
        if value.strip():
            result.append(value)
        return result

    if isinstance(value, dict):
        for item in value.values():
            result.extend(flatten_any_strings(item))
        return result

    if isinstance(value, (list, tuple)):
        for item in value:
            result.extend(flatten_any_strings(item))
        return result

    return result


def get_raw_author_name(raw_message: Dict[str, Any]) -> str:
    author = raw_message.get("author") or {}
    username = author.get("username") or ""
    global_name = author.get("global_name") or ""
    discriminator = author.get("discriminator") or ""

    if global_name and username:
        return f"{global_name} | {username}"

    if username and discriminator and discriminator != "0":
        return f"{username}#{discriminator}"

    return username or global_name or ""


def get_raw_author_id(raw_message: Dict[str, Any]) -> str:
    author = raw_message.get("author") or {}
    return str(author.get("id") or "")


def raw_message_to_text(raw_message: Dict[str, Any]) -> str:
    """
    Собирает максимум текста из Discord raw payload:
    content, embeds, fields, footer, author, components и запасной проход по JSON.
    """
    parts: List[str] = []

    append_unique_text(parts, raw_message.get("content"))
    append_unique_text(parts, raw_message.get("clean_content"))

    for embed in raw_message.get("embeds") or []:
        if not isinstance(embed, dict):
            continue

        author = embed.get("author") or {}
        footer = embed.get("footer") or {}

        append_unique_text(parts, author.get("name"))
        append_unique_text(parts, embed.get("title"))
        append_unique_text(parts, embed.get("description"))

        for field in embed.get("fields") or []:
            if not isinstance(field, dict):
                continue

            name = field.get("name", "")
            value = field.get("value", "")

            if name or value:
                append_unique_text(parts, f"{name}\n{value}")

        append_unique_text(parts, footer.get("text"))

        # Запасной режим: вытащить вообще все строки из embed.
        for text in flatten_any_strings(embed):
            append_unique_text(parts, text)

    # Иногда важные куски могут быть в компонентах.
    for component in raw_message.get("components") or []:
        for text in flatten_any_strings(component):
            append_unique_text(parts, text)

    return clean_auction_text("\n".join(parts))


def disnake_message_to_raw_like(message: disnake.Message) -> Dict[str, Any]:
    embeds = []

    for embed in getattr(message, "embeds", []) or []:
        try:
            embeds.append(embed.to_dict())
        except Exception:
            pass

    components = []

    for row in getattr(message, "components", []) or []:
        try:
            components.append(row.to_dict())
        except Exception:
            pass

    author = getattr(message, "author", None)

    return {
        "id": str(getattr(message, "id", "")),
        "channel_id": str(getattr(message.channel, "id", "")),
        "content": getattr(message, "content", "") or "",
        "clean_content": getattr(message, "clean_content", "") or "",
        "embeds": embeds,
        "components": components,
        "author": {
            "id": str(getattr(author, "id", "")),
            "username": str(getattr(author, "name", "")),
            "global_name": str(getattr(author, "global_name", "") or ""),
            "discriminator": str(getattr(author, "discriminator", "") or ""),
        },
        "timestamp": str(getattr(message, "created_at", "")),
        "_jump_url": getattr(message, "jump_url", ""),
    }


def make_jump_url(guild_id: int, channel_id: int, message_id: Any) -> str:
    if not guild_id or not channel_id or not message_id:
        return ""
    return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"


async def fetch_raw_discord_messages(
    channel_id: int,
    limit: int,
) -> Tuple[List[Dict[str, Any]], List[List[Any]]]:
    """
    Читает историю напрямую через Discord API.
    Это надёжнее, чем message.embeds, потому что мы видим сырой payload.
    """
    logs: List[List[Any]] = []
    token = os.getenv("DISCORD_TOKEN")

    if not token:
        logs.append(["REST", "", "DISCORD_TOKEN не найден, raw REST чтение пропущено", "", ""])
        return [], logs

    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": "PsIInkaBot AuctionPriceCounter",
    }

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"

    all_messages: List[Dict[str, Any]] = []
    before = None

    timeout = aiohttp.ClientTimeout(total=45)

    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        while len(all_messages) < limit:
            batch_limit = min(100, limit - len(all_messages))
            params = {"limit": str(batch_limit)}

            if before:
                params["before"] = str(before)

            try:
                async with session.get(url, params=params) as response:
                    if response.status == 429:
                        data = await response.json()
                        retry_after = float(data.get("retry_after", 1.0))
                        logs.append(["REST", "", f"Rate limit, ждём {retry_after:.2f} сек.", "", ""])
                        await asyncio.sleep(min(retry_after + 0.25, 15))
                        continue

                    if response.status != 200:
                        text = await response.text()
                        logs.append([
                            "REST",
                            "",
                            f"Discord API вернул статус {response.status}",
                            "",
                            text[:3000],
                        ])
                        break

                    batch = await response.json()

                    if not batch:
                        break

                    all_messages.extend(batch)
                    before = batch[-1].get("id")

                    if len(batch) < batch_limit:
                        break

            except Exception as e:
                logs.append(["REST", "", f"Ошибка raw REST чтения: {type(e).__name__}: {e}", "", ""])
                break

    return all_messages, logs


async def fetch_history_fallback(
    target_channel,
    guild_id: int,
    limit: int,
) -> Tuple[List[Dict[str, Any]], List[List[Any]]]:
    logs: List[List[Any]] = []
    result: List[Dict[str, Any]] = []

    if not hasattr(target_channel, "history"):
        logs.append(["HISTORY", "", "У канала нет метода history", "", ""])
        return result, logs

    try:
        async for message in target_channel.history(limit=limit, oldest_first=False):
            raw_like = disnake_message_to_raw_like(message)

            if not raw_like.get("_jump_url"):
                raw_like["_jump_url"] = make_jump_url(
                    guild_id,
                    int(raw_like.get("channel_id") or 0),
                    raw_like.get("id"),
                )

            result.append(raw_like)

    except Exception as e:
        logs.append(["HISTORY", "", f"Ошибка fallback history: {type(e).__name__}: {e}", "", ""])

    return result, logs


def raw_field_candidates(raw_message: Dict[str, Any], field_name_part: str) -> List[str]:
    result = []
    target = norm_auction_text(field_name_part)

    for embed in raw_message.get("embeds") or []:
        if not isinstance(embed, dict):
            continue

        for field in embed.get("fields") or []:
            if not isinstance(field, dict):
                continue

            name = field.get("name", "")
            value = field.get("value", "")

            if target in norm_auction_text(name):
                result.append(clean_auction_text(value))
                result.append(clean_auction_text(f"{name}\n{value}"))

    return [x for x in result if x]


def raw_title_candidates(raw_message: Dict[str, Any]) -> List[str]:
    result = []

    for embed in raw_message.get("embeds") or []:
        if isinstance(embed, dict):
            title = embed.get("title")
            if title:
                result.append(clean_auction_text(title))

    return result


def extract_new_lot_number(text: str, raw_message: Optional[Dict[str, Any]] = None) -> Optional[int]:
    candidates = []

    if raw_message:
        candidates.extend(raw_title_candidates(raw_message))

    candidates.append(text)

    for candidate in candidates:
        lot_match = NEW_AUCTION_LOT_RE.search(candidate)
        if lot_match:
            return int(lot_match.group(1))

    lower = norm_auction_text(text)

    # Запасной режим: если это точно новый лот, но слово "Лот" API отдало криво.
    if "последняя ставка" in lower and "начальная стоимость" in lower:
        fallback = re.search(r"(?:№|#|nº|n°|no\.?|n\s*o\.?)\s*(\d{1,8})", text, re.IGNORECASE)
        if fallback:
            return int(fallback.group(1))

    return None


def extract_between_labels(text: str, start_label: str, stop_labels: List[str]) -> str:
    stop_part = "|".join(re.escape(label) for label in stop_labels)

    pattern = re.compile(
        rf"{re.escape(start_label)}\s*:?\s*(.*?)(?=\n\s*(?:{stop_part})\s*:|\n\s*=+|\Z)",
        re.IGNORECASE | re.DOTALL,
    )

    match = pattern.search(text)
    if not match:
        return ""

    return clean_auction_text(match.group(1))


def extract_new_item_text(text: str, raw_message: Dict[str, Any]) -> str:
    raw_items = raw_field_candidates(raw_message, "Предмет")

    for item in raw_items:
        # Берём именно value поля, а не "Предмет\nvalue", если получилось.
        cleaned = clean_auction_text(item)
        if cleaned and norm_auction_text(cleaned) != "предмет":
            cleaned = re.sub(r"^\s*Предмет\s*\n", "", cleaned, flags=re.IGNORECASE).strip()
            return clean_auction_text(cleaned.lstrip("> ").strip())

    patterns = [
        r"(?:^|\n)\s*#+\s*Предмет\s*\n\s*>?\s*(.*?)(?=\n\s*(?:💰|⏳|#+\s*Последняя|Последняя\s+ставка|\*\*Торги|Торги\s+завершены|Лот\s+проверяется|-#\s*Опубликовано)|\Z)",
        r"(?:^|\n)\s*Предмет\s*\n\s*>?\s*(.*?)(?=\n\s*(?:💰|⏳|#+\s*Последняя|Последняя\s+ставка|\*\*Торги|Торги\s+завершены|Лот\s+проверяется|-#\s*Опубликовано)|\Z)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return clean_auction_text(match.group(1).lstrip("> ").strip())

    return ""


def extract_ancient_name(text: str) -> str:
    return extract_between_labels(
        text,
        "Наименование",
        ["Описание", "Начальная стоимость", "Конец торгов", "Скриншот-подтверждение владения", "Скриншот"],
    )


def extract_ancient_description(text: str) -> str:
    return extract_between_labels(
        text,
        "Описание",
        ["Начальная стоимость", "Конец торгов", "Скриншот-подтверждение владения", "Скриншот"],
    )


def extract_start_price(text: str, raw_message: Dict[str, Any]) -> Optional[int]:
    candidates = []
    candidates.extend(raw_field_candidates(raw_message, "Начальная стоимость"))
    candidates.append(text)

    for candidate in candidates:
        match = AUCTION_START_PRICE_RE.search(candidate)
        if match:
            return auction_money_to_int(match.group(1))

        # Если field name = "💰 Начальная стоимость", а value = "`700` бонкоинов"
        if "начальная" in norm_auction_text(candidate):
            price = auction_money_to_int(candidate)
            if price is not None:
                return price

    return None


def extract_last_bid_price_and_area(text: str, raw_message: Dict[str, Any]) -> Tuple[Optional[int], str]:
    candidates = []
    candidates.extend(raw_field_candidates(raw_message, "Последняя ставка"))
    candidates.append(text)

    for candidate in candidates:
        match = AUCTION_LAST_BID_RE.search(candidate)
        if match:
            return auction_money_to_int(match.group(1)), candidate

        if "последняя ставка" in norm_auction_text(candidate):
            price = auction_money_to_int(candidate)
            if price is not None:
                return price, candidate

    return None, ""


def extract_bidder(text: str, raw_message: Dict[str, Any], bid_area: str) -> str:
    candidates = []

    if bid_area:
        candidates.append(bid_area)

    candidates.extend(raw_field_candidates(raw_message, "Последняя ставка"))

    last_bid_match = re.search(r"Последняя\s+ставка", text, re.IGNORECASE)
    if last_bid_match:
        candidates.append(text[last_bid_match.end():last_bid_match.end() + 2000])

    candidates.append(text)

    for candidate in candidates:
        match = re.search(
            r"(?:^|\n|\s)(?:\*\*)?\s*От\s*:(?:\*\*)?\s*(.*?)(?=\n|$)",
            candidate,
            re.IGNORECASE | re.DOTALL,
        )

        if match:
            bidder = clean_auction_text(match.group(1))
            bidder = bidder.replace("**", "").strip()
            if bidder:
                return bidder

    return ""


def is_auctioneer_bidder(bidder: str, bid_area: str, text: str) -> bool:
    area = norm_auction_text(f"{bidder}\n{bid_area}\n{text[:1200]}")
    area = area.replace("*", "")

    for auctioneer_id in AUCTIONEER_IDS:
        if f"<@{auctioneer_id}>" in area or f"<@!{auctioneer_id}>" in area:
            return True

    return any(nick.lower() in area for nick in AUCTIONEER_USERNAMES)


def parse_new_auction_lot(info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    text = info["text"]
    raw_message = info["raw"]

    lot_no = extract_new_lot_number(text, raw_message)
    if lot_no is None:
        return None

    lower = norm_auction_text(text)

    start_price = extract_start_price(text, raw_message)
    item = extract_new_item_text(text, raw_message)

    base = {
        "lot": lot_no,
        "item": item,
        "start_price": start_price,
        "author": info.get("author", ""),
        "author_id": info.get("author_id", ""),
        "message_id": info.get("message_id", ""),
        "message_url": info.get("message_url", ""),
        "created_at": info.get("created_at", ""),
        "embeds_count": info.get("embeds_count", 0),
        "raw_text": text,
    }

    if "предмет возвращен продавцу" in lower:
        return {
            **base,
            "type": "returned",
            "status": "Возврат продавцу",
            "price": None,
            "bidder": "",
            "is_auctioneer": False,
            "closed": "торги завершены" in lower,
        }

    price, bid_area = extract_last_bid_price_and_area(text, raw_message)

    if price is None:
        if "лот проверяется администратором" in lower or "проверяется администратором" in lower:
            status = "Проверяется администратором, ставки ещё нет"
        else:
            status = "Нет последней ставки"

        return {
            **base,
            "type": "no_bid",
            "status": status,
            "price": None,
            "bidder": "",
            "is_auctioneer": False,
            "closed": "торги завершены" in lower,
        }

    bidder = extract_bidder(text, raw_message, bid_area)
    is_auctioneer = is_auctioneer_bidder(bidder, bid_area, text)

    return {
        **base,
        "type": "new",
        "status": "Засчитан: аукционист" if is_auctioneer else "Засчитан: люди",
        "price": price,
        "bidder": bidder or "не найдено поле От",
        "is_auctioneer": is_auctioneer,
        "closed": "торги завершены" in lower,
    }


def parse_ancient_auction_lot(info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    text = info["text"]

    ancient_match = ANCIENT_AUCTION_LOT_RE.search(text)
    if not ancient_match:
        return None

    lot_no = int(ancient_match.group(1))
    name = extract_ancient_name(text)
    description = extract_ancient_description(text)

    start_match = AUCTION_START_PRICE_RE.search(text)
    price = auction_money_to_int(start_match.group(1)) if start_match else None

    if price is None:
        return {
            "type": "ancient_bad_price",
            "lot": lot_no,
            "name": name,
            "description": description,
            "price": None,
            "author": info.get("author", ""),
            "message_id": info.get("message_id", ""),
            "message_url": info.get("message_url", ""),
            "created_at": info.get("created_at", ""),
            "raw_text": text,
        }

    return {
        "type": "ancient",
        "lot": lot_no,
        "name": name,
        "description": description,
        "price": price,
        "author": info.get("author", ""),
        "message_id": info.get("message_id", ""),
        "message_url": info.get("message_url", ""),
        "created_at": info.get("created_at", ""),
        "raw_text": text,
    }


def raw_to_info(raw_message: Dict[str, Any], guild_id: int, channel_id: int) -> Dict[str, Any]:
    message_id = str(raw_message.get("id") or "")
    real_channel_id = int(raw_message.get("channel_id") or channel_id)

    message_url = raw_message.get("_jump_url") or make_jump_url(guild_id, real_channel_id, message_id)
    text = raw_message_to_text(raw_message)

    return {
        "raw": raw_message,
        "text": text,
        "message_id": message_id,
        "message_url": message_url,
        "created_at": raw_message.get("timestamp") or "",
        "author": get_raw_author_name(raw_message),
        "author_id": get_raw_author_id(raw_message),
        "embeds_count": len(raw_message.get("embeds") or []),
        "components_count": len(raw_message.get("components") or []),
    }


def xlsx_col_name(index: int) -> str:
    result = ""

    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result

    return result


def clean_xlsx_value(value: Any) -> Any:
    if value is None:
        return ""

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value

    text = str(value)
    text = re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]", "", text)

    # Ограничение Excel на ячейку — 32767 символов.
    if len(text) > 32700:
        text = text[:32700] + "\n...[обрезано из-за лимита Excel на ячейку]"

    return text


def xlsx_cell(value: Any, row_idx: int, col_idx: int) -> str:
    value = clean_xlsx_value(value)
    cell_ref = f"{xlsx_col_name(col_idx)}{row_idx}"

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{cell_ref}"><v>{value}</v></c>'

    text = xml_escape(str(value))
    return f'<c r="{cell_ref}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def make_sheet_xml(rows: List[List[Any]]) -> str:
    sheet_rows = []

    for row_idx, row in enumerate(rows, start=1):
        cells = []

        for col_idx, value in enumerate(row, start=1):
            cells.append(xlsx_cell(value, row_idx, col_idx))

        sheet_rows.append(f'<row r="{row_idx}">{"".join(cells)}</row>')

    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheetViews><sheetView workbookViewId="0"/></sheetViews>
<sheetData>{"".join(sheet_rows)}</sheetData>
</worksheet>'''


def sanitize_sheet_name(name: str) -> str:
    name = re.sub(r'[\[\]\:\*\?\/\\]', "_", name)
    return name[:31] or "Лист"


def make_xlsx_file(sheets: List[Tuple[str, List[List[Any]]]], filename: str) -> io.BytesIO:
    file_obj = io.BytesIO()

    with zipfile.ZipFile(file_obj, "w", zipfile.ZIP_DEFLATED) as z:
        sheet_overrides = "\n".join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
            f'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(1, len(sheets) + 1)
        )

        z.writestr("[Content_Types].xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
{sheet_overrides}
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>''')

        z.writestr("_rels/.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>''')

        workbook_sheets = "\n".join(
            f'<sheet name="{xml_escape(sanitize_sheet_name(name))}" sheetId="{i}" r:id="rId{i}"/>'
            for i, (name, _) in enumerate(sheets, start=1)
        )

        z.writestr("xl/workbook.xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets>{workbook_sheets}</sheets>
</workbook>''')

        workbook_rels = "\n".join(
            f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, len(sheets) + 1)
        )

        z.writestr("xl/_rels/workbook.xml.rels", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
{workbook_rels}
</Relationships>''')

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

        z.writestr("docProps/core.xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
xmlns:dc="http://purl.org/dc/elements/1.1/"
xmlns:dcterms="http://purl.org/dc/terms/"
xmlns:dcmitype="http://purl.org/dc/dcmitype/"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:creator>PsIInka Bot</dc:creator>
<cp:lastModifiedBy>PsIInka Bot</cp:lastModifiedBy>
<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>
<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>''')

        z.writestr("docProps/app.xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
<Application>PsIInka Bot</Application>
</Properties>''')

        for i, (_, rows) in enumerate(sheets, start=1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", make_sheet_xml(rows))

    file_obj.seek(0)
    file_obj.name = filename
    return file_obj


def build_auction_prices_xlsx(
    people_rows: List[Dict[str, Any]],
    auctioneer_rows: List[Dict[str, Any]],
    ancient_rows: List[Dict[str, Any]],
    all_new_lot_rows: List[Dict[str, Any]],
    log_rows: List[List[Any]],
    raw_embed_rows: List[List[Any]],
    target_channel,
    scanned: int,
    limit: int,
    raw_messages_count: int,
    history_fallback_used: bool,
    skipped_returned: int,
    skipped_no_bid: int,
    skipped_bad_price: int,
    skipped_duplicates: int,
    raw_embed_rows_truncated: int,
) -> io.BytesIO:
    people_total = sum(row["price"] for row in people_rows if row.get("price") is not None)
    auctioneer_total = sum(row["price"] for row in auctioneer_rows if row.get("price") is not None)
    ancient_total = sum(row["price"] for row in ancient_rows if row.get("price") is not None)

    summary_rows = [
        ["Подсчёт цен аукциона"],
        ["Канал", getattr(target_channel, "name", str(target_channel))],
        ["Проверено сообщений", scanned],
        ["Лимит проверки", limit],
        ["Raw REST сообщений получено", raw_messages_count],
        ["Fallback history использован", "Да" if history_fallback_used else "Нет"],
        [],
        ["Категория", "Сумма", "Количество лотов"],
        ["Люди", people_total, len(people_rows)],
        ["Аукционист и бывший аукционист", auctioneer_total, len(auctioneer_rows)],
        ["Древние лоты", ancient_total, len(ancient_rows)],
        [],
        ["Пропущено / логи"],
        ["Возвраты продавцу", skipped_returned],
        ["Без последней ставки / проверяется админом", skipped_no_bid],
        ["С битой ценой", skipped_bad_price],
        ["Дубликаты лотов", skipped_duplicates],
        ["Сырые embed-логи обрезаны на количество", raw_embed_rows_truncated],
    ]

    new_headers = [
        "№ лота",
        "Предмет",
        "Итоговая цена",
        "Начальная цена",
        "Статус",
        "Ставка от",
        "Сообщение завершено?",
        "Автор сообщения",
        "ID сообщения",
        "Ссылка на сообщение",
    ]

    people_sheet = [new_headers]

    for row in sorted(people_rows, key=lambda x: x["lot"]):
        people_sheet.append([
            row.get("lot"),
            row.get("item", ""),
            row.get("price", ""),
            row.get("start_price", ""),
            row.get("status", ""),
            row.get("bidder", ""),
            "Да" if row.get("closed") else "Нет",
            row.get("author", ""),
            row.get("message_id", ""),
            row.get("message_url", ""),
        ])

    auctioneer_sheet = [new_headers]

    for row in sorted(auctioneer_rows, key=lambda x: x["lot"]):
        auctioneer_sheet.append([
            row.get("lot"),
            row.get("item", ""),
            row.get("price", ""),
            row.get("start_price", ""),
            row.get("status", ""),
            row.get("bidder", ""),
            "Да" if row.get("closed") else "Нет",
            row.get("author", ""),
            row.get("message_id", ""),
            row.get("message_url", ""),
        ])

    ancient_sheet = [["№ лота", "Наименование", "Описание", "Стартовая цена", "Автор", "ID сообщения", "Ссылка на сообщение"]]

    for row in sorted(ancient_rows, key=lambda x: x["lot"]):
        ancient_sheet.append([
            row.get("lot"),
            row.get("name", ""),
            row.get("description", ""),
            row.get("price", ""),
            row.get("author", ""),
            row.get("message_id", ""),
            row.get("message_url", ""),
        ])

    all_new_sheet = [[
        "№ лота",
        "Тип",
        "Статус",
        "Предмет",
        "Итоговая цена",
        "Начальная цена",
        "Ставка от",
        "Сообщение завершено?",
        "Автор сообщения",
        "ID автора",
        "Embeds count",
        "ID сообщения",
        "Ссылка",
        "Сырой текст",
    ]]

    for row in sorted(all_new_lot_rows, key=lambda x: (x.get("lot") or 0, str(x.get("message_id", "")))):
        all_new_sheet.append([
            row.get("lot"),
            row.get("type", ""),
            row.get("status", ""),
            row.get("item", ""),
            row.get("price", ""),
            row.get("start_price", ""),
            row.get("bidder", ""),
            "Да" if row.get("closed") else "Нет",
            row.get("author", ""),
            row.get("author_id", ""),
            row.get("embeds_count", ""),
            row.get("message_id", ""),
            row.get("message_url", ""),
            row.get("raw_text", ""),
        ])

    logs_sheet = [["Тип", "№ лота", "Причина/статус", "ID сообщения", "Ссылка", "Текст/детали"]]
    logs_sheet.extend(log_rows)

    raw_embed_sheet = [["Дата", "Автор", "ID автора", "Embeds count", "ID сообщения", "Ссылка", "Сырой текст"]]
    raw_embed_sheet.extend(raw_embed_rows)

    filename = f"auction_prices_{getattr(target_channel, 'id', 'channel')}.xlsx"

    return make_xlsx_file(
        [
            ("Итоги", summary_rows),
            ("Люди", people_sheet),
            ("Аукционисты", auctioneer_sheet),
            ("Древние", ancient_sheet),
            ("Все новые лоты", all_new_sheet),
            ("Логи", logs_sheet),
            ("Сырые embeds", raw_embed_sheet),
        ],
        filename=filename,
    )


@bot.slash_command(name="цены", description="Посчитать цены выкупа лотов в аукционном канале")
async def slash_auction_prices(
    interaction: disnake.CommandInteraction,
    канал: Optional[disnake.abc.GuildChannel] = commands.Param(
        default=None,
        description="Канал или тред с лотами. Если не указать — текущий канал.",
        channel_types=AUCTION_PRICE_CHANNEL_TYPES,
    ),
    лимит: int = commands.Param(
        default=20000,
        description="Сколько последних сообщений проверить. Максимум 50000.",
    ),
):
    if interaction.author.id != OWNER_ID:
        await interaction.response.send_message(
            "❌ Эта команда доступна только овнеру бота.",
            ephemeral=True,
        )
        return

    target_channel = канал or interaction.channel

    if not getattr(target_channel, "id", None):
        await interaction.response.send_message(
            "❌ Не удалось определить канал.",
            ephemeral=True,
        )
        return

    limit = max(1, min(int(лимит or 20000), 50000))

    await interaction.response.defer()

    guild_id = int(getattr(interaction.guild, "id", 0) or 0)
    channel_id = int(getattr(target_channel, "id", 0))

    people_rows: List[Dict[str, Any]] = []
    auctioneer_rows: List[Dict[str, Any]] = []
    ancient_rows: List[Dict[str, Any]] = []
    all_new_lot_rows: List[Dict[str, Any]] = []

    log_rows: List[List[Any]] = []
    raw_embed_rows: List[List[Any]] = []

    seen_new_lots = set()
    seen_ancient_lots = set()

    scanned = 0
    skipped_returned = 0
    skipped_no_bid = 0
    skipped_bad_price = 0
    skipped_duplicates = 0

    raw_embed_rows_limit = 5000
    raw_embed_rows_truncated = 0

    history_fallback_used = False

    try:
        raw_messages, rest_logs = await fetch_raw_discord_messages(channel_id, limit)
        log_rows.extend(rest_logs)

        # Если raw REST почему-то ничего не дал, пробуем старый disnake history.
        if not raw_messages:
            history_fallback_used = True
            raw_messages, fallback_logs = await fetch_history_fallback(target_channel, guild_id, limit)
            log_rows.extend(fallback_logs)

        raw_messages_count = len(raw_messages)

        for raw_message in raw_messages:
            scanned += 1

            info = raw_to_info(raw_message, guild_id, channel_id)
            text = info["text"]

            if not text:
                continue

            if info["embeds_count"] > 0:
                if len(raw_embed_rows) < raw_embed_rows_limit:
                    raw_embed_rows.append([
                        info.get("created_at", ""),
                        info.get("author", ""),
                        info.get("author_id", ""),
                        info.get("embeds_count", 0),
                        info.get("message_id", ""),
                        info.get("message_url", ""),
                        text,
                    ])
                else:
                    raw_embed_rows_truncated += 1

            new_lot = parse_new_auction_lot(info)

            if new_lot:
                lot_no = new_lot["lot"]

                if lot_no in seen_new_lots:
                    skipped_duplicates += 1

                    duplicate_row = {
                        **new_lot,
                        "status": "Дубликат: уже был более свежий вариант этого лота",
                    }

                    all_new_lot_rows.append(duplicate_row)

                    log_rows.append([
                        "NEW_DUPLICATE",
                        lot_no,
                        "Дубликат нового лота, пропущен",
                        info.get("message_id", ""),
                        info.get("message_url", ""),
                        text,
                    ])

                    continue

                seen_new_lots.add(lot_no)
                all_new_lot_rows.append(new_lot)

                if new_lot["type"] == "returned":
                    skipped_returned += 1
                    log_rows.append([
                        "NEW_RETURNED",
                        lot_no,
                        "Предмет возвращён продавцу, не считаем",
                        info.get("message_id", ""),
                        info.get("message_url", ""),
                        text,
                    ])
                    continue

                if new_lot["type"] == "no_bid":
                    skipped_no_bid += 1
                    log_rows.append([
                        "NEW_NO_BID",
                        lot_no,
                        new_lot.get("status", "Нет последней ставки"),
                        info.get("message_id", ""),
                        info.get("message_url", ""),
                        text,
                    ])
                    continue

                if new_lot.get("price") is None:
                    skipped_bad_price += 1
                    log_rows.append([
                        "NEW_BAD_PRICE",
                        lot_no,
                        "Не удалось достать итоговую цену",
                        info.get("message_id", ""),
                        info.get("message_url", ""),
                        text,
                    ])
                    continue

                if new_lot["is_auctioneer"]:
                    auctioneer_rows.append(new_lot)
                else:
                    people_rows.append(new_lot)

                continue

            ancient_lot = parse_ancient_auction_lot(info)

            if ancient_lot:
                lot_no = ancient_lot["lot"]

                if lot_no in seen_ancient_lots:
                    skipped_duplicates += 1
                    log_rows.append([
                        "ANCIENT_DUPLICATE",
                        lot_no,
                        "Дубликат древнего лота, пропущен",
                        info.get("message_id", ""),
                        info.get("message_url", ""),
                        text,
                    ])
                    continue

                seen_ancient_lots.add(lot_no)

                if ancient_lot["type"] == "ancient":
                    ancient_rows.append(ancient_lot)
                else:
                    skipped_bad_price += 1
                    log_rows.append([
                        "ANCIENT_BAD_PRICE",
                        lot_no,
                        "Древний лот найден, но стартовая цена не распарсилась",
                        info.get("message_id", ""),
                        info.get("message_url", ""),
                        text,
                    ])

                continue

            # Логируем подозрительные сообщения от ботов/с embeds, которые не распарсились.
            lower = norm_auction_text(text)
            maybe_auction = (
                info["embeds_count"] > 0
                or "лот" in lower
                or "начальная стоимость" in lower
                or "последняя ставка" in lower
                or "торги" in lower
            )

            if maybe_auction:
                log_rows.append([
                    "UNPARSED",
                    "",
                    "Сообщение похоже на аукционное, но не распарсилось",
                    info.get("message_id", ""),
                    info.get("message_url", ""),
                    text,
                ])

        people_total = sum(row["price"] for row in people_rows if row.get("price") is not None)
        auctioneer_total = sum(row["price"] for row in auctioneer_rows if row.get("price") is not None)
        ancient_total = sum(row["price"] for row in ancient_rows if row.get("price") is not None)

        xlsx_file = build_auction_prices_xlsx(
            people_rows=people_rows,
            auctioneer_rows=auctioneer_rows,
            ancient_rows=ancient_rows,
            all_new_lot_rows=all_new_lot_rows,
            log_rows=log_rows,
            raw_embed_rows=raw_embed_rows,
            target_channel=target_channel,
            scanned=scanned,
            limit=limit,
            raw_messages_count=raw_messages_count,
            history_fallback_used=history_fallback_used,
            skipped_returned=skipped_returned,
            skipped_no_bid=skipped_no_bid,
            skipped_bad_price=skipped_bad_price,
            skipped_duplicates=skipped_duplicates,
            raw_embed_rows_truncated=raw_embed_rows_truncated,
        )

        summary = (
            f"💰 **Подсчёт цен аукциона готов**\n"
            f"Канал проверки: {target_channel.mention if hasattr(target_channel, 'mention') else target_channel}\n"
            f"Проверено сообщений: `{scanned}` / лимит `{limit}`\n"
            f"Raw REST сообщений получено: `{raw_messages_count}`\n"
            f"Fallback history: `{'да' if history_fallback_used else 'нет'}`\n\n"
            f"👥 Люди: `{people_total}` 🪙 | лотов: `{len(people_rows)}`\n"
            f"🏛️ Аукционисты: `{auctioneer_total}` 🪙 | лотов: `{len(auctioneer_rows)}`\n"
            f"🏺 Древние лоты: `{ancient_total}` 🪙 | лотов: `{len(ancient_rows)}`\n"
            f"📦 Всего новых лотов распознано: `{len(all_new_lot_rows)}`\n\n"
            f"↩️ Возвраты продавцу пропущены: `{skipped_returned}`\n"
            f"➖ Без последней ставки / на проверке: `{skipped_no_bid}`\n"
            f"⚠️ С битой ценой пропущены: `{skipped_bad_price}`\n"
            f"🔁 Дубликаты лотов пропущены: `{skipped_duplicates}`\n"
            f"🧾 Лог-строк: `{len(log_rows)}`\n\n"
            f"📎 Excel-таблица с логами прикреплена ниже."
        )

        await interaction.followup.send(
            content=summary,
            file=disnake.File(xlsx_file, filename=xlsx_file.name),
        )

    except Exception as e:
        logger.error(f"Error in /цены: {e}", exc_info=True)
        await interaction.followup.send(
            f"❌ Ошибка при подсчёте цен: `{type(e).__name__}: {str(e)[:180]}`",
            ephemeral=True,
        )

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

    if not SessionLocal:
        await interaction.followup.send("❌ Гав! БД не подключена, временный лог не трогаю.", ephemeral=True)
        return

    records = pending_test_manager.read_records()
    if not records:
        await interaction.followup.send("ℹ️ ПсИИнка проверил временный лог — там пусто. *нюхает* 🐕", ephemeral=True)
        return

    count = 0
    try:
        for prov, mod, lat in records:
            db_manager.log_success(prov, mod, lat)
            count += 1
        pending_test_manager.clear()
        await interaction.followup.send(f"✅ ПсИИнка записал `{count}` успешных тестов в БД Neon! *виляет хвостом* 🐕",
                                        ephemeral=True)
    except Exception as e:
        logger.error(f"Error committing tests: {e}", exc_info=True)
        await interaction.followup.send(f"❌ Ошибка записи, временный лог НЕ очищен: {str(e)[:100]}", ephemeral=True)
# ============================================================================
# 🏠 КОМАНДА: !недвижка
# ============================================================================

REAL_ESTATE_ALLOWED_ROLES = ["Секретариат", "Фаеркадастр"]

REAL_ESTATE_WORLD = {
    "Сагрот": {
        "Свободный город Харгатрен": ["Харгатрен", "Юзофор", "Поселение на выбор"],
        "Дал Риада": ["Риадград", "Шбумпалес", "Зорказитрен", "Поселение на выбор"],
        "Кородовский Халифат": ["Коргас", "Гарнарет", "Поселение на выбор"],
        "Империя Мадези": ["Сельвио", "Молидей", "Поселение на выбор"],
        "Империя Рунакуны": ["Майотилики", "Мультака", "Сервиолака", "Поселение на выбор"],
        "Коталь-Ссагаса": ["Тука-малака", "Милотика", "Кико", "Поселение на выбор"],
        "Звертейл": ["Хад-Шафа", "Афхиз", "Ибнат", "Поселение на выбор"],
        "Альдейская Критархия": ["Аль-Дейр", "Сахр-аль-Нур", "Карьер-Ифрит", "Поселение на выбор"],
        "Северный пиратский конклав Рэма": ["Норг"],
    },
    "Вулькал": {
        "Солд-Ша": ["Вальтеран", "Дория", "Поселение на выбор"],
        "Деспотия Долла": ["Видхейм", "Роттердам", "Поселение на выбор"],
        "Талдрейк": ["Басфем"],
        "Герцогство Эдеры": ["Рекострал", "Королинд", "Поселение на выбор"],
        "Велдингрейм": ["Бреортол", "Облукастер", "Трастэд", "Поселение на выбор"],
        "Даргейт": ["Кост-Мурс", "Лагерта", "Лонс-Аб", "Аббанилья", "Поселение на выбор"],
    },
    "Клинар": {
        "Герцогство Акаты": ["Перим", "Краснианс", "Чернианск", "Поселение на выбор"],
        "Республика Ральма": ["Шелдом", "Леш", "Марза", "Поселение на выбор"],
        "Империя Торад Осод": ["Гортаг", "Олор", "Осод", "Поселение на выбор"],
        "Церковь Мороза": ["Тирин", "Курн", "Аватор", "Поселение на выбор"],
    },
    "Крорим": {
        "Республика Ивелтин": [
            "Ромау", "Болгар", "Карталин", "Горманд", "Назлин", "Тотеншор",
            "Вьесте", "Броивел", "Склоны Альбы", "Объятия матери", "Арзар-Дзеге",
            "Боннар", "Карналорт", "Поселение на выбор"
        ],
        "Стальное Королевство": [
            "Стальград", "Палхорн", "Аскар-Дур", "Жикарикан",
            "Махиненбаубург", "Цванралор", "Поселение на выбор"
        ],
    },
    "Брандар": {
        "Королевство Малеты": ["Ардена-Ара", "Аурум-Гард", "Матла", "Утильиа", "Поселение на выбор"],
        "Горный Дом Дурад-Рид": ["Ритонгард", "Балмор", "Тулпорт", "Поселение на выбор"],
        "Королевство Трари": ["Трарион", "Велгард", "Серебряная Бухта", "Новый порт", "Поселение на выбор"],
    },
    "Фертейт": {
        "Королевство Нивельдорф": ["Аскер", "Нордскер", "Апскер", "Поселение на выбор"],
    },
}

REAL_ESTATE_QUALITIES = [
    "Ужасное",
    "Плохое",
    "Ниже среднего",
    "Нормальное",
    "Хорошее",
    "Очень хорошее",
]

REAL_ESTATE_QUALITY_WEIGHTS = [0.8, 1, 2, 5, 3, 2]


def has_real_estate_access(member):
    member_roles = getattr(member, "roles", [])
    member_role_names = {role.name.strip().lower() for role in member_roles}
    allowed_role_names = {role_name.strip().lower() for role_name in REAL_ESTATE_ALLOWED_ROLES}

    return bool(member_role_names & allowed_role_names)


def roll_real_estate():
    location_variants = []

    for continent, countries in REAL_ESTATE_WORLD.items():
        for country, cities in countries.items():
            location_variants.append({
                "type": "normal",
                "continent": continent,
                "country": country,
                "cities": cities,
            })

    # Один-единственный дополнительный вариант во всём пуле:
    # если выпадает он, секретарь может выбрать континент, государство и город.
    location_variants.append({
        "type": "full_choice",
    })

    location = random.choice(location_variants)

    quality = random.choices(
        REAL_ESTATE_QUALITIES,
        weights=REAL_ESTATE_QUALITY_WEIGHTS,
        k=1
    )[0]

    if location["type"] == "full_choice":
        return "находящаяся на континенте на выбор, в государстве на выбор и городе на выбор", quality

    city = random.choice(location["cities"])
    country = location["country"]
    continent = location["continent"]

    return f"находящаяся в городе **{city}**, государство **{country}**, континент **{continent}**", quality


def clean_real_estate_text(text):
    text = text.strip()

    quote_pairs = [
        ('"', '"'),
        ("'", "'"),
        ("«", "»"),
        ("“", "”"),
        ("„", "“"),
    ]

    for left_quote, right_quote in quote_pairs:
        if text.startswith(left_quote) and text.endswith(right_quote):
            return text[1:-1].strip()

    return text


REAL_ESTATE_TRIGGER = "недвижкаролл"


@bot.listen("on_message")
async def real_estate_message_listener(message):
    if message.author.bot:
        return

    content = (message.content or "").strip()
    if not content:
        return

    parts = content.split(maxsplit=1)
    command_word = parts[0].casefold()

    if command_word != REAL_ESTATE_TRIGGER.casefold():
        return

    if not has_real_estate_access(message.author):
        await message.reply(
            "Гав... простите, но я не могу ничего поделать — вы не мой хозяин. "
            "Эта команда слушается только **Секретариат** или **Фаеркадастр**.",
            mention_author=False
        )
        return

    if len(parts) < 2 or not parts[1].strip():
        await message.reply(
            '❌ Укажи недвижку после команды. Пример: `Недвижкаролл старый особняк с садом`',
            mention_author=False
        )
        return

    estate_text = clean_real_estate_text(parts[1])
    location_text, quality = roll_real_estate()

    await message.reply(
        f'Недвижка "{estate_text}" определилась по запросу секретаря {message.author.mention} '
        f'как {location_text}, итоговое качество — **{quality}**.',
        mention_author=False
    )

# ============================================================================
# 🎲 КОМАНДА: Качестворолл
# ============================================================================

QUALITY_ROLL_ALLOWED_ROLES = ["Секретариат", "Фаеркадастр", "Анкетолог"]

QUALITY_ROLL_TRIGGER = "качестворолл"

QUALITY_ROLL_REFERENCE_TEXT = (
    "База материала: обычные паки — Железо, Легпак — Сталь. "
    "С Отличного качества доступен материал до +1 прочности от базы или равный/ниже, если подходит предмету."
)

QUALITY_ROLL_QUALITIES = [
    "Ужасное",          # 2%
    "Плохое",           # 5%
    "Ниже среднего",    # 10%
    "Приемлемое",       # 14%
    "Нормальное",       # 34%
    "Хорошее",          # 20%
    "Очень хорошее",    # 10%
    "Отличное",         # 4%
    "Шедевр",           # 1%
]

QUALITY_ROLL_WEIGHTS = [
    2,
    5,
    10,
    14,
    34,
    20,
    10,
    4,
    1,
]


def has_quality_roll_access(member):
    member_roles = getattr(member, "roles", [])
    member_role_names = {role.name.strip().lower() for role in member_roles}
    allowed_role_names = {role_name.strip().lower() for role_name in QUALITY_ROLL_ALLOWED_ROLES}

    return bool(member_role_names & allowed_role_names)


def roll_item_quality():
    return random.choices(
        QUALITY_ROLL_QUALITIES,
        weights=QUALITY_ROLL_WEIGHTS,
        k=1
    )[0]


@bot.listen("on_message")
async def quality_roll_message_listener(message):
    if message.author.bot:
        return

    content = (message.content or "").strip()
    if not content:
        return

    parts = content.split(maxsplit=1)
    command_word = parts[0].casefold()

    if command_word != QUALITY_ROLL_TRIGGER.casefold():
        return

    if not has_quality_roll_access(message.author):
        await message.reply(
            "Гав... простите, но я не могу ничего поделать — эта команда слушается только "
            "**Секретариат**, **Фаеркадастр** или **Анкетолог**.",
            mention_author=False
        )
        return

    if len(parts) < 2 or not parts[1].strip():
        await message.reply(
            '❌ Укажи предмет после команды. Пример: `Качестворолл меч из пака`',
            mention_author=False
        )
        return

    item_text = clean_real_estate_text(parts[1])
    quality = roll_item_quality()

    await message.reply(
        f'Предмет "{item_text}" определился по запросу секретаря {message.author.mention}, '
        f'итоговое качество — **{quality}**.\n\n'
        f'**Справка:**\n{QUALITY_ROLL_REFERENCE_TEXT}',
        mention_author=False
    )

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

        # Получаем базовый пул навыков
        skill_pool = dedupe_preserve_order(MERCENARIES_DB[mercenary_name].copy())  # Копируем, чтобы не менять оригинал
        
        # Проверяем специализацию
        specialization = roll_specialization(mercenary_name)
        
        # Если есть специализация — добавляем её навыки без дублей и без новых названий навыков
        if specialization:
            spec_skills = specialization["skills"]
            skill_pool = dedupe_preserve_order(skill_pool + spec_skills)
        
        # Роллим уровни для каждого навыка
        skills_with_levels = []
        for skill in skill_pool:
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
                value=f"**{specialization['name']}**\n_Добавляет навыки: {', '.join(specialization['skills'])}_",
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
        logger.info("Proxy mode allowed by .env, but proxy list refreshes only when /скажи прокси=Да.")
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
        discord_token = os.getenv("DISCORD_TOKEN")
        if not discord_token:
            raise RuntimeError("DISCORD_TOKEN не найден в .env")
        bot.run(discord_token)
    except Exception as e:
        logger.critical(f"💥 Startup crash: {e}", exc_info=True)
