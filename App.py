import streamlit as st
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import datetime
import pytz
import io

# --- CONFIGURAÇÕES DE ID ---
ID_PLANILHA = "1Z5lmqhYJVo1SvNUclNPQ88sGmI7en5dBS3xfhj_7TrU"
ID_PASTA_FOTOS = "1AFLfBEVqnJfGRJnCNvE7BC5k2puAY366"
FUSO_HORARIO = pytz.timezone('America/Manaus')

st.set_page_config(page_title="GREE - Kardex Web", page_icon="📦", layout="wide")

# --- CONEXÃO COM GOOGLE SERVICES (ESCOPOS ATUALIZADOS) ---
@st.cache_resource
def conectar():
    # Adicionado escopos específicos de escrita e criação de arquivos
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/spreadsheets"
    ]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    
    client = gspread.authorize(creds)
    planilha = client.open_by_key(ID_PLANILHA).sheet1
    
    # Construção do serviço do Drive para Upload
    drive = build('drive', 'v3', credentials=creds)
    
    return planilha, drive

sheet, drive_service = conectar()

# --- FUNÇÃO DE UPLOAD MELHORADA ---
def upload_foto(arquivo, codigo):
    try:
        file_metadata = {
            'name': f"foto_{codigo}.png",
            'parents': [ID_PASTA_FOTOS]
        }
        media = MediaIoBaseUpload(io.BytesIO(arquivo.getvalue()), mimetype='image/png')
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        # Link direto para visualização (UC = User Content)
        return f"https://drive.google.com/uc?id={file.get('id')}"
    except Exception as e:
        st.error(f"Erro técnico no Drive: {e}")
        return None

# --- TELA PRINCIPAL ---
st.title("📦 GREE - Kardex Digital Web")
codigo_busca = st.text_input("ESCANEIE OU DIGITE O CÓDIGO:", "").upper().strip()

if codigo_busca:
    dados = sheet.get_all_values()
    df = pd.DataFrame(dados[1:], columns=dados[0])
    item_rows = df[df['CÓDIGO'] == codigo_busca]
    
    if not item_rows.empty:
        item_atual = item_rows.tail(1)
        
        # --- EXIBIÇÃO DO ITEM ---
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
                st.info("Item sem foto no catálogo.")
                nova_foto = st.camera_input("Cadastrar Foto")
                if nova_foto:
                    with st.spinner('Enviando foto para o Drive...'):
                        url = upload_foto(nova_foto, codigo_busca)
                        if url:
                            # Atualiza a coluna 11 (FOTO) na linha correspondente
                            try:
                                cell = sheet.find(codigo_busca)
                                sheet.update_cell(cell.row, 11, url) 
                                st.success("Foto salva com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao atualizar planilha: {e}")
                        else:
                            st.error("Falha no upload. Verifique as permissões da pasta e se a API está ativa.")

        st.divider()

        # --- REGISTRO DE MOVIMENTAÇÃO ---
        with st.expander("📝 REGISTRAR NOVA MOVIMENTAÇÃO"):
            tipo = st.selectbox("Operação", ["SAÍDA", "ENTRADA", "INVENTÁRIO"])
            qtd = st.number_input("Quantidade", min_value=0.0, step=1.0)
            doc = st.text_input("REQUISIÇÃO/NF").upper()
            resp = st.text_input("RESPONSÁVEL").upper()
            
            if st.button("Confirmar Lançamento"):
                if resp:
                    try:
                        # Tratamento para ler números com vírgula ou ponto
                        valor_limpo = str(item_atual['SALDO ATUAL'].values[0]).replace('.', '').replace(',', '.')
                        saldo_ant = float(valor_limpo)
                    except:
                        saldo_ant = 0.0
                        
                    if tipo == "ENTRADA": novo_saldo = saldo_ant + qtd
                    elif tipo == "SAÍDA": novo_saldo = saldo_ant - qtd
                    else: novo_saldo = qtd 
                    
                    agora = datetime.datetime.now(FUSO_HORARIO)
                    dt_planilha = agora.strftime("%d/%m/%Y %H:%M")
                    
                    nova_linha = [
                        dt_planilha, codigo_busca, item_atual['DESCRIÇÃO'].values[0],
                        qtd, tipo, round(novo_saldo, 2),
                        doc, resp, item_atual['ARMAZÉM'].values[0], item_atual['LOCALIZAÇÃO'].values[0],
                        link_foto or ""
                    ]
                    sheet.append_row(nova_linha)
                    st.success("Movimentação registrada!")
                    st.rerun()
                else:
                    st.warning("Por favor, preencha o nome do Responsável.")

        # --- HISTÓRICO REESTRUTURADO E COLORIDO ---
        st.subheader("📜 Histórico Recente")
        hist = item_rows.tail(5).iloc[::-1].copy()
        
        # Formata data (remove horário da exibição)
        hist['DATA'] = hist['DATA'].apply(lambda x: str(x).split(' ')[0])
        
        # Colunas na ordem exata: DATA | VALOR MOV. | SALDO ATUAL | TIPO MOV. | RESPONSÁVEL
        colunas_v = ['DATA', 'VALOR MOV.', 'SALDO ATUAL', 'TIPO MOV.', 'RESPONSÁVEL']
        hist_final = hist[colunas_v]

        def style_rows(row):
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
        st.error("Código não encontrado na planilha LOGIX.")
