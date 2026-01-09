# --- HISTÓRICO REESTRUTURADO E COLORIDO ---
        st.subheader("📜 Histórico Recente")
        hist = item_rows.tail(5).iloc[::-1].copy()
        
        # Limpa a data para exibir apenas DD/MM/AAAA
        hist['DATA'] = hist['DATA'].apply(lambda x: str(x).split(' ')[0])
        
        # Define a ordem das colunas
        colunas_v = ['DATA', 'VALOR MOV.', 'SALDO ATUAL', 'TIPO MOV.', 'RESPONSÁVEL']
        hist_final = hist[colunas_v]

        # Função para colorir a linha toda baseada na coluna 'TIPO MOV.'
        def colorir_movimentacao(row):
            if row['TIPO MOV.'] == 'SAÍDA':
                return ['color: #d32f2f; font-weight: bold'] * len(row)  # Vermelho GREE
            elif row['TIPO MOV.'] == 'ENTRADA':
                return ['color: #2e7d32; font-weight: bold'] * len(row)  # Verde
            return [''] * len(row)

        # Exibe a tabela com o estilo aplicado
        st.dataframe(
            hist_final.style.apply(colorir_movimentacao, axis=1),
            hide_index=True, 
            use_container_width=True
        )
