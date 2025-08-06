# file: handlers/__init__.py

from . import start, profile, support, earning, admin, gmail, stats, promo

# Собираем все роутеры из модулей в один список
routers_list = [
    start.router,
    profile.router,
    support.router,
    earning.router,
    promo.router,
    admin.router,
    gmail.router,
    stats.router,
]