"""Migrations do app ``users`` usadas SOMENTE pelos testes.

As migrations reais 0003 a 0008 consultam ``user_tab_columns``, uma view do
dicionario de dados do Oracle. Elas existem para consertar colunas em uma base
Oracle ja existente e, por construcao, nao rodam em nenhum outro backend.

Para que a suite rode sem Oracle, ``sentiment_ai.testsettings`` aponta o app
``users`` para este pacote, que cria a mesma tabela final em uma unica
migration. As migrations de producao NAO foram alteradas.
"""
