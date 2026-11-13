# ADR 0006 propuesto — Ingreso por carpetas y lotes recuperables

- Estado: propuesto; pendiente de consulta para el modelo/grants/reglas adicionales.
- Actualización: 2026-11-13.
- Feature: [F004B propuesta](../features/F004B-ingestion-carpetas-proposal.md).
- La preparación original permanece en `feature/ingestion-operacion`.

## Base aprobada y evolución

FastAPI/PostgreSQL/RabbitMQ/Celery, TLS, cuentas locales, permisos y outbox ya están
aprobados. React/TypeScript/Vite fue elegido y verificado en F004A; reemplaza la
recomendación inicial de HTML/JavaScript sin framework. No se reabre esa elección.
Las reglas de éxito, duplicados, conservación, tamaño y controles por lote están
aceptadas; las decisiones adicionales se enumeran en la ficha F004B.

## Decisión propuesta

Entrada local por carpeta configurada, una raíz privada/volumen con subdirectorios
por fondo, entregas completas .part -> .pdf y lotes de una lista finita. Un ayudante
local permite depositar sin leer una copia todavía en curso. El navegador no elige
rutas del host. Código canónico ASCII en mayúsculas sin quitar ceros; advertir,
sin omitir automáticamente, contenido idéntico con códigos diferentes.

API y proceso de ingreso separado comparten módulos y PostgreSQL. El proceso
independiente permite recuperar lotes/outbox sin depender de una petición web ni
de un worker Celery Windows. El trabajo se registra en SQL y el archivo se mueve
con intención persistida y reconciliación. Una confirmación AMQP termina en cola,
no en success. El futuro consumidor conserva responsabilidad de idempotencia.

Migración aditiva de fondos, ámbitos, lotes, entradas, documentos, intentos, eventos,
movimientos y outbox. Ampliar auditoría con fondo opcional y filtro de alcance.
Acción, sesión y ámbito se verifican junto con la mutación; superusuario administra
fondos y accesos. No exponer PDF ni reencolar/retirar fallidos todavía.

Ampliar grants exactos del broker para tasks/processing/ingestion_test, conservando
integration. El productor puede bind/publicar pero no recibe read de processing;
las pruebas consumen únicamente la cola sintética. No usar permisos globales.

Validar estructura/páginas con pypdf en proceso con límites antes de publicar.
La ficha propone límites iniciales ajustables; el parser no es una garantía de
malware ni autoriza documentos reales. Fijar versión y comprobar seguridad/compatibilidad
cuando se apruebe instalar esa dependencia.

## Alternativas y consecuencias

El ingreso por carpetas sigue el flujo solicitado. Un cargador web sería útil para
seleccionar PDF desde el navegador, pero requiere streaming/cuotas y recuperación
de cargas de hasta 100 MB; se propone como ampliación posterior. Una vigilancia
continua cambia los controles acordados por lote y no se habilita implícitamente.

La interfaz consulta estados persistidos manualmente al principio; cualquier
actualización automática debe conservar caducidad de sesión y no inventar progreso.
SSE/WebSocket no son necesarios para verificar esta entrega. Las garantías frente
a caídas se prueban en cada transición de archivos/SQL/broker, sin prometer atomicidad
distribuida. Un único volumen reduce los casos iniciales sin borrar la futura opción
entre unidades. Docker/worker Linux siguen fuera de este alcance.

## Aprobación y fuentes

La ficha concreta tablas, grants, reglas, archivos y aceptación. No hay migraciones
ni cambios de runtime aplicados por este ADR. Pendiente de respuesta del responsable.

- [Mensajería aprobada](0001-messaging.md).
- [React aprobado](0007-react-portal.md).
- [pypdf: lector](https://pypdf.readthedocs.io/en/stable/modules/PdfReader.html).
- [RabbitMQ: confirmaciones](https://www.rabbitmq.com/docs/confirms).
- [RabbitMQ: control de acceso](https://www.rabbitmq.com/docs/access-control).
- [Celery: soporte](https://docs.celeryq.dev/en/stable/getting-started/introduction.html).
