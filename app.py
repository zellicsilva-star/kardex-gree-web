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
from supabase import create_client # [ADICIONADO] Biblioteca do Supabase

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
    
    # --- [ADICIONADO] CONEXÃO SUPABASE ---
    # Se der erro aqui, verifique se SUPABASE_URL e SUPABASE_KEY estão no Advanced Settings
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        supabase = create_client(url, key)
    except Exception as e:
        st.error(f"Erro nos Secrets do Supabase: {e}")
        st.stop()
    
    return planilha, drive, supabase # [ALTERADO] Retorna supabase também

try:
    sheet, drive_service, supabase = conectar() # [ALTERADO] Recebe supabase
except Exception as e:
    st.error(f"Erro de Conexão: {e}")
    st.stop()

# --- [ADICIONADO] FUNÇÃO DE LOG SUPABASE ---
def log_supabase(dados):
    try:
        # Envia para a tabela Kardex_Online
        supabase.table("Kardex_Online").insert(dados).execute()
    except Exception as e:
        st.warning(f"⚠️ Salvo no Excel, mas falha no Supabase: {e}")

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

# --- NOVA FUNÇÃO: BAIXAR IMAGEM ---
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

# Carregamento global de dados
dados = sheet.get_all_values()
df = pd.DataFrame(dados[1:], columns=dados[0])

