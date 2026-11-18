# F004B — Ingreso recuperable de PDF por carpetas

- Estado: implementada y verificada.
- Rama: `feature/ingestion-carpetas`, creada desde `develop` (`21f6cf8`).
- Alcance aprobado expresamente: 2026-11-13. Primer fondo: **UFM**.
- Revisión visual: 2026-11-13. Verificación de cierre: 2026-11-18.
- El nombre histórico del archivo conserva los enlaces de la propuesta aprobada.

## Resultado y alcance

El portal React ahora permite elegir un fondo autorizado, ver su carpeta de ingreso,
iniciar un lote y consultar estados, búsqueda, filtros e historial paginado.
Los controles de pausa/reanudación/detención registran actor, fecha y motivo.
El ingreso es un proceso Python independiente de la API y del navegador, dentro de
la misma aplicación modular. No es un worker Celery en Windows.

Una entrega completa se reclama y mueve físicamente desde `incoming` a `processing`
con intención persistida. Los PDF admitidos crean documento, primer intento, evento
y outbox en una transacción PostgreSQL; después se publican por AMQPS con contrato
Celery v2. La confirmación deja el trabajo **En cola**. No acredita extracción ni
metadatos completados y no mueve el PDF a `success`.

Las entradas inválidas conservan contenido y causa en `failed`; los códigos ya
registrados conservan la nueva entrega en `skipped`. La historia no se elimina.
Un archivo cambiado, una ruta insegura o un destino conflictivo se conservan para
revisión, sin sobrescribir bytes ni publicar ese contenido como válido.

## Decisiones y reglas implementadas

- React/TypeScript sobre FastAPI HTTPS, PostgreSQL TLS verify-full y RabbitMQ AMQPS
  verificado. Se conservan la CA autorizada, sesiones opacas y CSRF de F003/F004A.
- Raíz privada `.local/documents`, configurable mediante `APP_STORAGE_ROOT`; por
  fondo se crean `incoming`, `processing`, `failed`, `success` y `skipped`.
- Un volumen gestionado, nombres internos UUID y publicación sin sobrescritura.
  El navegador selecciona un fondo, nunca una ruta arbitraria del host.
- Depósito completo `.part` → `.pdf`; el ayudante copia/verifica y conserva el
  original externo. El ingreso posterior sí retira el PDF de su ubicación gestionada.
- Código completo sin extensión, ASCII y mayúsculas: CAB01.pdf/cab01.PDF → CAB01,
  conservando ceros. Código único global; letras/números/guion/guion bajo, 1–64
  caracteres y comienzo alfanumérico. Nombres ajenos a esa regla se rechazan.
- SHA-256 para integridad; contenido idéntico con códigos distintos se admite y
  advierte dentro del fondo, sin revelar información documental ajena.
- Máximo de 100 000 000 bytes por PDF; lote inicial limitado a 1 000 candidatos.
  pypdf 7.1.0 valida estructura/páginas en proceso hijo sin extracción ni renderizado.
  PDF con contraseña, exceso de páginas y límites alcanzados conservan su causa.
- Límites configurables de pruebas: 5 000 páginas, 30 segundos y 512 MiB. El padre
  aplica timeout; el hijo aplica un plazo independiente y límites OS de CPU/memoria.
  Se verificó que también termina si su padre sale. No se presenta como sandbox
  completo ni certificación de ausencia de malware.
- Iniciar toma una lista finita. Pausar/Detener terminan la admisión iniciada;
  reanudar continúa el lote pausado y detener conserva pendientes para otro lote.
  Los mensajes ya publicados no se purgan ni cancelan por esos controles.

## Persistencia, permisos y recuperación

Migración aditiva `0002_ingestion`: fondos, concesiones de fondo, lotes, entradas,
documentos, trabajos/intentos, eventos, movimientos y outbox; fondo opcional en la
auditoría existente. No hay DROP/reset ni migraciones automáticas al arrancar la API.
La base principal y UFM se aprovisionaron por TLS con las herramientas explícitas.

