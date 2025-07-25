# file: handlers/__init__.py

from . import start, profile, support, earning, admin, gmail

# Собираем все роутеры из модулей в один список
routers_list = [
    start.router,
    profile.router,
    support.router,
    earning.router,
    admin.router,
    gmail.router,
]