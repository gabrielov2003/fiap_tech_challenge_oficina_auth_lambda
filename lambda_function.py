import base64
import json
import os
import re
import time
import uuid

import jwt
import psycopg2

DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'oficina')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_SCHEMA = os.getenv('DB_SCHEMA', 'public')
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')
JWT_EXPIRACAO_SEGUNDOS = int(os.getenv('JWT_EXPIRACAO_SEGUNDOS', '3600'))

_conexao = None


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


def obter_conexao():
    global _conexao
    if _conexao is None or _conexao.closed:
        _conexao = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
            options=f'-c search_path={DB_SCHEMA}', connect_timeout=5
        )
        _conexao.autocommit = True
    return _conexao


def descartar_conexao():
    global _conexao
    if _conexao is not None and not _conexao.closed:
        _conexao.close()
    _conexao = None


def buscar_cliente(cpf):
    with obter_conexao().cursor() as cursor:
        cursor.execute("SELECT id_cliente, status FROM cliente WHERE documento = %s", (cpf,))
        return cursor.fetchone()


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
    except psycopg2.Error as e:
        log('erro_consulta_cliente', correlation_id, nivel='ERROR', erro=type(e).__name__)
        descartar_conexao()
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
