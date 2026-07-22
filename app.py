import base64
import datetime
import io
import json
import mimetypes
import time

import gspread
import pandas as pd
import pytz
import requests
import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image
from supabase import create_client


# --- CONFIGURAÇÕES ---
ID_PLANILHA = "1Z5lmqhYJVo1SvNUclNPQ88sGmI7en5dBS3xfhj_7TrU"
ID_PASTA_FOTOS = "1JrfpzjrhzvjHwpZkxKi162reL9nd5uAC"
URL_APPS_SCRIPT = "https://script.google.com/macros/s/AKfycbwOBW8cCR5bgdVcqAaf78OI4dsYeWBnraM4hR4YWUzN53RjMCT-GcKa0VHtBtQvYUL_pg/exec"
FUSO_HORARIO = pytz.timezone("America/Manaus")

st.set_page_config(page_title="GREE - Kardex Web", page_icon="📦", layout="wide")


@st.cache_resource
def conectar():
    """Conecta à planilha, ao Drive e ao Supabase."""
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]

    if "gcp_service_account" not in st.secrets:
        st.error("Credenciais não encontradas nos Secrets.")
        st.stop()

    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        st.secrets["gcp_service_account"], scope
    )
    client = gspread.authorize(creds)
    sheet = client.open_by_key(ID_PLANILHA).sheet1
    drive = build("drive", "v3", credentials=creds)

    try:
        supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except Exception as erro:
        st.error(f"Erro nos Secrets do Supabase: {erro}")
        st.stop()

    return sheet, drive, supabase


try:
    sheet, drive_service, supabase = conectar()
except Exception as erro:
    st.error(f"Erro de conexão: {erro}")
    st.stop()


def log_supabase(dados):
    try:
        supabase.table("Kardex_Online").insert(dados).execute()
    except Exception as erro:
        st.warning(f"Movimentação salva na planilha, mas falhou no Supabase: {erro}")


def extrair_id_foto(valor):
    """Aceita ID puro, URL do Drive ou fórmula IMAGE da planilha."""
    if valor is None:
        return None

    texto = str(valor).strip()
    if not texto or texto.lower() in {"nan", "none"}:
        return None

    if texto.startswith('=IMAGE("'):
        texto = texto[8:-2]
    if "id=" in texto:
        return texto.split("id=", 1)[1].split("&", 1)[0]
    if "/d/" in texto:
        return texto.split("/d/", 1)[1].split("/", 1)[0]

    # A coluna K recebe o ID puro do Google Apps Script.
    return texto


def baixar_imagem_drive(valor_foto):
    """Baixa a foto pelo ID salvo na coluna FOTO (K)."""
    file_id = extrair_id_foto(valor_foto)
    if not file_id:
        return None

    try:
        request = drive_service.files().get_media(fileId=file_id)
        arquivo = io.BytesIO()
        downloader = MediaIoBaseDownload(arquivo, request)
        concluido = False
        while not concluido:
            _, concluido = downloader.next_chunk()
        return arquivo.getvalue()
    except Exception:
        # Não use o ID em st.image: ele não é uma URL nem um caminho de arquivo.
        return None


def upload_foto(arquivo, codigo):
    """Envia a foto ao Apps Script e recebe o ID criado no Drive.

    O Apps Script executa como dono da pasta, evitando a limitação de quota
    das contas de serviço usadas pelo Streamlit.
    """
    try:
        extensao = mimetypes.guess_extension(arquivo.type or "") or ".png"
        if extensao == ".jpe":
            extensao = ".jpg"

        conteudo = arquivo.getvalue()
        payload = {
            "codigo": str(codigo).strip(),
            "nome_arquivo": f"{codigo}{extensao}",
            "mime_type": arquivo.type or "image/png",
            "conteudo_base64": base64.b64encode(conteudo).decode("ascii"),
        }
        # requests segue corretamente o redirecionamento do Apps Script para
        # script.googleusercontent.com, que é onde a resposta JSON é entregue.
        resposta = requests.post(
            URL_APPS_SCRIPT,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=60,
            allow_redirects=True,
        )
        resposta.raise_for_status()

        texto_resposta = resposta.text.strip()
        if not texto_resposta:
            raise RuntimeError(
                "O Apps Script respondeu vazio. Publique uma nova implantação "
                "do Web App após salvar o Code.gs."
            )
        try:
            retorno = resposta.json()
        except ValueError:
            raise RuntimeError(
                "O Apps Script não retornou JSON. Confirme que o Web App foi "
                "implantado com o novo Code.gs e acesso para qualquer pessoa."
            )

        if not retorno.get("sucesso") or not retorno.get("id"):
            raise RuntimeError(retorno.get("erro", "O Apps Script não retornou o ID da foto."))
        return retorno["id"]
    except requests.RequestException as erro:
        st.error(f"Erro de comunicação com o Apps Script: {erro}")
        return ""
    except Exception as erro:
        st.error(f"Erro no upload da foto: {erro}")
        return ""


