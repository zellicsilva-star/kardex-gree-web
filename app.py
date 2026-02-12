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

# --- CONEXÃO UNIFICADA ---
@st.cache_resource
def conectar():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Validação de Secrets
    if "gcp_service_account" not in st.secrets:
        st.error("Erro: Credenciais do Google não encontradas.")
        st.stop()
    if "SUPABASE_URL" not in st.secrets or "SUPABASE_KEY" not in st.secrets:
        st.error("Erro: Credenciais do Supabase ausentes nos Secrets.")
        st.stop()

    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    
    client = gspread.authorize(creds)
    planilha = client.open_by_key(ID_PLANILHA).sheet1
    drive = build('drive', 'v3', credentials=creds)
    
    # Conexão Supabase
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)
    
    return planilha, drive, supabase

try:
    sheet, drive_service, supabase = conectar()
except Exception as e:
    st.error(f"Erro Crítico de Conexão: {e}")
    st.stop()

# --- FUNÇÃO DE LOG SUPABASE ---
def log_supabase(dados):
    try:
        # NOME DA TABELA ATUALIZADO PARA: movimentacoes_bunker
        supabase.table("movimentacoes_bunker").insert(dados).execute()
    except Exception as e:
        st.warning(f"⚠️ Nota: Salvo no Sheets, mas erro no banco Supabase: {e}")

# --- FUNÇÕES DE DRIVE E IMAGEM ---
def upload_foto(arquivo, codigo):
    try:
        file_metadata = {'name': f"foto_{codigo}.png", 'parents': [ID_PASTA_FOTOS]}
        media = MediaIoBaseUpload(io.BytesIO(arquivo.getvalue()), mimetype='image/png')
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id', supportsAllDrives=True).execute()
        return f"https://drive.google.com/uc?export=view&id={file.get('id')}"
    except Exception as e:
        st.error(f"Erro no Upload (Drive): {e}")
        return None

def baixar_imagem_drive(link_planilha):
    if not link_planilha: return None
    try:
        file_id = None
        url = str(link_planilha).strip()
        if "id=" in url: file_id = url.split("id=")[1].split("&")[0]
        elif "/d/" in url: file_id = url.split("/d/")[1].split("/")[0]
        if not file_id: return None
        request = drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False: status, done = downloader.next_chunk()
        return fh.getvalue()
    except Exception: return None

def limpar_link(valor):
    v = str(valor).strip()
    if v.startswith('=IMAGE("'): return v[8:-2]
    return v

# --- INTERFACE ---
st.title("📦 GREE - Kardex Digital (Híbrido)")

query_params = st.query_params
codigo_url = query_params.get("codigo", "")
codigo_busca = st.text_input("ESCANEIE OU DIGITE O CÓDIGO:", value=codigo_url).upper().strip()

# Carregamento de dados (Sheets)
dados_raw = sheet.get_all_values()
df = pd.DataFrame(dados_raw[1:], columns=dados_raw[0])

