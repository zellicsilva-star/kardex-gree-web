import streamlit as st
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime
import io

# --- CONFIGURAÇÕES INICIAIS ---
ID_PLANILHA = "1Z5lmqhYJVo1SvNUclNPQ88sGmI7en5dBS3xfhj_7TrU"
ID_PASTA_FOTOS = "1AFLfBEVqnJfGRJnCNvE7BC5k2puAY366"

st.set_page_config(page_title="GREE - Kardex Web", page_icon="📦")

# --- CONEXÕES ---
def conectar_servicos():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    # Pega as credenciais dos Secrets do Streamlit
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    
    # Conexão Planilha
    client = gspread.authorize(creds)
    planilha = client.open_by_key(ID_PLANILHA).sheet1
    
    # Conexão Drive (Fotos)
    drive_service = build('drive', 'v3', credentials=creds)
    
    return planilha, drive_service

sheet, drive_service = conectar_servicos()

# --- FUNÇÃO UPLOAD FOTO ---
def upload_foto(arquivo, codigo):
    file_metadata = {'name': f"foto_{codigo}.png", 'parents': [ID_PASTA_FOTOS]}
    media = MediaIoBaseUpload(io.BytesIO(arquivo.getvalue()), mimetype='image/png')
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    # Retorna link público de visualização
    return f"https://drive.google.com/uc?id={file.get('id')}"

# --- INTERFACE ---
st.title("📦 GREE - Kardex Digital Web")

codigo_busca = st.text_input("ESCANEIE OU DIGITE O CÓDIGO:", "").upper().strip()

if codigo_busca:
    dados = sheet.get_all_values()
    df = pd.DataFrame(dados[1:], columns=dados[0])
    
    # Busca o item específico
    item_rows = df[df['CÓDIGO'] == codigo_busca]
    
    if not item_rows.empty:
        item_atual = item_rows.tail(1) # Pega a última linha para o saldo
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("SALDO ATUAL", item_atual['SALDO ATUAL'].values[0])
            st.write(f"**Descrição:** {item_atual['DESCRIÇÃO'].values[0]}")
            st.write(f"**Localização:** {item_atual['LOCALIZAÇÃO'].values[0]}")
        
        with col2:
            # Verifica se tem foto na Coluna 11 (Ajuste se for outra coluna)
            link_foto = item_atual['FOTO'].values[0] if 'FOTO' in item_atual.columns and item_atual['FOTO'].values[0] else None
            
            if link_foto:
                st.image(link_foto, caption="Foto do Produto")
            else:
                st.warning("Sem foto no catálogo.")
                nova_foto = st.camera_input("Cadastrar Foto")
                if nova_foto:
                    url = upload_foto(nova_foto, codigo_busca)
                    # Atualiza a célula de foto na linha correspondente na planilha
                    row_index = len(df) + 1 # Simplificação para o exemplo
                    # Busca a linha real na planilha para atualizar
                    cell = sheet.find(codigo_busca)
                    sheet.update_cell(cell.row, 11, url) # Coluna 11 = FOTO
                    st.success("Foto salva!")
                    st.rerun()

        st.divider()
        
        # --- MOVIMENTAÇÃO ---
        with st.expander("📝 REGISTRAR MOVIMENTAÇÃO"):
            tipo = st.selectbox("Operação", ["SAÍDA", "ENTRADA", "INVENTÁRIO"])
            qtd = st.number_input("Quantidade", min_value=0.0)
            resp = st.text_input("Responsável").upper()
            
            if st.button("Confirmar Lançamento"):
                # Lógica de saldo
                saldo_ant = float(item_atual['SALDO ATUAL'].values[0].replace(',', '.'))
                novo_saldo = (saldo_ant + qtd) if tipo == "ENTRADA" else (saldo_ant - qtd) if tipo == "SAÍDA" else qtd
                
                nova_linha = [
                    datetime.now().strftime("%d/%m/%Y %H:%M"),
                    codigo_busca,
                    item_atual['DESCRIÇÃO'].values[0],
                    qtd, tipo, round(novo_saldo, 2),
                    "", resp, item_atual['ARMAZÉM'].values[0], item_atual['LOCALIZAÇÃO'].values[0],
                    link_foto if link_foto else ""
                ]
                sheet.append_row(nova_linha)
                st.success("Lançado com sucesso!")
                st.rerun()

        # --- HISTÓRICO ---
        st.subheader("📜 Histórico Recente")
        hist = item_rows.tail(5).iloc[::-1] # Últimas 5
        st.table(hist[['DATA', 'TIPO MOV.', 'VALOR MOV.', 'RESPONSÁVEL']])
        
    else:
        st.error("Código não encontrado.")