def atualizar_id_foto_do_material(linhas_do_item, foto_id):
    """Grava o ID na coluna K de todas as movimentações do mesmo material."""
    celulas = [
        gspread.Cell(indice + 2, 11, foto_id)
        for indice in linhas_do_item.index
    ]
    if celulas:
        sheet.update_cells(celulas, value_input_option="RAW")


def numero(valor, padrao=0.0):
    try:
        return float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return padrao


def valor_planilha(valor):
    return str(round(valor, 2)).replace(".", ",")


def inserir_movimentacao(codigo, item, tipo, quantidade, documento, responsavel, observacao):
    saldo_anterior = numero(item["SALDO ATUAL"])
    if tipo == "ENTRADA":
        novo_saldo = saldo_anterior + quantidade
    elif tipo == "SAÍDA":
        novo_saldo = saldo_anterior - quantidade
    else:
        novo_saldo = quantidade

    agora = datetime.datetime.now(FUSO_HORARIO)
    data_movimento = agora.strftime("%d/%m/%Y %H:%M")
    foto_id = extrair_id_foto(item.get("FOTO", "")) or ""

    nova_linha = [
        data_movimento,
        f"'{codigo}",
        item["DESCRIÇÃO"],
        valor_planilha(quantidade),
        tipo,
        valor_planilha(novo_saldo),
        documento,
        responsavel,
        item.get("ARMAZÉM", ""),
        item.get("LOCALIZAÇÃO", ""),
        foto_id,  # Coluna K: ID puro do Drive.
        "",
        "",
        observacao,
    ]
    sheet.append_row(nova_linha, value_input_option="USER_ENTERED")

    log_supabase({
        "data_mov": data_movimento,
        "codigo": str(codigo),
        "descricao": item["DESCRIÇÃO"],
        "quantidade": float(quantidade),
        "tipo_mov": tipo,
        "saldo": float(novo_saldo),
        "documento": documento,
        "responsavel": responsavel,
        "observacao": observacao,
    })


st.title("📦 GREE - Kardex Digital Web")
codigo_url = st.query_params.get("codigo", "")
codigo_busca = st.text_input(
    "ESCANEIE OU DIGITE O CÓDIGO:", value=codigo_url
).upper().strip()

dados = sheet.get_all_values()
if not dados:
    st.warning("A planilha está vazia.")
    st.stop()

df = pd.DataFrame(dados[1:], columns=dados[0])

if not codigo_busca:
    st.info("Informe ou escaneie o código de um material para consultar o Kardex.")
    st.stop()

df["CÓDIGO"] = df["CÓDIGO"].astype(str).str.strip().str.upper()
item_rows = df[df["CÓDIGO"] == codigo_busca]

if item_rows.empty:
    st.warning(f"O código **{codigo_busca}** não foi encontrado.")
    with st.expander("🆕 CADASTRAR NOVO ITEM"):
        descricao = st.text_input("Descrição do item").upper()
        armazens = sorted(v for v in df.get("ARMAZÉM", pd.Series(dtype=str)).unique() if str(v).strip())
        armazem = st.selectbox("Armazém", armazens or ["MI03", "MI05", "MP01"])
        localizacao = st.text_input("Localização (ex.: A-01-01)").upper()
        saldo = st.number_input("Saldo inicial", min_value=0.0, step=1.0)
        observacao = st.text_input("Observação inicial").upper()
        responsavel = st.text_input("Responsável pelo cadastro").upper()

        if st.button("Salvar novo item"):
            if not descricao or not responsavel:
                st.error("Preencha a descrição e o responsável.")
            else:
                agora = datetime.datetime.now(FUSO_HORARIO)
                data_cadastro = agora.strftime("%d/%m/%Y %H:%M")
                sheet.append_row([
                    data_cadastro, f"'{codigo_busca}", descricao, valor_planilha(saldo),
                    "ENTRADA", valor_planilha(saldo), "CADASTRO INICIAL", responsavel,
                    armazem, localizacao, "", "", "", observacao,
                ], value_input_option="USER_ENTERED")
                log_supabase({
                    "data_mov": data_cadastro, "codigo": codigo_busca,
                    "descricao": descricao, "quantidade": float(saldo),
                    "tipo_mov": "ENTRADA", "saldo": float(saldo),
                    "documento": "CADASTRO INICIAL", "responsavel": responsavel,
                    "observacao": observacao,
                })
                st.success("Item cadastrado com sucesso.")
                time.sleep(1)
                st.rerun()
    st.stop()

item_atual = item_rows.iloc[-1]
coluna_dados, coluna_foto = st.columns(2)

