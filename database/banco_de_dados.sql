USE master;
GO

-- 1. Cria o banco se ele não existir
IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'WMS_DB')
BEGIN
    CREATE DATABASE WMS_DB;
END
GO

USE WMS_DB;
GO

-- ============================================================================
-- MÓDULO: CADASTROS BÁSICOS
-- ============================================================================

-- Tabela Unidades
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Unidades]') AND type in (N'U'))
BEGIN
    CREATE TABLE Unidades (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        Sigla NVARCHAR(50) NOT NULL UNIQUE,
        Descricao NVARCHAR(200),
        Decimais BIT, 
        Cadastro DATETIME DEFAULT GETDATE(),
        Alteracao DATETIME,
        RowVersion INT DEFAULT 1
    );
END
GO

-- Tabela Familias
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Familias]') AND type in (N'U'))
BEGIN
    CREATE TABLE Familias (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        Nome NVARCHAR(100) NOT NULL UNIQUE,
        Descricao NVARCHAR(200),
        VidaUtil INT,
        ValidadeModo NVARCHAR(50),
        AlertaDias INT,
        LoteModo NVARCHAR(50),
        GiroModo NVARCHAR(50),
        VariavelConsumo NVARCHAR(50),
        ValidadeMinimaDias INT,
        AreaPreferencial NVARCHAR(50),
        BlockVencido BIT,
        BlockSemValidade BIT,
        BlockSemLote BIT,
        BlockRepQualidade BIT,
        Cadastro DATETIME,
        Alteracao DATETIME,
        RowVersion INT DEFAULT 1
    );
END
GO

-- Tabela Produtos
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Produtos]') AND type in (N'U'))
BEGIN
    CREATE TABLE Produtos (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        Sku NVARCHAR(100) NOT NULL UNIQUE,
        Descricao NVARCHAR(200),
        Ean NVARCHAR(50),
        CodFornecedor NVARCHAR(50),
        Referencia NVARCHAR(100),
        Familia NVARCHAR(100),
        Unidade NVARCHAR(50),
        CamadasJson NVARCHAR(MAX), 
        ValidadeModo NVARCHAR(50),
        AlertaDias INT,
        LoteModo NVARCHAR(50),
        GiroModo NVARCHAR(50),
        AreaPreferencialModo NVARCHAR(50) DEFAULT 'Herdar',
        VariavelConsumo NVARCHAR(50),
        ValidadeMinimaDias INT,
        AreaPreferencial NVARCHAR(50),
        VidaUtil INT,
        Bloqueado BIT DEFAULT 0,
        MotivoBloqueio NVARCHAR(100),
        ObsBloqueio NVARCHAR(MAX),
        BlockVencido BIT,
        BlockSemValidade BIT,
        BlockSemLote BIT,
        BlockRepQualidade BIT,
        Cadastro DATETIME,
        Alteracao DATETIME,
        RowVersion INT DEFAULT 1
    );
END
GO

-- Tabela ProdutoEmbalagens (Com as novas colunas de dimensão)
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[ProdutoEmbalagens]') AND type in (N'U'))
BEGIN
    CREATE TABLE ProdutoEmbalagens (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        ProdutoId INT NOT NULL,
        Ean NVARCHAR(50) NOT NULL,
        Unidade NVARCHAR(20) NOT NULL,
        FatorConversao FLOAT NOT NULL DEFAULT 1,
        Tipo NVARCHAR(20) DEFAULT 'CAIXA', -- Tipos: BASE, PRODUTO, RECIPIENTE
        
        -- Dimensões Físicas (Novos Campos)
        Largura FLOAT,
        LarguraUn NVARCHAR(10),
        Altura FLOAT,
        AlturaUn NVARCHAR(10),
        Comprimento FLOAT,
        ComprimentoUn NVARCHAR(10),
        PesoBruto FLOAT,
        
        -- Flag de Unidade Principal
        EhPadrao BIT DEFAULT 0,
        
        Ativo BIT DEFAULT 1,
        
        -- Auditoria
        Cadastro DATETIME DEFAULT GETDATE(),
        Alteracao DATETIME,
        CriadoPor NVARCHAR(100),
        AtualizadoPor NVARCHAR(100),
        
        -- Garante integridade: Se apagar o produto, apaga as embalagens
        CONSTRAINT FK_ProdutoEmbalagens_Produto FOREIGN KEY (ProdutoId) 
        REFERENCES Produtos(Id) ON DELETE CASCADE
    );

    -- Índices para busca rápida
    CREATE INDEX IX_ProdutoEmbalagens_Ean ON ProdutoEmbalagens(Ean);
    CREATE INDEX IX_ProdutoEmbalagens_ProdutoId ON ProdutoEmbalagens(ProdutoId);
