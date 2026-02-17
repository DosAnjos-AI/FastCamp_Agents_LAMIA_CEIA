"""ADICIONANDO NOVOS CAMPOS DE VALIDAÇÃO AO PYDANTIC"""

import enum
import hashlib
import re
from typing import Any

from pydantic import (  #importando os modulos necessários
    BaseModel,
    EmailStr,
    Field,
    field_validator,
    model_validator,
    SecretStr,
    ValidationError,
)
#Descrevendo o padrão dos inputs (Senha + nome)
VALID_PASSWORD_REGEX = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$") #Garante que tenha pelo menos 1 letra minuscula, 1 letra maiuscula, pelo menosum digito, e tamanho minimo de 8 char
VALID_NAME_REGEX = re.compile(r"^[a-zA-Z]{2,}$")                            #Garante que se tenha apenas letras e espaços e no minimo 2 letras.


class Role(enum.IntFlag):       #Enumerador exclusivo(não repete valores), voltado em base dois, 
    Author = 1  
    Editor = 2
    Admin = 4
    SuperAdmin = 8


class User(BaseModel):          #Criando a classe usuário, que herda a classe BaseModel, por consequencia os seus atributos e funções
    name: str = Field(examples=["Arjan"])       #settando o nome para objeto, mas validando o campo como string e recebe exemplo
    email: EmailStr = Field(
        examples=["user@arjancodes.com"],
        description="The email address of the user",
        frozen=True,                            #Lembrar, que com essa opção em True, não se pode alterar depois.
    )
    password: SecretStr = Field(                #oculta o valor da senha com "***", não criptografa, apenas muda a skin
        examples=["Password123"], description="The password of the user"
    )
    role: Role = Field(
        default=None, description="The role of the user", examples=[1, 2, 4, 8] #Demonstra os exemplos, relaciona o numero a função autor=1; edito=2; ....
    )

    @field_validator("name")                        #Adicionando uma nova validação na classe dentro do pydantic, agora é uma função de classe, ou seja, uma validaçaõ personalizada
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not VALID_NAME_REGEX.match(v):           #Se o valor recebido não obedece as regras do regex de nome, retorna-se erro
            raise ValueError(
                "Name is invalid, must contain only letters and be at least 2 characters long"
            )
        return v

    @field_validator("role", mode="before")         #Adicionando dentro do field validador, para ser uma função de classe.
    @classmethod
    def validate_role(cls, v: int | str | Role) -> Role:    #Função de classe, 
        op = {int: lambda x: Role(x), str: lambda x: Role[x], Role: lambda x: x}
        try:
            return op[type(v)](v)
        except (KeyError, ValueError):
            raise ValueError(
                f"Role is invalid, please use one of the following: {', '.join([x.name for x in Role])}"
            )

    @model_validator(mode="before") 
    @classmethod
    def validate_user(cls, v: dict[str, Any]) -> dict[str, Any]:
        if "name" not in v or "password" not in v:                  #função de autenticação, saber se o nome e senhas conferem com o "Banco de dados"
            raise ValueError("Name and password are required")
        if v["name"].casefold() in v["password"].casefold():        #verifica se o usuário colocou o nome na senha, se sim, já dá erro
            raise ValueError("Password cannot contain name")
        if not VALID_PASSWORD_REGEX.match(v["password"]):           #Validando se a senha recebida obedece a lógica do regex
            raise ValueError(
                "Password is invalid, must contain 8 characters, 1 uppercase, 1 lowercase, 1 number"
            )
        v["password"] = hashlib.sha256(v["password"].encode()).hexdigest()  #Armazena a senha já em formato hash hexadecimal
        return v


def validate(data: dict[str, Any]) -> None: #nesta função além de validar já cria o objeto caso os dados estejam corretos
    try:
        user = User.model_validate(data)    #User.model_validade é a função herdada da classe User do BaseModels
        print(user)
    except ValidationError as e:
        print("User is invalid:")
        print(e)


def main() -> None:
    test_data = dict(                           #dicionário com os dados de teste
        good_data={
            "name": "Arjan",
            "email": "example@arjancodes.com",
            "password": "Password123",
            "role": "Admin",
        },
        bad_role={
            "name": "Arjan",
            "email": "example@arjancodes.com",
            "password": "Password123",
            "role": "Programmer",
        },
        bad_data={
            "name": "Arjan",
            "email": "bad email",
            "password": "bad password",
        },
        bad_name={
            "name": "Arjan<-_->",
            "email": "example@arjancodes.com",
            "password": "Password123",
        },
        duplicate={
            "name": "Arjan",
            "email": "example@arjancodes.com",
            "password": "Arjan123",
        },
        missing_data={
            "email": "<bad data>",
            "password": "<bad data>",
        },
    )

    for example_name, data in test_data.items():    #iteração dos exemplos acima
        print(example_name)
        validate(data)
        print()


if __name__ == "__main__": #Bora rodar!
    main()