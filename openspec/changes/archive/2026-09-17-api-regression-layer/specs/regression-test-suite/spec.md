## ADDED Requirements

### Requirement: Ejecución de la capa de API con dobles
La capa de API MUST ejercitar la aplicación HTTP completa sin conectarse a PostgreSQL y sin llamar a ningún LLM, sustituyendo el grafo de agentes y los servicios de datos por dobles que registran con qué se los llamó. MUST NOT requerir Docker, y MUST poder ejecutarse sola.

#### Scenario: Sin infraestructura
- **WHEN** se ejecuta solo la capa de API sin Docker y sin la base de datos en marcha
- **THEN** todos sus tests pasan, y ninguno abre una conexión a PostgreSQL ni llama a un LLM

#### Scenario: La autenticación no se dobla
- **WHEN** un test de esta capa envía una petición autenticada
- **THEN** el token se valida con el código real de autenticación, no con un doble

### Requirement: Regresión de la autenticación en el borde
La suite MUST verificar que la API rechaza con 401 cualquier token que no pueda validarse, y que no arranca sin una clave de firma utilizable (`SEC-01`, `SEC-02`).

#### Scenario: Token firmado con otra clave
- **WHEN** se envía un token bien formado pero firmado con una clave distinta de la del servidor
- **THEN** la respuesta es 401 y no se ejecuta el grafo

#### Scenario: Token sin usuario o sin tenant
- **WHEN** el token válido no trae usuario o no trae tenant
- **THEN** la respuesta es 401

#### Scenario: Tenant malformado en el token
- **WHEN** el token trae un `tenant_id` que no es un UUID, por ejemplo una cadena con comillas o un fragmento de SQL
- **THEN** la respuesta es 401, no un error interno, y el valor no llega a la capa de datos

#### Scenario: Petición sin token
- **WHEN** se llama a un endpoint protegido sin cabecera de autorización
- **THEN** la respuesta es 401

#### Scenario: Clave de firma ausente o demasiado corta
- **WHEN** se carga la API sin clave de firma JWT, o con una de menos de 32 caracteres
- **THEN** el arranque falla con un error que explica la causa, en lugar de usar un valor por defecto

### Requirement: Regresión del detalle de los errores internos
La suite MUST verificar que, ante un fallo interno, el cliente recibe un mensaje genérico con un identificador, y que el detalle queda únicamente en el log (`SEC-06`). Los mensajes escritos para el cliente MUST conservarse.

#### Scenario: Fallo interno en una respuesta normal
- **WHEN** el grafo lanza una excepción cuyo texto contiene una ruta del servidor o un mensaje del proveedor del LLM
- **THEN** el cliente recibe un error genérico con un identificador, ese texto no aparece en la respuesta, y el log contiene la traza con el mismo identificador

#### Scenario: Fallo interno durante el stream
- **WHEN** el grafo lanza una excepción mientras se emite el stream
- **THEN** el evento entregado lleva un error genérico con identificador, y el texto de la excepción no aparece

#### Scenario: Fallo interno en la ingesta
- **WHEN** la ingesta de un archivo permitido falla con una excepción que nombra la ruta temporal del servidor
- **THEN** el cliente recibe un error genérico con identificador y esa ruta no aparece en la respuesta

#### Scenario: Mensajes escritos para el cliente
- **WHEN** la petición se rechaza por una causa prevista, como una extensión de archivo no permitida o que el grafo no devuelva respuesta final
- **THEN** el cliente recibe el mensaje específico de esa causa, no el genérico

### Requirement: Regresión del objeto persistido en el caché
La suite MUST verificar que lo que se manda a persistir en el caché es la respuesta estructurada limpia, sin los mensajes de progreso que el stream añade para la interfaz (`BUG-01`).

#### Scenario: Lo que se guarda frente a lo que se emite
- **WHEN** una petición de stream que puede usar caché termina con una respuesta cacheable
- **THEN** el objeto que recibe el servicio de caché no contiene ningún mensaje de progreso, mientras que el texto emitido al cliente sí los lleva

#### Scenario: El evaluador recibe la respuesta limpia
- **WHEN** esa misma petición programa la evaluación de la respuesta
- **THEN** el texto que recibe el evaluador tampoco contiene mensajes de progreso

### Requirement: Regresión de la respuesta del stream en todos los caminos
La suite MUST verificar que `/chat/stream/` entrega la respuesta final también cuando la resuelve el supervisor, sin pasar por el redactor (`BUG-09`).

#### Scenario: Saludo, tema fuera de alcance o herramienta
- **WHEN** el supervisor resuelve la petición por sí mismo, como en un saludo, un tema fuera de alcance o la ejecución de una herramienta
- **THEN** el último evento del stream contiene la respuesta, y no solo las líneas de progreso

#### Scenario: Respuesta del redactor
- **WHEN** la petición la resuelve el redactor emitiendo su texto token a token
- **THEN** el último evento contiene la respuesta completa una sola vez, sin duplicarla
