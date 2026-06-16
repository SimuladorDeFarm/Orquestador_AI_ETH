# Documentación de API

---

## Autenticación

> Gestión de identidad y emisión de tokens de acceso JWT para clientes institucionales

---

### `POST /v1/login/authenticate`

**Autenticar usuario y emitir token JWT**

Valida las credenciales institucionales (RUT y correo electrónico) y, en caso de éxito, retorna un token JWT firmado digitalmente.

#### Flujo de validación ejecutado

1. Validación sintáctica del RUT (formato chileno estándar)
2. Verificación de pertenencia al curso de computación paralela y distribuida
3. Cotejo exacto del correo electrónico asignado oficialmente
4. Consulta en repositorio persistente de credenciales
5. Generación y firma criptográfica del token JWT

> **Uso del token:** Incluir en peticiones subsiguientes como `Authorization: Bearer <jwt_token>` en los encabezados HTTP.

---

#### Parameters

No parameters

---

#### Request Body `required`

**Media type:** `application/json`

```json
{
  "email": "usuario@ejemplo.cl",
  "rut": "12.345.678-9"
}
```

---

#### Responses

| Code | Description |
|------|-------------|
| 200  | Autenticación exitosa. Token JWT generado y listo para uso. |
| 400  | Datos de entrada inválidos o mal formados (RUT o email) |
| 401  | Credenciales incorrectas, estudiante no registrado o email no coincidente |
| 500  | Error interno del servidor durante generación o firma del JWT |

---

##### 200 — Autenticación exitosa

**Media type:** `application/json`

