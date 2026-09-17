## Purpose

Red de regresión automática que impide que vuelvan los defectos corregidos en la auditoría técnica. Separa la lógica que se comprueba sin infraestructura del aislamiento multi-tenant, que solo se puede demostrar contra un Postgres real.

## Requirements

### Requirement: Ejecución de la capa de lógica pura sin infraestructura
La capa de lógica pura MUST ejecutarse sin base de datos, sin llamadas a un LLM, sin archivo `.env` y sin cargar modelos de embeddings ni de re-ranking. Se MUST poder ejecutar sola, sin la capa de base de datos.

#### Scenario: Clon sin configuración
- **WHEN** se ejecuta solo la capa de lógica pura en un clon del repositorio sin `.env` y sin Docker
- **THEN** todos sus tests se recogen y se ejecutan, y ninguno falla por configuración ausente, conexión rechazada o importación

#### Scenario: Sin carga de modelos
- **WHEN** se ejecuta solo la capa de lógica pura
- **THEN** no se carga el modelo de embeddings ni el de re-ranking, y la ejecución completa tarda segundos, no el tiempo de importar la API

### Requirement: Base de datos desechable para la capa de base de datos
La capa de base de datos MUST ejecutarse contra una base PostgreSQL creada para la ejecución desde volumen vacío, con los scripts de inicialización del repositorio, y MUST eliminarla al terminar, incluido su volumen. MUST NOT conectarse a la base de desarrollo ni modificarla, ni tocar su volumen de datos.

#### Scenario: Base recién creada
- **WHEN** se ejecuta la capa de base de datos
- **THEN** los tests corren contra una base inicializada en esa misma ejecución, con el esquema, las políticas y los roles de los scripts del repositorio

#### Scenario: Limpieza al terminar
- **WHEN** termina la ejecución, con tests superados o fallidos
- **THEN** no queda ni el contenedor ni el volumen de la base de pruebas

#### Scenario: La base de desarrollo no se toca
- **WHEN** se ejecuta la suite completa con la base de desarrollo en marcha
- **THEN** los recuentos de la base de desarrollo y su volumen son idénticos antes y después

### Requirement: Fallo explícito sin Docker
Si la capa de base de datos está seleccionada y no se puede levantar la base desechable, la ejecución MUST fallar con un mensaje que indique la causa. MUST NOT saltarse los tests de esa capa ni darlos por superados.

#### Scenario: Docker no disponible
- **WHEN** se ejecuta la suite completa sin Docker disponible
- **THEN** la ejecución termina con fallo y el mensaje indica que no se pudo levantar la base de pruebas

#### Scenario: Selección explícita de la capa pura
- **WHEN** se ejecuta solo la capa de lógica pura sin Docker disponible
- **THEN** la ejecución termina con éxito, porque la capa de base de datos no estaba seleccionada

### Requirement: Alcance de la recolección
La ejecución por defecto MUST recoger tests solo del directorio de tests del proyecto, y MUST excluir las evaluaciones de calidad con juez LLM.

#### Scenario: Scripts sueltos de la raíz
- **WHEN** se ejecuta la suite por defecto
- **THEN** no se recoge ni se importa ningún script `test_*.py` de la raíz del repositorio

#### Scenario: Evaluaciones de calidad excluidas
- **WHEN** se ejecuta la suite por defecto
- **THEN** la evaluación de calidad existente no se ejecuta, y solo corre cuando se selecciona de forma explícita

### Requirement: Cada test de regresión demuestra que detecta su defecto
Cada test asociado a un hallazgo de la auditoría MUST fallar cuando se reintroduce el defecto que protege. Esa comprobación MUST quedar hecha antes de dar el test por bueno.

#### Scenario: Control negativo
- **WHEN** se reintroduce en el código el comportamiento anterior a la corrección de un hallazgo
- **THEN** al menos un test asociado a ese hallazgo falla

### Requirement: Regresión de la política de caché
La suite MUST verificar que solo se lee o escribe en el caché semántico cuando la respuesta es reutilizable para cualquier petición parecida (`BUG-02`, `BUG-06`, `BUG-10`).

#### Scenario: Intención no cacheable
- **WHEN** la intención de la respuesta es una herramienta, un tema fuera de alcance o un valor no reconocido
- **THEN** la respuesta no es cacheable

#### Scenario: Respuesta insuficiente
- **WHEN** la respuesta indica que necesita más información, o su confianza es menor que 0,5 o falta
- **THEN** la respuesta no es cacheable

#### Scenario: Respuesta reutilizable
- **WHEN** la intención es de búsqueda de conocimiento o un saludo, no necesita más información y su confianza es al menos 0,5
- **THEN** la respuesta es cacheable

#### Scenario: Parámetros de recuperación propios
- **WHEN** una petición trae `top_k_retrieve` o `top_k_rerank` distintos de 15 y 10
- **THEN** la petición no puede leer ni escribir caché

#### Scenario: Petición con historial
- **WHEN** una petición con los parámetros por defecto trae historial de conversación
- **THEN** la petición no puede leer ni escribir caché

#### Scenario: Parámetros fuera de rango
- **WHEN** una petición trae `top_k_retrieve` fuera de 1–50 o `top_k_rerank` fuera de 1–20
- **THEN** la petición se rechaza por validación

### Requirement: Regresión del ciclo de auto-corrección
La suite MUST verificar que cada reintento amplía la búsqueda dentro de los máximos, y que no se reintenta cuando ampliarla no puede cambiar el contexto (`BUG-05`).

#### Scenario: Ampliación por reintento
- **WHEN** se calcula la ventana de recuperación con base 15/10 en la primera pasada y en los dos reintentos siguientes
- **THEN** la ventana es 15/10, 30/15 y 45/20

