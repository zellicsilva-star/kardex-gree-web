import streamlit as st
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload 
import datetime
import pytz
import io
import time 
from PIL import Image 
from supabase import create_client 

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
        st.error("Credenciais do Google não encontradas nos Secrets.")
        st.stop()
    if "SUPABASE_URL" not in st.secrets:
        st.error("Credenciais do Supabase (URL) não encontradas.")
        st.stop()
        
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    
    client = gspread.authorize(creds)
    planilha = client.open_by_key(ID_PLANILHA).sheet1
    drive = build('drive', 'v3', credentials=creds)
    
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        supabase = create_client(url, key)
    except Exception as e:
        st.error(f"Erro ao conectar Supabase: {e}")
        st.stop()
    
    return planilha, drive, supabase

try:
    sheet, drive_service, supabase = conectar()
except Exception as e:
    st.error(f"Erro de Conexão: {e}")
    st.stop()

# --- FUNÇÃO DE LOG SUPABASE ---
def log_supabase(dados):
    try:
        # Tabela: Kardex_Online
        supabase.table("Kardex_Online").insert(dados).execute()
    except Exception as e:
        st.warning(f"⚠️ Salvo no Excel, mas falha no Supabase: {e}")

# --- FUNÇÕES AUXILIARES ---
def upload_foto(arquivo, codigo):
    try:
        file_metadata = {'name': f"foto_{codigo}.png", 'parents': [ID_PASTA_FOTOS]}
        media = MediaIoBaseUpload(io.BytesIO(arquivo.getvalue()), mimetype='image/png')
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id', supportsAllDrives=True).execute()
        return f"https://drive.google.com/uc?export=view&id={file.get('id')}"
    except Exception as e:
        st.error(f"Erro no Upload: {e}")
        return None

def baixar_imagem_drive(link_planilha):
    if not link_planilha: return None
    try:
        file_id = None
        url = str(link_planilha).strip()
        if "id=" in url: file_id = url.split("id=")[1].split("&")[0]
        elif "/d/" in url: file_id = url.split("/d/")[1].split("/")[0]
        if not file_id: return None
        request = drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False: status, done = downloader.next_chunk()
        return fh.getvalue()
    except Exception: return None

def limpar_link(valor):
    v = str(valor).strip()
    if v.startswith('=IMAGE("'): return v[8:-2]
    return v

# --- INTERFACE ---
st.title("📦 GREE - Kardex Digital Web")

codigo_busca = st.text_input("ESCANEIE OU DIGITE O CÓDIGO:").upper().strip()

# Carrega Dados
dados_planilha = sheet.get_all_values()
df = pd.DataFrame(dados_planilha[1:], columns=dados_planilha[0])

