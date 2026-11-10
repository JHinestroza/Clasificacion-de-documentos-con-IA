# Preguntas y decisiones pendientes

Actualizado: 2026-11-10. Cerrar cada decisión antes de implementar la feature afectada.

## Próxima ronda

1. ¿Se aprueba RabbitMQ + Celery como alternativa inicial? FastAPI, PostgreSQL y
   Docker Compose también siguen siendo candidatos hasta cerrar la base técnica.
2. ¿`success` significa procesamiento terminado y después revisión humana, o qué
   aprobación ocurre antes de la revisión mencionada por el responsable?
3. ¿`success` y `failed` deben contener los PDF movidos o copias? ¿Dónde se conserva
   el original y qué política de retención se requiere?
4. ¿Eliminar un fallido significa retirarlo de la cola, borrar resultados o destruir
   también el PDF? No habilitar destrucción física por defecto.

## Antes del entorno seguro y los usuarios

- Disponibilidad de Docker Desktop/WSL2, recursos del equipo, ubicación de carpetas,
  volúmenes y respaldos; inventario del servidor final cuando se conozca.
- Mecanismo de cifrado en reposo, custodia y recuperación de claves. TLS no cifra
  automáticamente los archivos ni los volúmenes.
- Nombres del servicio, autoridad de certificados local/institucional, distribución
  de confianza y renovación; no desactivar la verificación para desarrollo.
- Autenticación del portal, creación segura del primer superusuario y matriz de
  permisos por acción y por fondo/reporte. Sin contraseñas predeterminadas.
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

- Versión, criterios de aceptación, CI y estrategia de integración de `develop`
  hacia `main`. Publicar el tag, release o imágenes requiere autorización remota.
