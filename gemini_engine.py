# gemini_engine.py
import os
from google import genai
from google.genai import types
from curadoria import INSIGHTS_GERAIS

# Modelos tentados em ordem. Pode sobrescrever com a variável/secret GEMINI_MODEL.
# Os modelos "lite" respondem bem mais rápido; ficam na frente.
MODELOS_PREFERIDOS = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.8-flash",
]

# Tempo máximo (segundos) de cada chamada à API. Evita o "pensando para sempre".
TIMEOUT_SEGUNDOS = 30

# Guarda o último modelo que funcionou para não testar os outros toda vez.
_MODELO_OK = None

# Modelos que a API disse não existir (404): não são tentados de novo nesta execução.
_MODELOS_INDISPONIVEIS = set()


def _registrar_falha(nome: str, msg: str):
    global _MODELO_OK
    m = msg.upper()
    if "404" in m or "NOT_FOUND" in m or "NO LONGER AVAILABLE" in m:
        _MODELOS_INDISPONIVEIS.add(nome)
    if _MODELO_OK == nome and ("504" in m or "DEADLINE" in m or "503" in m or "UNAVAILABLE" in m):
        _MODELO_OK = None  # estava lento/fora: volta a testar a lista


MSG_CHAVE_INVALIDA = (
    "O Google recusou a chave do Gemini (401 UNAUTHENTICATED). Isso não é problema de modelo: "
    "a chave está inválida, incompleta ou é de um tipo que o Gemini não aceita. "
    "Gere uma nova chave em https://aistudio.google.com/apikey, cole-a inteira (sem aspas extras "
    "nem espaços) em GEMINI_API_KEY nos Secrets do Streamlit e reinicie o app."
)


def _erro_de_chave(msg: str) -> bool:
    """True quando o erro é de autenticação: trocar de modelo não adianta."""
    m = msg.upper()
    return ("401" in m or "UNAUTHENTICATED" in m or "API KEY NOT VALID" in m
            or "API_KEY_INVALID" in m or "ACCESS_TOKEN_TYPE_UNSUPPORTED" in m)


def _limpar_chave(key: str) -> str:
    """Remove espaços, quebras de linha e aspas que costumam vir ao colar a chave."""
    return (key or "").strip().strip('"').strip("'").strip()


def get_client(api_key: str = None):
    key = _limpar_chave(api_key or os.getenv("GEMINI_API_KEY"))
    if not key:
        raise ValueError("Chave GEMINI_API_KEY não encontrada.")
    return genai.Client(
        api_key=key,
        http_options=types.HttpOptions(timeout=TIMEOUT_SEGUNDOS * 1000),  # milissegundos
    )


def _descobrir_modelos(client):
    """Consulta a API e devolve modelos 'flash' que suportam generateContent."""
    try:
        nomes = []
        for m in client.models.list():
            acoes = getattr(m, "supported_actions", None) or []
            nome = (getattr(m, "name", "") or "").replace("models/", "")
            if "generateContent" in acoes and "flash" in nome:
                if any(x in nome for x in ("image", "tts", "live", "audio", "embedding", "preview", "exp")):
                    continue
                nomes.append(nome)
        # mais novos primeiro e, entre eles, os "lite" (mais rápidos) na frente
        return sorted(set(nomes), key=lambda n: (n.split("-")[1] if "-" in n else "", "lite" in n), reverse=True)
    except Exception:
        return []


def _ordem_modelos():
    ordem = []
    if _MODELO_OK:
        ordem.append(_MODELO_OK)
    override = os.getenv("GEMINI_MODEL")
    if override:
        ordem.append(override)
    ordem.extend(MODELOS_PREFERIDOS)
    vistos, final = set(), []
    for m in ordem:
        if m not in vistos and m not in _MODELOS_INDISPONIVEIS:
            vistos.add(m)
            final.append(m)
    return final


def _config_rapida(config, model_name):
    """Reduz o 'pensamento' do modelo para responder em segundos."""
    try:
        if model_name.startswith("gemini-2.5"):
            tc = types.ThinkingConfig(thinking_budget=0)
        else:
            tc = types.ThinkingConfig(thinking_level="low")
    except Exception:
        return config
    base = config if config is not None else types.GenerateContentConfig()
    try:
        return base.model_copy(update={"thinking_config": tc})
    except Exception:
        return config


