import streamlit as st
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
import datetime
import pytz
from PIL import Image
import io
import base64
import time

# --- CONFIGURAÇÕES ---
ID_PLANILHA = "1Z5lmqhYJVo1SvNUclNPQ88sGmI7en5dBS3xfhj_7TrU"
FUSO_HORARIO = pytz.timezone('America/Manaus')

st.set_page_config(page_title="GREE - Kardex Web", page_icon="📦", layout="wide")

# --- CONEXÃO COM GOOGLE SHEETS ---
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

# FUNÇÃO PARA FOTO ULTRA LEVE (EVITA BLOQUEIO DA API)
def processar_foto_mini(arquivo_foto):
    try:
        img = Image.open(arquivo_foto)
        # Reduz para 200px (tamanho de um ícone grande) para não sobrecarregar a planilha
        img.thumbnail((200, 200)) 
        buffer = io.BytesIO()
        # Salva com compressão alta
        img.save(buffer, format="JPEG", quality=40) 
        return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()
    except Exception as e:
        st.error(f"Erro ao processar imagem: {e}")
        return None

st.title("📦 GREE - Kardex Digital")

codigo_busca = st.text_input("ESCANEIE OU DIGITE O CÓDIGO:", "").upper().strip()

if codigo_busca:
    try:
        # Busca dados com proteção contra erro de limite de cota da API
        dados = sheet.get_all_values()
        df = pd.DataFrame(dados[1:], columns=dados[0])
        item = df[df['CÓDIGO'] == codigo_busca]
        
        if not item.empty:
            item_atual = item.tail(1)
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric("SALDO ATUAL", item_atual['SALDO ATUAL'].values[0])
                st.write(f"**Descrição:** {item_atual['DESCRIÇÃO'].values[0]}")
                st.write(f"**Localização:** {item_atual['LOCALIZAÇÃO'].values[0]}")
                
            with col2:
                foto_salva = item_atual['FOTO'].values[0] if 'FOTO' in item_atual.columns else ""
                
                if len(str(foto_salva)) > 100:
                    st.image(foto_salva, caption="Imagem do Produto", use_container_width=True)
                else:
                    st.warning("📸 Sem foto cadastrada.")
                    nova_foto = st.camera_input("Capturar Foto")
                    if nova_foto:
                        with st.spinner("Salvando..."):
                            img_base64 = processar_foto_mini(nova_foto)
                            if img_base64:
                                # Acha a linha e atualiza a Coluna K (11)
                                cell = sheet.find(codigo_busca)
                                # Espera 1 segundo para não travar a API do Google
                                time.sleep(1)
                                sheet.update_cell(cell.row, 11, img_base64)
                                st.success("Foto salva com sucesso!")
                                time.sleep(1)
                                st.rerun()

            st.divider()
            # Seção de Movimentação (Simplificada para teste)
            with st.expander("📝 REGISTRAR MOVIMENTAÇÃO"):
                st.write("Deseja registrar entrada ou saída?")
                if st.button("Sim, registrar"):
                    st.info("Funcionalidade de registro pronta para uso.")

        else:
            st.error("Código não encontrado.")
    except gspread.exceptions.APIError as e:
        st.error("O Google está processando muitas informações. Aguarde 30 segundos e tente novamente.")
    except Exception as e:
        st.error(f"Erro inesperado: {e}")
