import os
import uuid
import base64
from datetime import datetime
import streamlit as st
from supabase import create_client, Client
from curadoria import PERGUNTAS_CURATORIA
from gemini_engine import (
    get_client, avaliar_resposta_completa, stream_chat_lapidacao,
    stream_chat_mentor, extrair_resposta_pronta, resposta_falhou,
)

# Leitura opcional de arquivos de currículo
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    from docx import Document
except ImportError:
    Document = None

ETAPA_1 = "1. Contexto da Vaga"
ETAPA_2 = "2. Painel de Simulação"
ETAPA_3 = "3. Lapidação & Feedback"

MENU_MENTOR = "Mentor"
MENU_TREINO = "Treinador"
ROTULOS_MENU = {
    MENU_MENTOR: "✦  Mentor · conversa livre",
    MENU_TREINO: "✦  Treinador · simulação",
}
PERGUNTA_LIVRE = "Ainda não sei · conversa livre"
SUGESTOES_MENTOR = [
    "Não tenho uma resposta pronta para “fale sobre você”. Pode me ajudar a montar?",
    "Preciso de um exemplo de trabalho em equipe, mas não sei qual história contar.",
    "Me explique o método STAR com um exemplo e depois me ajude a aplicar no meu caso.",
]

# ============================================================
# CONFIGURAÇÃO DE PÁGINA E DESIGN EDITORIAL CLEAN
# ============================================================
st.set_page_config(
    page_title="Interview Lab AI",
    page_icon="icone.png",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;0,600;0,700;1,500;1,600&family=Cinzel:wght@500;600;700&family=Jost:wght@400;500;600&display=swap');

    :root {
        --floresta: #111E16;
        --musgo: #233A2C;
        --pergaminho: #F4EEE1;
        --marfim: #FBF8F1;
        --ouro: #A8834A;
        --ouro-claro: #C9A96E;
        --tinta: #2B2620;
        --sepia: #7A6F5E;
        --vinho: #6E2A26;
        --filete: rgba(168, 131, 74, 0.38);
    }

    /* ---------- Base: papel envelhecido ---------- */
    .stApp {
        background-color: var(--pergaminho);
        background-image:
            radial-gradient(ellipse at top, rgba(255,252,244,0.85) 0%, rgba(244,238,225,0) 60%),
            radial-gradient(ellipse at bottom, rgba(168,131,74,0.10) 0%, rgba(244,238,225,0) 55%),
            repeating-linear-gradient(0deg, rgba(120,100,70,0.018) 0px, rgba(120,100,70,0.018) 1px, transparent 1px, transparent 3px);
        color: var(--tinta);
        font-family: 'Jost', sans-serif;
        font-weight: 400;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
        text-rendering: optimizeLegibility;
    }
    .stApp p, .stApp li, .stApp label, .stMarkdown { font-family: 'Jost', sans-serif; }
    h1 span, h2 span, h3 span, h4 span { font-family: inherit !important; }
    .block-container { padding-top: 4.6rem; max-width: 1180px; }

    h1, h2, h3, h4 {
        font-family: 'Cormorant Garamond', serif !important;
        color: var(--floresta) !important;
        font-weight: 600 !important;
        letter-spacing: 0.01em;
    }
    h3 { font-size: 2.1rem !important; font-style: italic; font-weight: 600 !important; }
    h4 { font-size: 1.35rem !important; }
    strong, b { font-weight: 500; color: var(--floresta); }

    /* Rótulos dos campos em versalete */
    [data-testid="stWidgetLabel"] p {
        font-family: 'Jost', sans-serif !important;
        font-size: 0.76rem !important;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: var(--musgo) !important;
        font-weight: 600 !important;
    }

    /* Elementos decorativos */
    .kicker {
        font-family: 'Jost', sans-serif;
        letter-spacing: 0.28em;
        text-transform: uppercase;
        font-size: 0.74rem;
        font-weight: 600;
        color: var(--ouro);
        margin: 0;
    }
    .ornamento {
        display: flex; align-items: center; gap: 14px;
        color: var(--ouro); margin: 1.1rem auto 1.6rem auto; max-width: 100%;
    }
    .ornamento::before, .ornamento::after {
        content: ""; flex: 1; height: 1px;
        background: linear-gradient(90deg, transparent, var(--ouro-claro), transparent);
    }
    .ornamento span { font-size: 0.8rem; letter-spacing: 0.6em; padding-left: 0.6em; }
    .intro-secao { color: var(--sepia); font-size: 0.98rem; margin: -0.4rem 0 1.4rem 0; line-height: 1.6; }

    /* ---------- Cartões com moldura dupla ---------- */
    div[data-testid="stVerticalBlockBorderWrapper"], div[class*="st-key-moldura"] {
        background-color: var(--marfim);
        border: 1px solid var(--filete) !important;
        border-radius: 2px;
        box-shadow: inset 0 0 0 5px var(--marfim), inset 0 0 0 6px rgba(168,131,74,0.22),
                    0 10px 30px rgba(60, 45, 20, 0.06);
    }
    .cartao-metodo {
        background: var(--marfim);
        border: 1px solid var(--filete);
        border-left: 3px solid var(--ouro);
        padding: 16px 20px; margin: 10px 0 22px 0;
    }
    .cartao-metodo .rot {
        font-family: 'Jost', sans-serif; font-size: 0.74rem; font-weight: 600; letter-spacing: 0.14em; color: var(--floresta);
    }
    .cartao-metodo .txt { font-size: 0.95rem; color: #4A4236; }

    /* ---------- Botões ---------- */
    .stButton>button {
        background-color: var(--floresta);
        color: #F1E6CC;
        border: 1px solid var(--ouro);
        border-radius: 1px;
        padding: 0.7rem 1.5rem;
        font-family: 'Cinzel', serif;
        font-weight: 700;
        font-size: 0.82rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        width: 100%;
        box-shadow: inset 0 0 0 3px var(--floresta), inset 0 0 0 4px rgba(201,169,110,0.35);
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        background-color: var(--musgo);
        border-color: var(--ouro-claro);
        color: #FFF8E7;
        box-shadow: inset 0 0 0 3px var(--musgo), inset 0 0 0 4px rgba(201,169,110,0.6);
    }
    .stButton>button p { font-family: 'Cinzel', serif !important; font-weight: 700 !important; font-size: 0.82rem; }

    /* Contêiner dos botões ocupa a coluna toda (para o alinhamento funcionar) */
    .st-key-btn_toggle_cad, .st-key-btn_voltar_login1, .st-key-btn_voltar_login2,
    .st-key-btn_logout, .st-key-btn_historico {
        width: 100% !important; max-width: 100% !important;
    }
    .st-key-btn_toggle_cad div[data-testid="stButton"],
    .st-key-btn_voltar_login1 div[data-testid="stButton"],
    .st-key-btn_voltar_login2 div[data-testid="stButton"] {
        display: flex !important; justify-content: center !important; width: 100% !important;
    }
    .st-key-btn_logout div[data-testid="stButton"],
    .st-key-btn_historico div[data-testid="stButton"] {
        display: flex !important; justify-content: flex-end !important; width: 100% !important;
    }

    /* Botões secundários: contorno dourado */
    .st-key-btn_toggle_cad button, .st-key-btn_voltar_login1 button, .st-key-btn_voltar_login2 button,
    .st-key-btn_historico button, .st-key-btn_logout button,
    div[class*="st-key-sec_"] button, div[class*="st-key-sug_"] button, div[class*="st-key-nao_"] button {
        background-color: transparent !important;
        color: var(--floresta) !important;
        border: 1px solid var(--filete) !important;
        box-shadow: none !important;
    }
    .st-key-btn_toggle_cad button, .st-key-btn_voltar_login1 button, .st-key-btn_voltar_login2 button {
        width: 260px !important; max-width: 100% !important;
    }
    .st-key-btn_toggle_cad button:hover, .st-key-btn_voltar_login1 button:hover,
    .st-key-btn_voltar_login2 button:hover, .st-key-btn_historico button:hover,
    .st-key-btn_logout button:hover, div[class*="st-key-sec_"] button:hover,
    div[class*="st-key-sug_"] button:hover, div[class*="st-key-nao_"] button:hover {
        background-color: rgba(168,131,74,0.10) !important;
        border-color: var(--ouro) !important;
        color: var(--floresta) !important;
    }
    .st-key-btn_logout button, .st-key-btn_historico button {
        width: auto !important; padding: 0.45rem 1.1rem;
    }

    /* Sugestões do mentor: texto corrido, sem caixa alta */
    div[class*="st-key-sug_"] button {
        text-transform: none !important; letter-spacing: 0.01em !important;
        font-family: 'Cormorant Garamond', serif !important; font-size: 1.05rem !important;
        font-style: italic; font-weight: 600 !important; min-height: 74px; background-color: var(--marfim) !important;
    }
    div[class*="st-key-sug_"] button p {
        font-family: 'Cormorant Garamond', serif !important; font-size: 1.18rem !important; font-weight: 600 !important;
        white-space: normal !important; overflow: visible !important; text-overflow: clip !important;
        line-height: 1.35;
    }

    /* Link 'Esqueci minha senha' */
    .link-esqueci {
        color: #5E5547 !important; font-size: 0.92rem; text-decoration: none !important;
        border-bottom: 1px solid var(--filete); cursor: pointer; transition: color 0.2s ease;
    }
    .link-esqueci:hover { color: var(--floresta) !important; border-color: var(--ouro); }

    /* ---------- Campos ---------- */
    div[data-baseweb="input"], div[data-baseweb="textarea"], div[data-baseweb="select"] > div,
    .stTextInput>div>div>input, .stTextArea>div>div>textarea {
        background-color: var(--marfim) !important;
        border: 1px solid var(--filete) !important;
        border-radius: 1px !important;
        color: var(--tinta);
        font-family: 'Jost', sans-serif;
        font-size: 0.97rem;
    }
    div[data-baseweb="input"] input, div[data-baseweb="textarea"] textarea { background-color: transparent !important; }
    div[data-baseweb="input"]:focus-within, div[data-baseweb="textarea"]:focus-within,
    .stTextInput>div>div>input:focus, .stTextArea>div>div>textarea:focus {
        border-color: var(--ouro) !important;
        box-shadow: 0 0 0 1px var(--ouro) !important;
    }
    div[data-testid="stTextAreaRootElement"], div[data-testid="stTextAreaRootElement"] > div,
    div[data-baseweb="textarea"] > div { background-color: var(--marfim) !important; }

    /* Avisos (info, sucesso, alerta) no tom do papel */
    div[data-testid="stAlert"] > div, div[data-testid="stAlertContainer"] {
        background-color: var(--marfim) !important;
        border: 1px solid var(--filete) !important;
        border-left: 3px solid var(--ouro) !important;
        border-radius: 1px !important;
        color: var(--tinta) !important;
    }
    div[data-testid="stAlert"] p, div[data-testid="stAlertContainer"] p { color: var(--tinta) !important; }
    div[data-testid="stAlertContentError"] p, div[data-testid="stAlertContentWarning"] p { color: var(--vinho) !important; }

    section[data-testid="stFileUploaderDropzone"],
    div[data-testid="stFileUploaderDropzone"] {
        background-color: var(--marfim) !important; border: 1px dashed var(--ouro-claro) !important; border-radius: 1px !important;
    }

    /* ---------- Menu principal e etapas como abas clássicas ---------- */
    .st-key-menu_principal div[role="radiogroup"],
    .st-key-etapa_radio_main div[role="radiogroup"] {
        gap: 0 !important; border-bottom: 1px solid var(--filete); flex-wrap: wrap;
    }
    /* esconde as bolinhas do rádio (versões novas e antigas do Streamlit) */
    .st-key-menu_principal label[data-testid="stRadioOption"] > div > div:first-child:not([data-testid]),
    .st-key-etapa_radio_main label[data-testid="stRadioOption"] > div > div:first-child:not([data-testid]),
    .st-key-menu_principal div[role="radiogroup"] label > div:first-child:not(:has(p)),
    .st-key-etapa_radio_main div[role="radiogroup"] label > div:first-child:not(:has(p)) { display: none !important; }
    .st-key-menu_principal div[role="radiogroup"] label,
    .st-key-etapa_radio_main div[role="radiogroup"] label {
        padding: 0.7rem 1.6rem 0.6rem 1.6rem; margin: 0 !important;
        border-bottom: 2px solid transparent; cursor: pointer; transition: all 0.25s ease;
    }
    .st-key-menu_principal div[role="radiogroup"] label p,
    .st-key-etapa_radio_main div[role="radiogroup"] label p {
        font-family: 'Cinzel', serif !important; letter-spacing: 0.12em; text-transform: uppercase;
        font-size: 0.84rem !important; font-weight: 600 !important; color: var(--sepia);
    }
    .st-key-menu_principal div[role="radiogroup"] label:has(input:checked),
    .st-key-etapa_radio_main div[role="radiogroup"] label:has(input:checked) {
        border-bottom-color: var(--ouro);
        background: linear-gradient(180deg, transparent, rgba(168,131,74,0.08));
    }
    .st-key-menu_principal div[role="radiogroup"] label:has(input:checked) p,
    .st-key-etapa_radio_main div[role="radiogroup"] label:has(input:checked) p { color: var(--floresta); font-weight: 700 !important; }
    .st-key-menu_principal { margin-bottom: 1.6rem; }
    .st-key-menu_principal div[role="radiogroup"] label p { font-size: 0.9rem !important; }
    .st-key-etapa_radio_main { margin-bottom: 1.2rem; }

    /* ---------- Chat ---------- */
    div[data-testid="stChatMessage"] {
        background-color: var(--marfim);
        border: 1px solid rgba(168,131,74,0.22);
        border-radius: 2px;
        padding: 1rem 1.2rem;
    }
    div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) {
        background-color: rgba(35,58,44,0.05);
    }
    div[data-testid="stChatMessage"] img { border-radius: 50%; }
    div[data-testid="stChatInput"] textarea { font-family: 'Jost', sans-serif; }
    div[data-testid="stChatInput"] > div { border-color: var(--filete) !important; border-radius: 2px !important; background: var(--marfim); }

    /* Abas internas (Histórico) e expanders */
    button[data-baseweb="tab"] p { font-family: 'Cinzel', serif !important; font-weight: 600 !important; letter-spacing: 0.08em; font-size: 0.82rem !important; }
    div[data-baseweb="tab-highlight"] { background-color: var(--ouro) !important; }
    div[data-testid="stExpander"] details { border: 1px solid var(--filete); border-radius: 2px; background: var(--marfim); }

    /* Botões de exclusão (discretos, em vinho) */
    div[class*="st-key-exc_"] button {
        background-color: transparent !important; color: var(--vinho) !important;
        border: 1px solid rgba(110,42,38,0.35) !important; box-shadow: none !important;
    }
    div[class*="st-key-exc_"] button:hover { background-color: rgba(110,42,38,0.07) !important; }
    div[class*="st-key-sim_"] button {
        background-color: var(--vinho) !important; color: #FFF8E7 !important;
        border: 1px solid var(--vinho) !important; box-shadow: none !important;
    }
    div[class*="st-key-sim_"] button:hover { background-color: #571F1C !important; }

    .ident-conectado { text-align: right; padding-top: 0.8rem; margin-bottom: 0.4rem; }
    .ident-conectado .nome { font-family: 'Cormorant Garamond', serif; font-size: 1.45rem; font-weight: 600; font-style: italic; color: var(--floresta); }

    /* ===== Celular / tablet ===== */
    @media (max-width: 768px) {
        .stTextInput input, .stTextArea textarea { font-size: 16px !important; }
    }
    @media (max-width: 640px) {
        .block-container { padding: 2.5rem 1rem 5rem 1rem !important; }
        h3 { font-size: 1.6rem !important; }
        .titulo-login { font-size: 2.6rem !important; }
        .kicker { letter-spacing: 0.16em !important; font-size: 0.68rem !important; }
        .titulo-app { font-size: 2rem !important; }
        .subtitulo-app { font-size: 0.85rem !important; }
        .ident-conectado { text-align: left !important; padding-top: 0.4rem !important; }
        .st-key-btn_logout div[data-testid="stButton"],
        .st-key-btn_historico div[data-testid="stButton"] { justify-content: flex-start !important; }
        .stButton>button { min-height: 46px; }
        .st-key-menu_principal div[role="radiogroup"] label,
        .st-key-etapa_radio_main div[role="radiogroup"] label { padding: 0.6rem 0.8rem; }
        .st-key-menu_principal div[role="radiogroup"] label p,
        .st-key-etapa_radio_main div[role="radiogroup"] label p { font-size: 0.72rem !important; letter-spacing: 0.06em; }
    }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# ============================================================
# UTILITÁRIOS
# ============================================================
def extrair_texto_curriculo(uploaded_file):
    if not uploaded_file:
        return ""
    nome = uploaded_file.name.lower()
    texto = ""
    try:
        if nome.endswith(".pdf") and PdfReader:
            reader = PdfReader(uploaded_file)
            for page in reader.pages:
                texto += page.extract_text() or ""
        elif nome.endswith(".docx") and Document:
            doc = Document(uploaded_file)
            for p in doc.paragraphs:
                texto += p.text + "\n"
        elif nome.endswith(".txt"):
            texto = uploaded_file.read().decode("utf-8", errors="ignore")
    except Exception as e:
        st.error(f"Erro ao ler arquivo do currículo: {e}")
    return texto


def novo_id():
    return uuid.uuid4().hex[:10]


def agora_str():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return datetime.now().strftime("%d/%m/%Y %H:%M")


@st.cache_data
def logo_base64():
    try:
        caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icone.png")
        with open(caminho, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return ""


def logo_html(tamanho):
    """Logo circular discreta; se o arquivo não existir, não mostra nada."""
    b64 = logo_base64()
    if not b64:
        return ""
    return (
        f'<img src="data:image/png;base64,{b64}" '
        f'style="width:{tamanho}px;height:{tamanho}px;border-radius:50%;'
        f'box-shadow:0 2px 12px rgba(120,100,90,0.18);opacity:0.95;">'
    )


def avatar_ia():
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icone.png")
    return caminho if os.path.exists(caminho) else None


def ornamento(simbolo="✦ ✦ ✦"):
    return f'<div class="ornamento"><span>{simbolo}</span></div>'


def cabecalho_secao(kicker, titulo, intro):
    st.markdown(
        f'<p class="kicker">{kicker}</p><h3 style="margin-top:0.2rem;">{titulo}</h3>'
        f'<p class="intro-secao">{intro}</p>',
        unsafe_allow_html=True,
    )


def parecer_com_pergunta(pergunta, texto):
    """Garante que o parecer exibido comece com a pergunta (inclusive pareceres antigos)."""
    texto = texto or ""
    if texto.lstrip().startswith("**Pergunta:**") or not pergunta:
        return texto
    return f"**Pergunta:** {pergunta}\n\n---\n\n{texto}"


# ============================================================
# CONEXÃO COM SUPABASE & BANCO DE DADOS (COM SUPABASE AUTH + RLS)
# ============================================================
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_KEY") or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        st.error("Credenciais do Supabase não configuradas nos Secrets.")
        st.stop()
    return create_client(url, key)


supabase = init_supabase()

# Restaura a sessão autenticada do usuário a cada rerun para satisfazer o RLS
session_tokens = st.session_state.get("_sb_tokens")
if session_tokens:
    try:
        supabase.auth.set_session(session_tokens["access_token"], session_tokens["refresh_token"])
    except Exception:
        pass


def buscar_usuario(email):
    try:
        res = supabase.table("usuarios").select("*").eq("email", email).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None


def fazer_login_supabase(email, senha):
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": senha})
        if res.user and res.session:
            st.session_state["_sb_tokens"] = {
                "access_token": res.session.access_token,
                "refresh_token": res.session.refresh_token
            }
            return True
    except Exception:
        pass
    return False


def criar_usuario(nome, email, senha):
    # 1. Cria a conta no Supabase Auth (gera o token JWT para o RLS)
    res = supabase.auth.sign_up({"email": email, "password": senha})
    if res.user:
        if res.session:
            st.session_state["_sb_tokens"] = {
                "access_token": res.session.access_token,
                "refresh_token": res.session.refresh_token
            }
            supabase.auth.set_session(res.session.access_token, res.session.refresh_token)
        # 2. Insere o perfil na tabela 'usuarios'
        data = {
            "email": email,
            "nome": nome,
            "contexto_vaga": {},
            "avaliacoes": [],
            "mensagens_chat": []
        }
        return supabase.table("usuarios").insert(data).execute()
    return None


def enviar_recuperacao_senha(email):
    return supabase.auth.reset_password_for_email(email)


# ============================================================
# HISTÓRICO (Etapa 1 > Etapa 2 / Etapa 3)
# ============================================================
def vaga_ativa():
    ss = st.session_state
    for v in ss.get("historico", []):
        if v["id"] == ss.get("vaga_ativa_id"):
            return v
    return None


def limpar_vaga_ativa():
    ss = st.session_state
    ss["vaga_ativa_id"] = None
    ss["contexto_vaga"] = {}
    ss["etapa1_concluida"] = False
    ss["etapa2_concluida"] = False
    ss["ultima_pergunta"] = ""
    ss["ultima_avaliacao"] = ""
    ss["ultima_avaliacao_id"] = None
    ss["conversa_ativa_id"] = None
    ss["mensagens_chat"] = []


def definir_vaga_ativa(vaga_id):
    ss = st.session_state
    vaga = next((v for v in ss.get("historico", []) if v["id"] == vaga_id), None)
    if vaga is None:
        limpar_vaga_ativa()
        return
    ss["vaga_ativa_id"] = vaga["id"]
    ss["contexto_vaga"] = dict(vaga["contexto"])
    ss["etapa1_concluida"] = True
    ss["etapa2_concluida"] = bool(vaga["avaliacoes"])
    ultima = vaga["avaliacoes"][-1] if vaga["avaliacoes"] else None
    ss["ultima_pergunta"] = ultima["pergunta"] if ultima else ""
    ss["ultima_avaliacao"] = ultima["avaliacao"] if ultima else ""
    ss["ultima_avaliacao_id"] = ultima["id"] if ultima else None
    conv = vaga["conversas"][-1] if vaga["conversas"] else None
    ss["conversa_ativa_id"] = conv["id"] if conv else None
    ss["mensagens_chat"] = list(conv["mensagens"]) if conv else []


def carregar_sessao(user, email):
    """Carrega os dados do usuário (migrando dados antigos para o novo formato)."""
    ss = st.session_state
    ctx = dict(user.get("contexto_vaga") or {})
    historico = ctx.pop("_historico", None)
    ativa = ctx.pop("_vaga_ativa", None)
    ss["chat_livre"] = list(ctx.pop("_chat_livre", None) or [])

    if historico is None:
        historico = []
        avs_db = user.get("avaliacoes") or []
        msgs_db = user.get("mensagens_chat") or []
        if ctx.get("empresa"):
            vaga = {"id": novo_id(), "data": "Anterior", "contexto": ctx, "avaliacoes": [], "conversas": []}
            for a in avs_db:
                vaga["avaliacoes"].append({
                    "id": novo_id(), "data": "Anterior",
                    "pergunta": a.get("pergunta", ""), "resposta": "",
                    "avaliacao": a.get("avaliacao", "")
                })
            if msgs_db:
                ult = vaga["avaliacoes"][-1] if vaga["avaliacoes"] else None
                vaga["conversas"].append({
                    "id": novo_id(),
                    "avaliacao_id": ult["id"] if ult else None,
                    "pergunta": ult["pergunta"] if ult else "Conversa anterior",
                    "data": "Anterior", "mensagens": msgs_db
                })
            historico.append(vaga)
            ativa = vaga["id"]

    ss["usuario_logado"] = email
    ss["usuario_nome"] = user["nome"]
    ss["historico"] = historico
    ids = [v["id"] for v in historico]
    if ativa not in ids:
        ativa = ids[-1] if ids else None
    if ativa:
        definir_vaga_ativa(ativa)
    else:
        limpar_vaga_ativa()
    ss["etapa_radio_main"] = ETAPA_1
    ss["menu_principal"] = MENU_MENTOR


def salvar_progresso_banco(email):
    ss = st.session_state
    ctx = dict(ss.get("contexto_vaga", {}))
    ctx["_historico"] = ss.get("historico", [])
    ctx["_vaga_ativa"] = ss.get("vaga_ativa_id")
    ctx["_chat_livre"] = ss.get("chat_livre", [])[-80:]  # conversa do Mentor (últimas 80 mensagens)
    vaga = vaga_ativa()
    dados = {
        "contexto_vaga": ctx,
        "avaliacoes": vaga["avaliacoes"] if vaga else [],
        "mensagens_chat": ss.get("mensagens_chat", [])
    }
    try:
        supabase.table("usuarios").update(dados).eq("email", email).execute()
    except Exception as e:
        st.warning(f"Não foi possível salvar seu progresso agora: {e}")


def sincronizar_conversa():
    """Grava as mensagens do chat atual na conversa (Etapa 3) da vaga ativa."""
    ss = st.session_state
    vaga = vaga_ativa()
    if vaga is None:
        return
    conv = next((c for c in vaga["conversas"] if c["id"] == ss.get("conversa_ativa_id")), None)
    if conv is None:
        conv = {
            "id": novo_id(),
            "avaliacao_id": ss.get("ultima_avaliacao_id"),
            "pergunta": ss.get("ultima_pergunta") or "Conversa",
            "data": agora_str(),
            "mensagens": []
        }
        vaga["conversas"].append(conv)
        ss["conversa_ativa_id"] = conv["id"]
    conv["mensagens"] = list(ss.get("mensagens_chat", []))


def ir_para_etapa(nome_etapa):
    """Agenda a troca de etapa; é aplicada no próximo rerun, antes do radio ser criado."""
    st.session_state["_ir_para_etapa"] = nome_etapa
    st.session_state["_ir_para_menu"] = MENU_TREINO
    st.rerun()


def retomar_conversa(vaga_id, conv_id):
    ss = st.session_state
    definir_vaga_ativa(vaga_id)
    vaga = vaga_ativa()
    conv = next((c for c in vaga["conversas"] if c["id"] == conv_id), None)
    if conv:
        ss["conversa_ativa_id"] = conv["id"]
        ss["mensagens_chat"] = list(conv["mensagens"])
        aval = next((a for a in vaga["avaliacoes"] if a["id"] == conv.get("avaliacao_id")), None)
        if aval:
            ss["ultima_pergunta"] = aval["pergunta"]
            ss["ultima_avaliacao"] = aval["avaliacao"]
            ss["ultima_avaliacao_id"] = aval["id"]
    salvar_progresso_banco(ss["usuario_logado"])
    ir_para_etapa(ETAPA_3)


def excluir_vaga(vaga_id):
    ss = st.session_state
    ss["historico"] = [v for v in ss.get("historico", []) if v["id"] != vaga_id]
    era_ativa = ss.get("vaga_ativa_id") == vaga_id
    if era_ativa:
        restante = ss["historico"]
        if restante:
            definir_vaga_ativa(restante[-1]["id"])
        else:
            limpar_vaga_ativa()
    ss.pop("hist_vaga_sel", None)
    salvar_progresso_banco(ss["usuario_logado"])
    return era_ativa


def excluir_avaliacao(vaga_id, aval_id):
    ss = st.session_state
    vaga = next((v for v in ss.get("historico", []) if v["id"] == vaga_id), None)
    if vaga is None:
        return False
    vaga["avaliacoes"] = [a for a in vaga["avaliacoes"] if a["id"] != aval_id]
    afeta = False
    if ss.get("vaga_ativa_id") == vaga_id:
        ss["etapa2_concluida"] = bool(vaga["avaliacoes"])
        if ss.get("ultima_avaliacao_id") == aval_id:
            ult = vaga["avaliacoes"][-1] if vaga["avaliacoes"] else None
            ss["ultima_pergunta"] = ult["pergunta"] if ult else ""
            ss["ultima_avaliacao"] = ult["avaliacao"] if ult else ""
            ss["ultima_avaliacao_id"] = ult["id"] if ult else None
            ss["conversa_ativa_id"] = None
            ss["mensagens_chat"] = []
            afeta = True
    salvar_progresso_banco(ss["usuario_logado"])
    return afeta


def excluir_conversa(vaga_id, conv_id):
    ss = st.session_state
    vaga = next((v for v in ss.get("historico", []) if v["id"] == vaga_id), None)
    if vaga is None:
        return False
    vaga["conversas"] = [c for c in vaga["conversas"] if c["id"] != conv_id]
    afeta = ss.get("vaga_ativa_id") == vaga_id and ss.get("conversa_ativa_id") == conv_id
    if afeta:
        ss["conversa_ativa_id"] = None
        ss["mensagens_chat"] = []
    salvar_progresso_banco(ss["usuario_logado"])
    return afeta


def botao_excluir(chave, aviso, acao):
    """Exclusão em dois passos (Excluir -> Sim, excluir / Cancelar). Use só dentro do diálogo."""
    ss = st.session_state
    if ss.get("_exc_pendente") == chave:
        st.warning(aviso)
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Sim, excluir", key=f"sim_{chave}"):
                afeta = acao()
                ss["_exc_pendente"] = None
                if afeta:
                    st.rerun()  # muda algo na tela principal: fecha o histórico e atualiza
                else:
                    st.rerun(scope="fragment")  # mantém o histórico aberto
        with c2:
            if st.button("Cancelar", key=f"nao_{chave}"):
                ss["_exc_pendente"] = None
                st.rerun(scope="fragment")
    else:
        if st.button("Excluir", key=f"exc_{chave}"):
            ss["_exc_pendente"] = chave
            st.rerun(scope="fragment")


@st.dialog("Histórico", width="large")
def dialog_historico():
    historico = st.session_state.get("historico", [])
    if not historico:
        st.info("Seu histórico aparecerá aqui assim que você salvar a primeira vaga na Etapa 1.")
        return

    mapa = {v["id"]: v for v in historico}
    ids = [v["id"] for v in reversed(historico)]
    ativa = st.session_state.get("vaga_ativa_id")

    def rotulo(i):
        c = mapa[i]["contexto"]
        txt = f"{c.get('empresa', '?')} — {c.get('cargo', '?')} · {mapa[i].get('data', '')}"
        return txt + ("  (ativa)" if i == ativa else "")

    idx = ids.index(ativa) if ativa in ids else 0
    escolhido = st.selectbox("Vaga (histórico da Etapa 1)", ids, index=idx, format_func=rotulo, key="hist_vaga_sel")
    vaga = mapa[escolhido]

    avs = vaga["avaliacoes"]
    convs = [c for c in vaga["conversas"] if c.get("mensagens")]

    tab1, tab2, tab3 = st.tabs([
        "Etapa 1 — Contexto",
        f"Etapa 2 — Pareceres ({len(avs)})",
        f"Etapa 3 — Conversas ({len(convs)})",
    ])

    with tab1:
        c = vaga["contexto"]
        st.markdown(f"**Empresa:** {c.get('empresa', '')}")
        st.markdown(f"**Cargo:** {c.get('cargo', '')}")
        if c.get("linkedin"):
            st.markdown(f"**LinkedIn:** {c['linkedin']}")
        st.markdown("**Descrição & requisitos da vaga**")
        st.write(c.get("descricao", ""))
        if c.get("sobre_empresa"):
            st.markdown("**Sobre a empresa & cultura**")
            st.write(c["sobre_empresa"])
        if escolhido != ativa:
            if st.button("Usar esta vaga e ir para a Etapa 2", key=f"usar_{escolhido}"):
                definir_vaga_ativa(escolhido)
                salvar_progresso_banco(st.session_state["usuario_logado"])
                ir_para_etapa(ETAPA_2)
        else:
            st.caption("Esta é a vaga ativa no momento.")
        botao_excluir(
            f"vaga_{escolhido}",
            "Excluir esta vaga apaga também todos os pareceres e conversas dela. Essa ação não pode ser desfeita.",
            lambda: excluir_vaga(escolhido),
        )

    with tab2:
        if not avs:
            st.caption("Nenhum parecer gerado para esta vaga ainda.")
        for a in reversed(avs):
            with st.expander(f"{a.get('data', '')} · {a.get('pergunta', '')[:80]}"):
                if a.get("resposta"):
                    st.markdown("**Sua resposta**")
                    st.write(a["resposta"])
                st.markdown("**Parecer**")
                st.markdown(parecer_com_pergunta(a.get("pergunta"), a.get("avaliacao", "")))
                botao_excluir(
                    f"aval_{a['id']}",
                    "Excluir este parecer? Essa ação não pode ser desfeita.",
                    lambda aid=a["id"]: excluir_avaliacao(escolhido, aid),
                )

    with tab3:
        if not convs:
            st.caption("Nenhuma conversa com o mentor para esta vaga ainda.")
        for cv in reversed(convs):
            n = len(cv["mensagens"])
            with st.expander(f"{cv.get('data', '')} · {cv.get('pergunta', '')[:80]} ({n} msgs)"):
                for m in cv["mensagens"]:
                    with st.chat_message(m["role"]):
                        st.markdown(m["content"])
                if st.button("Retomar esta conversa", key=f"ret_{cv['id']}"):
                    retomar_conversa(escolhido, cv["id"])
                botao_excluir(
                    f"conv_{cv['id']}",
                    "Excluir esta conversa? Essa ação não pode ser desfeita.",
                    lambda cid=cv["id"]: excluir_conversa(escolhido, cid),
                )


# ============================================================
# TELA DE AUTENTICAÇÃO
# ============================================================
if "usuario_logado" not in st.session_state:
    st.session_state["usuario_logado"] = None

if "auth_mode" not in st.session_state:
    st.session_state["auth_mode"] = "login"

if not st.session_state["usuario_logado"]:
    st.markdown(f"""
    <div style="text-align: center; padding: 2rem 0 1.5rem 0;">
        <div style="margin-bottom: 1.1rem;">{logo_html(88)}</div>
        <p class="kicker">Atelier de Entrevistas · Est. MMXXVI</p>
        <h1 class="titulo-login" style="font-size: 4rem; font-style: italic; font-weight: 600 !important; margin: 0.3rem 0 0 0; line-height: 1.05;">Interview Lab AI</h1>
        <p style="font-family: 'Cormorant Garamond', serif; font-size: 1.4rem; font-weight: 500; font-style: italic; color: #6E6352; margin-top: 0.4rem;">A arte de contar a sua trajetória</p>
        <div style="max-width: 320px; margin: 0 auto;">{ornamento()}</div>
    </div>
    """, unsafe_allow_html=True)

    col_centered = st.columns([1, 1.2, 1])[1]
    with col_centered:

        # MODO 1: LOGIN
        if st.session_state["auth_mode"] == "login":
            email = st.text_input("E-mail profissional", key="login_email")
            senha = st.text_input("Senha", type="password", key="login_senha")

            st.write("")
            if st.button("Entrar na Conta ➔", key="btn_login"):
                if fazer_login_supabase(email, senha):
                    user = buscar_usuario(email)
                    if user:
                        carregar_sessao(user, email)
                        st.rerun()
                    else:
                        st.error("Perfil de usuário não encontrado na base.")
                else:
                    st.error("E-mail ou senha incorretos.")

            st.markdown("""
            <div style="text-align: center; margin-top: 0.8rem;">
                <a href="?recuperar=true" target="_self" class="link-esqueci">Esqueci minha senha</a>
            </div>
            """, unsafe_allow_html=True)

            if st.query_params.get("recuperar") == "true":
                st.query_params.clear()
                st.session_state["auth_mode"] = "recuperar"
                st.rerun()

            st.markdown("""
            <div style="margin: 2rem 0 0.5rem 0; text-align: center;">
                <hr style="border: none; border-top: 1px solid rgba(168,131,74,0.38); margin-bottom: 1.5rem;">
                <p style="font-size: 0.95rem; color: #6E6352; margin-bottom: 0.5rem;">Ainda não possui um acesso?</p>
            </div>
            """, unsafe_allow_html=True)

            if st.button("Criar nova conta", key="btn_toggle_cad"):
                st.session_state["auth_mode"] = "cadastro"
                st.rerun()

        # MODO 2: CRIAR CONTA
        elif st.session_state["auth_mode"] == "cadastro":
            st.markdown("<h3 style='text-align: center; margin-bottom: 1.5rem; font-size: 1.6rem;'>Criar nova conta</h3>", unsafe_allow_html=True)
            novo_nome = st.text_input("Nome completo", key="cad_nome")
            novo_email = st.text_input("E-mail profissional", key="cad_email")
            nova_senha = st.text_input("Defina uma senha (mín. 6 caracteres)", type="password", key="cad_senha")

            st.write("")
            if st.button("Finalizar Cadastro e Acessar ➔", key="btn_cadastrar"):
                if novo_email and nova_senha and novo_nome:
                    if len(nova_senha) < 6:
                        st.warning("A senha deve ter pelo menos 6 caracteres.")
                    else:
                        try:
                            criar_usuario(novo_nome, novo_email, nova_senha)
                            st.session_state["usuario_logado"] = novo_email
                            st.session_state["usuario_nome"] = novo_nome
                            st.session_state["historico"] = []
                            st.session_state["chat_livre"] = []
                            limpar_vaga_ativa()
                            st.session_state["etapa_radio_main"] = ETAPA_1
                            st.rerun()
                        except Exception as e:
                            st.warning(f"Não foi possível criar a conta (verifique se o e-mail já existe): {e}")
                else:
                    st.warning("Preencha todos os campos obrigatórios.")

            st.write("")
            if st.button("Voltar ao Login", key="btn_voltar_login1"):
                st.session_state["auth_mode"] = "login"
                st.rerun()

        # MODO 3: REDEFINIR SENHA
        elif st.session_state["auth_mode"] == "recuperar":
            st.markdown("<h3 style='text-align: center; margin-bottom: 0.5rem; font-size: 1.5rem;'>Recuperar Senha</h3>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; font-size: 0.88rem; color: #7A6F5E; margin-bottom: 1.5rem;'>Informe seu e-mail cadastrado para receber o link de redefinição.</p>", unsafe_allow_html=True)

            email_recup = st.text_input("E-mail cadastrado", key="recup_email")

            st.write("")
            if st.button("Enviar Link de Recuperação ➔", key="btn_confirmar_recup"):
                if not email_recup:
                    st.warning("Informe seu e-mail.")
                else:
                    try:
                        enviar_recuperacao_senha(email_recup)
                        st.success("Se o e-mail estiver cadastrado, enviamos um link de redefinição para sua caixa de entrada.")
                    except Exception as e:
                        st.error(f"Erro ao solicitar recuperação: {e}")

            st.write("")
            if st.button("Voltar ao Login", key="btn_voltar_login2"):
                st.session_state["auth_mode"] = "login"
                st.rerun()

    st.stop()

# ============================================================
# CABEÇALHO & IDENTIDADE LOGADA
# ============================================================
col_head1, col_head2 = st.columns([4, 1.4])
with col_head1:
    st.markdown(f"""
    <div style="display: flex; align-items: center; flex-wrap: wrap; gap: 16px; padding: 0.5rem 0 0.2rem 0;">
        {logo_html(72)}
        <div>
            <p class="kicker">Atelier de Entrevistas</p>
            <h1 class="titulo-app" style="font-size: 2.7rem; font-style: italic; font-weight: 600 !important; margin: 0; line-height: 1.1;">Interview Lab AI</h1>
            <p class="subtitulo-app" style="color: #7A6F5E; font-size: 1.25rem; font-weight: 500; margin-top: 0; font-family: 'Cormorant Garamond', serif; font-style: italic;">Simulação e lapidação narrativa para entrevistas</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
with col_head2:
    st.markdown(
        f"<div class='ident-conectado'>"
        f"<span class='kicker' style='font-size:0.68rem;'>Bem-vindo(a)</span><br>"
        f"<span class='nome'>{st.session_state.get('usuario_nome', 'Candidato')}</span></div>",
        unsafe_allow_html=True
    )
    if st.button("Sair da Sessão", key="btn_logout"):
        try:
            supabase.auth.sign_out()
        except Exception:
            pass
        st.session_state.clear()
        st.rerun()
    if st.button("Histórico", key="btn_historico"):
        st.session_state["_exc_pendente"] = None
        dialog_historico()

st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)

# Validação do Cliente Gemini
api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not api_key:
    st.warning("Chave GEMINI_API_KEY não configurada nos Secrets.")
    st.stop()

client = get_client(api_key)


# ============================================================
# MENU PRINCIPAL: MENTOR (conversa livre) | TREINADOR (etapas)
# ============================================================
ss = st.session_state
ss.setdefault("chat_livre", [])
destino_menu = ss.pop("_ir_para_menu", None)
if destino_menu in ROTULOS_MENU:
    ss["menu_principal"] = destino_menu
if ss.get("menu_principal") not in ROTULOS_MENU:
    ss["menu_principal"] = MENU_MENTOR

menu_atual = st.radio(
    "Menu",
    options=list(ROTULOS_MENU),
    format_func=lambda m: ROTULOS_MENU[m],
    horizontal=True,
    key="menu_principal",
    label_visibility="collapsed",
)


def levar_para_treinador(texto, pergunta):
    """Guarda o rascunho e abre o Treinador (Etapa 2, ou Etapa 1 se ainda não há vaga)."""
    ss["_rascunho_e2"] = texto
    ss["_pergunta_e2"] = pergunta
    ir_para_etapa(ETAPA_2 if ss.get("etapa1_concluida") else ETAPA_1)


if menu_atual == MENU_MENTOR:
    cabecalho_secao(
        "Antes do treino",
        "O Mentor",
        "Ainda não tem uma resposta pronta? Converse à vontade: o mentor faz perguntas sobre a sua "
        "trajetória, encontra os melhores exemplos e monta a resposta com você. Quando ela estiver "
        "pronta, leve-a ao Treinador para receber o parecer técnico.",
    )

    vaga = vaga_ativa()
    col_a, col_b = st.columns([1.6, 1], gap="medium")
    with col_a:
        opcoes_foco = [PERGUNTA_LIVRE] + list(PERGUNTAS_CURATORIA.keys())
        foco = st.selectbox("Pergunta que você quer preparar", opcoes_foco, key="mentor_pergunta")
    with col_b:
        usar_vaga = False
        if vaga:
            st.markdown("<div style='height:1.9rem'></div>", unsafe_allow_html=True)
            c = vaga["contexto"]
            usar_vaga = st.checkbox(
                f"Considerar a vaga {c.get('empresa', '')} — {c.get('cargo', '')}",
                value=True, key="mentor_usar_vaga",
            )
        else:
            st.caption("Dica: cadastrando a vaga na Etapa 1 do Treinador, o mentor personaliza as sugestões.")
    pergunta_foco = None if foco == PERGUNTA_LIVRE else foco

    st.markdown(ornamento("❦"), unsafe_allow_html=True)

    mensagens = ss["chat_livre"]
    prompt = None

    if not mensagens:
        st.markdown(
            "<p style='text-align:center; font-family:Cormorant Garamond, serif; font-size:1.4rem; font-weight:500; "
            "font-style:italic; color:#7A6F5E; margin-bottom:1rem;'>Por onde gostaria de começar?</p>",
            unsafe_allow_html=True,
        )
        cols = st.columns(len(SUGESTOES_MENTOR), gap="small")
        for i, (col, sug) in enumerate(zip(cols, SUGESTOES_MENTOR)):
            with col:
                if st.button(sug, key=f"sug_{i}"):
                    prompt = sug

    for msg in mensagens:
        avatar = avatar_ia() if msg["role"] == "assistant" else None
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])

    digitado = st.chat_input("Conte ao mentor sobre uma experiência, uma dúvida ou a vaga que você quer...", key="mentor_input")
    prompt = digitado or prompt

    if prompt:
        mensagens.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant", avatar=avatar_ia()):
            resposta = st.write_stream(stream_chat_mentor(
                client=client,
                historico_mensagens=mensagens,
                contexto_vaga=vaga["contexto"] if (vaga and usar_vaga) else None,
                pergunta_foco=pergunta_foco,
            ))
        if resposta_falhou(resposta):
            mensagens.pop()  # não salva a falha; dá para tentar de novo
        else:
            mensagens.append({"role": "assistant", "content": str(resposta)})
            salvar_progresso_banco(ss["usuario_logado"])
            st.rerun()

    if any(m["role"] == "assistant" for m in mensagens):
        ultima_ia = next(m["content"] for m in reversed(mensagens) if m["role"] == "assistant")
        pronta = extrair_resposta_pronta(ultima_ia)
        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
        with st.container(border=True, key="moldura_1"):
            st.markdown("<p class='kicker'>Do rascunho ao treino</p><h4 style='margin-top:0.2rem;'>Levar para o Treinador</h4>", unsafe_allow_html=True)
            if pronta:
                st.caption("O mentor montou a resposta abaixo. Ajuste o que quiser antes de levar.")
            else:
                st.caption("Quando o mentor entregar a resposta pronta, ela aparece aqui. Você também pode escrever ou colar a sua.")
            rascunho = st.text_area(
                "Sua resposta", value=pronta, height=200,
                key=f"rascunho_mentor_{len(mensagens)}", label_visibility="collapsed",
            )
            c1, c2 = st.columns([1.4, 1], gap="small")
            with c1:
                if st.button("Levar para o Treinador ➔", key="btn_levar_treino"):
                    if not rascunho.strip():
                        st.warning("Escreva ou peça ao mentor uma resposta antes de levar ao Treinador.")
                    else:
                        levar_para_treinador(rascunho.strip(), pergunta_foco)
            with c2:
                if st.button("Nova conversa", key="sec_nova_conversa"):
                    ss["chat_livre"] = []
                    salvar_progresso_banco(ss["usuario_logado"])
                    st.rerun()

    st.stop()

# ============================================================
# GERENCIAMENTO DAS ETAPAS (navegação automática)
# ============================================================
etapas_lista = [ETAPA_1]
if st.session_state.get("etapa1_concluida"):
    etapas_lista.append(ETAPA_2)
if st.session_state.get("etapa2_concluida"):
    etapas_lista.append(ETAPA_3)

destino = st.session_state.pop("_ir_para_etapa", None)
if destino in etapas_lista:
    st.session_state["etapa_radio_main"] = destino

if st.session_state.get("etapa_radio_main") not in etapas_lista:
    st.session_state["etapa_radio_main"] = etapas_lista[0]

etapa_atual = st.radio(
    "Navegação por Etapas:",
    options=etapas_lista,
    horizontal=True,
    key="etapa_radio_main"
)

# ============================================================
# ETAPA 1 — CONTEXTO DA VAGA
# ============================================================
if etapa_atual == ETAPA_1:
    cabecalho_secao("Etapa I", "Contexto da Vaga & Perfil",
                    "Insira os detalhes estratégicos do cargo pretendido. A IA utilizará esses dados para personalizar a avaliação.")
    if st.session_state.get("_rascunho_e2"):
        st.info("A resposta que você montou com o Mentor está guardada. Cadastre a vaga e ela aparecerá na Etapa 2, pronta para avaliar.")

    ctx = st.session_state.get("contexto_vaga", {})

    col1, col2 = st.columns(2, gap="medium")
    with col1:
        empresa = st.text_input("Empresa Alvo", value=ctx.get("empresa", ""), placeholder="Ex: Google, Itaú, Ambev...")
        linkedin = st.text_input("Perfil do LinkedIn (Opcional)", value=ctx.get("linkedin", ""), placeholder="https://linkedin.com/in/seu-perfil")
    with col2:
        cargo = st.text_input("Cargo Desejado", value=ctx.get("cargo", ""), placeholder="Ex: Gerente de Produto, Tech Lead...")
        curriculo_file = st.file_uploader("Upload de Currículo (PDF, DOCX)", type=["pdf", "docx", "txt"])

    descricao = st.text_area("Descrição & Requisitos da Vaga", value=ctx.get("descricao", ""), height=120, placeholder="Cole aqui os principais requisitos e responsabilidades do anúncio...")
    sobre_empresa = st.text_area("Sobre a Empresa & Cultura (Opcional)", value=ctx.get("sobre_empresa", ""), height=90, placeholder="Valores, momento de mercado, novos projetos...")

    if st.button("Salvar Contexto e Avançar para Etapa 2 ➔", key="btn_salvar_e1"):
        if not empresa or not cargo or not descricao:
            st.warning("Preencha pelo menos a Empresa, Cargo e Descrição da Vaga.")
        else:
            curriculo_texto = extrair_texto_curriculo(curriculo_file) if curriculo_file else ctx.get("curriculo_texto", "")
            novo_ctx = {
                "empresa": empresa,
                "cargo": cargo,
                "descricao": descricao,
                "sobre_empresa": sobre_empresa,
                "linkedin": linkedin,
                "curriculo_texto": curriculo_texto
            }

            vaga = vaga_ativa()
            mesma_vaga = (
                vaga is not None
                and vaga["contexto"].get("empresa", "").strip().lower() == empresa.strip().lower()
                and vaga["contexto"].get("cargo", "").strip().lower() == cargo.strip().lower()
            )
            if mesma_vaga:
                # Mesma empresa e cargo: só atualiza os dados (mantém pareceres e conversas)
                vaga["contexto"] = novo_ctx
                st.session_state["contexto_vaga"] = novo_ctx
            else:
                # Vaga nova: cria um novo registro no histórico
                nova = {"id": novo_id(), "data": agora_str(), "contexto": novo_ctx, "avaliacoes": [], "conversas": []}
                st.session_state.setdefault("historico", []).append(nova)
                definir_vaga_ativa(nova["id"])

            salvar_progresso_banco(st.session_state["usuario_logado"])
            ir_para_etapa(ETAPA_2)

# ============================================================
# ETAPA 2 — PAINEL DE SIMULAÇÃO
# ============================================================
elif etapa_atual == ETAPA_2:
    col_nav1, _ = st.columns([1.5, 4])
    with col_nav1:
        if st.button("⬅ Voltar para Contexto da Vaga", key="btn_voltar_e1"):
            ir_para_etapa(ETAPA_1)

    cabecalho_secao("Etapa II", "Simulação & Avaliação Técnica",
                    "Selecione uma pergunta técnica ou comportamental e responda via texto ou áudio.")

    lista_perguntas = list(PERGUNTAS_CURATORIA.keys())

    # Rascunho vindo do Mentor: preenche a resposta (e a pergunta, se foi escolhida lá)
    rascunho_mentor = st.session_state.pop("_rascunho_e2", None)
    pergunta_mentor = st.session_state.pop("_pergunta_e2", None)
    if rascunho_mentor:
        st.session_state["resp_texto_e2"] = rascunho_mentor
        st.session_state["tipo_resp_radio"] = "Texto"
        if pergunta_mentor in lista_perguntas:
            st.session_state["pergunta_e2"] = pergunta_mentor
        st.success("Resposta trazida do Mentor. Confira a pergunta selecionada e clique em Enviar e Avaliar.")

    pergunta_selecionada = st.selectbox("Escolha a Pergunta para Simular:", options=lista_perguntas, key="pergunta_e2")
    dados_pergunta = PERGUNTAS_CURATORIA[pergunta_selecionada]

    st.markdown(f"""
    <div class="cartao-metodo">
        <span class="rot">METODOLOGIA SUGERIDA</span><br><span class="txt">{dados_pergunta['tecnica']}</span>
        <div style="height:0.6rem"></div>
        <span class="rot">FOCO DO AVALIADOR</span><br><span class="txt">{dados_pergunta['expectativa']}</span>
    </div>
    """, unsafe_allow_html=True)

    tipo_resposta = st.radio("Formato da Resposta:", ["Texto", "Áudio"], horizontal=True, key="tipo_resp_radio")

    resposta_texto = None
    audio_bytes = None

    if tipo_resposta == "Texto":
        resposta_texto = st.text_area("Sua Resposta:", placeholder="Desenvolva sua resposta utilizando a técnica sugerida...", height=180, key="resp_texto_e2")
    else:
        audio_input = st.audio_input("Gravador de voz")
        if audio_input:
            audio_bytes = audio_input.read()

    if st.button("Enviar e Avaliar ➔", key="btn_avaliar_e2"):
        if not resposta_texto and not audio_bytes:
            st.warning("Por favor, forneça uma resposta em texto ou grave um áudio.")
        else:
            with st.spinner("Analisando alinhamento estratégico"):
                resultado = avaliar_resposta_completa(
                    client=client,
                    contexto=st.session_state.get("contexto_vaga", {}),
                    pergunta=pergunta_selecionada,
                    dados_pergunta=dados_pergunta,
                    resposta_texto=resposta_texto,
                    audio_bytes=audio_bytes
                )

            if resultado.startswith("Não foi possível obter resposta"):
                # Falhas não entram no histórico
                st.error(resultado)
            else:
                # A pergunta vai dentro do parecer (de propósito), para copiar/imprimir completo
                resultado = f"**Pergunta:** {pergunta_selecionada}\n\n---\n\n{resultado}"

                vaga = vaga_ativa()
                aval = {
                    "id": novo_id(),
                    "data": agora_str(),
                    "pergunta": pergunta_selecionada,
                    "resposta": (resposta_texto or "").strip() or "[Resposta enviada em áudio]",
                    "avaliacao": resultado
                }
                if vaga is not None:
                    vaga["avaliacoes"].append(aval)

                st.session_state["ultima_pergunta"] = pergunta_selecionada
                st.session_state["ultima_avaliacao"] = resultado
                st.session_state["ultima_avaliacao_id"] = aval["id"]
                # Um novo parecer abre uma conversa nova na Etapa 3 (a anterior fica no histórico)
                st.session_state["conversa_ativa_id"] = None
                st.session_state["mensagens_chat"] = []
                st.session_state["etapa2_concluida"] = True
                salvar_progresso_banco(st.session_state["usuario_logado"])
                st.rerun()

    if st.session_state.get("ultima_avaliacao"):
        with st.container(border=True, key="moldura_2"):
            st.markdown("<p class='kicker'>Parecer</p><h4 style='margin-top:0.2rem;'>Último Parecer Técnico Gerado</h4>", unsafe_allow_html=True)
            st.markdown(parecer_com_pergunta(st.session_state.get("ultima_pergunta"), st.session_state["ultima_avaliacao"]))

        if st.button("Avançar para Etapa 3 ➔", key="btn_avancar_e3"):
            ir_para_etapa(ETAPA_3)

# ============================================================
# ETAPA 3 — LAPIDAÇÃO & FEEDBACK
# ============================================================
elif etapa_atual == ETAPA_3:
    col_nav1, _ = st.columns([1.5, 4])
    with col_nav1:
        if st.button("⬅ Voltar para Simulação", key="btn_voltar_e2"):
            ir_para_etapa(ETAPA_2)

    cabecalho_secao("Etapa III", "Atelier de Lapidação Narrativa",
                    "Converse com o mentor para ajustar métricas, storytelling e pesquisar tendências da empresa no mercado em tempo real.")

    if st.session_state.get("ultima_pergunta"):
        st.caption(f"Conversando sobre: {st.session_state['ultima_pergunta']}")

    if "mensagens_chat" not in st.session_state:
        st.session_state["mensagens_chat"] = []

    for msg in st.session_state["mensagens_chat"]:
        with st.chat_message(msg["role"], avatar=avatar_ia() if msg["role"] == "assistant" else None):
            st.markdown(msg["content"])

    prompt_usuario = st.chat_input("Ex: Como posso destacar minha experiência com liderança nessa resposta?")
    if prompt_usuario:
        st.session_state["mensagens_chat"].append({"role": "user", "content": prompt_usuario})
        with st.chat_message("user"):
            st.markdown(prompt_usuario)

        with st.chat_message("assistant", avatar=avatar_ia()):
            resposta_ia = st.write_stream(
                stream_chat_lapidacao(
                    client=client,
                    historico_mensagens=st.session_state["mensagens_chat"],
                    contexto_vaga=st.session_state.get("contexto_vaga", {}),
                    pergunta=st.session_state.get("ultima_pergunta", "Pergunta Comportamental"),
                    parecer_anterior=st.session_state.get("ultima_avaliacao", "")
                )
            )

        if resposta_falhou(resposta_ia):
            # Falha: não salva, para você poder tentar de novo
            st.session_state["mensagens_chat"].pop()
        else:
            st.session_state["mensagens_chat"].append({"role": "assistant", "content": resposta_ia})
            sincronizar_conversa()
            salvar_progresso_banco(st.session_state["usuario_logado"])
