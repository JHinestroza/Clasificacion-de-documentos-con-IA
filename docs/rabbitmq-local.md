# RabbitMQ local: TLS y prueba de cola

## Estado y alcance

RabbitMQ 4.4.0 se ejecuta como servicio Windows. Esta feature comprueba AMQP real
por TLS con mensajes sintéticos; no ejecuta PDF, IA ni workers Celery. Docker sigue
reservado para la feature final. PostgreSQL y F003 continúan pendientes.

El listener de aplicación es `127.0.0.1:5671`, con certificado para `localhost` y
`127.0.0.1`; AMQP sin TLS en 5672 queda desactivado. No se abre la consola web de
administración. Esta feature no configura TLS de clustering/distribución Erlang:
no autoriza administración de nodos por red ni un despliegue remoto del equipo.

## Archivos y permisos Windows

Ejecutar desde una terminal de tu propia cuenta Windows. No ejecutar los preparadores
como `CodexSandboxOffline`, `CodexSandboxOnline` u otra cuenta Codex. El preparador
comprueba el usuario efectivo y se niega a crear activos bajo esas cuentas.

- `.env`: credenciales; se ajustan solo host `localhost` y puerto `5671` del broker.
- `.local/certs/`: CA y certificados originales, sin rotación.
- `.local/rabbitmq/`: certificado local del servidor, configuración y definitions
  con hash de contraseña; fuera de Git. La clave de la CA no se copia al servicio.
- `%APPDATA%/RabbitMQ/document-platform/`: copia mínima para el servicio, propiedad
  del usuario operador, con lectura para SYSTEM y acceso administrativo.
- `%APPDATA%/RabbitMQ/rabbitmq.conf`: configuración instalada. Se rechaza sobrescribir
  una configuración previa sin el marcador de esta aplicación.

No se crean cuentas de Windows. El usuario de RabbitMQ definido en `.env` carece
de etiquetas administrativas y solo tiene permisos sobre `document_platform.integration`
en su vhost de proyecto. Los recursos de procesamiento reales requerirán permisos
propios cuando se implemente esa feature. Se conservan usuarios y datos anteriores
del broker; no se purgan ni se borran colas existentes.

## Preparar e instalar

Desde la raíz del repositorio en PowerShell, con dependencias de desarrollo instaladas:

```powershell
.\backend\.venv\Scripts\python.exe -m scripts.prepare_rabbitmq_local
.\scripts\configure_rabbitmq_windows.ps1 -Restart
```

La preparación conserva las credenciales y el par TLS que ya generó para esta
integración. Un conflicto o certificado expirado requiere revisión explícita.
El instalador aplica ACL con `icacls`; reiniciar el servicio requiere consentimiento
administrativo de Windows (UAC). La parte elevada solo reinicia el servicio y no
crea archivos del proyecto bajo una identidad diferente.

## Publicar y ver mensajes

```powershell
.\backend\.venv\Scripts\python.exe -m document_platform.broker_probe check
.\backend\.venv\Scripts\python.exe -m document_platform.broker_probe publish --count 3
.\backend\.venv\Scripts\python.exe -m document_platform.broker_probe status
```

`publish` crea únicamente la topología de prueba, publica JSON persistente y espera
confirmación del broker. No procesa documentos. `status` consulta pasivamente y
muestra `messages_ready`; no crea, consume ni purga la cola.

```powershell
.\backend\.venv\Scripts\python.exe -m document_platform.broker_probe consume --requeue
.\backend\.venv\Scripts\python.exe -m document_platform.broker_probe status
.\backend\.venv\Scripts\python.exe -m document_platform.broker_probe consume --limit 2
```

Reencolar mantiene el mensaje pendiente; al recibirlo de nuevo se observa la marca
`redelivered`. El consumo normal valida el evento y confirma ACK. Un mensaje no
reconocido se conserva por reencolamiento. Solo se admite la cola dedicada; esta
herramienta nunca consume colas documentales. Cada comando está limitado a 100
mensajes y no hay bucle de consumo automático.

El conteo mostrado es de mensajes listos para entrega, no de todo el historial.
Todavía no hay persistencia PostgreSQL de estados, auditoría de usuario ni garantías
de idempotencia del futuro procesamiento documental. El ACK elimina el mensaje
confirmado de esta cola de prueba; no es una aprobación archivística.

## Pruebas de seguridad e integración

```powershell
.\backend\.venv\Scripts\python.exe -m scripts.verify_rabbitmq_local
```

La comprobación exige primero una conexión válida y después distingue rechazo real
por contraseña incorrecta, CA no confiable, hostname incorrecto y permisos fuera de
la cola autorizada. Comprueba que 5672 no escucha. No consume mensajes ni imprime
credenciales o URLs con contraseñas. No utiliza el worker Celery en Windows.

Para pytest, usar temporales nuevos propiedad de tu usuario, evitando carpetas
creadas previamente por las cuentas sandbox:

```powershell
$testParent = Join-Path (Get-Location).Path '.local/test-runs'
New-Item -ItemType Directory -Path $testParent -Force | Out-Null
$testRun = Join-Path $testParent ('rabbitmq-' + (Get-Date -Format 'yyyyMMdd-HHmmssfff'))
.\backend\.venv\Scripts\python.exe -m pytest -c backend/pyproject.toml backend/tests tests -q -W error --basetemp $testRun
```

Usar siempre un nombre nuevo: pytest puede limpiar el directorio que recibe como
`--basetemp`. Nunca pasar `.local`, almacenamiento documental o una carpeta con
credenciales como directorio base de pruebas.

## Diagnóstico y recuperación

- Conexión rechazada: comprobar servicio Windows y listener 5671, sin cambiar a 5672.
- Certificado rechazado: comprobar la CA y el hostname; no desactivar verificación.
- Acceso denegado: revisar el vhost/usuario y ACL de archivos; no conceder permisos
  globales ni usar un administrador del broker para la aplicación.
- Falla de arranque tras instalar: revisar el log del servicio y la configuración
  marcada; no eliminar su directorio `db`. Restaurar configuración previa requiere
  identificar su respaldo y reiniciar. No existe comando de borrado automático.
- `/ready` de la API puede seguir respondiendo 503 por ausencia de PostgreSQL aunque
  la comprobación independiente del broker sea correcta.

## Fuentes primarias

- [RabbitMQ TLS](https://www.rabbitmq.com/docs/ssl).
- [Windows y configuración del servicio](https://www.rabbitmq.com/docs/windows-configuration).
- [Importación de definitions](https://www.rabbitmq.com/docs/definitions).
- [Permisos RabbitMQ](https://www.rabbitmq.com/docs/access-control).
