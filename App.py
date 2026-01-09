import streamlit as st
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import datetime
import pytz
import io

# --- CONFIGURAÇÕES INICIAIS ---
ID_PLANILHA = "1Z5lmqhYJVo1SvNUclNPQ88sGmI7en5dBS3xfhj_7TrU"
ID_PASTA_FOTOS = "1AFLfBEVqnJfGRJnCNvE7BC5k2puAY366"
FUSO_HORARIO = pytz.timezone('America/Manaus')

st.set_page_config(page_title="GREE - Kardex Web", page_icon="📦")

# --- CONEXÕES ---
@st.cache_resource
def conectar_servicos():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    
    client = gspread.authorize(creds)
    planilha = client.open_by_key(ID_PLANILHA).sheet1
    drive_service = build('drive', 'v3', credentials=creds)
    
    return planilha, drive_service

try:
    sheet, drive_service = conectar_servicos()
except Exception as e:
    st.error(f"Erro de conexão: {e}")
    st.stop()

# --- FUNÇÃO UPLOAD FOTO ---
def upload_foto(arquivo, codigo):
    try:
        file_metadata = {'name': f"foto_{codigo}.png", 'parents': [ID_PASTA_FOTOS]}
        media = MediaIoBaseUpload(io.BytesIO(arquivo.getvalue()), mimetype='image/png')
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return f"https://drive.google.com/uc?id={file.get('id')}"
    except Exception as e:
        st.error(f"Erro na permissão do Google Drive: {e}. Verifique se o e-mail do JSON é EDITOR na pasta.")
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
                st.image(link_foto, caption="Foto do Produto")
            else:
                st.warning("Sem foto no catálogo.")
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
            qtd = st.number_input("Quantidade", min_value=0.0, step=1.0)
            doc = st.text_input("REQUISIÇÃO").upper()
            resp = st.text_input("RESPONSÁVEL").upper()
            
            if st.button("Confirmar Lançamento"):
                if not resp:
                    st.warning("Preencha o responsável!")
                else:
                    saldo_ant = float(item_atual['SALDO ATUAL'].values[0].replace(',', '.'))
                    if tipo == "ENTRADA": novo_saldo = saldo_ant + qtd
                    elif tipo == "SAÍDA": novo_saldo = saldo_ant - qtd
                    else: novo_saldo = qtd
                    
                    data_hora = datetime.datetime.now(FUSO_HORARIO).strftime("%d/%m/%Y %H:%M")
                    
                    # Ordem: DATA, CÓDIGO, DESCRIÇÃO, VALOR MOV., TIPO MOV., SALDO ATUAL, REQUISIÇÃO, RESPONSÁVEL, ARMAZÉM, LOCALIZAÇÃO, FOTO
                    nova_linha = [
                        data_hora, codigo_busca, item_atual['DESCRIÇÃO'].values[0],
                        qtd, tipo, round(novo_saldo, 2),
                        doc, resp, item_atual['ARMAZÉM'].values[0], item_atual['LOCALIZAÇÃO'].values[0],
                        link_foto if link_foto else ""
                    ]
                    sheet.append_row(nova_linha)
                    st.success("Lançado com sucesso!")
                    st.rerun()

        st.subheader("📜 Histórico Recente")
        # Mostrar as últimas 5 movimentações desse código
        hist = item_rows.tail(5).iloc[::-1]
        st.dataframe(hist[['DATA', 'TIPO MOV.', 'VALOR MOV.', 'RESPONSÁVEL']], hide_index=True)
        
    else:
        st.error("Código não encontrado.")
