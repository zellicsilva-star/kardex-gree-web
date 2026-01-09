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

st.set_page_config(page_title="GREE - Kardex Web (Direto na Planilha)", page_icon="📦", layout="wide")

# --- CONEXÃO APENAS COM PLANILHA (SEM DRIVE) ---
@st.cache_resource
def conectar():
    # Removemos a necessidade da API do Drive aqui para evitar erros
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

# --- FUNÇÃO: FOTO -> TEXTO (BASE64) ---
def processar_imagem(arquivo_foto):
    try:
        image = Image.open(arquivo_foto)
        
        # Reduzir tamanho para garantir que cabe na célula do Excel/Sheets
        # 300x300 é um bom tamanho para visualização rápida sem travar a planilha
        image.thumbnail((300, 300))
        
        # Converter para JPEG com compressão
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='JPEG', quality=60)
        img_byte_arr = img_byte_arr.getvalue()
        
        # Codificar em texto
        b64_string = base64.b64encode(img_byte_arr).decode('utf-8')
        return f"data:image/jpeg;base64,{b64_string}"
    except Exception as e:
        st.error(f"Erro ao processar imagem: {e}")
        return None

# --- TELA PRINCIPAL ---
st.title("📦 GREE - Kardex (Modo Planilha)")
st.caption("ℹ️ Sistema rodando em modo independente (Fotos salvas na célula)")

codigo_busca = st.text_input("ESCANEIE OU DIGITE O CÓDIGO:", "").upper().strip()

if codigo_busca:
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
            # Tenta ler a foto (funciona tanto para Link quanto para Base64)
            foto_existente = item_atual['FOTO'].values[0] if 'FOTO' in item_atual.columns else None
            
            if foto_existente and len(str(foto_existente)) > 10:
                st.image(foto_existente, use_container_width=True)
            else:
                st.info("📸 Sem foto cadastrada.")
                nova_foto = st.camera_input("Cadastrar Foto Agora")
                
                if nova_foto:
                    with st.spinner("Salvando na planilha..."):
                        # Processa a imagem
                        img_texto = processar_imagem(nova_foto)
                        
                        if img_texto:
                            # Salva na coluna 11 (K)
                            cell = sheet.find(codigo_busca)
                            sheet.update_cell(cell.row, 11, img_texto) 
                            st.success("Foto salva!")
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
                    
                    # Usa a foto atual (seja link antigo ou base64 novo)
                    foto_para_salvar = foto_existente or ""
                    
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
                        foto_para_salvar
                    ]
                    
                    sheet.append_row(nova_linha, value_input_option='USER_ENTERED')
                    st.success("✅ Registrado com sucesso!")
                    st.rerun()
                else:
                    st.warning("⚠️ Preencha o Responsável.")

        # --- HISTÓRICO ---
        st.subheader("📜 Histórico Recente")
        hist = item_rows.tail(5).iloc[::-1].copy()
        
        colunas_v = ['DATA', 'VALOR MOV.', 'TIPO MOV.', 'SALDO ATUAL', 'REQUISIÇÃO', 'RESPONSÁVEL']
        # Garante que só pega colunas que existem
        cols_existentes = [c for c in colunas_v if c in hist.columns]
        hist_final = hist[cols_existentes]

        if 'DATA' in hist_final.columns:
            hist_final['DATA'] = hist_final['DATA'].apply(lambda x: str(x).split(' ')[0])

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
        st.error("Código não encontrado na planilha.")