with coluna_dados:
    st.markdown(f"##### DESCRIÇÃO: {item_atual['DESCRIÇÃO']}")
    saldo_infor = item_atual.get("SALDO INFOR", "N/A")
    ultima_atualizacao = item_atual.get("ÚLTIMA ATUALIZAÇÃO", "---")
    saldo_kardex, saldo_infor_coluna = st.columns(2)
    saldo_kardex.metric("SALDO KARDEX", item_atual["SALDO ATUAL"])
    saldo_infor_coluna.metric("SALDO INFOR", ultima_atualizacao, help=f"Sincronizado em: {ultima_atualizacao}")
    st.write(f"**Localização:** {item_atual.get('LOCALIZAÇÃO', '')}")

    with st.expander("✏️ Editar localização"):
        nova_localizacao = st.text_input(
            "Nova localização", value=item_atual.get("LOCALIZAÇÃO", ""), key="editar_localizacao"
        ).upper()
        if st.button("Salvar localização"):
            try:
                linha = item_atual.name + 2
                coluna = dados[0].index("LOCALIZAÇÃO") + 1
                sheet.update_cell(linha, coluna, nova_localizacao)
                st.toast("Localização atualizada.", icon="📍")
                time.sleep(1)
                st.rerun()
            except Exception as erro:
                st.error(f"Erro ao atualizar localização: {erro}")

with coluna_foto:
    foto_bytes = baixar_imagem_drive(item_atual.get("FOTO", ""))
    if foto_bytes:
        try:
            imagem = Image.open(io.BytesIO(foto_bytes))
            st.image(imagem.rotate(270, expand=True), use_container_width=True)
        except Exception:
            st.image(foto_bytes, use_container_width=True)
    elif extrair_id_foto(item_atual.get("FOTO", "")):
        st.info("📷 A foto possui ID cadastrado, mas não pôde ser acessada pela conta de serviço.")
    else:
        st.info("📷 Item sem foto.")

st.divider()

with st.expander("📝 REGISTRAR MOVIMENTAÇÃO"):
    tipo = st.selectbox("Operação", ["SAÍDA", "ENTRADA", "INVENTÁRIO"])
    quantidade = st.number_input("Quantidade", min_value=0.0, step=1.0)
    documento = st.text_input("REQUISIÇÃO/NF").upper()
    observacao = st.text_input("OBSERVAÇÃO").upper()
    responsavel = st.text_input("RESPONSÁVEL").upper()

    if st.button("Confirmar lançamento"):
        if not responsavel:
            st.warning("Preencha o responsável.")
        else:
            try:
                inserir_movimentacao(
                    codigo_busca, item_atual, tipo, quantidade,
                    documento, responsavel, observacao,
                )
                st.toast("Movimentação registrada com sucesso.", icon="✅")
                time.sleep(1)
                st.rerun()
            except Exception as erro:
                st.error(f"Erro ao registrar movimentação: {erro}")

with st.expander("🗑️ EXCLUIR MOVIMENTAÇÃO (CORREÇÃO)"):
    opcoes = {
        f"{linha['DATA']} | {linha['TIPO MOV.']} | Qtd: {linha['VALOR MOV.']} | Resp: {linha['RESPONSÁVEL']}": indice
        for indice, linha in item_rows.iloc[::-1].iterrows()
    }
    if not opcoes:
        st.info("Não há registros para excluir deste item.")
    else:
        escolha = st.selectbox("Selecione o registro para excluir", list(opcoes))
        if st.button("Confirmar exclusão"):
            indice = opcoes[escolha]
            registro = item_rows.loc[indice]
            try:
                sheet.delete_rows(indice + 2)
                supabase.table("Kardex_Online").delete().eq(
                    "data_mov", registro["DATA"]
                ).eq("codigo", registro["CÓDIGO"]).execute()
                st.toast("Registro excluído.", icon="🗑️")
                time.sleep(1)
                st.rerun()
            except Exception as erro:
                st.error(f"Erro ao excluir: {erro}")

# --- HISTÓRICO: todas as movimentações, da mais recente para a mais antiga ---
st.subheader("📜 Histórico de movimentações")
historico = item_rows.iloc[::-1].copy()
colunas_desejadas = [
    "DATA", "VALOR MOV.", "TIPO MOV.", "SALDO ATUAL",
    "REQUISIÇÃO", "OBSERVAÇÃO", "RESPONSÁVEL",
]
colunas = [coluna for coluna in colunas_desejadas if coluna in historico.columns]

if "DATA" in historico.columns:
    historico["DATA"] = historico["DATA"].astype(str).str.split().str[0]

def colorir_linha(linha):
    tipo_mov = linha.get("TIPO MOV.", "")
    if tipo_mov == "SAÍDA":
        return ["color: #d32f2f; font-weight: bold"] * len(linha)
    if tipo_mov == "ENTRADA":
        return ["color: #2e7d32; font-weight: bold"] * len(linha)
    return [""] * len(linha)

st.dataframe(
    historico[colunas].style.apply(colorir_linha, axis=1),
    hide_index=True,
    use_container_width=True,
)
