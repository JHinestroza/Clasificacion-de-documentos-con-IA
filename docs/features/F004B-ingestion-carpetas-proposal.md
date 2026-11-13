# F004B propuesta — Ingreso de PDF desde carpetas

- Estado: propuesta concreta para consulta; no implementada ni aprobada.
- Fecha: 2026-11-13.
- Rama: `feature/ingestion-carpetas`, creada desde `develop` (`21f6cf8`).
- Continúa F004A y actualiza la preparación conservada en `feature/ingestion-operacion`.

## Problema y resultado previsto

El portal ya permite iniciar sesión, pero no existe un buzón operativo ni una
función que registre PDF o publique sus trabajos. Esta entrega permitirá depositar
archivos completos en una carpeta, elegir el fondo, iniciar un lote y comprobar
admisiones, omisiones, fallos e historial real. Un PDF admitido quedará en
`processing`, con publicación persistida y confirmada en RabbitMQ cuando esté disponible.

Esta fase termina en el estado **En cola**. No promete extracción de texto,
metadatos ni archivos en `success`. La confirmación del broker no acredita ejecución.
El worker Celery Linux y Docker siguen diferidos a la feature final; las reglas de
extracción y metadatos se desarrollarán en F005/F006 con fixtures controladas.

## Decisiones que se conservan

React/TypeScript sobre FastAPI HTTPS, PostgreSQL, RabbitMQ/Celery, sesiones y CSRF
F003, outbox e idempotencia del ADR 0001. No se vuelven a consultar estas decisiones.
Se preservan ramas anteriores, secretos en `.env` y archivos propiedad de Usuario.

`CAB01.pdf` y `CAB02.pdf` producen códigos CAB01/CAB02 conservando ceros. Máximo:
100 MB, equivalentes a 100 000 000 bytes por PDF. Los controles son por lote.
`success` exige metadatos terminados. Retirar un fallido no borra el PDF ni su historial.

## Flujo del operador propuesto

1. El superusuario configura el fondo y concede acceso explícito a sus operadores.
   El nombre del primer fondo está consultado; a falta de nombre solo se preparará
   el fondo ficticio PRUEBAS para comprobar la implementación.
2. La nueva vista **Ingreso de documentos** muestra el fondo y la ruta exacta de
   su buzón. El navegador selecciona un ID autorizado, nunca una ruta arbitraria.
3. Depositar cada PDF completo en `incoming`. Para evitar leer copias a medias,
   copiar con extensión `.part` y renombrar a `.pdf` al finalizar. Un ayudante local
   de depósito hará esos pasos, verificará tamaño/hash y conservará el original
   externo. Un tamaño estable por sí solo no demuestra que terminó la copia.
4. Pulsar **Iniciar lote** toma una lista finita de entregas completas. Archivos
   que lleguen después se conservan para otro lote; no se activa vigilancia continua.
5. La interfaz muestra código, nombre, estado, causa pública e historial. El ingreso
   mueve cada archivo admitido a `processing` mediante registro recuperable.
6. **Pausar** deja terminar la admisión iniciada y bloquea la siguiente; **Reanudar**
   continúa el mismo lote. **Detener** cierra el lote después de esa admisión y
   conserva los candidatos pendientes en `incoming` para un lote posterior.
   Ningún botón purga RabbitMQ ni cancela instantáneamente un trabajo ya publicado.

Ruta inicial propuesta en `.env`, fuera de Git: `APP_STORAGE_ROOT=.local/documents`.
Todos los directorios gestionados comparten volumen; se rechazan enlaces/reparse
points. Una ubicación distinta debe estar cifrada y ser accesible por Usuario.
El nombre visible del fondo es independiente de su clave interna de almacenamiento.

```text
.local/documents/<clave-fondo>/
  incoming/     PDF completos pendientes de admitir; .part se ignora
  processing/   PDF admitidos, publicación pendiente o en cola
  failed/       entradas inválidas/fallidas, con causa e historial
  success/      reservado al procesamiento de metadatos completado
  skipped/      nuevas entregas omitidas por código ya existente
```

Los destinos internos usan UUID; el nombre original solo es dato autorizado.
`skipped` evita mezclar una entrega duplicada con errores reencolables y evita
escanearla sin fin. No se reemplazan archivos existentes ni se borran originales
mientras el destino no esté publicado y verificado. Un fallo de broker mantiene
el PDF en `processing` y el outbox pendiente; no lo clasifica como PDF inválido.

## Reglas nuevas propuestas para confirmar en conjunto

- Código único global, insensible a mayúsculas ASCII: cab01.pdf y CAB01.pdf
  representan CAB01. Conservar el nombre/código original como metadato; no quitar
  ceros ni truncar/simplificar nombres. Para esta primera versión aceptar letras
  ASCII, números, guion y guion bajo; de 1 a 64 caracteres, empezando por letra/número.
  Otros nombres se registran como no válidos, sin inventarles un código.
