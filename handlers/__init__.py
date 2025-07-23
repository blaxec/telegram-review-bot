from . import start, profile, support, earning, admin

# Собираем все роутеры из модулей в один список
routers_list = [
    start.router,
    profile.router,
    support.router,
    earning.router,
    admin.router,]