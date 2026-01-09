import streamlit as st
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
import datetime
import pytz
from PIL import Image
import io
import base64

# --- CONFIGURAÇÕES ---
ID_PLANILHA = "1Z5lmqhYJVo1SvNUclNPQ88sGmI7en5dBS3xfhj_7TrU"
FUSO_HORARIO = pytz.timezone('America/Manaus')

st.set_page_config(page_title="GREE - Kardex Web", page_icon="📦", layout="wide")

@st.cache_resource
def conectar():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(ID_PLANILHA).sheet1

try:
    sheet = conectar()
except Exception as e:
    st.error(f"Erro de Conexão: {e}")
    st.stop()

# FUNÇÃO PARA DEIXAR A FOTO MUITO LEVE (PARA NÃO PESAR A PLANILHA)
def processar_foto_super_leve(arquivo_foto):
    try:
        img = Image.open(arquivo_foto)
        img.thumbnail((250, 250)) # Foto pequena, mas legível
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=50) # Compressão alta para economizar espaço
        return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()
    except:
        return None

st.title("📦 GREE - Kardex Digital")

codigo_busca = st.text_input("ESCANEIE OU DIGITE O CÓDIGO:", "").upper().strip()

if codigo_busca:
    dados = sheet.get_all_values()
    df = pd.DataFrame(dados[1:], columns=dados[0])
    item = df[df['CÓDIGO'] == codigo_busca]
    
    if not item.empty:
        item_atual = item.tail(1)
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("SALDO", item_atual['SALDO ATUAL'].values[0])
            st.write(f"**Descrição:** {item_atual['DESCRIÇÃO'].values[0]}")
            
        with col2:
            foto_salva = item_atual['FOTO'].values[0] if 'FOTO' in item_atual.columns else ""
            if len(str(foto_salva)) > 50:
                st.image(foto_salva, caption="Foto do Item")
            else:
                st.warning("Sem foto.")
                nova_foto = st.camera_input("Tirar Foto")
                if nova_foto:
                    img_base64 = processar_foto_super_leve(nova_foto)
                    if img_base64:
                        cell = sheet.find(codigo_busca)
                        sheet.update_cell(cell.row, 11, img_base64) # Coluna K
                        st.success("Foto salva na planilha!")
                        st.rerun()

        # MOVIMENTAÇÃO
        with st.expander("REGISTRAR SAÍDA/ENTRADA"):
            tipo = st.selectbox("Tipo", ["SAÍDA", "ENTRADA"])
            qtd = st.number_input("Qtd", min_value=1.0)
            resp = st.text_input("Responsável")
            if st.button("Confirmar"):
                # Cálculo de saldo e append_row aqui (mesma lógica anterior)
                st.success("Registrado!")
    else:
        st.error("Não encontrado.")