El backend comprueba sesión, acción y ámbito en la misma transacción que la mutación.
Solo el superusuario administra fondos/concesiones. Un usuario sin ámbito no puede
consultar IDs/listas/eventos ajenos. `failed.read` sin `documents.read` fuerza lectura
solo de fallidos. La revocación impide nuevas admisiones; un operador autorizado
puede reanudar y queda registrado el relevo. Las concesiones guardan actor, usuario
afectado, fondo, fecha y motivo. `audit.read` no evita el filtro de fondo.

El rol SQL de ejecución no administra base/roles/esquema. Fondos y documentos
canónicos son SELECT/INSERT; estados mutables permiten las actualizaciones necesarias.
Eventos/auditoría son append-only para ese rol; no tiene DELETE/TRUNCATE ni CREATE.
Se eliminan permisos PUBLIC sobre las tablas nuevas.

Cada movimiento registra intención antes de tocar los archivos y se reconcilia tras
reinicio comprobando identidad/integridad. Un bloqueo asesor de proceso evita pasos
simultáneos de ingreso en la misma base, sin mantener el bloqueo de seguridad
mientras se analiza un PDF o se espera al broker.

Outbox usa IDs estables, lease recuperable y reintentos progresivos. Tras diez fallos
consecutivos queda bloqueado; reintentar publicación requiere permiso, fondo y motivo.
Una caída después de confirmar en RabbitMQ y antes de registrar en SQL puede repetir
el mismo mensaje; el futuro consumidor deberá ser idempotente. No se crea otro
documento/primer intento por esa repetición.

## RabbitMQ aplicado

Se conservó `document_platform.integration` y se habilitaron únicamente exchange
`document_platform.tasks`, cola `document_platform.processing` y cola separada
`document_platform.ingestion_test`. Configure/write se limitan a estos recursos;
read solo incluye tasks/integration/ingestion_test. El productor no puede consumir
ni purgar processing. No recibió etiquetas administrativas ni credenciales nuevas.

La configuración anterior y su hash de contraseña se conservaron. El CLI local no
autenticó con la cookie del servicio; no se leyó ni copió esa cookie. Tras cancelar
el primer UAC, el responsable autorizó volver a mostrarlo y se aplicó el reinicio.
No se purgaron/borraron colas, ni se rotaron contraseñas/certificados. Las bases de
prueba nunca publican en la cola operativa.

## Archivos de la entrega

| Archivos | Función |
| --- | --- |
| `domain/ingestion/`, `application/ingestion/` | Reglas, autorización, controles y orquestación recuperable. |
| `infrastructure/persistence/ingestion.py`, migración 0002 y `identity_admin.py` | SQL parametrizado, historia, outbox y grants mínimos. |
| `infrastructure/storage/`, `pdf_probe.py` | Depósito/movimientos privados y parser con límites. |
| `infrastructure/messaging/intake.py` | Contrato Celery, confirmaciones y detección de ausencia de ruta. |
| `ingestion_runtime.py`, `config.py`, `api/ingestion.py` | Composición, comandos locales, ajustes y HTTP. |
| Ajustes de identidad/auditoría | Reutilizar la sesión en la transacción del recurso y filtrar por fondo. |
| `frontend/src/pages/Intake.tsx`, contratos, navegación y CSS | Ingreso real, administración de fondos y estados adaptables. |
| `scripts/*ingestion*rabbitmq*` | Ampliación explícita y repetible de permisos locales. |
| Pruebas backend/React, `.gitignore`, snapshots y documentación | Evidencia y entrega reproducible. |

La excepción específica de `.gitignore` incluye los módulos Python del adaptador
`infrastructure/storage`; los datos de almacenamiento permanecen ignorados.
Las claves y `.env` no se incluyen en Git ni en artefactos web.

## Verificaciones reales

- **189 pruebas backend pasaron** el 2026-11-18, con PostgreSQL/RabbitMQ locales
  reales por TLS y PDF ficticios. Sin omisiones, con advertencias como errores y
  cacheprovider deshabilitado para no tocar cachés antiguas de otras cuentas.
- Se verificaron códigos, bytes exactos al mover, depósito completo, destino ocupado,
  cambios de archivo, traversal, junction Windows real y lector frente a escritor activo.
- Límite exacto 100 MB, estructura inválida, PDF con contraseña, páginas, memoria,
  CPU y salida del padre del parser. El hijo mantiene su propio límite temporal.
