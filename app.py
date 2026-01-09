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
# ATUALIZADO: ID DA PASTA NOVA (FOTOS_KARDEX_NOVA) CONFIRMADO NO SEU PRINT
ID_PASTA_FOTOS = "1JrfpzjrhzvjHwpZkxKi162reL9nd5uAC" 
FUSO_HORARIO = pytz.timezone('America/Manaus')

st.set_page_config(page_title="GREE - Kardex Web", page_icon="📦", layout="wide")

# --- CONEXÃO ---
@st.cache_resource
def conectar():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    if "gcp_service_account" not in st.secrets:
        st.error("Credenciais não encontradas nos Secrets.")
        st.stop()
        
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    
    client = gspread.authorize(creds)
    planilha = client.open_by_key(ID_PLANILHA).sheet1
    drive = build('drive', 'v3', credentials=creds)
    
    return planilha, drive

try:
    sheet, drive_service = conectar()
except Exception as e:
    st.error(f"Erro de Conexão: {e}")
    st.stop()

# --- FUNÇÃO DE UPLOAD ---
def upload_foto(arquivo, codigo):
    try:
        file_metadata = {'name': f"foto_{codigo}.png", 'parents': [ID_PASTA_FOTOS]}
        media = MediaIoBaseUpload(io.BytesIO(arquivo.getvalue()), mimetype='image/png')
        
        # Faz o upload usando o espaço que você acabou de contratar
        file = drive_service.files().create(
            body=file_metadata, 
            media_body=media, 
            fields='id',
            supportsAllDrives=True
        ).execute()
        
        return f"https://drive.google.com/uc?id={file.get('id')}"
    except Exception as e:
        st.error(f"Erro no Upload: {e}")
        return None

# --- INTERFACE ---
st.title("📦 GREE - Kardex Digital Web")
codigo_busca = st.text_input("ESCANEIE OU DIGITE O CÓDIGO:", "").upper().strip()

if codigo_busca:
    # Busca dados
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
                st.info("📸 Item sem foto.")
                nova_foto = st.camera_input("Tirar Foto Agora")
                
                if nova_foto:
                    with st.spinner("Salvando foto no Drive..."):
                        url = upload_foto(nova_foto, codigo_busca)
                        
                    if url:
                        # Salva o link na planilha (Coluna 11 = K)
                        cell = sheet.find(codigo_busca)
                        sheet.update_cell(cell.row, 11, url) 
                        st.success("Foto salva com sucesso!")
                        st.rerun()

        st.divider()

        # --- REGISTRO DE MOVIMENTAÇÃO ---
        with st.expander("📝 REGISTRAR MOVIMENTAÇÃO"):
            tipo = st.selectbox("Operação", ["SAÍDA", "ENTRADA", "INVENTÁRIO"])
            qtd = st.number_input("Quantidade", min_value=0.0, step=1.0)
            doc = st.text_input("REQUISIÇÃO/NF").upper()
            resp = st.text_input("RESPONSÁVEL").upper()
            
            if st.button("Confirmar Lançamento"):
                if resp:
                    try:
                        saldo_ant = float(item_atual['SALDO ATUAL'].values[0].replace(',', '.'))
                    except:
                        saldo_ant = 0.0
                        
                    if tipo == "ENTRADA": novo_saldo = saldo_ant + qtd
                    elif tipo == "SAÍDA": novo_saldo = saldo_ant - qtd
                    else: novo_saldo = qtd 
                    
                    agora = datetime.datetime.now(FUSO_HORARIO)
                    dt_planilha = agora.strftime("%d/%m/%Y %H:%M")
                    
                    # MONTAGEM DA LINHA
                    nova_linha = [
                        dt_planilha, 
                        codigo_busca, 
                        item_atual['DESCRIÇÃO'].values[0],
                        qtd, 
                        tipo, 
                        str(round(novo_saldo, 2)).replace('.', ','),
                        doc, 
                        resp, 
                        item_atual['ARMAZÉM'].values[0], 
                        item_atual['LOCALIZAÇÃO'].values[0],
                        link_foto or ""
                    ]
                    
                    sheet.append_row(nova_linha, value_input_option='USER_ENTERED')
                    st.success("✅ Movimentação registrada!")
                    st.rerun()
                else:
                    st.warning("⚠️ Preencha o Responsável.")

        # --- HISTÓRICO ---
        st.subheader("📜 Histórico Recente")
        hist = item_rows.tail(5).iloc[::-1].copy()
        
        # Filtra apenas colunas que realmente existem para evitar erro
        cols_desejadas = ['DATA', 'VALOR MOV.', 'TIPO MOV.', 'SALDO ATUAL', 'REQUISIÇÃO', 'RESPONSÁVEL']
        cols_finais = [c for c in cols_desejadas if c in hist.columns]
        
        if 'DATA' in hist.columns:
             hist['DATA'] = hist['DATA'].apply(lambda x: str(x).split(' ')[0])
             
        hist_final = hist[cols_finais]

        def style_rows(row):
            if 'TIPO MOV.' in row:
                if row['TIPO MOV.'] == 'SAÍDA':
                    return ['color: #d32f2f; font-weight: bold'] * len(row)
                elif row['TIPO MOV.'] == 'ENTRADA':
                    return ['color: #2e7d32; font-weight: bold'] * len(row)
            return [''] * len(row)

        st.dataframe(
            hist_final.style.apply(style_rows, axis=1),
            hide_index=True,
            use_container_width=True
        )
    else:
        st.error("Código não encontrado.")
