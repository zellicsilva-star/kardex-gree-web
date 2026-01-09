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
# IMPORTANTE: Coloque seu e-mail aqui para a posse das fotos
SEU_EMAIL_DONO_DRIVE = "zellic.silva@gmail.com" 

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
        # Criamos o DataFrame e limpamos os nomes das colunas (removendo acentos e espaços)
        df = pd.DataFrame(dados[1:], columns=dados[0])
        df.columns = df.columns.str.strip().str.upper()
        
        # Localização costuma estar na Coluna J (índice 9 no Python, pois começa em 0)
        # Vamos tentar pegar pelo nome, se não existir, pegamos pela posição J
        colunas_lista = list(df.columns)
        
        df['CÓDIGO'] = df['CÓDIGO'].str.strip().str.upper()
        item_rows = df[df['CÓDIGO'] == codigo_busca]
        
        if not item_rows.empty:
            item_atual = item_rows.tail(1).to_dict('records')[0]
            
            # --- LÓGICA DA LOCALIZAÇÃO (COLUNA J) ---
            desc = item_atual.get('DESCRIÇÃO') or item_atual.get('DESCRICAO') or "Sem descrição"
            saldo = item_atual.get('SALDO ATUAL') or item_atual.get('SALDO') or "0"
            
            # Tentativa 1: Pelo nome "LOCALIZAÇÃO"
            # Tentativa 2: Pelo nome "LOCALIZACAO"
            # Tentativa 3: Pela posição física (Coluna J é a 10ª coluna, índice 9)
            local = item_atual.get('LOCALIZAÇÃO') or item_atual.get('LOCALIZACAO')
            if not local and len(colunas_lista) >= 10:
                nome_coluna_j = colunas_lista[9] # Pega o nome da 10ª coluna
                local = item_atual.get(nome_coluna_j)
            
            local = local if local else "Não informada"
            foto_link = item_atual.get('FOTO') or ""

            col1, col2 = st.columns(2)
            with col1:
                st.metric("SALDO ATUAL", saldo)
                st.info(f"📍 **Localização:** {local}")
                st.write(f"**Descrição:** {desc}")
            
            with col2:
                if foto_link and "http" in str(foto_link):
                    st.image(foto_link, caption=f"Foto de {codigo_busca}", use_container_width=True)
                else:
                    nova_foto = st.camera_input("Cadastrar Foto")
                    if nova_foto:
                        url = upload_foto(nova_foto, codigo_busca)
                        if url:
                            cell = sheet.find(codigo_busca)
                            # Atualiza a coluna 11 (K) com o link da foto
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
                    
                    # Ordem das colunas para gravar nova linha
                    nova_linha = [data_p, codigo_busca, desc, qtd, tipo, round(novo_saldo, 2), "", resp, "", local, foto_link]
                    
                    try:
                        sheet.append_row(nova_linha)
                        st.success("Lançamento realizado!")
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
            st.error(f"Código '{codigo_busca}' não encontrado.")
    else:
        st.warning("Planilha vazia.")