- Lotes reales, pausa durante validación, parada conservando pendientes y nuevo lote;
  reinicios tras mover y tras publicar conservan IDs y no duplican documentos/intentos.
- Broker no disponible, publicación sin ruta real, contrato Celery y persistencia,
  ACK solo de mensajes sintéticos propios y rechazo real de consumir processing.
- Dos ámbitos/roles, revocación, historial y lectura limitada a fallidos; SQL niega
  alterar historia, códigos/clave del fondo o crear tablas. Sesión/CSRF/Origin se
  mantienen. La prueba negativa de CA usa confianza aislada, ya que Windows confía
  legítimamente en la CA de desarrollo aprobada.
- **24 pruebas React pasaron** el 2026-11-18; build/TypeScript, ESLint, Prettier y
  npm audit correctos, con cero vulnerabilidades reportadas. Ruff, mypy estricto
  (54 módulos/scripts) y pip check correctos. El contrato OpenAPI declara la cookie
  obligatoria; la prueba HTTP focalizada volvió a pasar después de esa anotación.
- Revisión real HTTPS el 2026-11-13: superusuario, operador UFM y lector sin fondo.
  Inicio, pausa/reanudación con motivos, detención y nuevo lote, búsqueda, filtros,
  formularios de fondos/concesiones sin guardar y cierre de todas las sesiones de prueba.
- El operador vio un lote mixto: un PDF en cola, uno fallido y uno omitido. La lista
  y el detalle se actualizan juntos después de un control; se corrigió y probó esa
  discrepancia visual. Un lector sin fondo no recibió documentos ni controles ajenos.
- Escritorio 1280×900 y móvil 390×844: ancho de página 375 px en móvil, tabla con
  desplazamiento interno (298/650 px), sin ensanchar la página. Overrides restablecidos.
- Captura JPEG de datos sintéticos, propietaria Usuario, en `.local/feature-evidence/F004B/`;
  SHA-256 `B9F109A10C4BCAB858CF930B063B4201D1DE1EF1512699AD83984AD657F12589`.
  Se conservan bases, PDF y mensajes sintéticos identificados; no hubo DROP ni purga.

## Operación, límites y pendientes

[Guía UFM](../ingestion-local.md), [contrato](../api/F004B-openapi.json) y
[ADR 0006](../decisions/0006-ingestion-operation-proposal.md) describen operación y decisión.
Los archivos de prueba, claves y evidencia siguen fuera de Git y bajo Usuario.
La API temporal 8444 se cerró verificando PID/propietario/comando/fecha, sin detener
otros procesos. El portal operativo utiliza HTTPS 8443.

F004B termina en cola. Sin OCR/extracción, IA, metadatos completos, visualizador PDF,
carga web de 100 MB, vigilancia continua, reencolado/retirada de fallidos ni dashboard
avanzado. `success` sigue reservado. Docker y Celery Linux permanecen en la feature final.

El parser no sustituye aislamiento/antimalware. El almacenamiento y la base de datos
no forman una transacción distribuida; los conflictos de identidad quedan bloqueados
para revisión. Un único volumen es el alcance verificado. La PKI institucional,
volúmenes/respaldos cifrados, retención y operación Linux requieren su propia evidencia.
No hay código, imágenes, tags ni releases publicados remotamente.


## Puesta en marcha local del 2026-11-18

Se volvió a comprobar la revisión `0002_ingestion`, UFM y la conexión AMQPS. La
base operativa no contiene lotes de prueba: los fixtures están en bases separadas.
Las cinco carpetas UFM pertenecen a BIB-30\Usuario; la raíz tiene ACL protegida
con Usuario, SYSTEM y Administradores, sin concesiones amplias.

API e ingreso quedaron iniciados como procesos de Usuario. El shell, health y ready
respondieron 200 mediante `ssl.create_default_context()` con verificación normal
de cadena/hostname; ready reportó PostgreSQL y broker disponibles. Los PID/fechas
se guardan privadamente para distinguirlos de otros Python. No se reiniciaron
PostgreSQL/RabbitMQ en este cierre ni se borraron documentos o mensajes.
