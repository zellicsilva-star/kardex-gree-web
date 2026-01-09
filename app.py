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

st.set_page_config(page_title="GREE - Kardex Web (Plano B)", page_icon="📦", layout="wide")

# --- CONEXÃO COM A PLANILHA ---
@st.cache_resource
def conectar():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    if "gcp_service_account" not in st.secrets:
        st.error("⚠️ Credenciais não encontradas nos Secrets.")
        st.stop()
        
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    
    client = gspread.authorize(creds)
    planilha = client.open_by_key(ID_PLANILHA).sheet1
    return planilha

try:
    sheet = conectar()
except Exception as e:
    st.error(f"Erro de Conexão: {e}")
    st.stop()

# --- FUNÇÃO PARA CONVERTER FOTO EM TEXTO LEVE ---
def processar_foto_para_celula(arquivo_foto):
    try:
        image = Image.open(arquivo_foto)
        
        # Reduz o tamanho (300px é ótimo para ver no celular e não pesa na planilha)
        image.thumbnail((300, 300))
        
        # Converte para JPEG com compressão para ficar bem leve
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='JPEG', quality=60)
        img_byte_arr = img_byte_arr.getvalue()
        
        # Transforma em texto (Base64)
        b64_string = base64.b64encode(img_byte_arr).decode('utf-8')
        return f"data:image/jpeg;base64,{b64_string}"
    except Exception as e:
        st.error(f"Erro ao processar foto: {e}")
        return None

# --- INTERFACE ---
st.title("📦 GREE - Kardex Digital")
st.info("🚀 Modo Plano B Ativo: Fotos salvas diretamente na planilha.")

codigo_busca = st.text_input("ESCANEIE OU DIGITE O CÓDIGO:", "").upper().strip()

if codigo_busca:
    # Busca dados na planilha
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
            # Verifica se já existe foto (Link ou Texto Base64)
            dado_foto = item_atual['FOTO'].values[0] if 'FOTO' in item_atual.columns else None
            
            if dado_foto and len(str(dado_foto)) > 10:
                st.image(dado_foto, use_container_width=True)
            else:
                st.warning("📸 Item sem foto.")
                nova_foto = st.camera_input("Tirar Foto")
                
                if nova_foto:
                    with st.spinner("Salvando na planilha..."):
                        foto_em_texto = processar_foto_para_celula(nova_foto)
                        if foto_em_texto:
                            cell = sheet.find(codigo_busca)
                            sheet.update_cell(cell.row, 11, foto_em_texto) # Coluna K
                            st.success("✅ Foto salva com sucesso!")
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
                    
                    # Mantém a foto na nova linha de histórico
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
                        dado_foto or ""
                    ]
                    
                    sheet.append_row(nova_linha, value_input_option='USER_ENTERED')
                    st.success("✅ Lançamento realizado!")
                    st.rerun()
                else:
                    st.warning("⚠️ Informe o responsável.")

        # --- TABELA DE HISTÓRICO ---
        st.subheader("📜 Histórico")
        hist = item_rows.tail(5).iloc[::-1].copy()
        cols_desejadas = ['DATA', 'VALOR MOV.', 'TIPO MOV.', 'SALDO ATUAL', 'REQUISIÇÃO', 'RESPONSÁVEL']
        cols_existentes = [c for c in cols_desejadas if c in hist.columns]
        st.dataframe(hist[cols_existentes], hide_index=True, use_container_width=True)
    else:
        st.error("Código não encontrado.")