if codigo_busca:
    df['CÓDIGO'] = df['CÓDIGO'].astype(str).str.strip()
    item_rows = df[df['CÓDIGO'] == codigo_busca]
    
    if not item_rows.empty:
        item_atual = item_rows.tail(1)
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"##### DESCRIÇÃO: {item_atual['DESCRIÇÃO'].values[0]}")
            st.metric("SALDO KARDEX", item_atual['SALDO ATUAL'].values[0])
            st.write(f"**Localização:** {item_atual['LOCALIZAÇÃO'].values[0]}")
            
            with st.expander("✏️ Editar Localização"):
                nova_loc = st.text_input("Nova Localização", value=item_atual['LOCALIZAÇÃO'].values[0]).upper()
                if st.button("Salvar Localização"):
                    try:
                        linha = item_atual.index[0] + 2
                        col = dados_planilha[0].index('LOCALIZAÇÃO') + 1
                        sheet.update_cell(linha, col, nova_loc)
                        st.toast("Localização atualizada!"); time.sleep(1); st.rerun()
                    except Exception as e: st.error(f"Erro: {e}")

        with col2:
            link_foto = limpar_link(item_atual['FOTO'].values[0] if 'FOTO' in item_atual.columns else "")
            if link_foto and len(link_foto) > 10:
                with st.spinner("Carregando imagem..."):
                    img_bytes = baixar_imagem_drive(link_foto)
                    if img_bytes:
                        try:
                            st.image(Image.open(io.BytesIO(img_bytes)).rotate(270, expand=True), use_container_width=True)
                        except: st.image(img_bytes, use_container_width=True)
            else: st.info("📸 Sem foto.")

        st.divider()

        with st.expander("📝 REGISTRAR MOVIMENTAÇÃO"):
            tipo = st.selectbox("Operação", ["SAÍDA", "ENTRADA", "INVENTÁRIO"])
            qtd = st.number_input("Quantidade", min_value=0.0, step=1.0)
            doc = st.text_input("REQUISIÇÃO/NF").upper()
            obs = st.text_input("OBSERVAÇÃO").upper()
            resp = st.text_input("RESPONSÁVEL").upper()
            
            if st.button("Confirmar Lançamento"):
                if resp:
                    try: 
                        saldo_txt = str(item_atual['SALDO ATUAL'].values[0]).replace(',', '.')
                        saldo_ant = float(saldo_txt)
                    except: saldo_ant = 0.0
                    
                    novo_saldo = (saldo_ant + qtd) if tipo == "ENTRADA" else (saldo_ant - qtd) if tipo == "SAÍDA" else qtd
                    agora = datetime.datetime.now(FUSO_HORARIO)
                    dt_fmt = agora.strftime("%d/%m/%Y %H:%M")

                    # 1. Sheets
                    nova_linha = [dt_fmt, f"'{codigo_busca}", item_atual['DESCRIÇÃO'].values[0], str(qtd).replace('.', ','), tipo, str(round(novo_saldo, 2)).replace('.', ','), doc, resp, item_atual['ARMAZÉM'].values[0], item_atual['LOCALIZAÇÃO'].values[0], "", "", "", obs]
                    sheet.append_row(nova_linha, value_input_option='USER_ENTERED')
                    
                    # 2. Supabase (CORRIGIDO PARA 'descricao')
                    log_supabase({
                        "data_mov": dt_fmt,
                        "codigo": str(codigo_busca),
                        "descricao": item_atual['DESCRIÇÃO'].values[0], # Corrigido aqui
                        "quantidade": float(qtd),
                        "tipo_mov": tipo,
                        "saldo": float(novo_saldo),
                        "documento": doc,
                        "responsavel": resp,
                        "observacao": obs
                    })
                    st.toast("Sucesso!"); time.sleep(1); st.rerun()
                else: st.warning("⚠️ Preencha o Responsável.")
        
        # Histórico e Exclusão (Mantidos iguais)
        with st.expander("🗑️ EXCLUIR MOVIMENTAÇÃO"):
            opcoes = {f"{r['DATA']} | {r['TIPO MOV.']} | Qtd: {r['VALOR MOV.']}": i for i, r in item_rows.iloc[::-1].iterrows()}
            if opcoes:
                esc = st.selectbox("Registro:", list(opcoes.keys()))
                if st.button("🗑️ Excluir"):
                    try:
                        sheet.delete_rows(opcoes[esc] + 2)
                        st.toast("Excluído!"); time.sleep(1); st.rerun()
                    except Exception as e: st.error(f"Erro: {e}")
            else: st.info("Sem histórico.")

        st.subheader("📜 Histórico")
        st.dataframe(item_rows.tail(5).iloc[::-1][['DATA','TIPO MOV.','VALOR MOV.','SALDO ATUAL','RESPONSÁVEL']], hide_index=True, use_container_width=True)

    else:
        st.warning(f"⚠️ Código {codigo_busca} não encontrado.")
        with st.expander("🆕 CADASTRAR NOVO ITEM"):
            desc_novo = st.text_input("Descrição").upper()
            armazem = st.selectbox("Armazém", ["MI03", "MI05", "MP01"])
            loc = st.text_input("Localização").upper()
            saldo = st.number_input("Saldo Inicial", min_value=0.0)
            obs = st.text_input("Obs").upper()
            resp = st.text_input("Responsável").upper()
            
            if st.button("Salvar Novo Item"):
                if desc_novo and resp:
                    agora = datetime.datetime.now(FUSO_HORARIO); dt_cad = agora.strftime("%d/%m/%Y %H:%M")
                    sheet.append_row([dt_cad, f"'{codigo_busca}", desc_novo, str(saldo), "ENTRADA", str(saldo), "CADASTRO", resp, armazem, loc, "", "", "", obs], value_input_option='USER_ENTERED')
                    
                    # Supabase (CORRIGIDO PARA 'descricao')
                    log_supabase({
                        "data_mov": dt_cad, "codigo": str(codigo_busca), "descricao": desc_novo,
                        "quantidade": float(saldo), "tipo_mov": "ENTRADA", "saldo": float(saldo),
                        "documento": "CADASTRO", "responsavel": resp, "armazem": armazem,
                        "localizacao": loc, "observacao": obs
                    })
                    st.success("Cadastrado!"); time.sleep(2); st.rerun()
