import base64
import http.client
import json
import os
import re
import time
import uuid
from urllib.parse import urlsplit

import jwt

API_URL = os.getenv('API_URL', '')
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')
JWT_EXPIRACAO_SEGUNDOS = int(os.getenv('JWT_EXPIRACAO_SEGUNDOS', '3600'))


def log(evento, correlation_id, nivel='INFO', **campos):
    print(json.dumps({
        'level': nivel,
        'message': evento,
        'correlation_id': correlation_id,
        'service': 'oficina-auth',
        **campos
    }, ensure_ascii=False))


def validar_cpf(cpf):
    cpf = re.sub(r'\D', '', str(cpf or ''))
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return None
    for i in range(9, 11):
        soma = sum(int(cpf[j]) * (i + 1 - j) for j in range(i))
        digito = (soma * 10 % 11) % 10
        if digito != int(cpf[i]):
            return None
    return cpf


def token_de_servico():
    agora = int(time.time())
    return jwt.encode({
        "sub": "auth-lambda", "role": "servico", "type": "access", "fresh": False,
        "jti": str(uuid.uuid4()), "iat": agora, "nbf": agora, "exp": agora + 60,
    }, JWT_SECRET_KEY, algorithm="HS256")


def buscar_cliente(cpf):
    url = urlsplit(API_URL)
    tipo_conexao = http.client.HTTPSConnection if url.scheme == 'https' else http.client.HTTPConnection
    conexao = tipo_conexao(url.netloc, timeout=5)
    try:
        conexao.request(
            'GET', f"{url.path.rstrip('/')}/api/clientes/documento/{cpf}",
            headers={'Authorization': f'Bearer {token_de_servico()}'}
        )
        resposta = conexao.getresponse()
        corpo = resposta.read()
    finally:
        conexao.close()
    if resposta.status == 404:
        return None
    if resposta.status != 200:
        raise RuntimeError(f'OS Service respondeu {resposta.status} na consulta do cliente')
    cliente = json.loads(corpo)[0]
    return cliente['id_cliente'], cliente['status']


def gerar_token(id_cliente, cpf):
    agora = int(time.time())
    claims = {
        "sub": str(id_cliente),
        "role": "cliente",
        "cpf": cpf,
        "type": "access",
        "fresh": False,
        "jti": str(uuid.uuid4()),
        "iat": agora,
        "nbf": agora,
        "exp": agora + JWT_EXPIRACAO_SEGUNDOS,
    }
    return jwt.encode(claims, JWT_SECRET_KEY, algorithm="HS256")


def ler_corpo(event):
    corpo = event.get('body') or '{}'
    if event.get('isBase64Encoded'):
        corpo = base64.b64decode(corpo).decode('utf-8')
    try:
        return json.loads(corpo)
    except json.JSONDecodeError:
        return {}


def resposta(status, corpo, correlation_id):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "X-Correlation-ID": correlation_id},
        "body": json.dumps(corpo, ensure_ascii=False),
    }


def lambda_handler(event, context):
    correlation_id = (event.get('requestContext') or {}).get('requestId') or str(uuid.uuid4())

    cpf = validar_cpf(ler_corpo(event).get('cpf'))
    if not cpf:
        log('cpf_invalido', correlation_id)
        return resposta(400, {"erro": "CPF inválido"}, correlation_id)

    try:
        cliente = buscar_cliente(cpf)
    except Exception as e:
        log('erro_consulta_cliente', correlation_id, nivel='ERROR', erro=type(e).__name__)
        raise

    if not cliente:
        log('cliente_nao_encontrado', correlation_id)
        return resposta(404, {"erro": "Cliente não encontrado"}, correlation_id)

    id_cliente, status = cliente
    if status != 'ativo':
        log('cliente_inativo', correlation_id, id_cliente=id_cliente)
        return resposta(403, {"erro": "Cliente inativo"}, correlation_id)

    log('cliente_autenticado', correlation_id, id_cliente=id_cliente)
    return resposta(200, {
        "access_token": gerar_token(id_cliente, cpf),
        "token_type": "Bearer",
        "expires_in": JWT_EXPIRACAO_SEGUNDOS,
    }, correlation_id)
