
# Proyecto de Examen: Evolución y Mejoras

Este repositorio documenta el desarrollo progresivo de una aplicación para clasificación y análisis de portadas de libros, utilizando inteligencia artificial y Streamlit. El proceso inicia en `1_0examen.py` y culmina en `1_6examen.py`, mostrando cómo se fueron incorporando mejoras técnicas y funcionales.


Cada archivo representa una etapa de mejora, donde se agregan nuevas funciones, se optimiza el rendimiento y se refina la experiencia de usuario. El archivo final recomendado es `1_7examen.py`, que integra todas las mejoras previas y nuevas funcionalidades avanzadas.


## ¿Cómo instalar y ejecutar el proyecto?

### Opción rápida (Linux/Mac):
Puedes usar el script `install.sh` para automatizar la instalación:

1. Abre una terminal en la carpeta del proyecto.
2. Ejecuta:
  ```bash
  bash install.sh
  ```
  El script verifica Python, permite crear un entorno virtual y instala todas las dependencias necesarias.
3. Para correr la aplicación:
  ```bash
  streamlit run 1_6examen.py
  ```

### Opción manual (Windows, conda o solo Python):
Si tienes solo Python o conda, puedes instalar manualmente:

1. (Opcional) Crea un entorno virtual:
  - Con Python:
    ```bash
    python -m venv venv
    venv\Scripts\activate
    ```
  - Con conda:
    ```bash
    conda create -n bookclassifier python=3.8
    conda activate bookclassifier
    ```
2. Instala dependencias:
  ```bash
  pip install -r requirements.txt
  ```
3. Ejecuta la aplicación:
  ```bash
  streamlit run 1_6examen.py
  ```

> El script `install.sh` es útil para automatizar la instalación en sistemas Unix, pero en Windows o con conda se recomienda seguir los pasos manuales.

---


## Proceso de mejora y diferencias entre versiones

- **1_0examen.py**: Estructura básica, extracción de portada y análisis inicial con Gemini. Persistencia simple y barra de progreso.
- **1_1examen.py**: Corrección de errores, mejor manejo de logs, validación de datos y primeras métricas de libros/temas. Se mejora la legibilidad y se agregan descargas de Excel y JSON.
- **1_2examen.py**: Añade funciones para backup incremental, validación robusta de la base de datos, búsqueda inteligente de portadas, y limpieza avanzada de JSON. Se incorpora análisis con OpenAI y Gemini, y debugging detallado.
- **1_3examen.py**: Interfaz Streamlit más amigable, procesamiento optimizado de archivos grandes, tabla de biblioteca, búsqueda y visualización de resultados. Se mejora la experiencia de usuario y la visualización de datos.
- **1_4examen.py**: Validaciones avanzadas, extracción de metadatos del PDF, renderizado a mayor resolución, escaneo de más páginas, prompt optimizado para documentos históricos, y manejo de archivos grandes. Se agregan mejoras en la interacción y descargas.
- **1_5examen.py**: Refactorización para modularidad, eficiencia y robustez. Mejoras en el análisis con GPT-4o, búsqueda ultra-mejorada de portadas, y nuevas métricas. Se optimiza la descarga y visualización de la biblioteca.
- **1_6examen.py**: Versión consolidada, integra todas las mejoras previas, interfaz optimizada, código limpio, funciones avanzadas de análisis, validaciones, modularidad y experiencia de usuario.
- **1_7examen.py**: Versión más avanzada, añade nuevas funciones como eliminación de libros, mejoras en el análisis con IA, optimización de procesos, y una interfaz aún más robusta. Es la versión recomendada para uso actual.

Cada versión fue revisada y mejorada con base en retroalimentación, pruebas y necesidades detectadas durante el desarrollo.

## Notas adicionales

- Los archivos de respaldo se encuentran en la carpeta `backups/`.
- El archivo `biblioteca_temas.json` contiene información relevante para el funcionamiento del sistema.
- Puedes revisar cada versión para entender el proceso de mejora y evolución del código.

---

Si tienes dudas o sugerencias, consulta el historial de versiones o contacta al autor.