#### Scenario: Tope en los máximos
- **WHEN** la ampliación superaría los máximos de la API
- **THEN** la ventana queda en 50 candidatos y 20 documentos

#### Scenario: Ventana saturada
- **WHEN** la ventana del siguiente reintento sería igual a la actual
- **THEN** la recuperación se considera agotada

#### Scenario: Corpus agotado
- **WHEN** ninguna búsqueda llenó su cupo de candidatos y el redactor ya recibió todos los candidatos únicos
- **THEN** la recuperación se considera agotada

#### Scenario: Decisión del revisor
- **WHEN** el redactor pide más información
- **THEN** se vuelve a buscar solo si la recuperación no está agotada y no se han hecho ya dos pasadas; en cualquier otro caso, se termina

### Requirement: Regresión del historial de conversación
La suite MUST verificar que el historial que envía el cliente se convierte en contexto para el prompt de forma acotada y robusta ante turnos malformados (`BUG-03`).

#### Scenario: Ventana de turnos
- **WHEN** el historial tiene más de cuatro turnos
- **THEN** solo se incluyen los cuatro últimos, en orden

#### Scenario: Turnos malformados
- **WHEN** el historial contiene turnos que no son objetos o que no tienen rol o contenido
- **THEN** esos turnos se descartan sin error y el resto se incluye

#### Scenario: Historial vacío o inutilizable
- **WHEN** el historial está vacío o ninguno de sus turnos es utilizable
- **THEN** el resultado es una cadena vacía, sin encabezado

### Requirement: Regresión del nombre de archivo en la ingesta
La suite MUST verificar que el nombre de archivo que envía el cliente se reduce a un nombre sin componentes de ruta antes de usarse como origen del documento (`SEC-04`).

#### Scenario: Recorrido de directorios
- **WHEN** el nombre enviado contiene componentes de ruta con `/` o `\`, incluido `..`
- **THEN** el origen registrado es solo el último componente

### Requirement: Regresión de la firma del tenant
La suite MUST verificar que la firma que calcula la aplicación coincide con la que verifica la base de datos para el mismo tenant y la misma clave (`SEC-05`).

#### Scenario: Firma coincidente
- **WHEN** la aplicación firma un tenant con una clave, y la base calcula el HMAC-SHA256 del mismo tenant con esa clave
- **THEN** las dos firmas son idénticas

### Requirement: Regresión de los límites de las puntuaciones del evaluador
La suite MUST verificar que una puntuación fuera del rango 0–1 se rechaza en la validación de la respuesta del juez, antes de llegar a la base de datos (`DOC-02`).

#### Scenario: Puntuación fuera de rango
- **WHEN** alguna de las tres puntuaciones es menor que 0 o mayor que 1
- **THEN** la validación falla

### Requirement: Regresión del aislamiento entre tenants
La suite MUST verificar, contra la base desechable y con el rol de la aplicación, que un tenant solo ve sus filas cuando el contexto va firmado con la clave correcta (`SEC-05`, `SEC-03`, `PERF-01`). Cada comprobación de aislamiento MUST ir acompañada de un control positivo desde el tenant dueño de los datos.

#### Scenario: Contexto firmado válido
- **WHEN** el rol de la aplicación consulta con el contexto de un tenant firmado con la clave correcta
- **THEN** ve las filas de ese tenant y ninguna de otro

#### Scenario: Contexto sin firma o con firma falsa
- **WHEN** el rol de la aplicación fija un tenant sin firma, o con una firma que no corresponde a la clave
- **THEN** no ve ninguna fila

#### Scenario: Tenant reescrito desde la propia sentencia
- **WHEN** una consulta con contexto firmado de un tenant reescribe el tenant desde la propia sentencia
- **THEN** no obtiene filas del otro tenant

#### Scenario: Inyección en la consulta de GraphRAG
- **WHEN** la búsqueda en el grafo de conocimiento recibe como pregunta el payload de inyección de `SEC-03`
- **THEN** no devuelve relaciones de otro tenant

#### Scenario: Palabras de la pregunta como datos, no como SQL
- **WHEN** la búsqueda en el grafo recibe, con un tokenizador que deja pasar comillas, una tautología o una palabra con apóstrofo
- **THEN** no devuelve relaciones que no coincidan con ninguna palabra, y no falla con un error de sintaxis SQL

#### Scenario: Conexión reutilizada del pool
- **WHEN** una conexión usada con el contexto de un tenant vuelve al pool y otra operación la reutiliza sin fijar contexto
- **THEN** esa operación no ve filas del tenant anterior

#### Scenario: Contexto local a la transacción
- **WHEN** termina la transacción en la que la aplicación fijó el contexto de un tenant, aunque la conexión no se restablezca al volver al pool
- **THEN** la conexión ya no conserva ni el tenant ni su firma

### Requirement: Regresión de los privilegios del rol de la aplicación
La suite MUST verificar, contra la base desechable, que el rol de la aplicación no tiene más privilegios que los que necesita (`HYG-07`, `SEC-07`).

#### Scenario: Tabla nueva en el esquema público
- **WHEN** el superusuario crea una tabla nueva en el esquema público
- **THEN** el rol de la aplicación no puede leerla

#### Scenario: Creación de esquemas
- **WHEN** el rol de la aplicación intenta crear un esquema
- **THEN** la operación se deniega por falta de privilegios

#### Scenario: Ajustes propios del rol
- **WHEN** se inspeccionan los ajustes por defecto guardados para el rol de la aplicación
- **THEN** no hay ninguno

#### Scenario: Clave de firma inaccesible
- **WHEN** el rol de la aplicación intenta leer la clave de firma
- **THEN** la operación se deniega

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