if codigo_busca:
    df['CÓDIGO'] = df['CÓDIGO'].astype(str).str.strip()
    item_rows = df[df['CÓDIGO'] == codigo_busca]
    
    if not item_rows.empty:
        item_atual = item_rows.tail(1)
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"##### DESCRIÇÃO: {item_atual['DESCRIÇÃO'].values[0]}")
            c_saldo1, c_saldo2 = st.columns(2)
            with c_saldo1: st.metric("SALDO KARDEX", item_atual['SALDO ATUAL'].values[0])
            with c_saldo2:
                val_infor = item_atual['SALDO INFOR'].values[0] if 'SALDO INFOR' in item_atual.columns else "N/A"
                st.metric("SALDO INFOR", val_infor)
            st.write(f"**Localização:** {item_atual['LOCALIZAÇÃO'].values[0]}")
            st.write(f"**Armazém:** {item_atual['ARMAZÉM'].values[0]}")

        with col2:
            link_foto = limpar_link(item_atual['FOTO'].values[0] if 'FOTO' in item_atual.columns else "")
            if link_foto and len(link_foto) > 10:
                img_bytes = baixar_imagem_drive(link_foto)
                if img_bytes: st.image(img_bytes, use_container_width=True)
            else: st.info("📸 Sem foto cadastrada.")

        st.divider()

        with st.expander("📝 REGISTRAR MOVIMENTAÇÃO"):
            tipo = st.selectbox("Operação", ["SAÍDA", "ENTRADA", "INVENTÁRIO"])
            qtd = st.number_input("Quantidade", min_value=0.0, step=1.0)
            doc = st.text_input("REQUISIÇÃO/NF").upper()
            obs = st.text_input("OBSERVAÇÃO").upper()
            resp = st.text_input("RESPONSÁVEL").upper()
            
            if st.button("Confirmar Lançamento"):
                if resp:
                    try:
                        saldo_ant = float(item_atual['SALDO ATUAL'].values[0].replace(',', '.'))
                    except: saldo_ant = 0.0
                    
                    novo_saldo = (saldo_ant + qtd) if tipo == "ENTRADA" else (saldo_ant - qtd) if tipo == "SAÍDA" else qtd
                    agora = datetime.datetime.now(FUSO_HORARIO)
                    dt_fmt = agora.strftime("%d/%m/%Y %H:%M")

                    # Salvar no Google Sheets
                    nova_linha = [dt_fmt, f"'{codigo_busca}", item_atual['DESCRIÇÃO'].values[0], 
                                  str(qtd).replace('.', ','), tipo, str(round(novo_saldo, 2)).replace('.', ','), 
                                  doc, resp, item_atual['ARMAZÉM'].values[0], item_atual['LOCALIZAÇÃO'].values[0], 
                                  "", "", "", obs]
                    sheet.append_row(nova_linha, value_input_option='USER_ENTERED')

                    # Salvar no Supabase
                    log_supabase({
                        "data": dt_fmt, "codigo": str(codigo_busca), "descricao": item_atual['DESCRIÇÃO'].values[0],
                        "quantidade": float(qtd), "tipo_mov": tipo, "saldo": float(novo_saldo),
                        "documento": doc, "responsavel": resp, "armazem": item_atual['ARMAZÉM'].values[0],
                        "localizacao": item_atual['LOCALIZAÇÃO'].values[0], "observacao": obs
                    })
                    st.success("Lançamento concluído!")
                    time.sleep(1)
                    st.rerun()

    else:
        st.warning(f"⚠️ Código {codigo_busca} não encontrado.")
        with st.expander("🆕 CADASTRAR NOVO ITEM"):
            desc_novo = st.text_input("Descrição do Item").upper()
            armazem_novo = st.selectbox("Armazém", ["MI03", "MI05", "MP01", "AC13", "BR06", "BR01"])
            loc_novo = st.text_input("Localização").upper()
            saldo_ini = st.number_input("Saldo Inicial", min_value=0.0)
            resp_cad = st.text_input("Seu Nome (Responsável)").upper()

            if st.button("Salvar Novo Item"):
                if desc_novo and resp_cad:
                    agora = datetime.datetime.now(FUSO_HORARIO)
                    dt_fmt = agora.strftime("%d/%m/%Y %H:%M")
                    
                    # Sheets
                    nova_linha_cad = [dt_fmt, f"'{codigo_busca}", desc_novo, str(saldo_ini).replace('.', ','), 
                                      "ENTRADA", str(saldo_ini).replace('.', ','), "CADASTRO INICIAL", 
                                      resp_cad, armazem_novo, loc_novo, "", "", "", "NOVO CADASTRO"]
                    sheet.append_row(nova_linha_cad, value_input_option='USER_ENTERED')
                    
                    # Supabase
                    log_supabase({
                        "data": dt_fmt, "codigo": str(codigo_busca), "descricao": desc_novo,
                        "quantidade": float(saldo_ini), "tipo_mov": "ENTRADA", "saldo": float(saldo_ini),
                        "documento": "CADASTRO", "responsavel": resp_cad, "armazem": armazem_novo,
                        "localizacao": loc_novo, "observacao": "CADASTRO INICIAL"
                    })
                    st.success("Item cadastrado!")
                    time.sleep(1.5)
                    st.rerun()
