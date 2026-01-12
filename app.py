import streamlit as st
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload # Adicionado Download
import datetime
import pytz
import io
from PIL import Image # <--- IMPORTAÇÃO NECESSÁRIA PARA ROTACIONAR

# --- CONFIGURAÇÕES ---
ID_PLANILHA = "1Z5lmqhYJVo1SvNUclNPQ88sGmI7en5dBS3xfhj_7TrU"
ID_PASTA_FOTOS = "1JrfpzjrhzvjHwpZkxKi162reL9nd5uAC" 
FUSO_HORARIO = pytz.timezone('America/Manaus')

st.set_page_config(page_title="GREE - Kardex Web", page_icon="📦", layout="wide")

# --- CONEXÃO ---
@st.cache_resource
def conectar():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    if "gcp_service_account" not in st.secrets:
        st.error("Credenciais não encontradas nos Secrets.")
        st.stop()
        
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    
    client = gspread.authorize(creds)
    planilha = client.open_by_key(ID_PLANILHA).sheet1
    drive = build('drive', 'v3', credentials=creds)
    
    return planilha, drive

try:
    sheet, drive_service = conectar()
except Exception as e:
    st.error(f"Erro de Conexão: {e}")
    st.stop()

# --- FUNÇÃO DE UPLOAD ---
def upload_foto(arquivo, codigo):
    try:
        file_metadata = {'name': f"foto_{codigo}.png", 'parents': [ID_PASTA_FOTOS]}
        media = MediaIoBaseUpload(io.BytesIO(arquivo.getvalue()), mimetype='image/png')
        
        file = drive_service.files().create(
            body=file_metadata, 
            media_body=media, 
            fields='id',
            supportsAllDrives=True
        ).execute()
        
        return f"https://drive.google.com/uc?export=view&id={file.get('id')}"
    except Exception as e:
        st.error(f"Erro no Upload (Drive): {e}")
        return None

# --- NOVA FUNÇÃO: BAIXAR IMAGEM (Para funcionar no Site/GitHub) ---
def baixar_imagem_drive(link_planilha):
    if not link_planilha: return None
    try:
        file_id = None
        url = str(link_planilha).strip()
        
        if "id=" in url:
            file_id = url.split("id=")[1].split("&")[0]
        elif "/d/" in url:
            file_id = url.split("/d/")[1].split("/")[0]
            
        if not file_id: return None

        request = drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        return fh.getvalue()
    except Exception:
        return None

# --- LIMPEZA DE LINK ---
def limpar_link(valor):
    v = str(valor).strip()
    if v.startswith('=IMAGE("'): return v[8:-2]
    return v

# --- INTERFACE ---
st.title("📦 GREE - Kardex Digital Web")

# --- LÓGICA DE QR CODE ---
query_params = st.query_params
codigo_url = query_params.get("codigo", "")

codigo_busca = st.text_input("ESCANEIE OU DIGITE O CÓDIGO:", value=codigo_url).upper().strip()

