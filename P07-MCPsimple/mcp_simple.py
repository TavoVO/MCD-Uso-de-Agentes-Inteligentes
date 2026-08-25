from __future__ import annotations

# Importamos httpx para llamar a la API real del clima.
import httpx

# Importamos FastAPI para montar el servidor MCP en /mcp.
from fastapi import FastAPI

# Importamos FastMCP para crear una tool MCP de forma sencilla.
from mcp.server.fastmcp import FastMCP

# URL de la API de geocoding de Open-Meteo.
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

# URL de la API de pronóstico actual de Open-Meteo.
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


# Creamos el servidor MCP.
mcp = FastMCP(
    "MCPClimaSimple",
    stateless_http=True,  # No guardamos estado entre llamadas.
    json_response=True,  # Regresamos JSON simple.
    streamable_http_path="/",  # Luego lo montamos en /mcp.
)


# Convierte un código meteorológico en una frase corta.
def describir_codigo_clima(codigo: int | None) -> str:
    # Si no viene un código válido, devolvemos una frase genérica.
    if codigo is None:
        return "condición meteorológica desconocida"

    # Mapa pequeño de códigos comunes de Open-Meteo.
    labels = {
        0: "cielo despejado",
        1: "principalmente despejado",
        2: "parcialmente nublado",
        3: "nublado",
        45: "niebla",
        48: "niebla con escarcha",
        51: "llovizna ligera",
        61: "lluvia ligera",
        63: "lluvia moderada",
        65: "lluvia intensa",
        71: "nieve ligera",
        73: "nieve moderada",
        80: "chubascos ligeros",
        81: "chubascos moderados",
        82: "chubascos intensos",
        95: "tormenta",
    }

    # Si el código existe, usamos su texto; si no, lo mostramos como número.
    return labels.get(codigo, f"código meteorológico {codigo}")


# Hace una petición HTTP y exige una respuesta JSON.
def pedir_json(url: str, params: dict[str, object]) -> dict:
    # Llamamos a la API real con un timeout corto y claro.
    response = httpx.get(url, params=params, timeout=20.0)
    # Si hay error HTTP, levantamos la excepción.
    response.raise_for_status()
    # Convertimos la respuesta a JSON.
    data = response.json()
    # Aseguramos que el resultado sea un objeto.
    if not isinstance(data, dict):
        raise RuntimeError("La API del clima devolvió un formato inesperado.")
    # Regresamos el JSON ya validado.
    return data


# Tool MCP única: consultar el clima de una ciudad.
@mcp.tool()
def consultar_clima(ciudad: str = "Monterrey") -> dict:
    # Limpiamos la ciudad para evitar espacios sobrantes.
    ciudad_limpia = ciudad.strip() or "Monterrey"

    # Buscamos la ciudad en el servicio de geocoding.
    try:
        geocoding = pedir_json(
            GEOCODING_URL,
            {
                "name": ciudad_limpia,
                "count": 1,
                "language": "es",
                "format": "json",
            },
        )
    except (httpx.HTTPError, ValueError) as exc:
        # Si falla la red o la API, devolvemos un error claro.
        return {
            "status": "error",
            "mensaje": "No pude consultar el geocoding del clima.",
            "detalle": str(exc),
        }

    # Leemos la lista de resultados.
    resultados = geocoding.get("results")
    # Si no hay resultados, devolvemos un error claro.
    if not isinstance(resultados, list) or not resultados:
        return {
            "status": "error",
            "mensaje": f"No encontré la ciudad '{ciudad_limpia}'.",
        }

    # Tomamos el primer resultado para mantener el ejemplo simple.
    lugar = resultados[0]
    # Si el resultado no es un objeto, algo salió raro.
    if not isinstance(lugar, dict):
        return {
            "status": "error",
            "mensaje": "El geocoding devolvió un formato inesperado.",
        }

    # Sacamos coordenadas.
    latitud = lugar.get("latitude")
    longitud = lugar.get("longitude")
    # Si faltan coordenadas, no podemos seguir.
    if latitud is None or longitud is None:
        return {
            "status": "error",
            "mensaje": "La ciudad se encontró, pero faltan coordenadas válidas.",
        }

    # Consultamos el clima actual usando esas coordenadas.
    try:
        pronostico = pedir_json(
            FORECAST_URL,
            {
                "latitude": latitud,
                "longitude": longitud,
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code",
                "timezone": "auto",
            },
        )
    except (httpx.HTTPError, ValueError) as exc:
        # Si falla el pronóstico, también devolvemos un error simple.
        return {
            "status": "error",
            "mensaje": "No pude consultar el pronóstico del clima.",
            "detalle": str(exc),
        }

    # Leemos el bloque current.
    current = pronostico.get("current")
    # Si no viene current, devolvemos un error.
    if not isinstance(current, dict):
        return {
            "status": "error",
            "mensaje": "El pronóstico devolvió un formato inesperado.",
        }

    # Leemos el código del clima.
    codigo_clima = current.get("weather_code")
    # Lo traducimos a texto simple.
    texto_clima = describir_codigo_clima(int(codigo_clima) if codigo_clima is not None else None)

    # Regresamos un JSON fácil de leer por el modelo.
    return {
        "status": "ok",
        "ciudad": ciudad_limpia,
        "lugar": {
            "nombre": lugar.get("name"),
            "region": lugar.get("admin1"),
            "pais": lugar.get("country"),
        },
        "actual": {
            "hora": current.get("time"),
            "temperatura": current.get("temperature_2m"),
            "sensacion_termica": current.get("apparent_temperature"),
            "humedad": current.get("relative_humidity_2m"),
            "viento": current.get("wind_speed_10m"),
            "codigo": codigo_clima,
            "descripcion": texto_clima,
        },
        "resumen": (
            f"En {lugar.get('name')}, {texto_clima}. "
            f"Temperatura {current.get('temperature_2m')}°C."
        ),
    }


# Creamos la app web mínima y montamos el MCP.
app = FastAPI()
app.mount("/mcp", mcp.streamable_http_app())


# Si ejecutas este archivo directo, levanta el servidor.
if __name__ == "__main__":
    # Importamos uvicorn solo al final para mantener el archivo simple.
    import uvicorn

    # El servidor queda en http://127.0.0.1:8001/mcp.
    uvicorn.run("mcp_simple:app", host="127.0.0.1", port=8001, reload=False)
