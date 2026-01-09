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
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" not in st.secrets:
        st.error("Configure os Secrets no painel do Streamlit!")
        st.stop()
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    planilha = client.open_by_key(ID_PLANILHA).sheet1
    drive = build('drive', 'v3', credentials=creds)
    return planilha, drive

try:
    sheet, drive_service = conectar_banco()
except Exception as e:
    st.error(f"Erro de conexão: {e}")
    st.stop()

# --- FUNÇÃO FOTO ---
def upload_foto(arquivo, codigo):
    try:
        file_metadata = {'name': f"foto_{codigo}.png", 'parents': [ID_PASTA_FOTOS]}
        media = MediaIoBaseUpload(io.BytesIO(arquivo.getvalue()), mimetype='image/png')
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id', supportsAllDrives=True).execute()
        return f"https://drive.google.com/uc?id={file.get('id')}"
    except:
        return None

# --- INTERFACE ---
st.title("📦 GREE - Kardex Digital Web")
codigo_busca = st.text_input("ESCANEIE OU DIGITE O CÓDIGO:", "").upper().strip()

if codigo_busca:
    dados = sheet.get_all_values()
    df = pd.DataFrame(dados[1:], columns=dados[0])
    
    # Limpeza de cabeçalhos
    df.columns = df.columns.str.strip()
    
    # Filtra o item
    item_rows = df[df['CÓDIGO'].str.strip() == codigo_busca]
    
    if not item_rows.empty:
        # Pega a linha mais recente
        item_atual = item_rows.tail(1)
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("SALDO ATUAL", item_atual['SALDO ATUAL'].values[0])
            st.write(f"**Descrição:** {item_atual['DESCRIÇÃO'].values[0]}")
            
            # --- CORREÇÃO DA LOCALIZAÇÃO (COLUNA J) ---
            # Tenta pelo nome exato, se não encontrar ou estiver vazio, pega pelo índice da Coluna J (9)
            if 'LOCALIZAÇÃO' in item_atual.columns and item_atual['LOCALIZAÇÃO'].values[0].strip() != "":
                loc_val = item_atual['LOCALIZAÇÃO'].values[0]
            else:
                # Localiza a linha original nos dados brutos para pegar a coluna J com precisão
                linha_index = item_atual.index[0]
                loc_val = dados[linha_index + 1][9] if len(dados[linha_index + 1]) > 9 else "N/A"
            
            st.write(f"**Localização:** {loc_val}")
        
        with col2:
            link_foto = item_atual['FOTO'].values[0] if 'FOTO' in item_atual.columns and item_atual['FOTO'].values[0] else None
            if link_foto:
                st.image(link_foto, use_container_width=True)
            else:
                nova_foto = st.camera_input("Cadastrar Foto")
                if nova_foto:
                    url = upload_foto(nova_foto, codigo_busca)
                    if url:
                        cell = sheet.find(codigo_busca)
                        sheet.update_cell(cell.row, 11, url) 
                        st.success("Foto salva!")
                        st.rerun()

        st.divider()
        
        with st.expander("📝 REGISTRAR MOVIMENTAÇÃO"):
            tipo = st.selectbox("Operação", ["SAÍDA", "ENTRADA", "INVENTÁRIO"])
            qtd = st.number_input("Quantidade", min_value=0.0)
            resp = st.text_input("RESPONSÁVEL").upper()
            
            if st.button("Confirmar Lançamento") and resp:
                val_saldo = str(item_atual['SALDO ATUAL'].values[0]).replace(',', '.')
                saldo_ant = float(val_saldo) if val_saldo else 0.0
                
                novo_saldo = (saldo_ant + qtd) if tipo == "ENTRADA" else (saldo_ant - qtd) if tipo == "SAÍDA" else qtd
                data_p = datetime.datetime.now(FUSO_HORARIO).strftime("%d/%m/%Y %H:%M")
                
                # Registra mantendo a Localização na Coluna J
                sheet.append_row([data_p, codigo_busca, item_atual['DESCRIÇÃO'].values[0], qtd, tipo, round(novo_saldo,2), "", resp, "", loc_val, link_foto or ""])
                st.success("Lançado!")
                st.rerun()

        # --- HISTÓRICO ---
        st.subheader("📜 Histórico Recente")
        hist = item_rows.tail(5).iloc[::-1].copy()
        hist['DATA'] = hist['DATA'].apply(lambda x: str(x).split(' ')[0])
        
        colunas_v = ['DATA', 'VALOR MOV.', 'SALDO ATUAL', 'TIPO MOV.', 'RESPONSÁVEL']
        
        def colorir(row):
            cor = 'color: #d32f2f' if row['TIPO MOV.'] == 'SAÍDA' else 'color: #2e7d32' if row['TIPO MOV.'] == 'ENTRADA' else ''
            return [f'{cor}; font-weight: bold'] * len(row)

        st.dataframe(hist[colunas_v].style.apply(colorir, axis=1), hide_index=True, use_container_width=True)
    else:
        st.error("Código não encontrado.")
