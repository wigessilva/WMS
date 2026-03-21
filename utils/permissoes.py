# Dicionario central de permissoes dos perfis
# A chave principal representa o modulo (a "pasta"), e dentro temos as acoes especificas.
DICIONARIO_PERMISSOES = {
    "recebimento": {
        "nome": "Módulo de Recebimento",
        "acoes": {
            "rec_visualizar": "Visualizar Painel de Recebimento",
            "rec_bipar": "Bipar e Conferir Itens",
            "rec_editar_destino": "Editar Endereço de Destino",
            "rec_finalizar": "Finalizar Recebimento"
        }
    },
    "estoque": {
        "nome": "Módulo de Estoque",
        "acoes": {
            "est_visualizar": "Visualizar LPNs e Endereços",
            "est_movimentar": "Fazer Transferência de Local",
            "est_ajuste": "Ajuste de Inventário (Requer aprovação)"
        }
    },
    "sistema": {
        "nome": "Configurações e Sistema",
        "acoes": {
            "sis_usuarios": "Gerenciar Usuários e Perfis",
            "sis_parametros": "Alterar Parâmetros Globais"
        }
    }
}