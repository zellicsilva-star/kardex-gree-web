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
# IMPORTANTE: Coloque seu e-mail pessoal aqui
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
    dados = sheet.get_all_values()
    if len(dados) > 1:
        # Criamos o DataFrame e padronizamos cabeçalhos
        df = pd.DataFrame(dados[1:], columns=dados[0])
        original_cols = list(df.columns) # Guarda a ordem real das colunas (A, B, C...)
        
        df.columns = df.columns.str.strip().str.upper()
        df['CÓDIGO'] = df['CÓDIGO'].str.strip().str.upper()
        
        item_rows = df[df['CÓDIGO'] == codigo_busca]
        
        if not item_rows.empty:
            # Pega a linha mais recente
            linha_bruta = item_rows.tail(1).values[0] # Dados puros da linha
            item_dict = item_rows.tail(1).to_dict('records')[0]
            
            # 1. SALDO (Coluna F - índice 5)
            saldo = item_dict.get('SALDO ATUAL') or item_dict.get('SALDO') or "0"
            
            # 2. DESCRIÇÃO (Coluna C - índice 2)
            desc = item_dict.get('DESCRIÇÃO') or item_dict.get('DESCRICAO') or "Sem descrição"
            
            # 3. LOCALIZAÇÃO (Coluna J - índice 9)
            # Tentamos pelo nome, se falhar, pegamos direto pela posição 10 (índice 9)
            local = item_dict.get('LOCALIZAÇÃO') or item_dict.get('LOCALIZACAO')
            if (not local or local == "Não definida") and len(linha_bruta) >= 10:
                local = linha_bruta[9] # Posição exata da Coluna J

            foto_link = item_dict.get('FOTO') or ""

            col1, col2 = st.columns(2)
            with col1:
                st.metric("SALDO ATUAL", saldo)
                st.write(f"**Descrição:** {desc}")
                # Localização agora EMBAIXO da descrição
                st.info(f"📍 **Localização:** {local if local else 'Não informada'}")
            
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
                    
                    # Salva respeitando a estrutura de 11 colunas
                    nova_linha = [data_p, codigo_busca, desc, qtd, tipo, round(novo_saldo, 2), "", resp, "", local, foto_link]
                    
                    try:
                        sheet.append_row(nova_linha)
                        st.success("Lançado com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")

            st.subheader("📜 Histórico Recente")
            hist = item_rows.tail(5).iloc[::-1].copy()
            colunas_v = ['DATA', 'VALOR MOV.', 'TIPO MOV.', 'SALDO ATUAL', 'RESPONSÁVEL']
            colunas_existentes = [c for c in colunas_v if c in df.columns]
            
            def colorir(row):
                cor = 'color: #d32f2f' if row.get('TIPO MOV.') == 'SAÍDA' else 'color: #2e7d32' if row.get('TIPO MOV.') == 'ENTRADA' else ''
                return [f'{cor}; font-weight: bold'] * len(row)

            st.dataframe(hist[colunas_existentes].style.apply(colorir, axis=1), hide_index=True, use_container_width=True)
    else:
        st.error("Planilha sem dados.")
