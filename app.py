import streamlit as st
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
import datetime
import pytz
import time

# --- CONFIGURAÇÕES ---
ID_PLANILHA = "1Z5lmqhYJVo1SvNUclNPQ88sGmI7en5dBS3xfhj_7TrU"
FUSO_HORARIO = pytz.timezone('America/Manaus')

st.set_page_config(page_title="GREE - Kardex Digital", page_icon="📦", layout="wide")

# --- CONEXÃO ---
@st.cache_resource
def conectar():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(ID_PLANILHA).sheet1

try:
    sheet = conectar()
except Exception as e:
    st.error(f"Erro ao conectar com a planilha: {e}")
    st.stop()

# --- INTERFACE ---
st.title("📦 GREE - Controle de Kardex")
st.subheader("Consulta e Movimentação de Estoque")

codigo_busca = st.text_input("ESCANEIE OU DIGITE O CÓDIGO DO ITEM:", "").upper().strip()

if codigo_busca:
    try:
        # Busca todos os dados
        dados = sheet.get_all_values()
        df = pd.DataFrame(dados[1:], columns=dados[0])
        
        # Filtra pelo código buscado
        item_rows = df[df['CÓDIGO'] == codigo_busca]
        
        if not item_rows.empty:
            # Pega a última linha encontrada (saldo mais atual)
            item_atual = item_rows.tail(1)
            
            # Layout de exibição
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.markdown(f"### {item_atual['DESCRIÇÃO'].values[0]}")
                st.write(f"**📍 Localização:** {item_atual['LOCALIZAÇÃO'].values[0]}")
                st.write(f"**🏢 Armazém:** {item_atual['ARMAZÉM'].values[0]}")
                st.metric("SALDO ATUAL", item_atual['SALDO ATUAL'].values[0])

            with col2:
                # Se houver um link de foto na planilha, ele apenas exibe
                foto_url = item_atual['FOTO'].values[0] if 'FOTO' in item_atual.columns else ""
                if len(str(foto_url)) > 10:
                    st.image(foto_url, caption="Foto do Item", use_container_width=True)
                else:
                    st.info("💡 Sem foto cadastrada na planilha.")

            st.divider()

            # --- FORMULÁRIO DE MOVIMENTAÇÃO ---
            st.subheader("📝 Registrar Movimentação")
            with st.form("form_movimentacao", clear_on_submit=True):
                col_a, col_b = st.columns(2)
                with col_a:
                    tipo_mov = st.selectbox("Operação", ["SAÍDA", "ENTRADA", "INVENTÁRIO"])
                    quantidade = st.number_input("Quantidade", min_value=0.01, step=1.0)
                with col_b:
                    documento = st.text_input("Nº Requisição / NF").upper()
                    responsavel = st.text_input("Nome do Responsável").upper()
                
                btn_confirmar = st.form_submit_button("Confirmar Lançamento")

                if btn_confirmar:
                    if not responsavel:
                        st.warning("⚠️ Por favor, informe o responsável.")
                    else:
                        with st.spinner("Registrando..."):
                            # Cálculo do novo saldo
                            try:
                                saldo_velho = float(item_atual['SALDO ATUAL'].values[0].replace(',', '.'))
                            except:
                                saldo_velho = 0.0
                            
                            if tipo_mov == "ENTRADA":
                                novo_saldo = saldo_velho + quantidade
                            elif tipo_mov == "SAÍDA":
                                novo_saldo = saldo_velho - quantidade
                            else: # INVENTÁRIO
                                novo_saldo = quantidade

                            # Data e Hora
                            agora = datetime.datetime.now(FUSO_HORARIO)
                            data_formatada = agora.strftime("%d/%m/%Y %H:%M")

                            # Prepara a nova linha (mantendo a mesma estrutura da sua planilha)
                            nova_linha = [
                                data_formatada, 
                                codigo_busca, 
                                item_atual['DESCRIÇÃO'].values[0],
                                str(quantidade).replace('.', ','), 
                                tipo_mov, 
                                str(round(novo_saldo, 2)).replace('.', ','),
                                documento, 
                                responsavel, 
                                item_atual['ARMAZÉM'].values[0], 
                                item_atual['LOCALIZAÇÃO'].values[0],
                                foto_url # Mantém a foto que já existia
                            ]

                            # Envia para a planilha
                            sheet.append_row(nova_linha, value_input_option='USER_ENTERED')
                            
                            st.success(f"✅ {tipo_mov} de {quantidade} registrada com sucesso!")
                            time.sleep(2)
                            st.rerun()

            # --- HISTÓRICO ---
            st.subheader("📜 Últimas 5 Movimentações")
            hist = item_rows.tail(5).iloc[::-1] # Inverte para mostrar a mais recente primeiro
            st.table(hist[['DATA', 'TIPO MOV.', 'VALOR MOV.', 'SALDO ATUAL', 'RESPONSÁVEL']])

        else:
            st.error("❌ Código não encontrado na base de dados.")
    except Exception as e:
        st.error(f"Erro ao processar dados: {e}")
