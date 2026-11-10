# Requisitos y restricciones

Actualizado: 2026-11-10. Fuente: instrucciones del responsable del proyecto.
Este documento registra requisitos; no acredita funcionalidades implementadas.

## Acordado

| ID | Requisito |
| --- | --- |
| R01 | Trabajar por features con alcance, documentación, verificación y pendientes propios. |
| R02 | Mantener estado persistente e historial de documentos y trabajos para identificar avances y fallos. |
| R03 | Desarrollar inicialmente en Windows y ejecutar en Linux mediante Docker. El objetivo operativo es descargar imágenes y arrancar el sistema, sin instalar herramientas de desarrollo en el equipo de ejecución. La distribución en contenedores y el servidor final siguen pendientes. |
| R04 | Disponer al menos de carpetas `input`, `failed` y `success` con los archivos correspondientes. La política de copia o movimiento sigue pendiente. |
| R05 | Ingresar documentos desde una carpeta mediante una interfaz amigable con controles de inicio y parada. Definir pausa y cancelación por separado. |
| R06 | Omitir una nueva ingestión si su código ya está registrado y dejar constancia del motivo. Falta definir extracción y normalización del código. |
| R07 | Configurar fondo y metadatos según los archivos o lotes, mediante configuración y prompts. La salida debe respetar un esquema validado. |
| R08 | Administrar usuarios mediante un superusuario de la aplicación y aplicar mínimo privilegio. |
| R09 | Distinguir permisos para consultar documentos, ver dashboard y reportes, iniciar, pausar, detener, reencolar y eliminar. El backend debe verificar los permisos. |
| R10 | Registrar fallidos con motivo y permitir su evaluación en una cola separada, con opciones autorizadas de reprocesamiento o eliminación. |
| R11 | Cifrar todas las comunicaciones de la aplicación, incluidos documentos, credenciales y control, verificando la identidad del servidor. Proteger también los datos en reposo y sus copias; el mecanismo debe definirse y comprobarse. |
| R12 | Crear ramas por feature e integrar localmente en `develop` cuando estén verificadas. Preparar releases con versión y tag según criterios acordados. |
| R13 | Incorporar un dashboard avanzado más adelante; la consulta operativa de estados e historial debe acompañar al procesamiento. |

El superusuario de la aplicación no implica permisos de administrador del sistema,
de Docker o de PostgreSQL. El acceso a documentos y reportes deberá considerar el
alcance autorizado, por ejemplo por fondo, además del permiso de ejecutar una acción.

## Restricciones persistentes

- Consultar cambios relevantes de arquitectura, infraestructura, autenticación,
  seguridad, base de datos o alcance antes de implementarlos.
- No publicar código, imágenes, releases ni realizar operaciones Git remotas sin
  autorización expresa. Los merges locales de features verificadas están autorizados.
- No ejecutar borrados destructivos de datos o volúmenes sin autorización.
- No enviar documentos reales a proveedores de IA u otros servicios externos sin
  autorización. Utilizar documentos sintéticos durante las pruebas.
- No guardar secretos ni contenido documental en logs; limitar sus datos y proteger
  el acceso al historial y a la auditoría.
- No declarar una función terminada sin implementación, verificación y evidencia.
- No habilitar comunicaciones en texto plano ni desactivar la verificación de
  certificados. HTTPS y conexiones TLS verificadas serán obligatorias en los
  componentes seleccionados, también dentro de la red de Docker.

## Recomendaciones aún no aprobadas

- FastAPI y PostgreSQL, aplicación modular y procesos separados de API y workers.
- RabbitMQ + Celery como alternativa inicial de mensajería y ejecución.
- Docker Compose para administrar varios contenedores Linux como un conjunto.
- Original administrado e inmutable, con carpetas operativas cuyo comportamiento
  físico se acordará antes de implementar la ingestión.
- `success` como éxito técnico, separado de revisión y aprobación humana.
- Reintentos automáticos limitados para errores transitorios y evaluación manual
  de fallidos definitivos; la base de datos conserva el historial, aunque exista
  una cola separada de fallidos.
- Una reejecución autorizada crea un intento para el mismo documento, no una nueva
  ingestión que entre en conflicto con el control de código repetido.
- Perfiles, esquema de metadatos y prompts versionados por ejecución. Empezar con
  reglas o simulador hasta aprobar un proveedor y su tratamiento de datos.

## Secuencia propuesta de features

| Feature | Resultado demostrable propuesto |
| --- | --- |
| F001 — Acuerdos de trabajo | Requisitos, decisiones pendientes y ficha verificable de esta entrega documental. |
| F002 — Entorno seguro | Arranque reproducible, configuración, secretos y TLS verificado; pruebas de rechazo de conexiones inseguras. |
| F003 — Usuarios y permisos | Acceso y administración de usuarios; pruebas negativas de autorización y auditoría. |
| F004 — Ingestión y operación | Carpeta de ingreso, interfaz mínima, códigos, hashes, estados y control de inicio/pausa/parada. |
| F005 — Extracción recuperable | Workers, texto por página, fallos, cola separada, reencolado e idempotencia comprobada. |
| F006 — Metadatos configurables | Perfil de fondo, esquema y prompt versionados; propuestas validadas con evidencia. |
| F007 — Revisión y resultados | Flujo humano acordado y acciones autorizadas sobre resultados y fallidos. |

La secuencia no autoriza su implementación. El dashboard y los reportes avanzados
se planificarán después. Las funciones de seguridad, historial y recuperación
acompañarán a las features que las necesitan; no serán un endurecimiento posterior.
