import re
import requests
from datetime import datetime
from typing import Optional

# Pydantic será usado para:
# 1. Validar e filtrar a resposta da API Frankfurter (CurrencyResponse)
# 2. Estruturar e serializar o log completo da execucao (AgentIteration, AgentLog)
from pydantic import BaseModel, Field

from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL


# ============================================================================
# MODELOS PYDANTIC
# ============================================================================

class CurrencyResponse(BaseModel):
    """
    Modela a resposta da API Frankfurter.

    Por que Pydantic aqui?
    A API retorna campos extras (amount, base) que nao precisamos.
    extra='ignore' descarta silenciosamente tudo que nao esta declarado.
    model_validate() valida tipos e retorna instancia tipada em uma linha.
    """
    model_config = {"extra": "ignore"}

    date: str = Field(description="Data da cotacao no formato YYYY-MM-DD")
    rates: dict = Field(description="Codigo da moeda e taxa de conversao")


class AgentIteration(BaseModel):
    """
    Representa uma unica iteracao do loop ReAct.

    Por que Pydantic aqui?
    Garante estrutura consistente em cada iteracao do log,
    com campos opcionais para quando nao ha chamada de ferramenta.
    Serializa para JSON via .model_dump_json() sem codigo extra.
    """
    model_config = {"extra": "ignore"}

    numero: int
    resposta_llm: str
    ferramenta_chamada: Optional[str] = Field(default=None)
    argumento: Optional[str] = Field(default=None)
    resultado_ferramenta: Optional[str] = Field(default=None)


class AgentLog(BaseModel):
    """
    Log completo de uma execucao do agente.

    Por que Pydantic aqui?
    .model_dump_json(indent=2) serializa toda a estrutura aninhada
    (incluindo lista de AgentIteration) para JSON valido sem codigo extra.
    O mesmo objeto gera .json estruturado e .txt legivel.
    """
    model_config = {"extra": "ignore"}

    timestamp: str
    pais_origem: str
    pais_destino: str
    max_iteracoes: int
    iteracoes_utilizadas: int = Field(default=0)
    iteracoes: list[AgentIteration] = Field(default_factory=list)
    resposta_final: str = Field(default="")
    sucesso: bool = Field(default=False)


# ============================================================================
# CLASSE AGENT
# ============================================================================

class Agent:
    """
    Encapsula conexao com a API Groq e historico da conversa.

    O historico completo e acumulado em self.messages.
    Isso e essencial para o ReAct: o LLM precisa saber quais ferramentas
    ja chamou para nao repetir acoes e desperdicar iteracoes.
    """

    def __init__(self, system: str):
        self.client = Groq(api_key=GROQ_API_KEY)
        self.system = system
        self.messages: list[dict] = []

        # System prompt e sempre a primeira mensagem — nunca removido
        if self.system:
            self.messages.append({"role": "system", "content": self.system})

    def __call__(self, message: str = "") -> str:
        """Adiciona mensagem ao historico e retorna resposta do LLM."""
        if message:
            self.messages.append({"role": "user", "content": message})

        resposta = self._executar()

        # Acumula no historico para que o LLM saiba o que ja foi feito
        self.messages.append({"role": "assistant", "content": resposta})

        return resposta

    def _executar(self) -> str:
        """Faz a chamada a API Groq e retorna o texto da resposta."""
        completion = self.client.chat.completions.create(
            messages=self.messages,
            model=GROQ_MODEL,
        )
        return completion.choices[0].message.content


# ============================================================================
# FERRAMENTAS
# ============================================================================

def get_country_info(country_name: str) -> str:
    """
    Busca informacoes de um pais via REST Countries API.

    Estrategia de busca com fallback:
    1. Tenta pelo nome completo (/name/<country>)
    2. Se retornar populacao zero ou area muito pequena (territorio, nao pais),
       tenta pelo codigo ISO alpha-2 (/alpha/<country>) como fallback
    Isso resolve casos como "United States" que retorna o territorio
    "United States Minor Outlying Islands" antes do pais principal.

    Nota: JSON da API e muito aninhado (name.common, currencies.BRL.name).
    Achatamento feito manualmente — Pydantic seria forcado aqui.
    """
    country_name = country_name.strip()

    # Mapa de nomes comuns que a API resolve de forma errada pelo nome completo
    # A chave e o nome que o LLM tende a usar; o valor e o codigo ISO correto
    FALLBACK_ISO = {
        "united states": "US",
        "usa": "US",
        "uk": "GB",
        "united kingdom": "GB",
    }

    def _buscar_por_url(url: str) -> dict:
        """Faz a requisicao e retorna o primeiro resultado como dict."""
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()[0]

    def _formatar(data: dict) -> str:
        """Extrai e formata os campos relevantes de um resultado da API."""
        capital = data["capital"][0] if data.get("capital") else "N/A"
        populacao = f"{data['population']:,}"
        idiomas = ", ".join(data.get("languages", {}).values())

        currencies = data.get("currencies", {})
        if currencies:
            codigo = list(currencies.keys())[0]
            info = currencies[codigo]
            moeda = f"{info['name']} ({codigo})"
        else:
            moeda = "N/A"

        timezone = data.get("timezones", ["UTC"])[0]
        area = f"{data.get('area', 0):,.0f}"

        return (
            f"Country: {data['name']['common']}\n"
            f"Capital: {capital}\n"
            f"Population: {populacao}\n"
            f"Language: {idiomas}\n"
            f"Currency: {moeda}\n"
            f"Timezone: {timezone}\n"
            f"Area: {area} km2"
        )

    try:
        # Verifica se ha fallback direto para o nome informado
        chave = country_name.lower()
        if chave in FALLBACK_ISO:
            iso = FALLBACK_ISO[chave]
            data = _buscar_por_url(f"https://restcountries.com/v3.1/alpha/{iso}")
            return _formatar(data)

        # Busca pelo nome — caminho padrao
        data = _buscar_por_url(f"https://restcountries.com/v3.1/name/{country_name}")

        # Verifica se o resultado e um territorio e nao o pais principal
        # (ex: "United States Minor Outlying Islands" tem populacao 0)
        if data.get("population", 0) == 0:
            # Tenta busca por codigo alpha como fallback automatico
            alpha = data.get("cca2", "")
            if alpha:
                try:
                    data = _buscar_por_url(
                        f"https://restcountries.com/v3.1/alpha/{alpha}"
                    )
                except Exception:
                    pass

        return _formatar(data)

    except Exception as e:
        return f"ERROR: Could not fetch data for {country_name}: {str(e)}"


def convert_currency(from_code: str, to_code: str) -> str:
    """
    Converte 1 unidade da moeda origem para destino via Frankfurter API.

    Pydantic em acao:
    model_validate() recebe o JSON da API, valida os campos declarados
    e descarta os extras (extra='ignore'). Falha rapido se a API mudar.
    """
    from_code = from_code.strip().upper()
    to_code = to_code.strip().upper()

    url = f"https://api.frankfurter.dev/v1/latest?base={from_code}&symbols={to_code}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        dados = CurrencyResponse.model_validate(response.json())
        taxa = dados.rates[to_code]
        return f"1 {from_code} = {taxa:.4f} {to_code} (date: {dados.date})"

    except Exception as e:
        return f"ERROR: Could not convert {from_code} to {to_code}: {str(e)}"


# Ferramentas disponiveis para o loop ReAct
# calculate_timezone_diff removida — o LLM calcula manualmente com os offsets
# retornados por get_country_info, economizando uma iteracao por execucao
FERRAMENTAS = {
    "get_country_info": get_country_info,
    "convert_currency": convert_currency,
}