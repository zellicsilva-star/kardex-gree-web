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
# IMPORTANTE: Use seu email pessoal aqui para as fotos funcionarem
SEU_EMAIL_DONO_DRIVE = "seu-email@gmail.com" 

st.set_page_config(page_title="GREE - Kardex Web", page_icon="📦", layout="wide")

@st.cache_resource
def conectar_banco():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
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
        file_metadata = {'name': f"foto_{codigo}.png", 'parents': [ID_PASTA_FOTOS]}
        media = MediaIoBaseUpload(io.BytesIO(arquivo.getvalue()), mimetype='image/png')
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id', supportsAllDrives=True).execute()
        file_id = file.get('id')
        try:
            drive_service.permissions().create(
                fileId=file_id,
                body={'type': 'user', 'role': 'owner', 'emailAddress': SEU_EMAIL_DONO_DRIVE},
                transferOwnership=True, supportsAllDrives=True
            ).execute()
        except: pass
        return f"https://drive.google.com/uc?id={file_id}"
    except: return None

# --- INTERFACE ---
st.title("📦 GREE - Kardex Digital Web")
codigo_busca = st.text_input("ESCANEIE OU DIGITE O CÓDIGO:", "").upper().strip()

if codigo_busca:
    # Pegamos os valores brutos para não depender de nomes de colunas que podem mudar
    dados_brutos = sheet.get_all_values()
    
    if len(dados_brutos) > 1:
        # Criamos o DataFrame
        df = pd.DataFrame(dados_brutos[1:], columns=dados_brutos[0])
        
        # Filtramos pelo código (Coluna B - índice 1)
        # Usamos .values para garantir que pegamos a linha bruta da planilha
        item_rows = [linha for linha in dados_brutos if linha[1].strip().upper() == codigo_busca]
        
        if item_rows:
            # Pega a última linha encontrada (mais recente)
            linha_atual = item_rows[-1]
            
            # MAPEAMENTO POR ÍNDICE (A=0, B=1, C=2, D=3, E=4, F=5, G=6, H=7, I=8, J=9, K=10)
            # Se a ordem da sua planilha for a padrão:
            desc = linha_atual[2] if len(linha_atual) > 2 else "Sem descrição"
            saldo = linha_atual[5] if len(linha_atual) > 5 else "0"
            local = linha_atual[9] if len(linha_atual) > 9 else "Não informada"
            foto_link = linha_atual[10] if len(linha_atual) > 10 else ""

            col1, col2 = st.columns(2)
            with col1:
                st.metric("SALDO ATUAL", saldo)
                st.write(f"**Descrição:** {desc}")
                # LOCALIZAÇÃO ABAIXO DA DESCRIÇÃO
                st.warning(f"📍 **Localização:** {local}")
            
            with col2:
                if foto_link and "http" in str(foto_link):
                    st.image(foto_link, use_container_width=True)
                else:
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
                resp = st.text_input("RESPONSÁVEL").upper()
                
                if st.button("Confirmar Lançamento") and resp:
                    try:
                        saldo_ant = float(str(saldo).replace(',', '.'))
                    except:
                        saldo_ant = 0.0
                    
                    if tipo == "ENTRADA": novo_saldo = saldo_ant + qtd
                    elif tipo == "SAÍDA": novo_saldo = saldo_ant - qtd
                    else: novo_saldo = qtd
                    
                    data_p = datetime.datetime.now(FUSO_HORARIO).strftime("%d/%m/%Y %H:%M")
                    
                    # Salva respeitando a estrutura: Data(0), Cod(1), Desc(2), Qtd(3), Tipo(4), Saldo(5), Req(6), Resp(7), Arm(8), Local(9), Foto(10)
                    nova_linha = [data_p, codigo_busca, desc, qtd, tipo, round(novo_saldo, 2), "", resp, "", local, foto_link]
                    
                    try:
                        sheet.append_row(nova_linha)
                        st.success("Lançado com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")

            # Histórico (Baseado no DataFrame para facilitar visualização)
            st.subheader("📜 Histórico Recente")
            df.columns = [c.strip().upper() for c in df.columns]
            hist_df = df[df['CÓDIGO'] == codigo_busca].tail(5).iloc[::-1]
            
            colunas_v = ['DATA', 'VALOR MOV.', 'TIPO MOV.', 'SALDO ATUAL', 'RESPONSÁVEL']
            colunas_existentes = [c for c in colunas_v if c in df.columns]
            
            st.dataframe(hist_df[colunas_existentes], hide_index=True, use_container_width=True)
        else:
            st.error(f"Código '{codigo_busca}' não encontrado.")
    else:
        st.warning("Planilha vazia.")
