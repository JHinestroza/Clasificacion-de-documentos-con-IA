# Preguntas y decisiones pendientes

Actualizado: 2026-11-12. Cerrar cada decisión antes de implementar la feature afectada.

## Decisiones cerradas

- FastAPI, PostgreSQL, RabbitMQ, Celery y Docker Compose aprobados.
- Nuevas ramas `feature/nombre-feature` hasta nueva indicación.
- `success`: procesamiento de metadatos terminado, sin aprobación humana habitual.
- Los PDF se mueven físicamente a su carpeta de resultado.
- Eliminar un fallido: retirarlo del reencolamiento conservando PDF e historial,
  registrando quién, cuándo y por qué. No es una autorización de borrado físico.
- Docker no está instalado. El responsable difiere esa parte a una feature final.
- El responsable confirma que las ubicaciones actuales están cifradas; no se ha
  comprobado técnicamente la cobertura del host ni la de un futuro servidor.
- Los secretos operativos se guardan en `.env`, excluido del repositorio.
- Las cuentas serán locales y administradas por el superusuario; no se integrará
  inicio de sesión institucional en F003.

## Antes de los usuarios y de utilizar datos reales

- Custodia, recuperación y renovación de claves y certificados institucionales.
  F002 solo genera una CA de desarrollo y no instala confianza en Windows.
- El alcance por fondo/reporte debe concretarse antes de exponer esos recursos.
  F003 ya implementa cuentas locales, sesiones revocables, permisos y auditoría.
  Recuperación de cuentas y políticas de retención necesitan diseño antes de ampliarlas.
- Acceso solo local o desde otros equipos; API keys para clientes externos si se
  habilita también una API de carga.

## Antes de ingestión, extracción y metadatos

- Dos o tres nombres ficticios de PDF y ubicación exacta del código en el nombre.
- Reglas de normalización del código y deduplicación por contenido SHA-256.
- Tamaños y páginas habituales/máximos; picos de carga y forma de completar la copia
  de archivos en la carpeta de entrada.
- Alcance de iniciar, pausar y detener: por lote, fondo o ejecución completa.
- Política de reintentos, errores transitorios, documentos sin texto y fallos
  permanentes. Diferenciar cancelar un trabajo de detener el servicio.
- Primeros campos de metadatos, ejemplos sintéticos y esquema de salida esperado.
- Motor inicial: reglas, simulador o IA real; proveedor y autorización de tratamiento
  de datos antes de usar un servicio externo.

## Antes del primer release

- Instalar Docker y definir el despliegue Linux en la feature final; comprobar
  recursos, ubicación de volúmenes y cifrado del almacenamiento y respaldos.
- Revalidar PostgreSQL, RabbitMQ, permisos, reinicios y workers en el despliegue
  Linux; las pruebas locales Windows no sustituyen esa verificación.
- Versión, criterios de aceptación, CI y estrategia de integración de `develop`
  hacia `main`. Publicar el tag, release o imágenes requiere autorización remota.

## Resuelto el 2026-11-12

El alcance detallado de F003 ya fue aprobado; no volver a consultarlo. RabbitMQ está
instalado y se autorizó verificarlo por TLS antes de Docker. PostgreSQL 18.7 está
instalado e integrado por TLS en F003; allí persisten usuarios, sesiones y auditoría.
Docker, los workers Linux y el despliegue completo siguen diferidos a la feature final.
