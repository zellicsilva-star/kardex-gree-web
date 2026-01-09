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
    # Busca dados atualizados da planilha
    dados = sheet.get_all_values()
    cabecalhos = [str(c).strip().upper() for c in dados[0]]
    df = pd.DataFrame(dados[1:], columns=cabecalhos)
    
    # Filtra o item ignorando espaços
    item_rows = df[df['CÓDIGO'].str.strip() == codigo_busca]
    
    if not item_rows.empty:
        # Pega a linha mais recente
        item_atual = item_rows.tail(1)
        # Índice da linha na planilha original (dados tem cabeçalho, então +1)
        idx_original = item_atual.index[0] + 1 
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("SALDO ATUAL", item_atual['SALDO ATUAL'].values[0])
            st.write(f"**Descrição:** {item_atual['DESCRIÇÃO'].values[0]}")
            
            # --- BUSCA ROBUSTA DA LOCALIZAÇÃO (COLUNA J / ÍNDICE 9) ---
            loc_val = "Não encontrada"
            if 'LOCALIZAÇÃO' in item_atual.columns:
                loc_val = item_atual['LOCALIZAÇÃO'].values[0]
            elif 'LOCALIZACAO' in item_atual.columns:
                loc_val = item_atual['LOCALIZACAO'].values[0]
            
            # Se ainda estiver vazio, força a leitura da 10ª coluna (índice 9)
            if not loc_val or str(loc_val).strip() == "":
                try:
                    loc_val = dados[idx_original][9] 
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
                        try:
                            cell = sheet.find(codigo_busca)
                            sheet.update_cell(cell.row, 11, url) 
                            st.success("Foto salva!")
                            st.rerun()
                        except:
                            st.error("Erro ao vincular foto na planilha.")

        st.divider()
        
        with st.expander("📝 REGISTRAR MOVIMENTAÇÃO"):
            tipo = st.selectbox("Operação", ["SAÍDA", "ENTRADA", "INVENTÁRIO"])
            qtd = st.number_input("Quantidade", min_value=0.0, step=1.0)
            resp = st.text_input("RESPONSÁVEL").upper()
            
            if st.button("Confirmar Lançamento") and resp:
                try:
                    # Tratamento numérico do saldo
                    val_saldo = str(item_atual['SALDO ATUAL'].values[0]).replace(',', '.')
                    saldo_ant = float(val_saldo) if val_saldo and val_saldo != "" else 0.0
                    
                    if tipo == "ENTRADA": novo_saldo = saldo_ant + qtd
                    elif tipo == "SAÍDA": novo_saldo = saldo_ant - qtd
                    else: novo_saldo = qtd # Inventário
                    
                    data_p = datetime.datetime.now(FUSO_HORARIO).strftime("%d/%m/%Y %H:%M")
                    
                    # Montagem da linha para o Google Sheets (convertendo tudo para string para evitar erros)
                    nova_linha = [
                        str(data_p), 
                        str(codigo_busca), 
                        str(item_atual['DESCRIÇÃO'].values[0]), 
                        str(qtd), 
                        str(tipo), 
                        str(round(novo_saldo, 2)).replace('.', ','), 
                        "", # Requisição
                        str(resp), 
                        "", # Armazém
                        str(loc_val), 
                        str(link_foto or "")
                    ]
                    
                    # EXECUÇÃO DO UPLOAD
                    sheet.append_row(nova_linha, value_input_option='USER_ENTERED')
                    st.success("✅ Movimentação registrada no Google Sheets!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")

        # --- HISTÓRICO ---
        st.subheader("📜 Histórico Recente")
        hist = item_rows.tail(5).iloc[::-1].copy()
        
        # Garante que as colunas existam para o histórico
        colunas_v = [c for c in ['DATA', 'VALOR MOV.', 'SALDO ATUAL', 'TIPO MOV.', 'RESPONSÁVEL'] if c in df.columns]
        
        if not hist.empty:
            def colorir(row):
                cor = 'color: #d32f2f' if row.get('TIPO MOV.') == 'SAÍDA' else 'color: #2e7d32' if row.get('TIPO MOV.') == 'ENTRADA' else ''
                return [f'{cor}; font-weight: bold'] * len(row)
            
            st.dataframe(hist[colunas_v].style.apply(colorir, axis=1), hide_index=True, use_container_width=True)
    else:
        st.error("Código não encontrado.")