```json
{
  "jwt": "eyJhbGci0iJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

---

##### 400 — Datos de entrada inválidos

**Media type:** `application/problem+json`

```json
{
  "type": "https://example.com/",
  "title": "string",
  "status": 0,
  "detail": "string",
  "instance": "https://example.com/",
  "properties": {
    "additionalProp1": "string",
    "additionalProp2": "string",
    "additionalProp3": "string"
  }
}
```

---

##### 401 — Credenciales incorrectas

**Media type:** `application/problem+json`

```json
{
  "type": "https://example.com/",
  "title": "string",
  "status": 0,
  "detail": "string",
  "instance": "https://example.com/",
  "properties": {
    "additionalProp1": "string",
    "additionalProp2": "string",
    "additionalProp3": "string"
  }
}
```

---

##### 500 — Error interno del servidor

**Media type:** `application/problem+json`

```json
{
  "type": "https://example.com/",
  "title": "string",
  "status": 0,
  "detail": "string",
  "instance": "https://example.com/",
  "properties": {
    "additionalProp1": "string",
    "additionalProp2": "string",
    "additionalProp3": "string"
  }
}
```

---

## Public API

> Endpoints públicos sin autenticación

---

### `GET /v1/public/persons/simulate`

**Obtener lista de personas menores de edad**

Simula la consulta de personas menores de edad. Retorna una lista de objetos `PersonResponse`. Si no hay datos disponibles, lanza una excepción que resulta en un error 404.

---

#### Parameters

No parameters

---

#### Responses

| Code | Description |
|------|-------------|
| 200  | Lista de personas obtenida exitosamente |
| 404  | No se encontraron datos (lista vacía o nula) |

---

##### 200 — Lista de personas

**Media type:** `application/json`

```json
[
  {
    "rut": "12.345.678-5",
    "firstName": "JUAN",
    "lastName": "PÉREZ GÓMEZ",
    "gender": "MASCULINO",
    "birthDate": "1995-08-15",
    "active": true
  }
]
```

---

##### 404 — No se encontraron datos

No se encontraron datos (lista vacía o nula).

---

## Consulta de Personas

> Recuperación segura de datos personales mediante token de acceso único (UUID) y validación de identidad institucional

---

### `GET /v1/person/{uuid}`

**Consultar datos personales por UUID**

Recupera la información personal registrada en el sistema institucional mediante un identificador único (UUID). Requiere autenticación previa vía encabezado Authorization.

#### Flujo de ejecución

1. Validación y extracción del identificador de credencial desde el JWT
2. Validación de formato UUID (RFC 4122)
3. Consulta en repositorio con estrategia de carga explícita
4. Transformación a DTO de respuesta con normalización de campos

> **Nota de seguridad:** El token de acceso se valida antes de consultar datos sensibles. Todos los accesos se registran para auditoría forense y cumplimiento normativo institucional.

---

#### Parameters

| Name | Type | In | Required | Description |
|------|------|----|----------|-------------|
| Authorization | string | header | ✅ required | Token de acceso institucional. Formato obligatorio: `Bearer <jwt_token>` |
| uuid | string($uuid) | path | ✅ required | Identificador único de acceso en formato UUID v4 |

**Ejemplos:**

- `Authorization`: `Bearer eyJhbGciOiJIUzI1NiJ9...`
- `uuid`: `550e8400-e29b-41d4-a716-446655440000`

---

#### Responses

| Code | Description |
|------|-------------|
| 200  | Persona encontrada. Datos retornados en formato JSON normalizado. |
| 400  | Formato de UUID inválido o parámetros malformados |
| 401  | Token de autorización inválido, expirado o ausente |
| 404  | No existe registro asociado al UUID proporcionado |

---

##### 200 — Persona encontrada

**Media type:** `application/json`

```json
{
  "rut": "12.345.678-5",
  "firstName": "JUAN",
  "lastName": "PÉREZ GÓMEZ",
  "gender": "MASCULINO",
  "birthDate": "1995-08-15",
  "active": true
}
```

---

##### 400 — UUID inválido o parámetros malformados

**Media type:** `application/problem+json`

```json
{
  "type": "https://example.com/",
  "title": "string",
  "status": 0,
  "detail": "string",
  "instance": "https://example.com/",
  "properties": {
    "additionalProp1": "string",
    "additionalProp2": "string",
    "additionalProp3": "string"
  }
}
```

---

##### 401 — Token inválido, expirado o ausente

**Media type:** `application/problem+json`

```json
{
  "type": "https://example.com/",
  "title": "string",
  "status": 0,
  "detail": "string",
  "instance": "https://example.com/",
  "properties": {
    "additionalProp1": "string",
    "additionalProp2": "string",
    "additionalProp3": "string"
  }
}
```

---

##### 404 — UUID no encontrado

**Media type:** `application/problem+json`

```json
{
  "type": "https://example.com/",
  "title": "string",
  "status": 0,
  "detail": "string",
  "instance": "https://example.com/",
  "properties": {
    "additionalProp1": "string",
    "additionalProp2": "string",
    "additionalProp3": "string"
  }
}
```

---

## Schemas

### `LoginResponse` — object

Respuesta HTTP 200 tras autenticación exitosa. Contiene el token de acceso para siguientes peticiones.

| Campo | Tipo | Acceso | Descripción |
|-------|------|--------|-------------|
| jwt | string | read-only | Token JWT de acceso |

---

### `ProblemDetail` — object

| Campo | Tipo | Descripción |
|-------|------|-------------|
| type | string (uri) | URI que identifica el tipo de problema |
| title | string | Título legible del problema |
| status | integer (int32) | Código de estado HTTP |
| detail | string | Descripción detallada del error |
| instance | string (uri) | URI de la instancia específica del error |
| properties | object | Propiedades adicionales del error |

---

### `LoginRequest` — object

Credenciales requeridas para autenticación de usuario.

| Campo | Tipo | Acceso | Restricciones |
|-------|------|--------|---------------|
| email* | string (email) | write-only | [0, 255] caracteres · matches `^[A-Za-z0-9+_.−]+@(.+)$` |
| rut* | string | write-only | [9, 12] caracteres · matches `^\d{1,2}\.?\d{3}\.?\d{3}-[0-9kK]$` |

---

### `PersonResponse` — object

Estructura de datos personales de un usuario para consumo vía API. Campos calculados y normalizados en tiempo de construcción.

| Campo | Tipo | Acceso | Restricciones |
|-------|------|--------|---------------|
| rut | string | read-only | matches `^\d{1,2}\.?\d{3}\.?\d{3}-[0-9kK]$` |
| firstName | string | read-only | — |
| lastName | string | read-only | — |
| gender | string | read-only | — |
| birthDate | string (date) | read-only | — |
| active | boolean | read-only | — |