END
GO

-- Tabela ProdutosAlias
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[ProdutosAlias]') AND type in (N'U'))
BEGIN
    CREATE TABLE ProdutosAlias (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        Cnpj NVARCHAR(20),
        CodFornecedor NVARCHAR(100),
        SkuInterno NVARCHAR(100),
        CriadoPor NVARCHAR(50),
        Cadastro DATETIME DEFAULT GETDATE()
    );
END
GO

-- Tabela UnidadesAlias
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[UnidadesAlias]') AND type in (N'U'))
BEGIN
    CREATE TABLE UnidadesAlias (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        UXml NVARCHAR(20),
        UInterna NVARCHAR(20),
        Cadastro DATETIME DEFAULT GETDATE()
    );
END
GO

-- ============================================================================
-- MÓDULO: ESTOQUE
-- ============================================================================

-- Tabela Locais
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Locais]') AND type in (N'U'))
BEGIN
    CREATE TABLE Locais (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        Nome NVARCHAR(100) NOT NULL UNIQUE,
        Tipo NVARCHAR(50),
        Cnpj NVARCHAR(20),
        Obs NVARCHAR(200),
        Ativo BIT DEFAULT 1,
        EhPadrao BIT DEFAULT 0,
        Cadastro DATETIME,
        Alteracao DATETIME,
        CriadoPor NVARCHAR(50),
        AtualizadoPor NVARCHAR(50),
        RowVersion INT DEFAULT 1
    );
END
GO

-- Tabela Areas
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Areas]') AND type in (N'U'))
BEGIN
    CREATE TABLE Areas (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        Nome NVARCHAR(50) NOT NULL UNIQUE,
        Descricao NVARCHAR(200),
        Ativo BIT DEFAULT 1,
        Cadastro DATETIME DEFAULT GETDATE(),
        Alteracao DATETIME,
        CriadoPor NVARCHAR(50),
        AtualizadoPor NVARCHAR(50),
        RowVersion INT DEFAULT 1
    );
END
GO

-- Tabela Enderecos
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Enderecos]') AND type in (N'U'))
BEGIN
    CREATE TABLE Enderecos (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        Area NVARCHAR(50),
        Rua INT,
        Predio INT,
        Nivel INT,
        Tipo NVARCHAR(50),
        CapacidadeTipo NVARCHAR(20),
        CapacidadeVal FLOAT,
        GrupoBloqueio NVARCHAR(20),
        ComprimentoUtil FLOAT,
        Ativo BIT DEFAULT 1,
        Uso NVARCHAR(50),
        SkuFixo NVARCHAR(100),
        CapacidadePicking FLOAT,
        UnidadePicking NVARCHAR(20),
        CargaMaxKg FLOAT,
        Cadastro DATETIME,
        Alteracao DATETIME,
        CriadoPor NVARCHAR(50),
        RowVersion INT DEFAULT 1
    );
    CREATE INDEX IX_Lpns_Endereco ON Lpns(Endereco);
END
GO

