# Flujo Git y publicación

`main` es la rama predeterminada y distribuye la versión estable. `dev` es la rama de trabajo. Los cambios se desarrollan y prueban en `dev` y se proponen a `main` mediante un Pull Request. Las ramas temporales se reservan para trabajo aislado y se retiran cuando su contenido queda integrado o archivado de forma verificable.

GitHub Actions ejecuta el bootstrap Docker, el recorrido de caja negra, el reinicio y la suite hermética en Linux AMD64. El control de integración es `Docker AMD64`. Para Windows y la instalación móvil, consulta los resultados por plataforma. [Estado](estado.md)

Para publicar, revisa el PR y los controles críticos, integra conservando la ascendencia y comprueba el clon convencional de `main`. Crea una etiqueta anotada sobre el SHA aprobado y publica las notas de versión. El despliegue empieza con el comando del README y la instalación móvil usa `/app/`. [Releases](https://github.com/SeBytev3/CIVIA/releases)

Sincroniza `dev` a partir de `main` con avance rápido o integración normal. Antes de retirar referencias, comprueba los PR abiertos, los worktrees y la ascendencia de cada punta. Las etiquetas publicadas y los commits históricos conservan sus referencias.
