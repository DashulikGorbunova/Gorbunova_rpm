import ast
from pathlib import Path
import pytest
from app.domain.entities import User, Order
from app.domain.errors import AccessDenied
from app.modules.orders.service import OrderService


def test_services_do_not_depend_on_web_or_orm():
    root = Path(__file__).resolve().parents[1]/'app'
    for path in [*root.glob('modules/*/service.py'),*root.glob('domain/*.py')]:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node,ast.ImportFrom):
                assert not (node.module or '').startswith(('fastapi','sqlalchemy','redis','app.models','app.core'))
            if isinstance(node,ast.Import):
                assert not any(x.name.startswith(('fastapi','sqlalchemy','redis')) for x in node.names)


def test_idor_business_rule_without_http():
    class Repository:
        def get(self,order_id,lock=False):
            return Order(1,1,1,1,'PENDING')
        def cancel(self,order_id):
            pytest.fail('Foreign order must not be changed')
    service = OrderService(Repository())
    with pytest.raises(AccessDenied):
        service.cancel(1,User(2,'bob@example.org','student','unused'))
