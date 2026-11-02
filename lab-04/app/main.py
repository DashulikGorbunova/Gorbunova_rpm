from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis import Redis
from anyio import to_thread
from app.core.redis import menu_redis
from app.modules.menu.repository import MenuRepository
from app.modules.menu.cache import MenuCache
from app.core.config import Settings
from app.core.jwt import JwtCodec
from app.database import make_session_factory
from app.domain.errors import InvalidCredentials, AccessDenied, NotFound, Conflict
from app.modules.auth.router import router as auth
from app.modules.users.router import router as users
from app.modules.menu.router import router as menu
from app.modules.orders.router import router as orders
from app.modules.delivery.router import router as delivery

def create_app(settings: Settings | None = None):
    settings = settings or Settings()
    factory = make_session_factory(settings.database_url)
    cache = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
    menu_client = menu_redis(settings.redis_url)
    def warmup():
        with factory() as db:
            MenuRepository(db,MenuCache(menu_client,settings)).list()
    @asynccontextmanager
    async def lifespan(app):
        if settings.cache_enabled and settings.cache_warmup:
            await to_thread.run_sync(warmup)
        yield
        menu_client.close()
        cache.close()
        factory.kw['bind'].dispose()
    app = FastAPI(title='Сириус.Еда — лабораторная №4',
                  docs_url='/docs' if settings.debug else None, redoc_url=None,
                  openapi_url='/openapi.json' if settings.debug else None, lifespan=lifespan)
    app.state.settings, app.state.codec = settings, JwtCodec(settings)
    app.state.session_factory, app.state.redis = factory, cache
    app.state.menu_redis = menu_client
    app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins,
                       allow_credentials=True, allow_methods=['GET','POST','PATCH'],
                       allow_headers=['Authorization','Content-Type'])
    async def domain_error(request: Request, exc):
        code = {InvalidCredentials:401,AccessDenied:403,NotFound:404,Conflict:409}[type(exc)]
        return JSONResponse({'detail':str(exc)},status_code=code,
                            headers={'WWW-Authenticate':'Bearer'} if code == 401 else None)
    for error in (InvalidCredentials,AccessDenied,NotFound,Conflict):
        app.add_exception_handler(error,domain_error)
    for router in (auth,users,menu,orders,delivery):
        app.include_router(router)
    @app.get('/health', tags=['system'])
    def health():
        return {'status':'ok'}
    return app

app = create_app()