class _ChaveInvalida(Exception):
    pass


def _gerar(client, contents, config=None):
    """Tenta gerar conteúdo percorrendo modelos. Retorna (texto, erros)."""
    global _MODELO_OK
    erros = []
    tentados = set()

    def tentar(model_name):
        global _MODELO_OK
        if model_name in tentados or model_name in _MODELOS_INDISPONIVEIS:
            return None
        tentados.add(model_name)
        for cfg in (_config_rapida(config, model_name), config):
            try:
                kwargs = {"model": model_name, "contents": contents}
                if cfg is not None:
                    kwargs["config"] = cfg
                resp = client.models.generate_content(**kwargs)
                if resp and resp.text:
                    _MODELO_OK = model_name
                    return resp.text
                erros.append(f"{model_name}: resposta vazia")
                return None
            except Exception as e:
                msg = str(e)
                erros.append(f"{model_name}: {msg}")
                if _erro_de_chave(msg):
                    raise _ChaveInvalida(msg)
                _registrar_falha(model_name, msg)
                # Só repete sem a config de 'thinking' se o erro for sobre isso
                if "thinking" not in msg.lower():
                    return None
        return None

    try:
        for nome in _ordem_modelos():
            texto = tentar(nome)
            if texto:
                return texto, erros

        for nome in _descobrir_modelos(client):
            texto = tentar(nome)
            if texto:
                return texto, erros
    except _ChaveInvalida:
        return None, [MSG_CHAVE_INVALIDA] + erros[-1:]

    return None, erros


def avaliar_resposta_completa(client, contexto: dict, pergunta: str, dados_pergunta: dict,
                              resposta_texto: str = None, audio_bytes: bytes = None,
                              audio_mime: str = "audio/wav"):
    """Avalia a resposta do candidato (áudio ou texto)."""
    contexto = contexto or {}
    dados_pergunta = dados_pergunta or {}

    prompt_texto = f"""
    {INSIGHTS_GERAIS}

    CONTEXTO DA VAGA E EMPRESA:
    Empresa: {contexto.get('empresa', 'Não informada')}
    Cargo: {contexto.get('cargo', 'Não informado')}
    Descrição da Vaga: {contexto.get('descricao', 'Não informada')}
    Sobre a Empresa: {contexto.get('sobre_empresa', 'Não informada')}
    Perfil LinkedIn do Candidato: {contexto.get('linkedin', 'Não informado')}
    Texto do Currículo: {contexto.get('curriculo_texto', 'Não informado')}

    PERGUNTA DA ENTREVISTA SELECIONADA:
    "{pergunta}"

    TÉCNICA ESPERADA PARA ESTA PERGUNTA: {dados_pergunta.get('tecnica', 'STAR')}
    EXPECTATIVA DO RECRUTADOR: {dados_pergunta.get('expectativa', 'Avaliação geral')}

    INSTRUÇÕES DE AVALIAÇÃO:
    1. Se houver áudio anexado, transcreva-o primeiro na íntegra.
    2. Avalie o alinhamento da resposta do candidato com os requisitos da vaga e a expectativa técnica da pergunta.
    3. Seja direto e conciso. Retorne um parecer estruturado contendo:
       - Transcrição (se aplicável)
       - Diagnóstico Geral e % de Alinhamento (0 a 100%)
       - Análise Técnica da Estrutura da Resposta
       - Pontos Fortes
       - Lacunas e Oportunidades de Melhoria
       - Reescrita Sugerida de Alto Impacto
    """

    if resposta_texto and str(resposta_texto).strip():
        prompt_texto += f"\n\nRESPOSTA ESCRITA DO CANDIDATO:\n{str(resposta_texto).strip()}"

    parts = []
    if audio_bytes and isinstance(audio_bytes, bytes) and len(audio_bytes) > 0:
        parts.append(types.Part.from_bytes(data=audio_bytes, mime_type=audio_mime))
    parts.append(types.Part.from_text(text=prompt_texto))

    texto, erros = _gerar(client, parts)
    if texto:
        return texto

    return "Não foi possível obter resposta da API do Gemini. Detalhes do erro:\n\n" + "\n\n".join(erros)


