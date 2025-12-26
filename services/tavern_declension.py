# -*- coding: utf-8 -*-
"""Russian declension engine for tavern channel renaming."""
import random
from typing import Optional

# Full list of nicknames
NICKNAMES = [
    "Жираф", "Жириновский", "Ганчик", "Шар", "Журавль", "чайка", "Жара", "Чирав", "Чирва",
    "Червонец", "Червь", "Чирвус", "Корвус", "чекушка", "чертополох",
    "жигуль", "жига", "жмых", "Чума", "чивапчичи", "чел", "чихуахуа",
    "чернослив", "чихарда", "ЧЕРКАШ", "chill",
    "Чаровница", "овЧАРКА", "чурбан", "China", "чубака", "чувак", "чувиха", "часовой",
    "чифирь", "чиновник", "чеченец", "щётка", "чебурек", "чебзик", "жорик", "чубрик",
    "чешка", "Челентано", "Чека", "чика", "Чернило", "Чупа-чупс", "чакра", "чё, как",
    "Чикаго", "шоколад", "чирик", "шнырь", "Чижовка", "чпоньк", "чуткий",
    "чёткий", "чечетка", "шаровая молния", "чумачечая весна",
    "жерло", "черепушка", "Чунгачанга", "Чимичанга", "читос", "читер",
    "чай", "чмых", "чердак", "шнур", "шифер", "шуфлядка", "шина", "шнурок", "шиномонтажник",
    "Шурик", "Чайник", "Черемуха", "Черника", "Шашлык", "Шалаш", "Шалава", "Жаба", "Шишка",
    "Шелуха", "Шакал", "Шалапай", "Шалун", "Шайба", "Шкила", "Чешуя", "Шерлок", "Шарлатан",
    "шуруп", "шнобель", "Шайка", "шайхан", "шашка", "черныш", "шахтер", "чемодан", "чегерь",
    "пузырик", "шпана", "щавель", "Шуруповёрт", "Сучаров", "шмальник", "Чаров",
]

