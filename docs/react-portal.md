# Portal React local

La interfaz de F004A utiliza los usuarios y permisos F003: login/logout, cuentas,
autorizaciones, auditoría y cambio de contraseña propia. Todavía no ingresa PDF ni
publica trabajos. Los archivos permanecen bajo la cuenta Windows Usuario.

## Compilar y ejecutar

Desde la raíz, con Node 24.19.x y el entorno Python existente:

```powershell
$env:npm_config_cache = Join-Path (Get-Location).Path '.local/npm-cache'
npm.cmd ci --prefix frontend --ignore-scripts --no-fund
npm.cmd --prefix frontend run build
.\backend\.venv\Scripts\python.exe -m document_platform
```

La aplicación se sirve en `https://localhost:8443/`. El primer build debe preceder al
arranque; si la API ya estaba iniciada antes de compilar por primera vez, reiniciarla.
No hace falta ejecutar Node para servir la interfaz. Para cambios de frontend,
`npm.cmd --prefix frontend run dev` recompila en watch; la misma API sirve HTTPS.
No usar vite dev/preview con HTTP ni desactivar la validación de TLS.

`APP_WEB_DIST_DIR` admite otro directorio compilado, con valor predeterminado
`frontend/dist`. No colocar documentos, claves ni `.env` en ese directorio. Vite no
carga archivos env ni publica APP_*; las conexiones son relativas al mismo origen.

## Confianza HTTPS del navegador: pendiente

La CA de desarrollo todavía no es confiable para el navegador. El intento de
comprobación fue rechazado con `ERR_CERT_AUTHORITY_INVALID`; no se saltó el aviso.
La API y recursos compilados se verificaron desde un cliente que confía explícitamente
en `.local/certs/ca.crt`, conservando hostname y validación de cadena.

Antes de utilizar el portal en el navegador, el responsable debe elegir entre
confiar explícitamente en esa CA de desarrollo en el entorno local o proporcionar
una cadena/certificado institucional válido. No se modifica automáticamente el
almacén Windows. Confiar una raíz permite validar certificados firmados por ella y
requiere custodiar su clave privada. El certificado público propuesto es:

- Archivo: `.local/certs/ca.crt`; no es la clave privada.
- SHA-256: `277A36B2AF21B9FCD33A24EF5AE2836D80719C8C8C6DFA32783596DDC6A91D13`.
- Identificador del almacén SHA-1: `883400F07F8410419067E8DE6AF24ACC1C2D3991`.
- Vigencia actual: hasta 2027-11-10. Revalidar la huella si se renueva la CA.

No omitir los avisos ni instalar una raíz diferente sin comprobar su identidad.
La prueba visual del portal sigue pendiente; las pruebas de componentes no la sustituyen.

## Acceso y acciones

Usuario inicial `admin`; contraseña actual inicialmente indicada por
`APP_BOOTSTRAP_ADMIN_PASSWORD` en el `.env` raíz. Si ya se cambió por la API, usar
la contraseña nueva: la variable de inicialización no es un restablecimiento.
No copiar el secreto a comandos, código o capturas de pantalla.

- Inicio consulta la disponibilidad real de base de datos y broker.
- Usuarios y permisos solo aparece al superusuario. Se puede crear una cuenta,
  activarla/desactivarla y asignar permisos con motivo. La cuenta actual y los
  superusuarios no tienen editor de concesiones ordinarias en esta pantalla.
- Auditoría requiere superusuario o `audit.read`. Los actores se identifican por
  usuario propio o UUID; no hay un endpoint adicional que exponga otras cuentas.
- Mi cuenta cambia la contraseña propia y obliga a volver a iniciar sesión.
- Cerrar sesión confirma la revocación del servidor; un error de conexión se
  muestra sin declarar falsamente que la sesión se cerró.

Los listados se consultan por páginas de 20 registros. Los motivos se muestran como
texto y se conservan en PostgreSQL. Las cuentas desactivadas y la auditoría no se borran.
Un permiso de procesamiento o documentos queda reservado hasta incorporar su función
y los filtros por fondo; no autoriza por sí solo acceso a documentos inexistentes.

## Verificación

```powershell
npm.cmd --prefix frontend run test
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run format:check
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend audit --audit-level=moderate
```

Vitest/jsdom usa identidades sintéticas y respuestas controladas, sin contraseñas
reales ni documentos. Las pruebas backend completas con PostgreSQL real se explican
en [desarrollo](development.md). [La ficha F004A](features/F004A-react-portal.md)
distingue resultados automáticos, HTTPS real y comprobación visual pendiente.
