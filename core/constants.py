"""Общие для всей экосистемы справочники.

Архетипы и уровни доступа используются сразу в нескольких приложениях
(quiz определяет архетип, users его хранит, lms по уровню открывает контент),
поэтому держим их в одном месте, чтобы значения не разъезжались.
"""

# Архетипы — результат квиз-воронки и основа «умного тегирования» в CRM.
ARCHETYPE_SEEKER = 'seeker'
ARCHETYPE_CREATOR = 'creator'
ARCHETYPE_SAGE = 'sage'
ARCHETYPE_RULER = 'ruler'
ARCHETYPE_LOVER = 'lover'
ARCHETYPE_HERO = 'hero'

ARCHETYPE_CHOICES = [
    (ARCHETYPE_SEEKER, 'Искатель'),
    (ARCHETYPE_CREATOR, 'Творец'),
    (ARCHETYPE_SAGE, 'Мудрец'),
    (ARCHETYPE_RULER, 'Правитель'),
    (ARCHETYPE_LOVER, 'Любовник'),
    (ARCHETYPE_HERO, 'Герой'),
]

ARCHETYPE_LABELS = dict(ARCHETYPE_CHOICES)

# Короткие описания — показываем на странице результата квиза.
ARCHETYPE_DESCRIPTIONS = {
    ARCHETYPE_SEEKER: 'Вы в пути. Ищете свой смысл и не готовы соглашаться на чужие ответы.',
    ARCHETYPE_CREATOR: 'Вы создаёте. Вам важно выразить себя и оставить след в мире.',
    ARCHETYPE_SAGE: 'Вы понимаете. Сначала разобраться, потом действовать — ваш способ жить.',
    ARCHETYPE_RULER: 'Вы держите опору. Порядок и ответственность — ваша сила.',
    ARCHETYPE_LOVER: 'Вы чувствуете. Близость и красота для вас не роскошь, а воздух.',
    ARCHETYPE_HERO: 'Вы преодолеваете. Там, где другие останавливаются, вы делаете шаг.',
}

# Уровни вовлечения пользователя (упаковка тарифов).
TIER_SEEKER = 'seeker'
TIER_CREATOR = 'creator'
TIER_MAGE = 'mage'

TIER_CHOICES = [
    (TIER_SEEKER, 'Искатель — бесплатный доступ'),
    (TIER_CREATOR, 'Творец — закрытый клуб'),
    (TIER_MAGE, 'Маг — личное ведение'),
]

TIER_LABELS = dict(TIER_CHOICES)

# Короткие названия для интерфейса — полные слишком длинные для бейджа.
TIER_SHORT_LABELS = {
    TIER_SEEKER: 'Искатель',
    TIER_CREATOR: 'Творец',
    TIER_MAGE: 'Маг',
}
