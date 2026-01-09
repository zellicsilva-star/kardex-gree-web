import streamlit as st
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import datetime
import pytz
import io

# --- CONFIGURAÇÕES ---
ID_PLANILHA = "1Z5lmqhYJVo1SvNUclNPQ88sGmI7en5dBS3xfhj_7TrU"
ID_PASTA_FOTOS = "1AFLfBEVqnJfGRJnCNvE7BC5k2puAY366"
FUSO_HORARIO = pytz.timezone('America/Manaus')

st.set_page_config(page_title="GREE - Kardex Web", page_icon="📦", layout="wide")

# --- CONEXÃO ---
@st.cache_resource
def conectar_banco():
    # Escopos para Planilha e Drive
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Verifica se os Secrets existem para não dar erro de tela branca
    if "gcp_service_account" not in st.secrets:
        st.error("Erro: Credenciais (Secrets) não encontradas no Streamlit Cloud.")
        st.stop()
        
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    
    client = gspread.authorize(creds)
    planilha = client.open_by_key(ID_PLANILHA).sheet1
    drive = build('drive', 'v3', credentials=creds)
    
    return planilha, drive

# Tenta conectar
try:
    sheet, drive_service = conectar_banco()
except Exception as e:
    st.error(f"Erro ao conectar com o Google: {e}")
    st.stop()

# --- FUNÇÃO UPLOAD ---
def upload_foto(arquivo, codigo):
    try:
        file_metadata = {'name': f"foto_{codigo}.png", 'parents': [ID_PASTA_FOTOS]}
        media = MediaIoBaseUpload(io.BytesIO(arquivo.getvalue()), mimetype='image/png')
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return f"https://drive.google.com/uc?id={file.get('id')}"
    except:
        return None

# --- INTERFACE ---
st.title("📦 GREE - Kardex Digital Web")
codigo_busca = st.text_input("ESCANEIE OU DIGITE O CÓDIGO:", "").upper().strip()

if codigo_busca:
    dados = sheet.get_all_values()
    df = pd.DataFrame(dados[1:], columns=dados[0])
    item_rows = df[df['CÓDIGO'] == codigo_busca]
    
    if not item_rows.empty:
        item_atual = item_rows.tail(1)
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("SALDO ATUAL", item_atual['SALDO ATUAL'].values[0])
            st.write(f"**Descrição:** {item_atual['DESCRIÇÃO'].values[0]}")
            st.write(f"**Localização:** {item_atual['LOCALIZAÇÃO'].values[0]}")
        
        with col2:
            link_foto = item_atual['FOTO'].values[0] if 'FOTO' in item_atual.columns and item_atual['FOTO'].values[0] else None
            if link_foto:
                st.image(link_foto)
            else:
                nova_foto = st.camera_input("Cadastrar Foto")
                if nova_foto:
                    url = upload_foto(nova_foto, codigo_busca)
                    if url:
                        cell = sheet.find(codigo_busca)
                        sheet.update_cell(cell.row, 11, url) 
                        st.success("Foto salva!")
                        st.rerun()
                    else:
                        st.error("Erro no Drive. Verifique se a API está ATIVA e se o e-mail do JSON é EDITOR na pasta.")

        st.divider()
        
        with st.expander("📝 REGISTRAR MOVIMENTAÇÃO"):
            tipo = st.selectbox("Operação", ["SAÍDA", "ENTRADA", "INVENTÁRIO"])
            qtd = st.number_input("Quantidade", min_value=0.0)
            resp = st.text_input("RESPONSÁVEL").upper()
            
            if st.button("Confirmar Lançamento") and resp:
                data_p = datetime.datetime.now(FUSO_HORARIO).strftime("%d/%m/%Y %H:%M")
                # Salva na planilha mantendo a ordem das colunas
                sheet.append_row([data_p, codigo_busca, item_atual['DESCRIÇÃO'].values[0], qtd, tipo, "", "", resp, "", "", link_foto or ""])
                st.success("Lançado!")
                st.rerun()

        # --- HISTÓRICO COM CORES E ORDEM SOLICITADA ---
        st.subheader("📜 Histórico Recente")
        hist = item_rows.tail(5).iloc[::-1].copy()
        
        # Formata data
        hist['DATA'] = hist['DATA'].apply(lambda x: str(x).split(' ')[0])
        
        # Ordem: DATA | VALOR MOV. | SALDO ATUAL | TIPO MOV. | RESPONSÁVEL
        colunas_v = ['DATA', 'VALOR MOV.', 'SALDO ATUAL', 'TIPO MOV.', 'RESPONSÁVEL']
        
        def colorir_linha(row):
            if row['TIPO MOV.'] == 'SAÍDA':
                return ['color: #d32f2f; font-weight: bold'] * len(row)
            elif row['TIPO MOV.'] == 'ENTRADA':
                return ['color: #2e7d32; font-weight: bold'] * len(row)
            return [''] * len(row)

        st.dataframe(
            hist[colunas_v].style.apply(colorir_linha, axis=1),
            hide_index=True,
            use_container_width=True
        )
    else:
        st.error("Código não encontrado.")
