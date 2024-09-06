import pytest
from app import app

def test_app():
    response = app.test_client().get('/api/employees_hierarchy')
    assert response.status_code == 200
    response = app.test_client().get('/')
    assert response.status_code == 200
    assert 'Корпоративный портал' in response.data.decode('utf-8')