- Un mismo SHA-256 con códigos diferentes genera advertencia con acceso por fondo;
  no se omite automáticamente. Nunca revelar datos de otro fondo al informar un duplicado.
- PDF cifrados con contraseña quedan fallidos con motivo acotado; no recolectar
  contraseñas documentales en esta fase. La conexión y disco siguen cifrados.
- Validación inicial con pypdf en proceso hijo sin extracción/renderizado. Límites
  propuestos de pruebas: 5 000 páginas, 30 segundos y 512 MiB por proceso, además
  de los 100 MB acordados. Deben ser configurables y medidos; no son dimensionamiento
  institucional. Fallos/avisos del parser no se vuelcan crudos a logs ni al navegador.
- No abrir ni servir el contenido PDF desde el portal en esta entrega.
- Creación de fondos y concesión/revocación de acceso: solo superusuario. Un usuario
  ordinario necesita permiso de acción **y** acceso al fondo en cada consulta/comando.
  La revocación impide nuevas admisiones; el trabajo ya admitido conserva su historia.

## Cambios de base de datos propuestos, sin aplicar

Migración aditiva `0002_ingestion`, sin DROP, reset ni privilegios administrativos
para la API. Las tablas estarán en el esquema `ingestion`:

| Tabla | Contenido y restricción principal |
| --- | --- |
| `fonds` | UUID, nombre, clave de almacenamiento única e inmutable y activo. |
| `user_fonds` | Usuario/fondo únicos; concesión/revocación auditadas. |
| `batches` | Fondo, actor, estado/control, lista de candidatos y fechas. |
| `intake_items` | Cada entrega, incluso omitida/inválida; nombre, código original/normalizado, tamaño/hash y causa. |
| `documents` | UUID canónico, código único global, fondo y referencia relativa al PDF. |
| `jobs` | Documento, intento único y estado; el primer intento no se duplica por carreras. |
| `events` | Historia de cambios con causa acotada, fecha y actor/correlación. |
| `file_moves` | Intención, origen/destino relativos, integridad y etapa del movimiento recuperable. |
| `outbox` | Evento/tarea estable, intentos, próxima publicación, lease y confirmación. |

Documento, intento, evento y outbox se confirman en una transacción. El movimiento
físico se coordina mediante intención persistida y reconciliación; no existe una
transacción distribuida entre archivos, SQL y RabbitMQ. Repetir el publicador después
de una caída puede repetir un mensaje con el mismo ID; el futuro consumidor debe
ser idempotente. Una carrera de códigos no crea otro documento canónico.

Agregar fondo opcional a la auditoría F003 y filtrar los eventos documentales por
alcance. `audit.read` por sí solo no permite leer eventos de otros fondos. La auditoría
general existente conserva su comportamiento. Sesión, permiso, ámbito y mutación
se comprueban dentro de la misma transacción, incluyendo revocaciones concurrentes.

Grants de ejecución propuestos: SELECT/INSERT/UPDATE solo donde se cambia estado;
SELECT/INSERT para historia y auditoría, sin UPDATE/DELETE/TRUNCATE; membresías
permiten retirar la concesión conservando su evento. Sin CREATE/DROP de runtime.

## Procesos y RabbitMQ propuestos

Conservar FastAPI y añadir un proceso local independiente de ingreso dentro del
mismo paquete Python: recibe comandos persistidos, valida, mueve, recupera y publica.
Cerrar el navegador no destruye el lote. No es un worker Celery Windows.

Tarea versionada `document_platform.process_document.v1`, JSON persistente con IDs
estables de evento, documento, intento, lote y fondo, versión y correlación. El mensaje
no contiene PDF, texto, prompts, contraseñas ni rutas absolutas. Usar AMQPS verificado,
confirmaciones y detección de ausencia de ruta; no marcar en cola ante fallo incierto.

| Recurso | Propósito |
| --- | --- |
| `document_platform.integration` | Conservar sin cambios el probe anterior. |
| `document_platform.tasks` | Exchange durable para tareas. |
| `document_platform.processing` | Cola durable operativa, sin consumo en esta fase. |
| `document_platform.ingestion_test` | Cola sintética separada con routing key propia. |

Ampliar solo permisos exactos de estos recursos en el vhost de la aplicación, sin
etiquetas administrativas. Configure/write limitados a esas entidades; read permite
el exchange para bind y las colas integration/ingestion_test para pruebas. El productor
no recibe read de `processing`, por lo que no puede consumir ni purgar esa cola.
No usar regex globales, borrar/purgar colas ni mezclar IDs de bases de prueba con
la cola operativa. Los permisos de un futuro consumidor se definirán con F005/final.

## Interfaz y API previstas

Añadir **Ingreso de documentos** al portal React actual: selector de fondo autorizado,
ruta del buzón, acciones de lote, conteos de estados persistidos, búsqueda, filtros,
paginación y detalle de eventos. Un estado sin datos muestra su vacío; no usar números
simulados ni porcentajes de OCR. Administrar fondos/accesos será una sección exclusiva
para el superusuario. Reutilizar cookies, CSRF, sanitización y protección de navegación.

