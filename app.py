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
# COLOQUE SEU E-MAIL ABAIXO (O dono da pasta no Drive)
SEU_EMAIL_PESSOAL = "kardex@alien-isotope-483613-d3.iam.gserviceaccount.com" 

st.set_page_config(page_title="GREE - Kardex Web", page_icon="📦", layout="wide")

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

def upload_foto(arquivo, codigo):
    try:
        # 1. Upload inicial do arquivo
        file_metadata = {
            'name': f"foto_{codigo}.png", 
            'parents': [ID_PASTA_FOTOS]
        }
        media = MediaIoBaseUpload(io.BytesIO(arquivo.getvalue()), mimetype='image/png')
        
        file = drive_service.files().create(
            body=file_metadata, 
            media_body=media, 
            fields='id',
            supportsAllDrives=True
        ).execute()
        
        file_id = file.get('id')

        # 2. Transferir a "propriedade" para o seu e-mail para não gastar cota da service account
        permission = {
            'type': 'user',
            'role': 'owner',
            'emailAddress': SEU_EMAIL_PESSOAL
        }
        # transferOwnership=True é o que resolve o erro de cota definitivamente
        drive_service.permissions().create(
            fileId=file_id,
            body=permission,
            transferOwnership=True,
            supportsAllDrives=True
        ).execute()
        
        return f"https://drive.google.com/uc?id={file_id}"
    except Exception as e:
        st.error(f"Erro técnico: {e}")
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
                st.image(link_foto, use_container_width=True)
            else:
                nova_foto = st.camera_input("Cadastrar Foto")
                if nova_foto:
                    url = upload_foto(nova_foto, codigo_busca)
                    if url:
                        cell = sheet.find(codigo_busca)
                        sheet.update_cell(cell.row, 11, url) 
                        st.success("Foto salva com sucesso!")
                        st.rerun()

        st.divider()
        
        with st.expander("📝 REGISTRAR MOVIMENTAÇÃO"):
            tipo = st.selectbox("Operação", ["SAÍDA", "ENTRADA", "INVENTÁRIO"])
            qtd = st.number_input("Quantidade", min_value=0.0)
            resp = st.text_input("RESPONSÁVEL").upper()
            
            if st.button("Confirmar Lançamento") and resp:
                try:
                    valor_limpo = str(item_atual['SALDO ATUAL'].values[0]).replace(',', '.')
                    saldo_ant = float(valor_limpo)
                except:
                    saldo_ant = 0.0
                    
                novo_saldo = (saldo_ant + qtd) if tipo == "ENTRADA" else (saldo_ant - qtd) if tipo == "SAÍDA" else qtd
                data_p = datetime.datetime.now(FUSO_HORARIO).strftime("%d/%m/%Y %H:%M")
                
                sheet.append_row([data_p, codigo_busca, item_atual['DESCRIÇÃO'].values[0], qtd, tipo, round(novo_saldo,2), "", resp, "", "", link_foto or ""])
                st.success("Lançado!")
                st.rerun()

        # --- HISTÓRICO COM COLUNAS TIPO MOV AO LADO DE VALOR MOV ---
        st.subheader("📜 Histórico Recente")
        hist = item_rows.tail(5).iloc[::-1].copy()
        hist['DATA'] = hist['DATA'].apply(lambda x: str(x).split(' ')[0])
        
        # Ordem: DATA | VALOR MOV. | TIPO MOV. | SALDO ATUAL | RESPONSÁVEL
        colunas_v = ['DATA', 'VALOR MOV.', 'TIPO MOV.', 'SALDO ATUAL', 'RESPONSÁVEL']
        
        def colorir(row):
            cor = 'color: #d32f2f' if row['TIPO MOV.'] == 'SAÍDA' else 'color: #2e7d32' if row['TIPO MOV.'] == 'ENTRADA' else ''
            return [f'{cor}; font-weight: bold'] * len(row)

        st.dataframe(hist[colunas_v].style.apply(colorir, axis=1), hide_index=True, use_container_width=True)
    else:
        st.error("Código não encontrado.")
