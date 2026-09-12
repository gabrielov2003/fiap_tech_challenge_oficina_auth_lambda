import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lambda_function import validar_cpf


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
