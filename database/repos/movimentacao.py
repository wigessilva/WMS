from datetime import datetime
from ..base import BaseRepo


class MovementsRepo(BaseRepo):
    def __init__(self):
        super().__init__("HistoricoMovimentacoes")

    def registrar(self, **kwargs):
        usuario = kwargs.get("Usuario", "Sistema")
        tipo = kwargs.get("TipoOperacao", "")

        lpn = kwargs.get("Lpn")
        sku = kwargs.get("Sku")
        qtd = float(kwargs.get("QtdMovimentada", 0))

        origem = kwargs.get("Origem", "")
        destino = kwargs.get("Destino", "")
        doc_ref = kwargs.get("DocumentoRef", "")
        obs = kwargs.get("Obs", "")

        agora = datetime.now()

        query = """
            INSERT INTO Movimentacoes (
                DataHora, Usuario, TipoOperacao, 
                Lpn, Sku, QtdMovimentada, 
                Origem, Destino, DocumentoRef, Obs
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        self.execute_non_query(query, (
            agora, usuario, tipo,
            lpn, sku, qtd,
            origem, destino, doc_ref, obs
        ))

    def get_kardex_sku(self, sku):
        """Busca toda a história de um SKU ordem cronológica (Antigo -> Novo)"""
        query = """
            SELECT 
                DataMovimento, 
                TipoOperacao, 
                QtdMovimentada, 
                Lpn, 
                Usuario, 
                DocumentoRef 
            FROM HistoricoMovimentacoes 
            WHERE Sku = ? 
            ORDER BY DataMovimento ASC, Id ASC
        """
        return self.execute_query(query, (sku,))

    def get_timeline_lpn(self, lpn):
        query = """
            SELECT * FROM HistoricoMovimentacoes 
            WHERE Lpn = ? 
            ORDER BY DataMovimento DESC
        """
        return self.execute_query(query, (lpn,))