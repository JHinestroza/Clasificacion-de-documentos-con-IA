# Ingreso local de PDF — UFM

F004B recibe PDF desde una carpeta, conserva su historia y publica trabajos por
AMQPS. El documento admitido queda **En cola**, físicamente en `processing`.
La extracción de texto, los metadatos y las acciones de reencolar/retirar fallidos
se entregarán después. `success` está reservado a metadatos terminados.

## Arranque habitual

Usar PowerShell bajo la cuenta Windows **Usuario**, desde la raíz del repositorio.
PostgreSQL y RabbitMQ deben estar iniciados. Las credenciales siguen en el `.env`
ignorado; los certificados y claves permanecen en archivos protegidos de `.local`.
No ejecutar estos comandos bajo cuentas sandbox Codex.

Terminal 1, API y portal HTTPS:

```powershell
.\backend\.venv\Scripts\python.exe -m document_platform
```

Terminal 2, proceso de ingreso:

```powershell
.\backend\.venv\Scripts\python.exe -m document_platform.ingestion_runtime run
```

Abrir [el portal local](https://localhost:8443/#ingreso), iniciar sesión y seleccionar
**Ingreso de documentos → UFM**. La cuenta inicial es `admin`; su contraseña inicial
está en `APP_BOOTSTRAP_ADMIN_PASSWORD` del `.env`. Si se cambió desde Mi cuenta,
utilizar la contraseña actual. No es la contraseña del administrador PostgreSQL.

Ambos procesos comparten la configuración; no se necesita un servidor Node para
servir el portal compilado. Si se modifica el frontend, compilar como explica
[la guía React](react-portal.md). No ejecutar un servidor HTTP Vite.

La disponibilidad de PostgreSQL/RabbitMQ no demuestra que el proceso de ingreso
esté encendido. Si un lote no avanza, comprobar también la segunda terminal.
Cerrar el navegador no detiene ese proceso ni pierde el lote.

## Depositar los primeros archivos

La raíz predeterminada es `APP_STORAGE_ROOT=.local/documents`. La ruta concreta
se muestra en el portal a quienes tienen permiso para iniciar el ingreso:

```text
.local/documents/UFM/
  incoming/     entregas completas pendientes; archivos .part ignorados
  processing/   PDF admitidos, con publicación pendiente o ya en cola
  failed/       entradas fallidas con contenido e historial conservados
  success/      reservado a metadatos completados en una entrega futura
  skipped/      nuevas entregas omitidas por código ya registrado
```

Para comprobar el ingreso, utilizar PDF ficticios llamados `CAB01.pdf`, `CAB02.pdf`,
etc. El ayudante de depósito evita publicar una copia incompleta y conserva el
archivo original externo:

```powershell
.\backend\.venv\Scripts\python.exe -m document_platform.ingestion_runtime deposit 'C:\PDF-Pruebas\CAB01.pdf' --fonds UFM
```

El ayudante copia a `.part`, comprueba tamaño/integridad y publica el nombre final
sin sobrescribir un archivo existente. Una copia interrumpida queda como `.part`
y no entra al lote. El origen externo se conserva; los movimientos posteriores
entre carpetas gestionadas sí retiran el archivo de su ubicación anterior.

Alternativa manual: copiar dentro de `incoming` con extensión `.part` y renombrar
al nombre final `.pdf` cuando la copia haya terminado. Habilitar la visualización
de extensiones en el Explorador para evitar nombres como `CAB01.pdf.pdf`.
No basta con observar dos veces el mismo tamaño para garantizar una entrega completa.

## Operar un lote

1. Depositar los PDF completos y elegir UFM en la interfaz.
2. Pulsar **Iniciar lote**. Se toma una lista finita de los PDF presentes.
3. Seleccionar el lote y pulsar **Actualizar estado** para consultar progreso,
   filtro de estado, búsqueda e historial. Los conteos proceden de PostgreSQL.
4. Los archivos que lleguen después de iniciar quedan para otro lote.

Solo puede existir un lote activo por fondo. **Pausar** permite terminar la
admisión iniciada y bloquea la siguiente; **Reanudar** continúa ese lote.
**Detener** termina esa admisión, cierra el lote y conserva los pendientes en
`incoming` para un nuevo inicio. Ningún control purga RabbitMQ ni cancela tareas
ya publicadas. El historial del lote detenido conserva los candidatos que no admitió.

`Ingreso terminado` significa que acabó la admisión del lote; sus documentos pueden
seguir pendientes de publicación o en cola. No significa que sus metadatos estén listos.
No hay porcentajes de OCR ni resultados simulados.

## Reglas y límites

- Código completo sin extensión, normalizado a mayúsculas ASCII sin quitar ceros:
  `cab01.PDF` → `CAB01`. Es único globalmente entre fondos.
- De 1 a 64 caracteres: letras ASCII, números, guion o guion bajo; comenzar por
  letra/número. Nombres con espacios, múltiples puntos u otros caracteres fallan
  con una causa pública; no se reescriben silenciosamente.
- Máximo de 100 MB = 100 000 000 bytes por PDF. Límite inicial de 1 000 archivos
  por lote, configurable en `APP_INTAKE_BATCH_LIMIT`.
- Validación estructural con pypdf 7.1.0 en un proceso separado, sin extraer texto,
  renderizar páginas ni ejecutar contenido PDF. PDF con contraseña quedan fallidos.
- Límites iniciales: `APP_INTAKE_MAX_PAGES=5000`,
  `APP_INTAKE_PARSER_SECONDS=30`, `APP_INTAKE_PARSER_MEMORY_MB=512`.
  El padre aplica timeout; el hijo tiene su propio plazo y límites de CPU/memoria.
- Código repetido: se conserva la nueva entrega en `skipped`, con evento y causa;
  no se crea otro documento/trabajo ni se vuelve a analizar con el parser.
- Contenido idéntico con códigos distintos se admite y genera advertencia dentro
  del ámbito autorizado. No se revelan datos de otros fondos al avisar de duplicados.

Todas las carpetas gestionadas deben estar en la misma unidad local. Se rechazan
traversal, enlaces/reparse points y destinos ocupados. Cambiar de volumen gestionado
requiere diseñar y probar ese flujo; no se habilita mediante una copia improvisada.
Las ACL no prueban cifrado. El responsable reporta cifrado en las ubicaciones actuales;
PKI institucional, cobertura de respaldos y despliegue final conservan su verificación pendiente.
Un parser estructural no certifica ausencia de malware. Las pruebas usan solo PDF sintéticos.

## Permisos de personas

El superusuario administra fondos y accesos desde la vista de ingreso. Una cuenta
ordinaria necesita permiso de acción **y** acceso explícito al fondo:

| Acción | Permiso |
| --- | --- |
| Iniciar/reanudar lote y reintentar publicación bloqueada | `processing.start` |
| Pausar | `processing.pause` |
| Detener | `processing.stop` |
| Consultar documentos del lote | `documents.read` |
| Consultar solo fallidos | `failed.read` |
| Consultar historial/auditoría | `audit.read` |

Las consultas de control de lotes están disponibles para operadores con acciones
de ingreso o lectura. `failed.read` sin `documents.read` siempre limita la lista
a fallidos, incluso ante una llamada directa que solicite otro filtro.
La revocación impide nuevas admisiones; lo ya admitido conserva su historia.
La cuenta de superusuario de la aplicación no es administrador de PostgreSQL/Windows.
No se sirve el contenido de los PDF desde el portal en esta entrega.

## Fallos y recuperación

Errores de PDF conservan el archivo en `failed`, con código/causa técnica disponible
e historial; esos datos no se publican como metadatos completados. Archivos ocupados
se esperan. Si cambia la identidad del archivo o existe conflicto de destino, se
conservan los bytes y el registro del movimiento para revisión; no sobrescribir ni
borrar manualmente las ubicaciones para forzar un reintento.

Una caída de RabbitMQ conserva el PDF en `processing` y la publicación en outbox.
Se reintenta con espera progresiva y un máximo de diez fallos consecutivos. Después,
**Reintentar publicación** requiere permiso, fondo y motivo. Es el mismo trabajo,
no un reencolado de procesamiento. No introducir un PDF duplicado para resolverlo.

Una caída después de publicar y antes de confirmar en SQL puede repetir el mensaje
con el mismo ID. Los documentos e intentos permanecen únicos; el futuro consumidor
será responsable de idempotencia. La confirmación del productor solo acredita
recepción por RabbitMQ, no ejecución de metadatos.

Al reiniciar, el ingreso reconcilia movimientos pendientes y recupera publicaciones
con lease vencido. Un bloqueo asesor PostgreSQL impide dos pasos simultáneos en la
misma base. No se ejecuta Celery worker en Windows.

Para detener la aplicación local, usar Ctrl+C en cada terminal. El estado persistido
se conserva. En Windows/Python 3.14 se han observado avisos de transporte y procesos
pendientes de cierre de Uvicorn; identificar PID, propietario, comando y fecha de
creación antes de una terminación explícita. Nunca detener todos los procesos Python.

## Preparar otra instalación local

Solo cuando no esté provisionada esta entrega:

```powershell
.\backend\.venv\Scripts\python.exe -m document_platform.identity_admin init-db
.\scripts\configure_ingestion_rabbitmq_windows.ps1
.\backend\.venv\Scripts\python.exe -m document_platform.ingestion_runtime init-local
```

`init-db` aplica migración aditiva y grants mínimos sin DROP ni reset. El preparador
RabbitMQ conserva credenciales, certificado y colas, y amplía solo las entidades
aprobadas. Si el CLI no autentica contra el servicio, aplica las definiciones mediante
un reinicio con UAC; no copia la cookie de administración ni imprime sus diagnósticos.
No es necesario repetirlo en cada arranque.

`init-local` inicia/cierra una sesión del superusuario inicial, configura UFM y
restringe la raíz de archivos a Usuario/SYSTEM/Administradores. No rota contraseñas.
Si la contraseña inicial ya cambió, administrar UFM desde el portal con la cuenta
actual; el bootstrap no sirve para recuperar/resetear esa cuenta.

El productor RabbitMQ solo opera `document_platform.tasks`,
`document_platform.processing`, `document_platform.ingestion_test` y conserva
`document_platform.integration`. No puede consumir/purgar la cola operativa.
Las bases sintéticas publican únicamente en `document_platform.ingestion_test`.
Las herramientas del probe anterior consultan su propia cola integration, no trabajos PDF.

## Verificación y evidencia

Ver [desarrollo](development.md), [contrato estático](api/F004B-openapi.json) y
[la ficha F004B](features/F004B-ingestion-carpetas-proposal.md). Las bases y capturas
sintéticas se conservan en ubicaciones ignoradas; no hay limpieza mediante DROP/purga.
Docker, worker Linux, OCR/metadatos y reencolamiento/retirada de fallidos siguen
fuera del alcance de esta entrega.
