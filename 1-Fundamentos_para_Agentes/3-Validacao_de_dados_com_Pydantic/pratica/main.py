import re
import sys
from datetime import datetime

# Garante que o terminal exibe caracteres especiais corretamente (acentos, cedilha)
sys.stdout.reconfigure(encoding="utf-8")

from config import SYSTEM_PROMPT, MAX_ITERATIONS
from agent import Agent, AgentLog, AgentIteration, FERRAMENTAS


# ============================================================================
# LOOP PRINCIPAL DO AGENTE REACT
# ============================================================================

def agent_loop(
    pais_origem: str,
    pais_destino: str,
    max_iterations: int = MAX_ITERATIONS,
    log_file: str = "agent_log"
) -> str:
    """
    Executa o loop ReAct (Thought -> Action -> PAUSE -> Observation -> Answer).

    O padrao ReAct funciona assim:
    1. O LLM recebe o prompt e responde com Thought + Action + PAUSE
    2. O loop detecta a Action, executa a ferramenta correspondente
    3. O resultado e devolvido ao LLM como Observation
    4. O ciclo se repete ate o LLM emitir Answer ou o limite ser atingido

    Args:
        pais_origem: Pais de origem do usuario (ex: "Brasil")
        pais_destino: Pais que o usuario quer conhecer (ex: "Japao")
        max_iterations: Limite de iteracoes do loop
        log_file: Nome base dos arquivos de log (sem extensao)
    """

    agente = Agent(system=SYSTEM_PROMPT)

    # Estrutura Pydantic que acumula o log completo da execucao
    log = AgentLog(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        pais_origem=pais_origem,
        pais_destino=pais_destino,
        max_iteracoes=max_iterations,
    )

    # Prompt inicial fixo — o agente infere o idioma pelo pais de origem
    proximo_prompt = f"Estou em {pais_origem}, me fale sobre {pais_destino}"

    resultado_final = ""

    print(f"\nIniciando comparacao: {pais_origem} vs {pais_destino}")
    print(f"Limite de iteracoes: {max_iterations}")
    print("-" * 60)

    for i in range(1, max_iterations + 1):

        # Na ultima iteracao, instrui o LLM a finalizar obrigatoriamente
        # com os dados que ja tem — evita chamada extra apos o loop
        if i == max_iterations:
            proximo_prompt = (
                f"{proximo_prompt}\n\n"
                f"ATENCAO: Esta e sua ultima iteracao ({i}/{max_iterations}). "
                f"Finalize AGORA com Answer usando os dados ja coletados."
            )

        print(f"  Iteracao {i}/{max_iterations}", end=" -> ")

        resposta = agente(proximo_prompt)

        registro = AgentIteration(
            numero=i,
            resposta_llm=resposta,
        )

        # ----------------------------------------------------------------
        # DETECCAO DE ANSWER — verificado ANTES de Action
        # Correcao critica: o LLM as vezes emite Action + Answer na mesma
        # resposta (iteracao final). Verificar Answer primeiro garante que
        # a resposta final nao seja ignorada pelo bloco de Action.
        # ----------------------------------------------------------------
        if "Answer" in resposta:
            print("concluido")

            answer_match = re.search(r"Answer:?\s*(.+)", resposta, re.DOTALL | re.IGNORECASE)
            resultado_final = answer_match.group(1).strip() if answer_match else resposta

            log.sucesso = True
            log.iteracoes.append(registro)
            break

        # ----------------------------------------------------------------
        # DETECCAO DE ACTION — ferramenta a executar
        # O LLM sinaliza com PAUSE que quer executar uma ferramenta.
        # O regex extrai o nome da ferramenta e os argumentos.
        # ----------------------------------------------------------------
        if "PAUSE" in resposta and "Action" in resposta:
            action_match = re.findall(
                r"Action:\s*([a-z_]+):\s*(.+)", resposta, re.IGNORECASE
            )

            if action_match:
                nome_ferramenta = action_match[0][0].strip()
                argumento = action_match[0][1].strip()

                print(f"{nome_ferramenta}({argumento})")

                registro.ferramenta_chamada = nome_ferramenta
                registro.argumento = argumento

                if nome_ferramenta in FERRAMENTAS:
                    try:
                        # convert_currency requer 2 argumentos separados por virgula
                        if nome_ferramenta == "convert_currency":
                            args = [a.strip() for a in argumento.split(",")]
                            resultado_ferramenta = (
                                FERRAMENTAS[nome_ferramenta](*args)
                                if len(args) == 2
                                else "ERROR: convert_currency requer 2 argumentos"
                            )
                        else:
                            resultado_ferramenta = FERRAMENTAS[nome_ferramenta](argumento)

                    except Exception as e:
                        resultado_ferramenta = f"ERROR: {str(e)}"
                else:
                    resultado_ferramenta = "ERROR: ferramenta nao encontrada"

                registro.resultado_ferramenta = str(resultado_ferramenta)

                # Observation e o que o LLM recebera na proxima iteracao
                proximo_prompt = f"Observation: {resultado_ferramenta}"

                log.iteracoes.append(registro)
                continue

        # Iteracao sem Action nem Answer — Thought puro
        print("raciocinio")
        log.iteracoes.append(registro)

    # ----------------------------------------------------------------
    # FINALIZACAO
    # ----------------------------------------------------------------
    log.iteracoes_utilizadas = len(log.iteracoes)
    log.resposta_final = resultado_final

    _salvar_log(log, log_file)

    print("-" * 60)
    print("\nRESPOSTA FINAL:")
    print("=" * 60)
    print(resultado_final)
    print("=" * 60)
    print(f"Iteracoes utilizadas: {log.iteracoes_utilizadas}/{max_iterations}")
    print(f"Log salvo em: {log_file}.json e {log_file}.txt")

    return resultado_final