Contratos nuevos en `/api/v1/ingestion`: fondos visibles, administración de fondos y
concesiones, creación/listado/detalle de lotes, comandos pause/resume/stop y consultas
paginadas de entradas/eventos. Mutaciones con CSRF y razones para concesiones/controles.
Permisos existentes: `processing.start` para iniciar/reanudar, `processing.pause`,
`processing.stop`, `documents.read`, `failed.read` y `audit.read`, siempre con ámbito.
Los botones de retry/dismiss se mantienen fuera del alcance hasta F005/F007.

## Archivos previstos y alternativas

- `domain/ingestion/`, `application/ingestion/`: reglas, casos de uso y puertos.
- `infrastructure/persistence/ingestion.py`, `storage/`, adaptador PDF/publicador:
  SQL, movimientos, límites y outbox, separados de HTTP.
- `api/ingestion.py`, composición, entry point y configuración central validada.
- `backend/migrations/versions/0002_ingestion.py`, aprovisionamiento y grants.
- Ajuste acotado de identidad/auditoría para permisos y alcance transaccionales.
- `frontend/src/pages/`, contratos y navegación: interfaz sobre el HTTPS existente.
- Preparador explícito de topología/permisos broker, fixtures, contratos y guías.

Se recomienda ingreso por carpeta y lotes por ser el flujo acordado y verificable
ahora. Un cargador web con archivos de hasta 100 MB agregaría streaming, cuotas y
recuperación de cargas; puede añadirse después si se necesita. Vigilancia continua,
SSE/WebSocket y múltiples volúmenes gestionados quedan para una ampliación concreta.

## Riesgos y comprobaciones de aceptación pendientes

- Copia incompleta/ocupada, cambio de archivo durante lectura, traversal, reparse
  points y destino ocupado: no publicar bytes distintos ni sobrescribir archivos.
- PDF sintético válido CAB01: un documento, primer intento y mensaje confirmado;
  CAB02: otro; código repetido: una omisión auditada con PDF preservado.
- Límite de 100 MB, formato/estructura/páginas, PDF cifrado y timeout/memoria del parser.
  El parser no certifica ausencia de malware; solo usar documentos sintéticos.
- Reinicios entre registrar intención, mover y confirmar SQL/outbox: reconciliar
  contenido e historial sin duplicar documentos ni perder entregas.
- Broker caído, sin ruta o caída después del confirm: conservar publicación pendiente
  o repetible con IDs estables; nunca publicar metadatos válidos ficticios.
- Inicio/pausa/reanudación/detención reales, entrega posterior reservada al próximo
  lote, pendientes conservados y recuperación aunque se cierre el navegador.
- Dos usuarios/fondos: denegar IDs, listados, comandos y auditoría ajenos; revocación
  efectiva y backend resistente a llamadas directas. Mantener regresión F003/F004A.
- UI escritorio/móvil, teclado, estados vacíos/errores y datos reales del backend.
- HTTPS/API, SQL verify-full y AMQPS verificados; controles negativos de CA/hostname.
- Pruebas reales PostgreSQL y cola sintética aislada, lint/tipos/build y escaneo de
  secretos. Bases y evidencia sintéticas conservadas, sin DROP ni purga.

## Evidencia actual y autorización necesaria

En esta preparación se inspeccionaron código, requisitos y propuesta previa y se
consultaron fuentes primarias. Solo se redactó el alcance y ADR; no se crearon buzones,
no se cambiaron `.env`, SQL ni RabbitMQ y no se movieron/leyeron PDF institucionales.
Enlaces locales, exclusión de secretos, diff y propietarios comprobados: correctos.
No se repitieron pruebas de runtime: no cambió código; las pruebas funcionales
de ingestión aún no existen ni se ejecutaron.
Las comprobaciones funcionales anteriores siguen pendientes y no acreditan esta feature.

La consulta nueva es el esquema/ámbito, reglas adicionales y grants concretos de
esta entrega. [AGENTS.md](../../AGENTS.md) exige: “Consult new architecture, security,
authentication, database, infrastructure or scope decisions.” Se mantiene la propuesta
sin integrar en `develop` hasta implementar y verificar el alcance que se apruebe.

## Referencias

- [ADR 0006 propuesto](../decisions/0006-ingestion-operation-proposal.md).
- [Requisitos](../requirements.md), [pendientes](../open-questions.md).
- [pypdf: PdfReader y límites del lector](https://pypdf.readthedocs.io/en/stable/modules/PdfReader.html).
- [RabbitMQ: confirma publicación frente a consumo](https://www.rabbitmq.com/docs/confirms).
- [RabbitMQ: permisos por operación](https://www.rabbitmq.com/docs/access-control).
- [Celery: plataformas soportadas](https://docs.celeryq.dev/en/stable/getting-started/introduction.html).
