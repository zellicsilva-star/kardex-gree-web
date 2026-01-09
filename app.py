import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

st.title("🕵️‍♂️ Teste de Diagnóstico do Drive")

# 1. Mostra quem o Streamlit ACHA que é o robô
try:
    creds_dict = st.secrets["gcp_service_account"]
    email_robo = creds_dict.get("client_email", "Não encontrado")
    st.info(f"🤖 O Robô configurado nos Secrets é: **{email_robo}**")
except Exception as e:
    st.error(f"Erro ao ler Secrets: {e}")
    st.stop()

# 2. Configura a Pasta (Use o ID da pasta NOVA que você criou)
ID_PASTA = st.text_input("Cole o ID da Pasta Nova aqui:", "1JrfpzjrhzvjHwpZkxKi162reL9nd5uAC")

if st.button("Tentar Criar Arquivo de Teste"):
    try:
        # Conexão
        creds = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        drive_service = build('drive', 'v3', credentials=creds)

        # Tenta criar um arquivo de texto simples
        file_metadata = {
            'name': 'teste_de_conexao.txt',
            'parents': [ID_PASTA]
        }
        media = MediaIoBaseUpload(io.BytesIO(b"Ola, eu sou o robo e estou funcionando!"), mimetype='text/plain')

        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True
        ).execute()

        st.success(f"✅ SUCESSO! O robô conseguiu criar o arquivo. ID: {file.get('id')}")
        st.balloons()

    except Exception as e:
        st.error(f"❌ FALHA: {e}")
        st.write("---")
        st.warning("O que isso significa:")
        error_msg = str(e)
        if "Insufficient permissions" in error_msg:
            st.markdown(f"""
            O robô **{email_robo}** não tem permissão de **EDITOR** na pasta **{ID_PASTA}**.
            1. Copie o e-mail azul acima.
            2. Vá na pasta {ID_PASTA} no Drive.
            3. Adicione ele como EDITOR.
            """)
        elif "quota" in error_msg.lower():
             st.markdown("O robô está sem espaço (Quota Exceeded).")
        else:
            st.markdown("Erro desconhecido. Verifique se a API do Drive está ativada no console.")
