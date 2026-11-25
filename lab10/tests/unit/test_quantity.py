import pytest
from app.domain.quantity import valid_quantity
@pytest.mark.parametrize('n,expected',[(0,False),(1,True),(2,True),(50,True),(99,True),(100,True),(101,False),(-1,False)])
def test_boundaries(n,expected):
    assert valid_quantity(n) is expected
