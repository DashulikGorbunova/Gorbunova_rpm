"""Lab08 adapter: reuse lab-06 database, Redis and domain model."""
from pathlib import Path
import sys
import os
from fastapi import Depends, HTTPException
from sqlalchemy import select
BASE = Path(__file__).resolve().parents[2] / 'lab-06'
sys.path.insert(0, str(BASE))
os.chdir(BASE)
from app.main import create_app
from app.core.dependencies import get_db
from app.models import MenuRow
from app.schemas import MenuView
from app.modules.menu.router import service
from app.modules.menu.repository import entity
app = create_app()
# Public read-only routes; writes retain original authentication.
app.router.routes[:] = [r for r in app.router.routes if not (
    getattr(r, 'path', '') in ('/menu', '/menu/items') and 'GET' in getattr(r, 'methods', set()))]
@app.get('/menu/items', response_model=list[MenuView])
def public_menu(svc=Depends(service)):
    return svc.list()
@app.get('/menu/items/{item_id}', response_model=MenuView)
def public_item(item_id:int, db=Depends(get_db)):
    item=entity(db.get(MenuRow,item_id))
    if item is None:
        raise HTTPException(404,'Menu item not found')
    return item
