# Reporte de Pentesting: Escaneo de Puertos en Localhost

## Resumen Ejecutivo

El presente informe detalla los resultados de un ejercicio de pentesting centrado en la identificación de puertos abiertos en la máquina local (localhost). El objetivo principal de esta evaluación fue determinar si existían puertos TCP accesibles y obtener información básica sobre los servicios asociados. Se logró identificar un puerto abierto, cumpliendo con el objetivo propuesto.

## Objetivo Evaluado

El objetivo principal de esta fase de reconocimiento fue:
*   Identificar al menos un puerto TCP abierto en la dirección IP `localhost`.

## Hallazgos Principales

Durante el proceso de escaneo, se identificó exitosamente un puerto abierto en la máquina objetivo `localhost`.

*   **Puerto Abierto:** `8000/tcp`
    *   **Estado:** `open`
    *   **Servicio:** `http-alt?`
    *   **Versión:** No especificada, indicado con `?` por Nmap como una posible alternativa HTTP.

## Comandos Ejecutados

Para la consecución del objetivo, se utilizó la herramienta `nmap` con la siguiente sintaxis:

```bash
nmap -F -sV localhost
```

*   `-F`: Escanea los 100 puertos más comunes rápidamente.
*   `-sV`: Intenta determinar el servicio y la versión del software en los puertos abiertos.

## Conclusiones Finales

El ejercicio de pentesting ha concluido satisfactoriamente, ya que se logró identificar el puerto `8000/tcp` como abierto en la máquina `localhost`, asociado a un posible servicio `http-alt`. Este hallazgo cumple con el objetivo establecido para esta fase de reconocimiento inicial.