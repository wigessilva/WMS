import bcrypt
import json

from ..base import BaseRepo


class PerfisRepo(BaseRepo):
    def __init__(self):
        super().__init__(table_name="Perfis")

    # Cria um novo perfil no banco de dados convertendo o dicionario de permissoes em JSON
    def criar_perfil(self, nome, descricao, permissoes_dict):
        query = '''
            INSERT INTO Perfis (Nome, Descricao, Permissoes, Ativo) 
            VALUES (?, ?, ?, 1)
        '''
        permissoes_json = json.dumps(permissoes_dict)
        self.execute_non_query(query, (nome, descricao, permissoes_json))

    # Retorna as permissoes de um perfil especifico ja convertidas para dicionario Python
    def obter_permissoes(self, perfil_id):
        query = "SELECT Permissoes FROM Perfis WHERE Id = ?"
        resultado = self.execute_query(query, (perfil_id,))

        # Ajustado para usar a coluna 'Permissoes'
        if resultado and resultado[0]['Permissoes']:
            return json.loads(resultado[0]['Permissoes'])
        return {}


class UsuariosRepo(BaseRepo):
    def __init__(self):
        super().__init__(table_name="Usuarios")

    # Retorna a lista de usuários com os nomes dos perfis (JOIN)
    def list(self, page=1, page_size=20, filters=None):
        offset = (page - 1) * page_size

        # Base da query
        query_base = '''
            FROM Usuarios u
            INNER JOIN Perfis p ON u.PerfilId = p.Id
            WHERE 1=1
        '''
        params = []

        # Aplicação de filtros (Busca rápida por Nome ou Login)
        if filters:
            for f in filters:
                if f.get("type") == "quick":
                    query_base += " AND (u.Nome LIKE ? OR u.Login LIKE ?)"
                    val = f"%{f['value']}%"
                    params.extend([val, val])

        # Busca o total para a paginação
        total = self.execute_query(f"SELECT COUNT(*) as Total {query_base}", params)[0]['Total']

        # Busca os dados paginados
        query_data = f'''
            SELECT u.Id, u.Nome, u.Login, p.Nome as Perfil, u.UltimoLogin, u.Ativo
            {query_base}
            ORDER BY u.Nome
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        '''
        params.extend([offset, page_size])
        rows = self.execute_query(query_data, params)

        return total, rows

    # Verifica o login e a senha, trazendo as permissoes do perfil atrelado em uma unica consulta
    def autenticar(self, login, senha_plana):
        # Usando aspas simples triplas para query multi-linha
        query = '''
            SELECT u.Id, u.Nome, u.SenhaHash, p.Permissoes 
            FROM Usuarios u 
            INNER JOIN Perfis p ON u.PerfilId = p.Id 
            WHERE u.Login = ? AND u.Ativo = 1 AND p.Ativo = 1
        '''
        resultado = self.execute_query(query, (login,))

        if resultado:
            usuario = resultado[0]
            senha_hash_db = usuario['SenhaHash'].encode('utf-8')
            senha_digitada = senha_plana.encode('utf-8')

            # Valida o hash com a senha digitada
            if bcrypt.checkpw(senha_digitada, senha_hash_db):
                # Atualiza a data e hora do ultimo login
                self.execute_non_query("UPDATE Usuarios SET UltimoLogin = DATEADD(HOUR, -3, GETUTCDATE()) WHERE Id = ?", (usuario['Id'],))

                return {
                    "id": usuario['Id'],
                    "nome": usuario['Nome'],
                    "permissoes": json.loads(usuario['Permissoes']) if usuario['Permissoes'] else {}
                }

        # Retorna None se login nao existir ou senha estiver incorreta
        return None

    # Cadastra usuario encriptando a senha antes de salvar
    def criar_usuario(self, perfil_id, nome, login, senha_plana, usuario_logado_id):
        senha_bytes = senha_plana.encode('utf-8')
        salt = bcrypt.gensalt()
        senha_hash = bcrypt.hashpw(senha_bytes, salt).decode('utf-8')

        query = '''
            INSERT INTO Usuarios (PerfilId, Nome, Login, SenhaHash, CriadoPor) 
            VALUES (?, ?, ?, ?, ?)
        '''
        self.execute_non_query(query, (perfil_id, nome, login, senha_hash, usuario_logado_id))