if codigo_busca:
    df['CÓDIGO'] = df['CÓDIGO'].astype(str).str.strip()
    item_rows = df[df['CÓDIGO'] == codigo_busca]
    
    if not item_rows.empty:
        item_atual = item_rows.tail(1)
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"##### DESCRIÇÃO: {item_atual['DESCRIÇÃO'].values[0]}")
            
            c_saldo1, c_saldo2 = st.columns(2)
            with c_saldo1:
                st.metric("SALDO KARDEX", item_atual['SALDO ATUAL'].values[0])
            
            with c_saldo2:
                val_infor = item_atual['SALDO INFOR'].values[0] if 'SALDO INFOR' in item_atual.columns else "N/A"
                val_data = item_atual['ÚLTIMA ATUALIZAÇÃO'].values[0] if 'ÚLTIMA ATUALIZAÇÃO' in item_atual.columns else "---"
                st.metric("SALDO INFOR", val_infor, help=f"Sincronizado em: {val_data}")
            
            st.caption(f"🕒 **Última sincronização Infor:** {val_data}")
            st.write(f"**Localização:** {item_atual['LOCALIZAÇÃO'].values[0]}")
            
            with st.expander("✏️ Editar Localização"):
                nova_loc = st.text_input("Nova Localização", value=item_atual['LOCALIZAÇÃO'].values[0], key="edit_loc").upper()
                if st.button("Salvar Localização"):
                    try:
                        linha_planilha = item_atual.index[0] + 2
                        coluna_idx = dados[0].index('LOCALIZAÇÃO') + 1
                        sheet.update_cell(linha_planilha, coluna_idx, nova_loc)
                        st.toast("Localização atualizada com sucesso!", icon='📍')
                        time.sleep(1.5) 
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao atualizar localização: {e}")
            
        with col2:
            dado_foto_raw = item_atual['FOTO'].values[0] if 'FOTO' in item_atual.columns else None
            link_limpo = limpar_link(dado_foto_raw)
            if link_limpo and len(link_limpo) > 10:
                with st.spinner("Carregando imagem..."):
                    imagem_bytes = baixar_imagem_drive(link_limpo)
                    if imagem_bytes:
                        try:
                            img_pil = Image.open(io.BytesIO(imagem_bytes))
                            img_rotated = img_pil.rotate(270, expand=True) 
                            st.image(img_rotated, use_container_width=True)
                        except:
                            st.image(imagem_bytes, use_container_width=True)
                    else:
                        st.image(link_limpo, use_container_width=True)
            else:
                st.info("📸 Item sem foto.")

        st.divider()

        # --- REGISTRO DE MOVIMENTAÇÃO ---
        with st.expander("📝 REGISTRAR MOVIMENTAÇÃO"):
            tipo = st.selectbox("Operação", ["SAÍDA", "ENTRADA", "INVENTÁRIO"])
            qtd = st.number_input("Quantidade", min_value=0.0, step=1.0)
            doc = st.text_input("REQUISIÇÃO/NF").upper()
            obs = st.text_input("OBSERVAÇÃO").upper()  # Nova Coluna N
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
                    
                    link_foto_final = link_limpo
                    valor_foto_planilha = link_foto_final if link_foto_final else ""
                    agora = datetime.datetime.now(FUSO_HORARIO)
                    dt_planilha = agora.strftime("%d/%m/%Y %H:%M")
                    
                    # Coluna N é a 14ª coluna
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
                        valor_foto_planilha,
                        "", # Coluna L (Saldo Infor - Mantido vazio no log)
                        "", # Coluna M (Ult. Atualiz - Mantido vazio no log)
                        obs # Coluna N (OBSERVAÇÃO)
                    ]
                    
                    sheet.append_row(nova_linha, value_input_option='USER_ENTERED')
                    
                    # --- [ADICIONADO] LOG SUPABASE ---
                    log_supabase({
                        "data_mov": dt_planilha,
                        "codigo": str(codigo_busca),
                        "descricao": item_atual['DESCRIÇÃO'].values[0], # "descricao" conforme seu banco
                        "quantidade": float(qtd),
                        "tipo_mov": tipo,
                        "saldo": float(novo_saldo),
                        "documento": doc,
                        "responsavel": resp,
                        "observacao": obs
                    })
                    
                    st.toast("Movimentação registrada com sucesso!", icon='✅')
                    time.sleep(1.5) 
                    st.rerun()
                else:
                    st.warning("⚠️ Preencha o Responsável.")
        
        with st.expander("🗑️ EXCLUIR MOVIMENTAÇÃO RECENTE (CORREÇÃO)"):
            opcoes_exclusao = {
                f"{row['DATA']} | {row['TIPO MOV.']} | Qtd: {row['VALOR MOV.']} | Resp: {row['RESPONSÁVEL']}": i 
                for i, row in item_rows.iloc[::-1].iterrows() 
            }
            if not opcoes_exclusao:
                st.info("Não há registros para excluir deste item.")
            else:
                escolha = st.selectbox("Selecione o registro para excluir:", list(opcoes_exclusao.keys()))
                if st.button("🗑️ Confirmar Exclusão"):
                    index_df = opcoes_exclusao[escolha]
                    linha_para_deletar = index_df + 2
                    try:
                        sheet.delete_rows(linha_para_deletar)
                        st.toast(f"Registro excluído!", icon='🗑️')
                        time.sleep(1.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao excluir: {e}")

        # --- HISTÓRICO ---
        st.subheader("📜 Histórico Recente")
        hist = item_rows.tail(5).iloc[::-1].copy()
        
        # Inserido 'OBSERVAÇÃO' ao lado de 'REQUISIÇÃO'
        cols_desejadas = ['DATA', 'VALOR MOV.', 'TIPO MOV.', 'SALDO ATUAL', 'REQUISIÇÃO', 'OBSERVAÇÃO', 'RESPONSÁVEL']
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
        st.warning(f"⚠️ O código **{codigo_busca}** não foi encontrado.")
        with st.expander("🆕 CADASTRAR NOVO ITEM"):
            st.write("Preencha os dados para incluir este item no banco de dados.")
            desc_novo = st.text_input("Descrição do Item").upper()
            if 'ARMAZÉM' in df.columns:
                opcoes_armazem = sorted(df['ARMAZÉM'].unique().tolist())
                opcoes_armazem = [opt for opt in opcoes_armazem if opt.strip()]
            else:
                opcoes_armazem = ["MI03", "MI05", "MP01"]
            armazem_novo = st.selectbox("Armazém", opcoes_armazem)
            loc_novo = st.text_input("Localização (ex: A-01-01)").upper()
            saldo_inicial = st.number_input("Saldo Inicial", min_value=0.0, step=1.0)
            obs_novo = st.text_input("Observação Inicial").upper()
            resp_cad = st.text_input("Responsável pelo Cadastro").upper()
            
            if st.button("Salvar Novo Item"):
                if desc_novo and resp_cad:
                    try:
                        agora = datetime.datetime.now(FUSO_HORARIO)
                        dt_cad = agora.strftime("%d/%m/%Y %H:%M")
                        nova_linha_cad = [
                            dt_cad, f"'{codigo_busca}", desc_novo,
                            str(saldo_inicial).replace('.', ','), "ENTRADA", 
                            str(saldo_inicial).replace('.', ','), "CADASTRO INICIAL",
                            resp_cad, armazem_novo, loc_novo, "", "", "", obs_novo
                        ]
                        sheet.append_row(nova_linha_cad, value_input_option='USER_ENTERED')
                        
                        # --- [ADICIONADO] LOG SUPABASE ---
                        log_supabase({
                            "data_mov": dt_cad,
                            "codigo": str(codigo_busca),
                            "descricao": desc_novo,
                            "quantidade": float(saldo_inicial),
                            "tipo_mov": "ENTRADA",
                            "saldo": float(saldo_inicial),
                            "documento": "CADASTRO INICIAL",
                            "responsavel": resp_cad,
                            "observacao": obs_novo
                        })

                        st.success("Item cadastrado com sucesso!")
                        time.sleep(2)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao cadastrar: {e}")
                else:
                    st.error("Preencha a Descrição e o Responsável.")
