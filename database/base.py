import pyodbc
import os
import re
from dotenv import load_dotenv

# 1. Calcula a pasta principal do projeto (uma pasta acima da pasta 'database')
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 2. Monta o caminho exato para o ficheiro .env
ENV_PATH = os.path.join(BASE_DIR, '.env')

# 3. Carrega o ficheiro apontando diretamente para ele
load_dotenv(ENV_PATH)


class BaseRepo:
    def __init__(self, table_name=None, database="WMS_DB"):
        self.table_name = table_name

        # Vai buscar as credenciais de forma segura
        db_server = os.getenv("DB_SERVER", "localhost,1433")
        db_user = os.getenv("DB_USER")
        db_pass = os.getenv("DB_PASS")

        # Monta a string de conexao sem expor dados no codigo
        self.conn_str = (
            "DRIVER={ODBC Driver 17 for SQL Server};"
            f"SERVER={db_server};"
            f"DATABASE={database};"
            f"UID={db_user};"
            f"PWD={db_pass};"
        )

        # Verifica se as variaveis de ambiente foram carregadas corretamente
        if not db_user or not db_pass:
            raise ValueError("Credenciais da base de dados nao configuradas nas variaveis de ambiente.")

    def get_all(self):
        # Retorna todos os registros da tabela.
        if self.table_name:
            return self.execute_query(f"SELECT * FROM {self.table_name}")
        return []

    def execute_query(self, query, params=()):
        conn = pyodbc.connect(self.conn_str)
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            if cursor.description:
                columns = [column[0] for column in cursor.description]
                results = [dict(zip(columns, row)) for row in cursor.fetchall()]
                return results
            return []
        finally:
            conn.close()

    def execute_non_query(self, query, params=()):
        conn = pyodbc.connect(self.conn_str)
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def execute_non_query_count(self, query, params=()):
        # Executa um comando (UPDATE/DELETE) e retorna o número de linhas afetadas.
        # Útil para validações de concorrência.

        conn = pyodbc.connect(self.conn_str)
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            row_count = cursor.rowcount
            conn.commit()
            return row_count
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def list(self, page: int, page_size: int, filters: list):
        if not self.table_name: return 0, []

        # Estratégia Híbrida:
        # 1. Se tiver filtro "quick" (busca geral), usamos o método Python (seguro para buscar em tudo)
        # 2. Se forem filtros específicos (Coluna=Valor), usamos SQL (MUITO mais rápido)

        has_quick = any(f.get("type") == "quick" for f in filters)
        if has_quick:
            return self._list_in_memory(page, page_size, filters)
        else:
            return self._list_sql_optimized(page, page_size, filters)

    def _list_sql_optimized(self, page, page_size, filters):
        # 1. Monta o WHERE dinamicamente
        where_clause, params = self._build_where_clause(filters)

        # 2. Conta o total de registros (com filtro)
        count_query = f"SELECT COUNT(*) as total FROM {self.table_name} {where_clause}"
        count_res = self.execute_query(count_query, params)
        total = count_res[0]['total'] if count_res else 0

        # FORÇA A CONVERSÃO PARA INTEIRO (Proteção Absoluta)
        safe_page = int(page)
        safe_page_size = int(page_size)

        offset = (safe_page - 1) * safe_page_size

        data_query = f"""
            SELECT * FROM {self.table_name} 
            {where_clause}
            ORDER BY Id DESC
            OFFSET {offset} ROWS FETCH NEXT {safe_page_size} ROWS ONLY
        """
        rows = self.execute_query(data_query, params)
        return total, rows

    def _list_in_memory(self, page, page_size, filters):
        # Método antigo (Lento para muitos dados, mas versátil para 'quick search')
        rows = self.execute_query(f"SELECT * FROM {self.table_name}")
        filtered = [r for r in rows if self._matches_filter(r, filters)]

        total = len(filtered)
        start = max(0, (page - 1) * page_size)
        end = start + page_size
        return total, filtered[start:end]

    def _build_where_clause(self, filters):
        if not filters: return "", []

        conditions = []
        params = []

        for f in filters:
            col = f.get("column")
            val = f.get("value")
            op = f.get("operator")
            ftype = f.get("type")

            if not col or ftype == "quick": continue

            # NOVA BARREIRA DE SEGURANCA: Valida o nome da coluna
            # Permite apenas letras (maiusculas e minusculas), numeros e sublinhados (_)
            # Qualquer tentativa de injetar comandos SQL falhara aqui
            if not re.match(r"^[A-Za-z0-9_]+$", str(col)):
                continue

            # Mapeamento de Operadores
            if ftype == "text":
                if op == "contém":
                    conditions.append(f"{col} LIKE ?")
                    params.append(f"%{val}%")
                elif op == "começa com":
                    conditions.append(f"{col} LIKE ?")
                    params.append(f"{val}%")
                elif op == "igual a":
                    conditions.append(f"{col} = ?")
                    params.append(val)

            elif ftype == "number":
                try:
                    # Converte para float/int para garantir segurança
                    num_val = float(val)
                    if op == "=":
                        conditions.append(f"{col} = ?")
                        params.append(num_val)
                    elif op == "≥":
                        conditions.append(f"{col} >= ?")
                        params.append(num_val)
                    elif op == "≤":
                        conditions.append(f"{col} <= ?")
                        params.append(num_val)
                    elif op == "entre":
                        val2 = float(f.get("value2"))
                        conditions.append(f"{col} BETWEEN ? AND ?")
                        params.extend([min(num_val, val2), max(num_val, val2)])
                except:
                    continue  # Pula se valor inválido

        if conditions:
            return " WHERE " + " AND ".join(conditions), params
        return "", []

    def _matches_filter(self, row, filters):
        # Mantido para uso no _list_in_memory (filtro Quick)
        for f in filters or []:
            ftype = f.get("type")
            if ftype == "quick":
                q = str(f.get("value", "")).strip().lower()
                if q and not any(q in str(v).lower() for v in row.values()):
                    return False
                continue
            col = f.get("column")
            if col not in row: continue

            if ftype == "text":
                src = str(row.get(col, "")).lower()
                val = str(f.get("value", "")).lower()
                op = f.get("operator")
                if op == "contém" and val not in src: return False
                if op == "começa com" and not src.startswith(val): return False
                if op == "igual a" and src != val: return False

            elif ftype == "number":
                rv = row.get(col)
                if rv is None: return False
                val = f.get("value")
                op = f.get("operator")
                try:
                    if op == "=" and not (rv == val): return False
                    if op == "≥" and not (rv >= val): return False
                    if op == "≤" and not (rv <= val): return False
                    if op == "entre":
                        val2 = f.get("value2")
                        if not (min(val, val2) <= rv <= max(val, val2)): return False
                except Exception:
                    return False
        return True

    def execute_transaction(self, commands):

        # Executa uma lista de comandos (query, params) em uma única transação atômica.
        # Se um falhar, nenhum é salvo.

        conn = pyodbc.connect(self.conn_str)
        cursor = conn.cursor()
        try:
            for query, params in commands:
                cursor.execute(query, params)
            conn.commit()  # Salva tudo de uma vez
            return True
        except Exception as e:
            conn.rollback()  # Desfaz tudo se der erro
            raise e
        finally:
            conn.close()