def _montar_chat(historico_mensagens, contexto_vaga, pergunta, parecer_anterior):
    contexto_vaga = contexto_vaga or {}
    system_instruction = f"""
    Você é um mentor sênior de carreiras e recrutador de elite.
    Seu objetivo é ajudar o candidato a lapidar a resposta para a pergunta: "{pergunta}".

    DADOS DO CANDIDATO E DA VAGA:
    - Empresa: {contexto_vaga.get('empresa', 'Não informada')}
    - Cargo: {contexto_vaga.get('cargo', 'Não informado')}
    - Descrição: {contexto_vaga.get('descricao', 'Não informada')}
    - Sobre a Empresa: {contexto_vaga.get('sobre_empresa', 'Não informada')}
    - LinkedIn: {contexto_vaga.get('linkedin', 'Não informado')}
    - Resumo do Currículo: {contexto_vaga.get('curriculo_texto', 'Não informado')}
    - Último parecer de avaliação: {parecer_anterior}

    DIRETRIZES:
    1. As informações fornecidas acima são suas referências principais.
    2. Use busca na web só se for realmente necessário (novidades da empresa, tendências).
    3. Dê feedbacks elegantes, práticos e objetivos e construa a melhor narrativa profissional possível com o candidato.
    """
    contents = []
    for msg in historico_mensagens:
        role = "user" if msg.get("role") == "user" else "model"
        texto = msg.get("content", "")
        if str(texto).strip():
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=str(texto))]))
    return system_instruction, contents


FALHA_CHAT = "Não foi possível gerar a resposta do chat no momento."
MARCADOR_RESPOSTA = "✦ Sua resposta pronta"


def resposta_falhou(texto) -> bool:
    """True quando o texto devolvido pelo chat é uma mensagem de erro (não deve ser salvo)."""
    t = str(texto or "")
    return t.startswith(FALHA_CHAT) or t.startswith(MSG_CHAVE_INVALIDA)


def _stream(client, system_instruction, contents, permitir_busca=True):
    """Streaming com troca automática de modelo. Primeiro sem busca na web (mais rápido)."""
    config_simples = types.GenerateContentConfig(system_instruction=system_instruction)
    configs = [config_simples]
    if permitir_busca:
        configs.append(types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ))

    erros = []

    def tentar(nome, base):
        """Gera os pedaços de texto; devolve via exceção _Pronto quando terminar com sucesso."""
        global _MODELO_OK
        for cfg in (_config_rapida(base, nome), base):
            emitiu = False
            try:
                for chunk in client.models.generate_content_stream(model=nome, contents=contents, config=cfg):
                    if chunk and chunk.text:
                        emitiu = True
                        yield chunk.text
                if emitiu:
                    _MODELO_OK = nome
                    raise _Pronto()
                erros.append(f"{nome}: resposta vazia")
                return
            except _Pronto:
                raise
            except Exception as e:
                if emitiu:
                    raise _Pronto()  # já mostrou parte do texto; encerra sem repetir
                msg = str(e)
                erros.append(f"{nome}: {msg}")
                if _erro_de_chave(msg):
                    raise _ChaveInvalida(msg)
                _registrar_falha(nome, msg)
                if "thinking" not in msg.lower():
                    return

    try:
        for base in configs:
            tentados = set()
            for nome in _ordem_modelos():
                tentados.add(nome)
                yield from tentar(nome, base)
            for nome in _descobrir_modelos(client):
                if nome in tentados or nome in _MODELOS_INDISPONIVEIS:
                    continue
                tentados.add(nome)
                yield from tentar(nome, base)
    except _Pronto:
        return
    except _ChaveInvalida:
        yield MSG_CHAVE_INVALIDA
        return

    yield FALHA_CHAT + " Detalhes:\n\n" + "\n\n".join(erros)


class _Pronto(Exception):
    pass