-- ============================================================================
-- TABELA LPNs
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Lpns]') AND type in (N'U'))
BEGIN
    CREATE TABLE Lpns (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        Lpn NVARCHAR(50) NOT NULL,
        Origem NVARCHAR(50),
        PrRef NVARCHAR(50),        -- Coluna Nova: Referência do Recebimento
        Sku NVARCHAR(100),
        Descricao NVARCHAR(200),
        Emb NVARCHAR(20),
        Lote NVARCHAR(50),
        Fabricacao NVARCHAR(50),   -- Coluna Nova: Data de Fabricação
        Validade DATETIME,
        Endereco NVARCHAR(50),
        QtdOriginal FLOAT,
        QtdAtual FLOAT,
        Unidade NVARCHAR(20),
        Estado NVARCHAR(50),
        Status NVARCHAR(50),
        Obs NVARCHAR(500),
        Cadastro DATETIME DEFAULT GETDATE(),
        Alteracao DATETIME,
        CriadoPor NVARCHAR(50),
        AtualizadoPor NVARCHAR(50),
        RowVersion INT DEFAULT 1,
        QtdAnterior FLOAT,
        EnderecoAnterior NVARCHAR(50)
    );
    -- Cria os índices de busca
    CREATE INDEX IX_Lpns_Codigo ON Lpns(Lpn);
    CREATE INDEX IX_Lpns_PrRef ON Lpns(PrRef); -- Índice Novo
END
GO

-- ============================================================================
-- MÓDULO: RECEBIMENTO
-- ============================================================================

-- Tabela Recebimento
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Recebimento]') AND type in (N'U'))
BEGIN
    CREATE TABLE Recebimento (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        PrCode NVARCHAR(50) NOT NULL UNIQUE,
        Nfe NVARCHAR(100),
        Fornecedor NVARCHAR(200),
        Cnpj NVARCHAR(20),
        Oc NVARCHAR(MAX),
        DataChegada NVARCHAR(50),
        Status NVARCHAR(50),
        Conferente NVARCHAR(100),
        ObsFiscal NVARCHAR(MAX),
        DataFim NVARCHAR(50),
        HistoricoTentativas NVARCHAR(MAX),
        Cadastro DATETIME DEFAULT GETDATE(),
        Alteracao NVARCHAR(50),
        CriadoPor NVARCHAR(100),
        AtualizadoPor NVARCHAR(100),
        RowVersion INT DEFAULT 1
    );
END
GO

-- Tabela RecebimentoItens
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RecebimentoItens]') AND type in (N'U'))
BEGIN
    CREATE TABLE RecebimentoItens (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        PrCode NVARCHAR(50) NOT NULL,
        Sku NVARCHAR(100),
        Descricao NVARCHAR(200),
        Qtd FLOAT,
        Und NVARCHAR(20),
        Lote NVARCHAR(50),
        Fab NVARCHAR(50),
        Val NVARCHAR(50),
        Vencimento NVARCHAR(50),
        IntEmb NVARCHAR(50),
        IntMat NVARCHAR(50),
        Identificacao NVARCHAR(100),
        CertQual NVARCHAR(100),
        Larg FLOAT,
        Comp FLOAT,
        Status NVARCHAR(50),
        Destino NVARCHAR(100),
        EanNota NVARCHAR(50),
        Preco FLOAT,
        CodOrig NVARCHAR(100),
        EhBonificacao BIT DEFAULT 0,
        QtdColetada FLOAT DEFAULT 0,
        ConferenteUltimo NVARCHAR(100),
        DataUltimaBipagem NVARCHAR(50),
        TentativasErro INT DEFAULT 0,
        DadosQualidade NVARCHAR(MAX),
        UndConferencia NVARCHAR(20),
        ObsFiscal NVARCHAR(MAX),
        DivergenciaVisual NVARCHAR(MAX),
        Cadastro NVARCHAR(50),
        Alteracao NVARCHAR(50),
        CriadoPor NVARCHAR(100),
        AtualizadoPor NVARCHAR(100),
        RowVersion INT DEFAULT 1,
        DescricaoXml NVARCHAR(200)
    );
    CREATE INDEX IX_RecebimentoItens_PrCode ON RecebimentoItens(PrCode);
END
GO