if codigo_busca:
    # Busca dados
    dados = sheet.get_all_values()
    df = pd.DataFrame(dados[1:], columns=dados[0])
    
    df['CÓDIGO'] = df['CÓDIGO'].astype(str).str.strip()
    item_rows = df[df['CÓDIGO'] == codigo_busca]
    
    if not item_rows.empty:
        item_atual = item_rows.tail(1)
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"##### DESCRIÇÃO: {item_atual['DESCRIÇÃO'].values[0]}")
            st.metric("SALDO ATUAL", item_atual['SALDO ATUAL'].values[0])
            st.write(f"**Localização:** {item_atual['LOCALIZAÇÃO'].values[0]}")
            
            with st.expander("✏️ Editar Localização"):
                nova_loc = st.text_input("Nova Localização", value=item_atual['LOCALIZAÇÃO'].values[0], key="edit_loc").upper()
                if st.button("Salvar Localização"):
                    try:
                        linha_planilha = item_atual.index[0] + 2
                        coluna_idx = dados[0].index('LOCALIZAÇÃO') + 1
                        sheet.update_cell(linha_planilha, coluna_idx, nova_loc)
                        st.success("Localização atualizada com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao atualizar localização: {e}")
            
        with col2:
            # --- VISUALIZAÇÃO ATRAVÉS DO DRIVE (FUNCIONAL NO SITE) ---
            dado_foto_raw = item_atual['FOTO'].values[0] if 'FOTO' in item_atual.columns else None
            link_limpo = limpar_link(dado_foto_raw)
            
            if link_limpo and len(link_limpo) > 10:
                with st.spinner("Carregando imagem..."):
                    imagem_bytes = baixar_imagem_drive(link_limpo)
                    if imagem_bytes:
                        # --- ÁREA DE ROTAÇÃO ---
                        try:
                            # Abre a imagem usando PIL a partir dos bytes baixados
                            img_pil = Image.open(io.BytesIO(imagem_bytes))
                            # Rotaciona 90 graus (ajuste para 270 ou -90 se ficar de cabeça para baixo)
                            # expand=True garante que a imagem inteira apareça após rodar
                            img_rotated = img_pil.rotate(90, expand=True) 
                            st.image(img_rotated, use_container_width=True)
                        except:
                             # Se der erro na rotação, mostra a original
                            st.image(imagem_bytes, use_container_width=True)
                        # -----------------------
                    else:
                        st.image(link_limpo, use_container_width=True) # Tenta link direto se falhar
            else:
                st.info("📸 Item sem foto.")

        st.divider()

        # --- REGISTRO DE MOVIMENTAÇÃO ---
        with st.expander("📝 REGISTRAR MOVIMENTAÇÃO"):
            tipo = st.selectbox("Operação", ["SAÍDA", "ENTRADA", "INVENTÁRIO"])
            qtd = st.number_input("Quantidade", min_value=0.0, step=1.0)
            doc = st.text_input("REQUISIÇÃO/NF").upper()
            resp = st.text_input("RESPONSÁVEL").upper()
            
            nova_foto_upload = st.file_uploader("Atualizar Foto (Opcional)", type=["png", "jpg", "jpeg"])
            
            if st.button("Confirmar Lançamento"):
                if resp:
                    try:
                        saldo_ant = float(item_atual['SALDO ATUAL'].values[0].replace(',', '.'))
                    except:
                        saldo_ant = 0.0
                        
                    if tipo == "ENTRADA": novo_saldo = saldo_ant + qtd
                    elif tipo == "SAÍDA": novo_saldo = saldo_ant - qtd
                    else: novo_saldo = qtd 
                    
                    # Lógica da Foto
                    link_foto_final = link_limpo
                    
                    if nova_foto_upload:
                        with st.spinner("Enviando foto para o Drive..."):
                            link_gerado = upload_foto(nova_foto_upload, codigo_busca)
                            if link_gerado:
                                link_foto_final = link_gerado
                                
                    valor_foto_planilha = link_foto_final if link_foto_final else ""

                    agora = datetime.datetime.now(FUSO_HORARIO)
                    dt_planilha = agora.strftime("%d/%m/%Y %H:%M")
                    
                    nova_linha = [
                        dt_planilha, 
                        f"'{codigo_busca}", 
                        item_atual['DESCRIÇÃO'].values[0],
                        str(qtd).replace('.', ','), 
                        tipo, 
                        str(round(novo_saldo, 2)).replace('.', ','),
                        doc, 
                        resp, 
                        item_atual['ARMAZÉM'].values[0], 
                        item_atual['LOCALIZAÇÃO'].values[0],
                        valor_foto_planilha
                    ]
                    
                    sheet.append_row(nova_linha, value_input_option='USER_ENTERED')
                    st.success("✅ Movimentação registrada!")
                    st.rerun()
                else:
                    st.warning("⚠️ Preencha o Responsável.")

        # --- HISTÓRICO ---
        st.subheader("📜 Histórico Recente")
        hist = item_rows.tail(5).iloc[::-1].copy()
        
        cols_desejadas = ['DATA', 'VALOR MOV.', 'TIPO MOV.', 'SALDO ATUAL', 'REQUISIÇÃO', 'RESPONSÁVEL']
        cols_finais = [c for c in cols_desejadas if c in hist.columns]
        
        if 'DATA' in hist.columns:
             hist['DATA'] = hist['DATA'].apply(lambda x: str(x).split(' ')[0])
             
        hist_final = hist[cols_finais]

        def style_rows(row):
            if 'TIPO MOV.' in row:
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
        st.error("Código não encontrado.")
