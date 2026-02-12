import streamlit as st
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload 
import datetime
import pytz
import io
import time 
from PIL import Image 
from supabase import create_client

# --- CONFIGURAÇÕES ---
ID_PLANILHA = "1Z5lmqhYJVo1SvNUclNPQ88sGmI7en5dBS3xfhj_7TrU"
ID_PASTA_FOTOS = "1JrfpzjrhzvjHwpZkxKi162reL9nd5uAC"
FUSO_HORARIO = pytz.timezone('America/Manaus')

st.set_page_config(page_title="GREE - Kardex Web", page_icon="📦", layout="wide")

# --- CONEXÃO ---
@st.cache_resource
def conectar():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Validação de Secrets
    if "SUPABASE_URL" not in st.secrets or "SUPABASE_KEY" not in st.secrets:
        st.error("Erro: Credenciais do Supabase ausentes nos Secrets do Streamlit Cloud.")
        st.stop()

    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    
    client = gspread.authorize(creds)
    planilha = client.open_by_key(ID_PLANILHA).sheet1
    drive = build('drive', 'v3', credentials=creds)
    
    # Conexão Supabase
    supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    
    return planilha, drive, supabase

try:
    sheet, drive_service, supabase = conectar()
except Exception as e:
    st.error(f"Erro Crítico: {e}")
    st.stop()

# --- FUNÇÃO DE SALVAMENTO ---
def log_supabase(dados):
    try:
        # Nome da tabela conforme seu print image_69c17b.png
        supabase.table("movimentacoes_bunker").insert(dados).execute()
    except Exception as e:
        st.warning(f"⚠️ Salvo no Sheets, mas falha no banco: {e}")

# ... (Mantenha as funções auxiliares de foto e link iguais ao seu código anterior) ...

st.title("📦 GREE - Kardex Digital (Híbrido)")

# --- LÓGICA DE BUSCA E LANÇAMENTO ---
query_params = st.query_params
codigo_url = query_params.get("codigo", "")
codigo_busca = st.text_input("ESCANEIE OU DIGITE O CÓDIGO:", value=codigo_url).upper().strip()

dados_raw = sheet.get_all_values()
df = pd.DataFrame(dados_raw[1:], columns=dados_raw[0])

if codigo_busca:
    df['CÓDIGO'] = df['CÓDIGO'].astype(str).str.strip()
    item_rows = df[df['CÓDIGO'] == codigo_busca]
    
    if not item_rows.empty:
        item_atual = item_rows.tail(1)
        # ... (Interface de visualização igual) ...

        with st.expander("📝 REGISTRAR MOVIMENTAÇÃO"):
            tipo = st.selectbox("Operação", ["SAÍDA", "ENTRADA", "INVENTÁRIO"])
            qtd = st.number_input("Quantidade", min_value=0.0)
            doc = st.text_input("REQUISIÇÃO/NF").upper()
            resp = st.text_input("RESPONSÁVEL").upper()
            
            if st.button("Confirmar Lançamento"):
                if resp:
                    agora = datetime.datetime.now(FUSO_HORARIO)
                    dt_fmt = agora.strftime("%d/%m/%Y %H:%M")
                    
                    # Log Supabase - Os nomes das chaves devem bater com as colunas da tabela
                    log_supabase({
                        "data_mov": dt_fmt, # Nome ajustado para bater com seu print
                        "codigo": str(codigo_busca),
                        "descricao": item_atual['DESCRIÇÃO'].values[0],
                        "quantidade": float(qtd),
                        "tipo_mov": tipo,
                        "armazem": item_atual['ARMAZÉM'].values[0]
                    })
                    
                    # Log Sheets (Mantendo seu fluxo atual)
                    nova_linha = [dt_fmt, f"'{codigo_busca}", item_atual['DESCRIÇÃO'].values[0], str(qtd), tipo, "", doc, resp]
                    sheet.append_row(nova_linha, value_input_option='USER_ENTERED')
                    
                    st.success("Lançamento concluído!")
                    time.sleep(1)
                    st.rerun()
