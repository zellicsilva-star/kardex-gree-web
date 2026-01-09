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
    # Limpeza profunda dos cabeçalhos para evitar erros de busca
    cabecalhos = [str(c).strip().upper() for c in dados[0]]
    df = pd.DataFrame(dados[1:], columns=cabecalhos)
    
    # Filtra o item
    item_rows = df[df['CÓDIGO'].str.strip() == codigo_busca]
    
    if not item_rows.empty:
        item_atual = item_rows.tail(1)
        # Índice real na lista 'dados' (DataFrame index + 1 para compensar o cabeçalho)
        idx_dados = item_atual.index[0] + 1
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("SALDO ATUAL", item_atual['SALDO ATUAL'].values[0])
            st.write(f"**Descrição:** {item_atual['DESCRIÇÃO'].values[0]}")
            
            # --- BUSCA ROBUSTA DA LOCALIZAÇÃO ---
            # Tenta encontrar a coluna J (índice 9) diretamente nos dados brutos
            try:
                loc_val = dados[idx_dados][9] if len(dados[idx_dados]) > 9 else "Não informada"
            except:
                loc_val = "Não informada"
            
            st.info(f"📍 **Localização:** {loc_val}")
        
        with col2:
            # Verifica se existe coluna FOTO e se tem conteúdo
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
                            st.error("Erro ao vincular foto.")

        st.divider()
        
        with st.expander("📝 REGISTRAR MOVIMENTAÇÃO"):
            tipo = st.selectbox("Operação", ["SAÍDA", "ENTRADA", "INVENTÁRIO"])
            qtd = st.number_input("Quantidade", min_value=0.0, step=1.0)
            resp = st.text_input("RESPONSÁVEL").upper()
            
            if st.button("Confirmar Lançamento") and resp:
                try:
                    # Garante que o saldo seja tratado como número decimal
                    val_saldo = str(item_atual['SALDO ATUAL'].values[0]).replace(',', '.')
                    saldo_ant = float(val_saldo) if val_saldo.strip() != "" else 0.0
                    
                    if tipo == "ENTRADA": novo_saldo = saldo_ant + qtd
                    elif tipo == "SAÍDA": novo_saldo = saldo_ant - qtd
                    else: novo_saldo = qtd 
                    
                    data_p = datetime.datetime.now(FUSO_HORARIO).strftime("%d/%m/%Y %H:%M")
                    
                    # Cria a nova linha convertendo valores para o formato do Sheets (Vírgula para decimal)
                    nova_linha = [
                        str(data_p), 
                        str(codigo_busca), 
                        str(item_atual['DESCRIÇÃO'].values[0]), 
                        str(qtd).replace('.', ','), 
                        str(tipo), 
                        str(round(novo_saldo, 2)).replace('.', ','), 
                        "", # Req
                        str(resp), 
                        "", # Arm
                        str(loc_val), 
                        str(link_foto or "")
                    ]
                    
                    # Envia para a planilha forçando o formato de entrada do usuário
                    sheet.append_row(nova_linha, value_input_option='USER_ENTERED')
                    st.success("✅ Lançamento realizado com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro no lançamento: {e}")

        # --- HISTÓRICO ---
        st.subheader("📜 Histórico Recente")
        hist = item_rows.tail(5).iloc[::-1].copy()
        colunas_v = [c for c in ['DATA', 'VALOR MOV.', 'SALDO ATUAL', 'TIPO MOV.', 'RESPONSÁVEL'] if c in df.columns]
        
        if not hist.empty:
            def colorir(row):
                cor = 'color: #d32f2f' if row.get('TIPO MOV.') == 'SAÍDA' else 'color: #2e7d32' if row.get('TIPO MOV.') == 'ENTRADA' else ''
                return [f'{cor}; font-weight: bold'] * len(row)
            
            st.dataframe(hist[colunas_v].style.apply(colorir, axis=1), hide_index=True, use_container_width=True)
    else:
        st.error("Código não encontrado.")
