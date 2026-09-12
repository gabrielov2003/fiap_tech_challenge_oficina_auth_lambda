import json
import os
import re

import jwt
import psycopg2

DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'oficina')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')


def validar_cpf(cpf):
    cpf = re.sub(r'\D', '', cpf or '')
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return None
    for i in range(9, 11):
        soma = sum(int(cpf[j]) * (i + 1 - j) for j in range(i))
        digito = (soma * 10 % 11) % 10
        if digito != int(cpf[i]):
            return None
    return cpf


def buscar_cliente(cpf):
    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id_cliente FROM cliente WHERE documento = %s", (cpf,))
            return cursor.fetchone()
    finally:
        conn.close()


def gerar_token(id_cliente, cpf):
    return jwt.encode({"id_cliente": id_cliente, "cpf": cpf}, JWT_SECRET_KEY, algorithm="HS256")


def lambda_handler(event, context):
    body = json.loads(event.get('body') or '{}')
    cpf = validar_cpf(body.get('cpf'))
    if not cpf:
        return {"statusCode": 400, "body": json.dumps({"erro": "CPF inválido"})}

    cliente = buscar_cliente(cpf)
    if not cliente:
        return {"statusCode": 404, "body": json.dumps({"erro": "Cliente não encontrado"})}

    id_cliente = cliente[0]
    token = gerar_token(id_cliente, cpf)
    return {"statusCode": 200, "body": json.dumps({"access_token": token})}
