# Usuarios, permisos y PostgreSQL local

F003 proporciona una API HTTPS de cuentas y auditoría. Todavía no hay pantalla de
login, ingestión de PDF ni ejecución de trabajos documentales. Los siguientes
comandos se ejecutan desde la raíz del repositorio con la cuenta Windows `Usuario`.

## Estado de esta instalación

- PostgreSQL 18.7, servicio `postgresql-x64-18`, loopback 5432 con TLS obligatorio.
- Base `document_platform`; rol de ejecución `document_app`, sin administración SQL.
- Superusuario de aplicación `admin`, creado explícitamente. Su contraseña inicial
  está en `APP_BOOTSTRAP_ADMIN_PASSWORD` del `.env` ignorado; no se muestra en consola.
- RabbitMQ local AMQPS 5671. Ver [su guía](rabbitmq-local.md) para la cola sintética.
- Todas las ubicaciones actuales se declaran cifradas por el responsable. La
  comprobación de cifrado del servidor, volúmenes y respaldos sigue pendiente.

## Arrancar y probar lo ya instalado

Primera terminal PowerShell, desde la raíz:

```powershell
.\backend\.venv\Scripts\python.exe -m document_platform
```

Segunda terminal:

```powershell
.\backend\.venv\Scripts\python.exe scripts/probe_identity_local.py
```

El comprobador valida la CA y nombre `localhost`, verifica `/ready`, inicia sesión
con el secreto de inicialización de `.env`, consulta identidad, usuarios, catálogo
y auditoría, cierra sesión y espera 401 al consultar de nuevo. No imprime la
contraseña ni cookies y no crea cuentas adicionales. Sí registra sus sesiones y
acciones en auditoría. Si cambiaste la contraseña del usuario inicial, la antigua
variable de bootstrap ya no permite iniciar sesión; no es una función de recuperación.

Para una consulta de salud sin credenciales:

```powershell
curl.exe --cacert .local/certs/ca.crt https://localhost:8443/api/v1/health
curl.exe --cacert .local/certs/ca.crt https://localhost:8443/api/v1/ready
```

No se usan opciones que omitan validación TLS. La CA de desarrollo está autorizada y verificada en el almacén Windows de Usuario
desde F004A; no se instaló en el almacén de la máquina. Detener la API con `Ctrl+C`.

## Preparar una instalación local nueva

Esta sección documenta lo aplicado; no requiere repetir la configuración de
servicio en esta computadora. El preparador nativo está dirigido a PostgreSQL 18
con su ruta estándar y cuenta `NetworkService`. Revisar estas rutas antes de
usarlo en una instalación distinta. No es un instalador general ni un despliegue Linux.

1. Preparar Python y certificados con [la guía de desarrollo](development.md).
2. Instalar PostgreSQL. Su contraseña administrativa debe coincidir con
   `APP_DB_ADMIN_PASSWORD` de `.env`; la aplicación utiliza otra contraseña,
   `APP_DB_PASSWORD`, sin compartir el rol administrador.
3. Ejecutar como Usuario el preparador que solicita UAC para configurar TLS y
   reiniciar únicamente el servicio PostgreSQL del proyecto:

```powershell
powershell.exe -NoProfile -File scripts/configure_postgres_windows.ps1
```

El preparador conserva la CA existente, crea un certificado PostgreSQL con SAN
localhost/127.0.0.1/::1/postgres, copia la identidad TLS a
`C:\ProgramData\DocumentPlatform\PostgreSQL` y limita su lectura al operador,
NetworkService, SYSTEM y administradores. No copia la clave privada de la CA.
Añade un include a `postgresql.conf`; el original queda respaldado bajo
`.local/postgres/postgresql.conf.before-tls`. Reejecutar no rota la identidad.
Los certificados vencidos o conjuntos parciales requieren revisión y renovación.

Se rechaza todo acceso sin TLS y todo origen fuera de loopback. La cuenta postgres
puede administrar por TLS local; `document_app` solo accede a la base del proyecto
y bases sintéticas con el prefijo autorizado. No se envían credenciales por texto plano.

Provisionar el rol limitado, base y migraciones, desde este checkout:

```powershell
.\backend\.venv\Scripts\python.exe -m document_platform.identity_admin init-db
```

Solo este comando y la migración cargan las credenciales de administrador SQL. No
borra datos ni cambia contraseñas existentes; comprueba propietarios/roles y
reaplica privilegios del proyecto. La API utiliza únicamente las credenciales de
servicio. Las migraciones se ejecutan explícitamente, nunca al arrancar un worker.
No se permite un downgrade destructivo.

Agregar al `.env` `APP_BOOTSTRAP_ADMIN_USERNAME` y un valor aleatorio único de al
menos 16 caracteres para `APP_BOOTSTRAP_ADMIN_PASSWORD`, preferiblemente generado
por un gestor de contraseñas. Este equipo ya tiene ambos. Después:

```powershell
.\backend\.venv\Scripts\python.exe -m document_platform.identity_admin create-superuser
```

El comando no imprime el secreto y solo inicializa una vez. La contraseña del
portal se almacena como Argon2id. El `.env` no es un listado de contraseñas de todos
los usuarios. Tras cambiar la contraseña inicial, la variable de bootstrap queda
obsoleta para login; no se sobrescribe automáticamente ni se usa para restablecerla.

## Contrato de API

[OpenAPI estático](api/F003-openapi.json), generado desde la aplicación; las rutas
Swagger/OpenAPI públicas siguen deshabilitadas. Base: `https://localhost:8443/api/v1`.

| Método/ruta | Autorización y comportamiento |
| --- | --- |
| `GET /auth/csrf` | Obtener desafío y cookie CSRF; si existe sesión debe ser válida. |
| `POST /auth/login` | Origin y CSRF; cuerpo username/password; devuelve usuario y nuevo CSRF, establece sesión en cookie. |
| `GET /auth/me` | Sesión válida; devuelve usuario y permisos, nunca hash. |
| `POST /auth/logout` | Sesión, Origin y CSRF; revoca sesión y elimina cookies. |
| `POST /auth/password` | Sesión, Origin y CSRF; current_password/new_password; revoca todas las sesiones del usuario. |
| `GET /users` | Solo superusuario; paginado. |
| `POST /users` | Solo superusuario, Origin y CSRF; username/password/is_superuser (false por defecto). |
| `PATCH /users/{uuid}/active` | Solo superusuario, Origin y CSRF; active y reason de 3–500 caracteres. Protege al último superusuario activo. |
| `PUT /users/{uuid}/permissions` | Solo superusuario, Origin y CSRF; permissions y reason; reemplaza concesiones explícitas. No permite autoasignación. |
| `GET /permissions` | Sesión válida; catálogo de códigos. |
| `GET /audit` | Superusuario o `audit.read`; paginado; actor, acción, recurso, resultado, fecha y motivo. |

Para las mutaciones, enviar exactamente `Origin: https://localhost:8443` y
`X-CSRF-Token` con el desafío obtenido; conservar cookies entre solicitudes y usar
el nuevo desafío tras login. Las cookies Secure/HttpOnly/SameSite=Strict no tienen
Domain y utilizan Path=/. No hay tokens de sesión en JSON ni localStorage.
Todas las respuestas de identidad usan `Cache-Control: no-store`.

La paginación acepta `limit` de 1 a 100 y `offset` de 0 a 100000. Los nombres se
normalizan a minúsculas ASCII y admiten 3–64 letras, números, puntos, guiones y
subrayados. Las contraseñas nuevas admiten 16–128 caracteres no vacíos en una línea.

Los cambios de contraseña, estado y permisos revocan sesiones. No hay borrado de
cuentas. Crear otro superusuario requiere una petición explícita de un superusuario.
Un usuario ordinario solo recibe concesiones explícitas; el permiso `audit.read`
no permite administrar cuentas. Los demás códigos de documentos, dashboard,
reportes, procesamiento y fallidos se aplicarán a sus futuros recursos y ámbitos.

Errores: 400 operación inválida, 401 sesión/credencial inválida, 403 permiso o
Origin/CSRF rechazado, 409 conflicto, 422 entrada inválida sin reproducir valores,
429 límite temporal, 503 persistencia no disponible. Un error de almacenamiento no
confirma la operación como exitosa. La auditoría no admite UPDATE/DELETE/TRUNCATE
con el rol de ejecución, aunque el administrador propietario de PostgreSQL conserva
su autoridad. No escribir documentos ni secretos en los motivos administrativos.

## Pruebas PostgreSQL reproducibles

```powershell
$env:RUN_PG_INTEGRATION = '1'
$testParent = Join-Path (Get-Location).Path '.local/test-runs'
New-Item -ItemType Directory -Path $testParent -Force | Out-Null
$testRun = Join-Path $testParent ('identity-' + (Get-Date -Format 'yyyyMMdd-HHmmssfff'))
.\backend\.venv\Scripts\python.exe -m pytest -c backend/pyproject.toml backend/tests tests -q -W error --basetemp $testRun
Remove-Item Env:RUN_PG_INTEGRATION
```

Se crean bases nuevas `document_platform_test_<hex>` con cuentas sintéticas, nunca
se usa un PDF real. Sin la variable, las pruebas de integración se omiten de forma
explícita. No se borran bases automáticamente: el registro local identifica las
inicializadas y una limpieza futura requiere autorización de borrado.

El límite inicial es cinco fallos por nombre en 15 minutos; Argon2id tiene límite
de concurrencia. Inactividad 30 minutos y duración absoluta ocho horas. Las
variables `APP_AUTH_*` permiten ajustes validados. Medir coste y carga en el futuro
servidor; el bloqueo transaccional de identidad prioriza consistencia para esta
administración local. No sustituye límites de tráfico para una futura exposición remota.