def stream_chat_lapidacao(client, historico_mensagens: list, contexto_vaga: dict,
                          pergunta: str, parecer_anterior: str):
    """Chat da Etapa 3 (lapidação a partir do parecer). Use com st.write_stream()."""
    system_instruction, contents = _montar_chat(historico_mensagens, contexto_vaga, pergunta, parecer_anterior)
    yield from _stream(client, system_instruction, contents)


def stream_chat_mentor(client, historico_mensagens: list, contexto_vaga: dict = None,
                       pergunta_foco: str = None):
    """
    Mentor livre: conversa ANTES do treino, para ajudar o candidato a encontrar
    exemplos e montar a resposta do zero. Funciona com ou sem vaga cadastrada.
    """
    ctx = contexto_vaga or {}
    if ctx.get("empresa"):
        bloco_vaga = f"""
    VAGA QUE O CANDIDATO ESTÁ PREPARANDO (use como referência, sem inventar fatos):
    - Empresa: {ctx.get('empresa', '')}
    - Cargo: {ctx.get('cargo', '')}
    - Descrição: {ctx.get('descricao', '')}
    - Sobre a empresa: {ctx.get('sobre_empresa', '') or 'Não informado'}
    - Currículo: {ctx.get('curriculo_texto', '') or 'Não informado'}
    """
    else:
        bloco_vaga = "\n    O candidato ainda não cadastrou uma vaga. Ajude de forma geral e, se fizer sentido, pergunte para qual vaga ele se prepara.\n"

    foco = (f'\n    PERGUNTA QUE ELE QUER TREINAR: "{pergunta_foco}"\n'
            if pergunta_foco else "")

    system_instruction = f"""
    Você é o Mentor do Interview Lab AI: um mentor de carreira sênior, caloroso, elegante e direto.
    O candidato está conversando com você ANTES de treinar no simulador, porque ainda não tem
    uma resposta pronta. Seu papel é ajudá-lo a descobrir bons exemplos na própria trajetória e
    transformá-los em uma resposta de entrevista forte.
    {bloco_vaga}{foco}
    COMO CONDUZIR:
    1. Faça perguntas curtas, uma ou duas por vez, para extrair situações reais, números e resultados.
       Nunca invente experiências, empresas ou métricas: use apenas o que o candidato contar.
    2. Escolha a técnica certa: STAR (Situação, Tarefa, Ação, Resultado) para perguntas comportamentais;
       pitch Passado-Presente-Futuro para apresentação pessoal; exemplo prático + aplicação para aprendizado.
    3. Quando tiver material suficiente, entregue a resposta completa, em primeira pessoa, natural para
       falar em voz alta (cerca de 1 a 2 minutos), dentro deste formato exato:

    ---
    #### {MARCADOR_RESPOSTA}
    (a resposta aqui, em parágrafos)

    ---

    4. Depois da resposta, em uma linha, sugira levá-la ao Treinador para receber o parecer técnico.
    5. Responda sempre em português do Brasil, com frases claras e sem excesso de jargão.
    """
    contents = []
    for msg in historico_mensagens:
        role = "user" if msg.get("role") == "user" else "model"
        texto = str(msg.get("content", "")).strip()
        if texto:
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=texto)]))
    yield from _stream(client, system_instruction, contents, permitir_busca=False)


def extrair_resposta_pronta(texto: str) -> str:
    """Pega a resposta que o mentor marcou como pronta; se não houver marcação, devolve ''."""
    texto = str(texto or "")
    if MARCADOR_RESPOSTA not in texto:
        return ""
    trecho = texto.split(MARCADOR_RESPOSTA, 1)[1]
    trecho = trecho.split("\n---", 1)[0]
    linhas = [l for l in trecho.strip().splitlines() if not l.strip().startswith("#")]
    return "\n".join(linhas).strip().strip("*").strip()


def simular_chat_lapidacao_com_busca(client, historico_mensagens: list, contexto_vaga: dict,
                                     pergunta: str, parecer_anterior: str):
    """Versão sem streaming (mantida por compatibilidade)."""
    return "".join(stream_chat_lapidacao(client, historico_mensagens, contexto_vaga, pergunta, parecer_anterior))
