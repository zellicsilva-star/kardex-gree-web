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
    # Abre a planilha e garante acesso à primeira aba
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
        # supportsAllDrives=True é essencial para Service Accounts
        file = drive_service.files().create(
            body=file_metadata, 
            media_body=media, 
            fields='id',
            supportsAllDrives=True 
        ).execute()
        return f"https://drive.google.com/uc?id={file.get('id')}"
    except Exception as e:
        st.error(f"Erro no Drive: {e}. Verifique se a pasta está compartilhada com o e-mail da Service Account.")
        return None

# --- INTERFACE ---
st.title("📦 GREE - Kardex Digital Web")
codigo_busca = st.text_input("ESCANEIE OU DIGITE O CÓDIGO:", "").upper().strip()

if codigo_busca:
    # Obtém todos os valores para processamento manual (mais seguro que depender apenas do Pandas)
    dados_brutos = sheet.get_all_values()
    headers = [str(h).strip().upper() for h in dados_brutos[0]]
    df = pd.DataFrame(dados_brutos[1:], columns=headers)
    
    # Busca o item ignorando espaços e casos
    item_rows = df[df['CÓDIGO'].str.strip() == codigo_busca]
    
    if not item_rows.empty:
        item_atual = item_rows.tail(1)
        # Localiza a linha exata na planilha (index do DF + 2 porque o Sheets começa em 1 e tem cabeçalho)
        linha_sheets = item_atual.index[0] + 2
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("SALDO ATUAL", item_atual['SALDO ATUAL'].values[0])
            st.write(f"**Descrição:** {item_atual['DESCRIÇÃO'].values[0]}")
            
            # --- CORREÇÃO DA LOCALIZAÇÃO (COLUNA J = ÍNDICE 9) ---
            try:
                # Tenta pegar pela posição física da coluna J na lista de dados brutos
                loc_val = dados_brutos[linha_sheets-1][9] 
            except:
                loc_val = "N/A"
            
            st.info(f"📍 **Localização:** {loc_val}")
        
        with col2:
            link_foto = item_atual['FOTO'].values[0] if 'FOTO' in item_atual.columns and item_atual['FOTO'].values[0] else None
            if link_foto:
                st.image(link_foto, use_container_width=True)
            else:
                nova_foto = st.camera_input("Cadastrar Foto")
                if nova_foto:
                    url = upload_foto(nova_foto, codigo_busca)
                    if url:
                        # Coluna 11 é a K (FOTO)
                        sheet.update_cell(linha_sheets, 11, url)
                        st.success("Foto salva!")
                        st.rerun()

        st.divider()
        
        with st.expander("📝 REGISTRAR MOVIMENTAÇÃO"):
            tipo = st.selectbox("Operação", ["SAÍDA", "ENTRADA", "INVENTÁRIO"])
            qtd = st.number_input("Quantidade", min_value=0.0, step=1.0)
            resp = st.text_input("RESPONSÁVEL").upper()
            
            if st.button("Confirmar Lançamento") and resp:
                try:
                    # Cálculo de saldo tratando vírgula brasileira
                    saldo_str = str(item_atual['SALDO ATUAL'].values[0]).replace(',', '.')
                    saldo_ant = float(saldo_str) if saldo_str else 0.0
                    
                    if tipo == "ENTRADA": novo_saldo = saldo_ant + qtd
                    elif tipo == "SAÍDA": novo_saldo = saldo_ant - qtd
                    else: novo_saldo = qtd
                    
                    agora = datetime.datetime.now(FUSO_HORARIO).strftime("%d/%m/%Y %H:%M")
                    
                    # Nova linha seguindo a estrutura da Imagem 6
                    nova_linha = [
                        agora, codigo_busca, item_atual['DESCRIÇÃO'].values[0],
                        str(qtd).replace('.', ','), tipo, str(round(novo_saldo, 2)).replace('.', ','),
                        "", resp, "", loc_val, link_foto or ""
                    ]
                    
                    # Gravação forçada
                    sheet.append_row(nova_linha, value_input_option='USER_ENTERED')
                    st.success("Lançamento realizado!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")

        st.subheader("📜 Histórico")
        st.dataframe(item_rows.tail(5).iloc[::-1], use_container_width=True, hide_index=True)
    else:
        st.error("Código não encontrado.")