-- Tabela RecebimentoLeituras
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RecebimentoLeituras]') AND type in (N'U'))
BEGIN
    CREATE TABLE RecebimentoLeituras (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        RecebimentoItemId INT NOT NULL,  -- Link com a linha do item
        Qtd FLOAT NOT NULL,              -- O quanto foi bipado (pode ser negativo em caso de estorno)
        EanLido NVARCHAR(50),            -- O código exato que o operador leu
        Usuario NVARCHAR(100),
        DataHora DATETIME DEFAULT GETDATE(),
        DispositivoId NVARCHAR(100),
        Lpn NVARCHAR(50),
        Estornado BIT NOT NULL DEFAULT 0,
        
        -- Garante integridade: se apagar o item, apaga os logs
        FOREIGN KEY (RecebimentoItemId) REFERENCES RecebimentoItens(Id) ON DELETE CASCADE
    );
    
    -- Índices
    CREATE INDEX IX_RecebimentoLeituras_Item ON RecebimentoLeituras(RecebimentoItemId);
    CREATE INDEX IX_RecebimentoLeituras_Lpn ON RecebimentoLeituras(Lpn);
END
GO

-- Tabela HistoricoXml
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[HistoricoXml]') AND type in (N'U'))
BEGIN
    CREATE TABLE HistoricoXml (
        ChaveNfe NVARCHAR(100) PRIMARY KEY,
        DataProcessamento DATETIME DEFAULT GETDATE()
    );
END
GO

-- ============================================================================
-- MÓDULO: SISTEMA
-- ============================================================================

-- Tabela Impressoras
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Impressoras]') AND type in (N'U'))
BEGIN
    CREATE TABLE Impressoras (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        Nome NVARCHAR(100),
        Caminho NVARCHAR(200),
        Tipo NVARCHAR(20),
        Porta INT,
        Cadastro NVARCHAR(50),
        CriadoPor NVARCHAR(50)
    );
END
GO

-- Tabela PoliticasGlobais
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[PoliticasGlobais]') AND type in (N'U'))
BEGIN
    CREATE TABLE PoliticasGlobais (
        Id INT DEFAULT 1 PRIMARY KEY,
        ConfigJson NVARCHAR(MAX),
        UltimaAtualizacao DATETIME DEFAULT GETDATE()
    );
    IF NOT EXISTS (SELECT * FROM PoliticasGlobais WHERE Id = 1)
    BEGIN
        INSERT INTO PoliticasGlobais (Id, ConfigJson) VALUES (1, '{}');
    END
END
GO

-- Tabela RecebimentoSessoes (Controle de Tempo e Recontagens)
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[RecebimentoSessoes]') AND type in (N'U'))
BEGIN
    CREATE TABLE RecebimentoSessoes (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        PrCode NVARCHAR(50) NOT NULL,
        Tipo NVARCHAR(50), -- '1ª Contagem', '2ª Contagem', etc.
        Usuario NVARCHAR(100),
        DataInicio DATETIME DEFAULT GETDATE(),
        DataFim DATETIME NULL,
        Status NVARCHAR(50) DEFAULT 'Em Andamento',
        Observacao NVARCHAR(200),
        
        CONSTRAINT FK_Sessoes_Recebimento FOREIGN KEY (PrCode) 
        REFERENCES Recebimento(PrCode) ON DELETE CASCADE
    );

    CREATE INDEX IX_Sessoes_PrCode ON RecebimentoSessoes(PrCode);
END
GO

-- ============================================================================
-- TABELA DE AUDITORIA (LOG TRANSICOES)
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[LogTransicoes]') AND type in (N'U'))
BEGIN
    CREATE TABLE LogTransicoes (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        Tabela NVARCHAR(50),      -- Ex: 'Recebimento'
        RegistroId NVARCHAR(50),  -- Ex: 'PR-2026-0001'
        De NVARCHAR(50),          -- Status Anterior (Ex: Aguardando Vínculo)
        Para NVARCHAR(50),        -- Novo Status (Ex: Bloqueado Fiscal)
        Usuario NVARCHAR(100),
        DataHora DATETIME DEFAULT GETDATE(),
        Motivo NVARCHAR(MAX)      -- Contexto (Ex: 'Divergência de Quantidade no item X')
    );
    -- Índice para consultas rápidas de histórico
    CREATE INDEX IX_LogTransicoes_Registro ON LogTransicoes(RegistroId);
END
GO