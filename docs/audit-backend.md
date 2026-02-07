# Auditoria técnica do backend (otrack / MEOS Results)

## Arquitetura atual

### Stack e framework
- **Framework**: FastAPI (Python) com Uvicorn. O app está exposto em `main.py` via `FastAPI(...)`. Endpoints REST em `/api`. 
- **Parsing XML**: `xmltodict` para parse de IOF ResultList/CourseData. 
- **Uploads**: `python-multipart` para `UploadFile` (form-data).

### Estrutura de pastas
- `main.py`: aplicação FastAPI, rotas, parsing, persistência em arquivo. 
- `models.py`: modelos Pydantic (não usados nas rotas atuais). 
- `parser_iof.py`: parser alternativo (não usado pelas rotas atuais). 
- `storage.py`: helpers de persistência em JSON (não usado pelas rotas atuais). 
- `data/`: diretório de eventos persistidos (JSON por evento). 

### Como roda (dev/prod)
- **Dev**: `uvicorn main:app --reload` (com variáveis de ambiente locais). 
- **Prod**: `Procfile` indica `uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2`. 

## Deploy e configuração

### Variáveis de ambiente
- `MEOS_CORS_ORIGINS`: lista CSV de origins permitidos. 
- `MEOS_CORS_REGEX`: regex opcional para origins. 
- `MEOS_DATA_DIR` ou `DATA_DIR`: diretório para arquivos JSON de eventos (default: `./data`). 
- `MEOS_ADMIN_TOKEN`: token admin para endpoints de deleção. 
- `APP_VERSION`: fallback para versão da aplicação caso metadata de pacote não esteja disponível (default `0.0.0`). 
- `APP_PACKAGE_NAME`: nome do pacote a ser consultado via `importlib.metadata` para resolver `APP_VERSION`. 
- `GIT_SHA` e `BUILD_TIME`: opcionais, expostos em `/api/health` como metadados. 

### Portas e CORS
- Porta configurável via `PORT` (default 8000). 
- CORS permissivo a origins configurados + regex opcional. 

### Storage e banco
- Persistência **em arquivo JSON por evento** dentro de `DATA_DIR`. Não há banco relacional/NoSQL. 
- Cada evento é salvo em `{DATA_DIR}/{eventId}.json` e contém o blob completo. 

## Fluxo de dados

### 1) Importação de eventos (upload)
- Endpoint `POST /api/events/import` aceita: 
  - `result` (arquivo obrigatório) com IOF ResultList. 
  - `course` (arquivo opcional) com IOF CourseData. 
  - `organizer` (form-data opcional). 
- Validação básica: extensão e presença de `<ResultList` no início do arquivo. 

### 2) Parsing/validação
- `parse_iof_xml(...)` converte ResultList em um objeto com `name`, `date`, `organizer`, `classes` e `competitors`. 
- `parse_course_xml(...)` armazena CourseData “bruto”; `extract_course_metrics(...)` tenta extrair métricas (length/climb). 
- Merges de métricas por classe via normalização de nomes (case/acento). 

### 3) Persistência
- `save_event(...)` gera ID determinístico (SHA1 de um payload do evento) e grava JSON em disco. 
- Também gera índice auxiliar `__index` e agrega `courseMetrics`. 

### 4) Leitura
- `GET /api/events`: varre `DATA_DIR`, lê cada arquivo e retorna resumo por evento. 
- `GET /api/events/{id}/blob`: retorna blob completo do evento. 
- `GET /api/events/{id}/classes`: retorna resumo por classe (competitors + métricas). 

### 5) Deleção/admin
- `DELETE /api/events/{id}` requer `x-admin-token` com `MEOS_ADMIN_TOKEN`. 
- Em caso de token inválido, retorna 403. 

## Lista de endpoints reais (extraídos do código)

- `GET /api/health` 
- `HEAD /api/health` 
- `GET /api/events` 
- `GET /api/events/{eid}/blob` 
- `GET /api/events/{eid}/classes` 
- `POST /api/events/import` 
- `DELETE /api/events/{eid}` 

## Contratos (endpoints usados pelo frontend)

### GET /api/events
- **Response 200**: mapa `{id: {id, name, date, organizer, classesCount, hasCourseData}}`. 

### GET /api/events/:id/blob
- **Response 200**: evento completo. 
- **Response 404**: `{detail: "Evento não encontrado"}`. 

### POST /api/events/import
- **Request**: `multipart/form-data` com `result` obrigatório, `course` opcional, `organizer` opcional. 
- **Response 200**: resumo `{id, name, date, organizer, classesCount, hasCourseData, hasCourseMetrics}`. 
- **Errors**: 
  - 400: extensão inválida ou ResultList inválido. 
  - 500: erro no processamento inesperado. 

