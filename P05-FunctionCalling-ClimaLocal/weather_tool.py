"""Herramienta real que consulta Open-Meteo.

La idea educativa aquí es simple:
1. El modelo decide llamar get_weather.
2. Este archivo traduce la ciudad a coordenadas con geocoding.
3. Luego consulta el clima actual.
4. Regresa un JSON limpio para que el modelo lo redacte en español.
"""

from __future__ import annotations

from typing import Any

import httpx


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


# Mapa pequeño de códigos meteorológicos WMO.
# No hace falta cubrirlos todos para aprender el flujo; solo los más comunes.
WEATHER_CODE_LABELS = {
    0: "cielo despejado",
    1: "principalmente despejado",
    2: "parcialmente nublado",
    3: "nublado",
    45: "niebla",
    48: "niebla con escarcha",
    51: "llovizna ligera",
    53: "llovizna moderada",
    55: "llovizna intensa",
    61: "lluvia ligera",
    63: "lluvia moderada",
    65: "lluvia intensa",
    66: "lluvia helada ligera",
    67: "lluvia helada intensa",
    71: "nieve ligera",
    73: "nieve moderada",
    75: "nieve intensa",
    77: "granizo de nieve",
    80: "chubascos ligeros",
    81: "chubascos moderados",
    82: "chubascos intensos",
    85: "chubascos de nieve ligeros",
    86: "chubascos de nieve intensos",
    95: "tormenta",
    96: "tormenta con granizo ligero",
    99: "tormenta con granizo intenso",
}


def _clean_text(value: Any) -> str:
    """
    Convierte un valor cualquiera en texto limpio.

    Esto evita errores cuando el modelo manda datos inesperados.
    """

    if value is None:
        return ""
    return str(value).strip()


def _request_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    """Hace una petición HTTP y exige una respuesta JSON válida."""

    try:
        response = httpx.get(url, params=params, timeout=20.0)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"No se pudo consultar {url}: {exc}") from exc
    except ValueError as exc:
        raise RuntimeError(f"La API respondió con un formato no JSON en {url}.") from exc

    if not isinstance(data, dict):
        raise RuntimeError("La API devolvió una estructura inesperada.")

    return data


def _format_location(result: dict[str, Any]) -> str:
    """Construye un nombre humano para la ciudad encontrada."""

    parts = [
        result.get("name"),
        result.get("admin1"),
        result.get("country"),
    ]
    cleaned_parts = [str(part).strip() for part in parts if part]
    return ", ".join(cleaned_parts)


def _describe_weather_code(code: Any) -> str:
    """Convierte el código WMO en una frase corta en español."""

    try:
        numeric_code = int(code)
    except (TypeError, ValueError):
        return "condición meteorológica desconocida"

    return WEATHER_CODE_LABELS.get(numeric_code, f"código meteorológico {numeric_code}")


def get_weather(city: str) -> dict[str, Any]:
    """Consulta clima actual para una ciudad.

    Este es el corazón de la herramienta:
    - primero busca la ciudad,
    - luego pide el clima actual,
    - y finalmente devuelve un JSON pequeño y claro.
    """

    cleaned_city = _clean_text(city)
    if not cleaned_city:
        return {
            "status": "error",
            "error_type": "invalid_city",
            "message": "La ciudad está vacía o no se pudo leer correctamente.",
        }

    geocoding = _request_json(
        GEOCODING_URL,
        {
            "name": cleaned_city,
            "count": 5,
            "language": "es",
            "format": "json",
        },
    )

    results = geocoding.get("results")
    if not isinstance(results, list) or not results:
        return {
            "status": "error",
            "error_type": "city_not_found",
            "message": f"No encontré la ciudad '{cleaned_city}'.",
        }

    # Para este proyecto mínimo elegimos el primer resultado.
    # En clase esto ayuda a mantener el flujo fácil de seguir.
    location = results[0]
    if not isinstance(location, dict):
        return {
            "status": "error",
            "error_type": "unexpected_geocoding_format",
            "message": "El geocoding devolvió un formato inesperado.",
        }

    latitude = location.get("latitude")
    longitude = location.get("longitude")
    if latitude is None or longitude is None:
        return {
            "status": "error",
            "error_type": "missing_coordinates",
            "message": "La ciudad se encontró, pero faltan coordenadas válidas.",
        }

    forecast = _request_json(
        FORECAST_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": (
                "temperature_2m,apparent_temperature,relative_humidity_2m,"
                "wind_speed_10m,weather_code"
            ),
            "timezone": "auto",
        },
    )

    current = forecast.get("current")
    current_units = forecast.get("current_units", {})
    if not isinstance(current, dict):
        return {
            "status": "error",
            "error_type": "unexpected_forecast_format",
            "message": "El clima actual devolvió un formato inesperado.",
        }
    if not isinstance(current_units, dict):
        current_units = {}

    weather_code = current.get("weather_code")
    weather_text = _describe_weather_code(weather_code)

    return {
        "status": "ok",
        "source": "Open-Meteo",
        "location": {
            "name": location.get("name"),
            "admin1": location.get("admin1"),
            "country": location.get("country"),
            "timezone": forecast.get("timezone") or location.get("timezone"),
            "latitude": forecast.get("latitude", latitude),
            "longitude": forecast.get("longitude", longitude),
        },
        "current": {
            "time": current.get("time"),
            "temperature_2m": current.get("temperature_2m"),
            "apparent_temperature": current.get("apparent_temperature"),
            "relative_humidity_2m": current.get("relative_humidity_2m"),
            "wind_speed_10m": current.get("wind_speed_10m"),
            "weather_code": weather_code,
            "weather_text": weather_text,
            "units": {
                "temperature_2m": current_units.get("temperature_2m"),
                "apparent_temperature": current_units.get("apparent_temperature"),
                "relative_humidity_2m": current_units.get("relative_humidity_2m"),
                "wind_speed_10m": current_units.get("wind_speed_10m"),
            },
        },
        "summary": (
            f"En {_format_location(location)} hay {weather_text}. "
            f"Temperatura {current.get('temperature_2m')}°C."
        ),
    }
