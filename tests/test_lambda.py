import base64
import json
import os
import sys

import jwt
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import lambda_function
from lambda_function import lambda_handler, validar_cpf

SEGREDO = 'segredo-de-teste-com-mais-de-32-caracteres'
CPF_VALIDO = '11144477735'


@pytest.fixture(autouse=True)
def configurar_segredo(monkeypatch):
    monkeypatch.setattr(lambda_function, 'JWT_SECRET_KEY', SEGREDO)


def evento(corpo, request_id='req-123'):
    return {'body': json.dumps(corpo), 'requestContext': {'requestId': request_id}}


def cliente_encontrado(monkeypatch, id_cliente, status):
    monkeypatch.setattr(lambda_function, 'buscar_cliente', lambda cpf: (id_cliente, status))


def test_cpf_valido():
    assert validar_cpf("11144477735") == "11144477735"


def test_cpf_formatado():
    assert validar_cpf("111.444.777-35") == "11144477735"


def test_cpf_digito_verificador_invalido():
    assert validar_cpf("11144477736") is None


def test_cpf_todos_digitos_iguais():
    assert validar_cpf("11111111111") is None


def test_cpf_tamanho_invalido():
    assert validar_cpf("123") is None


def test_cpf_vazio():
    assert validar_cpf("") is None


def test_cpf_numerico():
    assert validar_cpf(11144477735) == "11144477735"


def test_handler_cpf_invalido():
    assert lambda_handler(evento({'cpf': '123'}), None)['statusCode'] == 400


def test_handler_corpo_invalido():
    assert lambda_handler({'body': 'nao-e-json'}, None)['statusCode'] == 400


def test_handler_cliente_nao_encontrado(monkeypatch):
    monkeypatch.setattr(lambda_function, 'buscar_cliente', lambda cpf: None)
    assert lambda_handler(evento({'cpf': CPF_VALIDO}), None)['statusCode'] == 404


def test_handler_cliente_inativo(monkeypatch):
    cliente_encontrado(monkeypatch, 7, 'inativo')
    assert lambda_handler(evento({'cpf': CPF_VALIDO}), None)['statusCode'] == 403


def test_handler_gera_token_valido(monkeypatch):
    cliente_encontrado(monkeypatch, 7, 'ativo')
    resposta = lambda_handler(evento({'cpf': '111.444.777-35'}), None)
    assert resposta['statusCode'] == 200

    claims = jwt.decode(json.loads(resposta['body'])['access_token'], SEGREDO, algorithms=['HS256'])
    assert claims['sub'] == '7'
    assert claims['role'] == 'cliente'
    assert claims['cpf'] == CPF_VALIDO
    assert claims['type'] == 'access'
    assert claims['exp'] > claims['iat']


def test_handler_propaga_correlation_id(monkeypatch):
    cliente_encontrado(monkeypatch, 7, 'ativo')
    resposta = lambda_handler(evento({'cpf': CPF_VALIDO}, request_id='abc-999'), None)
    assert resposta['headers']['X-Correlation-ID'] == 'abc-999'


def test_handler_corpo_base64(monkeypatch):
    cliente_encontrado(monkeypatch, 7, 'ativo')
    corpo = base64.b64encode(json.dumps({'cpf': CPF_VALIDO}).encode()).decode()
    assert lambda_handler({'body': corpo, 'isBase64Encoded': True}, None)['statusCode'] == 200


class ConexaoFalsa:
    chamadas = []
    resposta = (200, b'[]')

    def __init__(self, host, timeout):
        self.host = host

    def request(self, metodo, caminho, headers):
        ConexaoFalsa.chamadas.append((self.host, metodo, caminho, headers))

    def getresponse(self):
        status, corpo = ConexaoFalsa.resposta
        return type('Resposta', (), {'status': status, 'read': lambda self: corpo})()

    def close(self):
        pass


@pytest.fixture
def os_service(monkeypatch):
    ConexaoFalsa.chamadas = []
    monkeypatch.setattr(lambda_function, 'API_URL', 'http://oficina-lb.local')
    monkeypatch.setattr(lambda_function.http.client, 'HTTPConnection', ConexaoFalsa)
    return ConexaoFalsa


def test_consulta_cliente_no_os_service_com_token_de_servico(os_service):
    os_service.resposta = (200, json.dumps([{'id_cliente': 7, 'status': 'ativo', 'nome': 'Maria'}]).encode())
    assert lambda_function.buscar_cliente(CPF_VALIDO) == (7, 'ativo')

    host, metodo, caminho, headers = os_service.chamadas[0]
    assert (host, metodo, caminho) == ('oficina-lb.local', 'GET', f'/api/clientes/documento/{CPF_VALIDO}')
    claims = jwt.decode(headers['Authorization'].split()[1], SEGREDO, algorithms=['HS256'])
    assert claims['role'] == 'servico'
    assert claims['exp'] - claims['iat'] == 60


def test_cliente_inexistente_no_os_service(os_service):
    os_service.resposta = (404, b'{"erro": "Cliente n\xc3\xa3o encontrado"}')
    assert lambda_function.buscar_cliente(CPF_VALIDO) is None


def test_os_service_fora_do_ar_gera_erro(os_service):
    os_service.resposta = (503, b'{}')
    with pytest.raises(RuntimeError):
        lambda_handler(evento({'cpf': CPF_VALIDO}), None)