def _salvar_log(log: AgentLog, nome_base: str) -> None:
    """
    Serializa o AgentLog para dois formatos usando o mesmo objeto Pydantic.

    .model_dump_json() e metodo nativo do Pydantic v2 que converte toda a
    estrutura aninhada (incluindo lista de AgentIteration) para JSON valido,
    respeitando tipos e nomes dos campos declarados no modelo.
    """

    # JSON estruturado — facil de processar programaticamente
    with open(f"{nome_base}.json", "w", encoding="utf-8") as f:
        f.write(log.model_dump_json(indent=2))

    # TXT legivel — gerado a partir do mesmo objeto Pydantic
    with open(f"{nome_base}.txt", "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("LOG DO AGENTE DE COMPARACAO DE PAISES\n")
        f.write("=" * 60 + "\n")
        f.write(f"Timestamp:        {log.timestamp}\n")
        f.write(f"Pais origem:      {log.pais_origem}\n")
        f.write(f"Pais destino:     {log.pais_destino}\n")
        f.write(f"Max iteracoes:    {log.max_iteracoes}\n")
        f.write(f"Iteracoes usadas: {log.iteracoes_utilizadas}\n")
        f.write(f"Sucesso:          {log.sucesso}\n")
        f.write("=" * 60 + "\n\n")

        for it in log.iteracoes:
            f.write(f"--- ITERACAO {it.numero} ---\n")
            f.write(f"Resposta LLM:\n{it.resposta_llm}\n")
            if it.ferramenta_chamada:
                f.write(f"Ferramenta: {it.ferramenta_chamada}({it.argumento})\n")
                f.write(f"Resultado:  {it.resultado_ferramenta}\n")
            f.write("\n")

        f.write("=" * 60 + "\n")
        f.write("RESPOSTA FINAL\n")
        f.write("=" * 60 + "\n")
        f.write(log.resposta_final + "\n")


# ============================================================================
# ENTRADA DO USUARIO
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("AGENTE DE COMPARACAO DE PAISES")
    print("=" * 60)
    print("ATENCAO: A resposta sera fornecida no idioma")
    print("         oficial do seu pais de origem.")
    print("=" * 60)

    pais_origem = input("\nSeu pais de origem: ").strip()
    pais_destino = input("Pais que deseja conhecer: ").strip()

    nome_log = f"log_{pais_origem}_{pais_destino}".replace(" ", "_")

    agent_loop(
        pais_origem=pais_origem,
        pais_destino=pais_destino,
        log_file=nome_log
    )