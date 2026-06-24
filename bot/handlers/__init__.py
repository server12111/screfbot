from aiogram import Router

from bot.handlers import start, earn, withdraw, profile, bonus, promo, top, admin, tasks


def setup_routers() -> Router:
    main_router = Router()
    main_router.include_router(admin.router)
    main_router.include_router(start.router)
    main_router.include_router(earn.router)
    main_router.include_router(withdraw.router)
    main_router.include_router(profile.router)
    main_router.include_router(bonus.router)
    main_router.include_router(promo.router)
    main_router.include_router(top.router)
    main_router.include_router(tasks.router)
    return main_router