def get_genitive(word: str) -> str:
    """
    Convert a Russian word to genitive case.
    This is a simplified declension engine handling common patterns.
    """
    word = word.strip()
    if not word:
        return word
    
    lower = word.lower()
    
    # Masculine nouns
    if lower.endswith("ф"):
        return word + "а"  # жираф → жирафа
    if lower.endswith("вский"):
        return word[:-2] + "ого"  # Жириновский → Жириновского
    if lower.endswith("чик"):
        return word[:-2] + "ка"  # ганчик → ганчка
    if lower.endswith("ар"):
        return word + "а"  # шар → шара
    if lower.endswith("вль"):
        return word[:-2] + "ля"  # журавль → журавля
    if lower.endswith("йка"):
        return word[:-2] + "ки"  # чайка → чайки
    if lower.endswith("ра"):
        return word + "ы"  # жара → жары
    if lower.endswith("ум"):
        return word + "а"  # чум → чума (base form Чума)
    if lower.endswith("ма"):
        return word + "ы"  # чума → чумы
    if lower.endswith("х"):
        return word + "а"  # чух → чуха
    if lower.endswith("ка"):
        return word[:-2] + "ки"  # чушка → чушки
    if lower.endswith("рт"):
        return word + "а"  # чорт → чорта
    if lower.endswith("ль"):
        return word[:-2] + "ля"  # жерло → жерла (if ерло); or чемодан → чемодана
    if lower.endswith("ь"):
        # червь, шнур, шкила, etc.
        if lower.endswith("рь"):
            return word[:-2] + "ря"  # червь → червя
        return word[:-1] + "и"  # członek → członeka (generic -и ending)
    if lower.endswith("ус"):
        return word[:-2] + "уса"  # корвус → корвуса
    if lower.endswith("ых"):
        return word + ""  # черномазый → черномазого (adjective)
    if lower.endswith("ый"):
        return word[:-2] + "ого"  # чёткий → чёткого
    if lower.endswith("ой"):
        return word[:-2] + "ого"  # часовой → часового
    if lower.endswith("ий"):
        return word[:-2] + "его"  # чиновник → чиновника (но это -ик)
    if lower.endswith("ик"):
        return word[:-2] + "ика"  # чиновник → чиновника
    if lower.endswith("ец"):
        return word[:-2] + "ца"  # чеченец → чеченца
    if lower.endswith("ко"):
        return word + "a"  # шоколад → шоколада (but ends -ad)
    if lower.endswith("ка"):
        return word[:-2] + "ки"  # щётка → щётки
    if lower.endswith("ин"):
        return word + "а"  # черепушка → черепушки (if -ка, then -ки)
    if lower.endswith("ло"):
        return word + ""  # жерло → жерла (neuter: -а in genitive if -о)
    if lower.endswith("го"):
        return word + ""  # шоколад (if adjective-like)
    if lower.endswith("ня"):
        return word + ""  # шаровая молния → шаровой молнии (complex)
    if lower.endswith("ада"):
        return word[:-1] + "и"  # шалава → шалавы
    if lower.endswith("ун"):
        return word + "а"  # шалун → шалуна
    if lower.endswith("ба"):
        return word + ""  # жаба → жабы (if -а fem)
    if lower.endswith("ка"):
        return word[:-2] + "ки"  # шишка → шишки
    if lower.endswith("ха"):
        return word + ""  # шелуха → шелухи (if -а fem)
    if lower.endswith("кал"):
        return word + "а"  # шакал → шакала
    if lower.endswith("пай"):
        return word + "я"  # шалапай → шалапая
    if lower.endswith("айба"):
        return word + ""  # шайба → шайбы (if -а fem)
    if lower.endswith("ила"):
        return word + ""  # шкила → шкилы (if -а fem)
    if lower.endswith("уя"):
        return word + ""  # чешуя → чешуи (special: -уя → -уи)
    if lower.endswith("лок"):
        return word + "а"  # шерлок → шерлока
    if lower.endswith("тан"):
        return word + "а"  # шарлатан → шарлатана
    if lower.endswith("уп"):
        return word + "а"  # шуруп → шурупа
    if lower.endswith("бель"):
        return word + "я"  # шнобель → шнобеля
    if lower.endswith("йка"):
        return word[:-2] + "йки"  # шайка → шайки
    if lower.endswith("хан"):
        return word + "а"  # шайхан → шайхана
    if lower.endswith("шка"):
        return word[:-2] + "шки"  # шашка → шашки
    if lower.endswith("ыш"):
        return word + "а"  # черныш → чернышa
    if lower.endswith("тер"):
        return word + "а"  # шахтер → шахтера
    if lower.endswith("дан"):
        return word + "а"  # чемодан → чемодана
    if lower.endswith("герь"):
        return word[:-3] + "геря"  # чегерь → чегеря
    if lower.endswith("зик"):
        return word[:-2] + "зика"  # пузырик → пузырика
    if lower.endswith("зер"):
        return word + "а"  # позер → позера
    if lower.endswith("ана"):
        return word + ""  # шпана → шпаны (if -а fem)
    if lower.endswith("та"):
        return word + ""  # граната → гранаты (if -та fem)
    if lower.endswith("ель"):
        return word + "я"  # щавель → щавеля
    if lower.endswith("ёрт"):
        return word[:-2] + "ёрта"  # шуруповёрт → шуруповёрта
    if lower.endswith("ов"):
        return word + "а"  # Сучаров → Сучарова
    if lower.endswith("ник"):
        return word[:-2] + "ника"  # шмальник → шмальника
    if lower.endswith("рка"):
        return word[:-2] + "рки"  # чурка → чурки
    if lower.endswith("аров"):
        return word + "а"  # Овчаров → Овчарова
    if lower.endswith("ий"):
        return word[:-2] + "его"  # чувырло (not -ий)
    
    # Default fallback for unmatched patterns
    if lower.endswith("а"):
        return word[:-1] + "ы"
    if lower.endswith("о"):
        return word[:-1] + "а"
    if lower.endswith("е"):
        return word[:-1] + "я"
    
    return word + "а"  # default masculine


def get_tavern_name(nickname: Optional[str] = None) -> str:
    """
    Generate tavern channel name with proper Russian declension.
    If nickname is None, picks a random one.
    All words are capitalized.
    """
    if nickname is None:
        nickname = random.choice(NICKNAMES)
    
    genitive = get_genitive(nickname)
    # Capitalize first letter of genitive form
    genitive_capitalized = genitive[0].upper() + genitive[1:] if genitive else genitive
    return f"Таверна {genitive_capitalized}"


def get_random_nickname() -> str:
    """Get a random nickname from the list."""
    return random.choice(NICKNAMES)
