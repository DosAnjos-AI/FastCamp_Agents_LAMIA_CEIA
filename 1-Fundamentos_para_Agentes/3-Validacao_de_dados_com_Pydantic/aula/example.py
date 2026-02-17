from enum import auto, IntFlag
from typing import Any

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    SecretStr,
    ValidationError,
)


class Role(IntFlag):
    Author = auto()
    Editor = auto()
    Developer = auto()
    Admin = Author | Editor | Developer


class User(BaseModel):                              #A classe herdada aqui, veio do import do pydantic
    name: str = Field(examples=["Arjan"])           #Adicionando os campos, conforme necessidade do projeto, resolução do problema.
    email: EmailStr = Field(                        #Função veio do import do pydantic, serve para validação de e-mail
        examples=["example@arjancodes.com"],
        description="The email address of the user",
        frozen=True,                                #Não permite alterações futuras
    )
    password: SecretStr = Field(                    #Função que veio do import pydantic, ela serve para omitir os caracteres da senha "***"
        examples=["Password123"], description="The password of the user"
    )
    role: Role = Field(default=None, description="The role of the user")


def validate(data: dict[str, Any]) -> None:         #Função validação do modelo do usuário, permitindo validar se os dados estão de acordo com a estrutrua do usuário
    try:
        user = User.model_validate(data)
        print(user)
    except ValidationError as e:                    #Caso der algum tipo de erro, vai printar o tipo de erro,
        print("User is invalid")
        for error in e.errors():
            print(error)


def main() -> None:
    good_data = {                                   #Dicionário com bons exemplos, ou seja, dados válidos
        "name": "Arjan",
        "email": "example@arjancodes.com",          
        "password": "Password123",
    }
    bad_data = {"email": "<bad data>", "password": "<bad data>"}    #Dicionário com exemplos de dados errados/indesejados. Neste, além de naõ ter o padrão, ainda faltou o campo nome
    #chamando a função com os exemplos acima.
    print('Exemplo GOOD DATA')
    validate(good_data)
    print('\n\nExemplo BAD DATA')
    validate(bad_data)


if __name__ == "__main__":
    main()


    """Após a execução, vc nota que ele identificou a falta do usuário e percebeu os erros de estrutura de email,
        Portanto, ele fez isso sem que precisasse criar funções de validações na mão."""