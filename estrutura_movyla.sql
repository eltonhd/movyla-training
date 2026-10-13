CREATE TABLE exercicios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            grupo_muscular TEXT NOT NULL,
            equipamento TEXT,
            repeticoes_min INTEGER,
            repeticoes_max INTEGER,
            incremento_carga REAL
        , video_url TEXT, responsavel_id INTEGER);



CREATE TABLE treinos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL
        , descricao TEXT, dia_semana INTEGER, responsavel_id INTEGER);

CREATE TABLE treino_exercicios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            treino_id INTEGER NOT NULL,
            exercicio_id INTEGER NOT NULL,
            ordem INTEGER NOT NULL, progressao TEXT NOT NULL DEFAULT "automatica", incremento REAL NOT NULL DEFAULT 2.5,
            FOREIGN KEY (treino_id) REFERENCES treinos(id),
            FOREIGN KEY (exercicio_id) REFERENCES exercicios(id)
        );

CREATE TABLE sessoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            treino_id INTEGER NOT NULL,
            data TEXT NOT NULL, usuario_id INTEGER,
            FOREIGN KEY (treino_id) REFERENCES treinos(id)
        );

CREATE TABLE series (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sessao_id INTEGER NOT NULL,
            exercicio_id INTEGER NOT NULL,
            numero_serie INTEGER NOT NULL,
            carga REAL NOT NULL,
            repeticoes INTEGER NOT NULL,
            rir REAL,
            rpe REAL,
            observacoes TEXT, treino_exercicio_id INTEGER,
            FOREIGN KEY (sessao_id) REFERENCES sessoes(id),
            FOREIGN KEY (exercicio_id) REFERENCES exercicios(id)
        );

CREATE TABLE usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            usuario TEXT NOT NULL UNIQUE,
            senha TEXT NOT NULL,
            tipo TEXT NOT NULL DEFAULT 'aluno',
            ativo INTEGER NOT NULL DEFAULT 1
        , foto TEXT, responsavel_id INTEGER);

CREATE TABLE treino_alunos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            treino_id INTEGER NOT NULL, dia_semana INTEGER,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
            FOREIGN KEY (treino_id) REFERENCES treinos(id),
            UNIQUE(usuario_id, treino_id)
        );

CREATE TABLE treino_series (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            treino_exercicio_id INTEGER NOT NULL,
            numero_serie INTEGER NOT NULL,
            repeticoes_prescritas INTEGER,
            FOREIGN KEY (treino_exercicio_id)
                REFERENCES treino_exercicios(id)
                ON DELETE CASCADE
        );

CREATE TABLE treino_aluno_series (id INTEGER PRIMARY KEY AUTOINCREMENT, treino_aluno_id INTEGER NOT NULL, treino_exercicio_id INTEGER NOT NULL, numero_serie INTEGER NOT NULL, repeticoes_prescritas INTEGER, FOREIGN KEY (treino_aluno_id) REFERENCES treino_alunos(id), FOREIGN KEY (treino_exercicio_id) REFERENCES treino_exercicios(id));

CREATE TABLE assinaturas_personais (id INTEGER PRIMARY KEY AUTOINCREMENT, personal_id INTEGER NOT NULL UNIQUE, plano TEXT NOT NULL, valor_mensal REAL NOT NULL DEFAULT 0, data_inicio TEXT, proximo_vencimento TEXT, isento INTEGER NOT NULL DEFAULT 0, motivo_isencao TEXT, observacoes TEXT, tipo_assinatura TEXT NOT NULL DEFAULT paga, periodo_quantidade INTEGER, periodo_unidade TEXT, FOREIGN KEY(personal_id) REFERENCES usuarios(id));

CREATE TABLE pagamentos_personais (id INTEGER PRIMARY KEY AUTOINCREMENT, assinatura_id INTEGER NOT NULL, competencia TEXT NOT NULL, valor_pago REAL NOT NULL, data_pagamento TEXT NOT NULL, forma_pagamento TEXT, observacoes TEXT, FOREIGN KEY(assinatura_id) REFERENCES assinaturas_personais(id));