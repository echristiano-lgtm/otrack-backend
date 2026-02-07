# Contrato mínimo da API (otrack backend)

> Este contrato descreve o comportamento **real** observado no código. Não inventa endpoints.

## Base URL
- `/api`

## GET /api/events

### Request
- Sem parâmetros.

### Response 200
```json
{
  "<eventId>": {
    "id": "<eventId>",
    "name": "<string>",
    "date": "YYYY-MM-DD",
    "organizer": "<string>",
    "classesCount": 3,
    "hasCourseData": true
  }
}
```

### Errors
- Não há erros específicos implementados; erros internos retornam 500 padrão.

## GET /api/events/{id}/blob

### Request
- Path param: `id` (string).

### Response 200
Evento completo com classes e competidores:
```json
{
  "id": "<eventId>",
  "name": "<string>",
  "date": "YYYY-MM-DD",
  "organizer": "<string>",
  "classes": {
    "<className>": {
      "name": "<className>",
      "competitors": [
        {
          "id": "<string>",
          "name": "<string>",
          "club": "<string>",
          "status": "<string>",
          "pos": "<string>",
          "timeS": 1234,
          "splits": [
            {"seq": 1, "code": "31", "split": 123, "cum": 123}
          ]
        }
      ]
    }
  },
  "courseData": {"...": "..."},
  "courseMetrics": {"...": "..."}
}
```

### Response 404
```json
{"detail": "Evento não encontrado"}
```

## POST /api/events/import

### Request (multipart/form-data)
- `result` **obrigatório**: arquivo IOF ResultList (`.xml`, `.iof`, `.html`, `.htm`).
- `course` opcional: arquivo IOF CourseData (mesmas extensões).
- `organizer` opcional: string.

### Response 200
```json
{
  "id": "<eventId>",
  "name": "<string>",
  "date": "YYYY-MM-DD",
  "organizer": "<string>",
  "classesCount": 3,
  "hasCourseData": true,
  "hasCourseMetrics": true
}
```

### Response 400
- Extensão inválida:
```json
{"detail": "Resultados devem ser IOF XML (.xml/.iof/.html/.htm)"}
```
- Conteúdo inválido:
```json
{"detail": "Arquivo de resultados não parece conter IOF ResultList válido."}
```

### Response 500
```json
{"detail": "Erro no processamento: <erro>"}
```

## POST /api/events/import-xml
- **Não existe** (a rota real é `/api/events/import`).

## DELETE /api/events/{id}

### Request
- Header obrigatório: `x-admin-token: <MEOS_ADMIN_TOKEN>`.

### Response 200
```json
{"ok": true}
```

### Response 403
```json
{"detail": "Forbidden"}
```

### Response 404
```json
{"detail": "Evento não encontrado"}
```

## GET /api/health

### Response 200
```json
{
  "ok": true,
  "version": "0.0.0",
  "apiSchemaVersion": "2024-10-01",
  "dataDir": "<path>",
  "corsOrigins": ["http://localhost:5173"],
  "commitSha": "<optional>",
  "buildTime": "<optional>"
}
```

## GET /health

- Alias de `/api/health` sem prefixo `/api` (mesmo payload). Útil para compatibilidade temporária.

## Limites e observações

- **Tamanho do upload**: limite prático de 10MB no parser de IOF (checado no parse). 
- **Timeouts**: não configurados explicitamente no app. 
- **Rate limit**: não há. 
- **Auth**: somente `DELETE` usa admin token. 
- **Versionamento**: `version` vem de metadata do pacote (se `APP_PACKAGE_NAME` estiver definido e resolvível) ou de `APP_VERSION` (fallback `0.0.0`). `apiSchemaVersion` deve mudar apenas quando o contrato da API mudar. 
- **Rotas**: `/health` e `/api/health` coexistem; preferir `/api/health` para clientes novos. 