### POST /api/events/import-xml
- **Não existe** (a rota implementada é `/api/events/import`). 

### DELETE /api/events/:id
- **Request**: header `x-admin-token`. 
- **Response 200**: `{ok: true}`. 
- **Response 403**: `{detail: "Forbidden"}`. 
- **Response 404**: `{detail: "Evento não encontrado"}`. 

### GET /api/health
- **Response 200**: `{ok, version, apiSchemaVersion, dataDir, corsOrigins}` (+ `commitSha` e `buildTime` se presentes). 

## Top 10 riscos / débitos técnicos

1) **Persistência em arquivos locais**: risco de perda de dados em deploys efêmeros e ausência de backup/replicação. 
2) **Sem autenticação global**: apenas deleção tem token; leitura/import não têm controle. 
3) **Uploads sem limite de tamanho no endpoint** além do check manual; risco de OOM/latência. 
4) **Sem validação robusta de schema IOF**; parsing permissivo pode aceitar payloads inválidos. 
5) **Falta de index e busca**; `GET /api/events` lê todos os JSONs a cada chamada. 
6) **Sem travas de concorrência**; gravações simultâneas podem causar corrupção parcial em disco. 
7) **Sem observabilidade estruturada** (logs estruturados, métricas, traces). 
8) **Sem versionamento de API** formal (além de `version`). 
9) **Admin token fixo**; sem rotação/auditoria. 
10) **Dependências/arquivos não usados** (`models.py`, `storage.py`, `parser_iof.py`) aumentam ambiguidade. 

## Gargalos prováveis e pontos de falha

- **CPU**: parsing XML grande (IOF) pode ser pesado para arquivos 10MB+. 
- **Memória**: arquivos grandes são carregados em memória (`await result.read()`). 
- **IO**: `GET /api/events` lê todos os arquivos de `DATA_DIR` a cada chamada. 
- **Timeouts**: sem controle explícito; uploads podem travar workers. 
- **Concorrência**: escrita simultânea em disco sem lock pode gerar arquivos inconsistentes. 

## Observabilidade atual e lacunas

- Logs apenas via `print` na verificação de admin token. 
- Não há métricas, tracing ou logs estruturados. 
- Falta ID de request/correlation para rastreio de erros. 

## Checklist de segurança (estado atual)

- **CORS**: configurável por env; regex opcional. 
- **Headers de segurança**: não configurados (CSP, HSTS, etc.). 
- **Validação upload**: extensão e heurística de conteúdo; sem validação MIME/tamanho server-side além do parser. 
- **Rate limiting**: ausente. 
- **Auth/admin token**: token único via `MEOS_ADMIN_TOKEN`, sem expiração/rotina de rotação. 

## Roadmap priorizado

### 0-2 semanas (rápido e seguro)
- Documentar contrato mínimo de API (este doc). 
- Adicionar `apiSchemaVersion` no `/api/health` (feito). 
- Padronizar logs de erro estruturados (ex.: `logging` JSON). 
- Limite de upload configurável por env + validação MIME básica. 

### 2 meses (estabilidade e confiabilidade)
- Persistência em storage durável (S3 ou DB) + backups automáticos. 
- Cache/índice para `GET /api/events` (evitar varrer disco em toda chamada). 
- Autenticação básica (JWT ou API key) para import/delete. 
- Sanitização e validação de schema IOF com libs de validação XML. 

### 12 meses (escala/operacional)
- OpenAPI formal para versionamento e compatibilidade. 
- Observabilidade completa: métricas (Prometheus), tracing (OpenTelemetry). 
- Migração para armazenamento estruturado (DB) + jobs de ingestão. 

## PRs pequenos sugeridos (baixo risco)

1) Melhorar `/api/health` com `apiSchemaVersion` e metadados de build (feito). 
2) Adicionar limite configurável de upload por env. 
3) Log estruturado para falhas no parse e erros 5xx. 
4) Sanitização de `organizer`/`name` e validações de campos obrigatórios. 
5) Documentação de execução local e exemplos `curl`. 

## Como validar

### Local
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

### Curl rápido
```bash
curl -s http://localhost:8000/api/health
curl -s http://localhost:8000/api/events
```

## Riscos e rollback

- **Risco**: mudança em `/api/health` afeta consumidores que validam chaves estritas. 
- **Rollback**: `git revert <commit>` ou remover `apiSchemaVersion` da resposta. 
