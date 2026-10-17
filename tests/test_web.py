import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "suhail.db"))
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-demo-password")
    import importlib
    import database
    import app as app_module
    importlib.reload(database)
    importlib.reload(app_module)
    app_module.app.config.update(TESTING=True)
    with app_module.app.test_client() as client:
        yield client


def sign_in(client):
    login_page = client.get('/login')
    assert login_page.status_code == 200
    import re
    token = re.search(r'name="csrf_token" value="([^"]+)"', login_page.get_data(as_text=True)).group(1)
    answer = client.post('/login', data={'password':'strong-demo-password','csrf_token':token})
    assert answer.status_code == 302


def csrf_token(client):
    import re
    page=client.get('/inputs')
    return re.search(r'name="csrf-token" content="([^"]+)"', page.get_data(as_text=True)).group(1)


def test_login_protection_and_simulation(client):
    assert client.get('/history').status_code == 302
    assert client.get('/healthz').json['status'] == 'ok'
    sign_in(client)
    token = csrf_token(client)
    bad = client.post('/simulate', json={'S0':20}, headers={'X-CSRF-Token':'wrong'})
    assert bad.status_code == 403
    resp = client.post('/simulate', json={'S0':5000,'R0':100,'T_days':5,'dose_days':[1,3]},
                       headers={'X-CSRF-Token':token})
    assert resp.status_code == 200, resp.get_json()
    assert len(resp.json['results']['chart']['day']) == 6
    sim_id = resp.json['id']
    assert client.get('/view/'+str(sim_id)).status_code == 200
    assert client.get('/history').status_code == 200
    pdf = client.get('/pdf/'+str(sim_id))
    assert pdf.status_code == 200
    assert pdf.data.startswith(b'%PDF')


def test_bad_input_is_rejected(client):
    sign_in(client)
    token = csrf_token(client)
    resp = client.post('/simulate', json={'T_days':2,'dose_days':[3]},
                       headers={'X-CSRF-Token':token})
    assert resp.status_code == 400
