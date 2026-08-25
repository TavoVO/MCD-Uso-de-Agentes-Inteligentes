# Crear una prueba del API de chat GPT con soporte de conversación
import os
from dotenv import load_dotenv
from openai import OpenAI

# Carga las variables de entorno desde el archivo .env
load_dotenv()

# Obtiene la clave de OpenAI desde la variable de entorno
api_key = os.getenv("OPENAI_API_KEY")

# Si no hay clave, detiene la ejecución con un error claro
if api_key is None:
    raise ValueError("No se encontró OPENAI_API_KEY en el archivo .env")

# Inicializa el cliente de OpenAI con la API Key
client = OpenAI(api_key=api_key)


def crear_respuesta(messages):
    """Envía el historial de mensajes a OpenAI y devuelve el texto de la respuesta."""
    response = client.responses.create(
        model="gpt-4o-mini",
        input=messages,
        temperature=0.7,
        max_output_tokens=100,
        top_p=1.0,
    )

    output_text = response.output_text
    return output_text, response


def main():
    """Función principal que ejecuta el bucle de conversación interactiva."""
    print("Chat interactivo con OpenAI GPT. Escribe 'salir' o 'exit' para terminar.")

    # Historial inicial de la conversación. El rol system define el comportamiento del asistente.
    messages = [
        {"role": "system", "content": "Eres un asistente útil y conversacional."}
    ]

    while True:
        try:
            # Lee la entrada del usuario desde la consola
            user_input = input("Usuario: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSaliendo. ¡Hasta luego!")
            break

        # Si el usuario no escribió nada, vuelve a pedir entrada
        if not user_input:
            continue

        # Comandos para finalizar la conversación
        if user_input.lower() in ("salir", "exit", "quit"):
            print("Saliendo. ¡Hasta luego!")
            break

        # Guarda el mensaje del usuario en el historial
        messages.append({"role": "user", "content": user_input})

        try:
            # Solicita la respuesta al modelo usando todo el historial
            assistant_text, response = crear_respuesta(messages)
        except Exception as error:
            print(f"Error al solicitar la respuesta: {error}")
            continue

        # Agrega la respuesta del asistente al historial para mantener el contexto
        messages.append({"role": "assistant", "content": assistant_text})

        # Imprime la respuesta del asistente
        print("\nAsistente:", assistant_text)

        # Muestra información del modelo y uso de tokens si está disponible
        usage_tokens = getattr(response.usage, "total_tokens", None)
        response_ms = getattr(response, "response_ms", None)
        print(
            f"[Modelo: {response.model}, Tokens totales: {usage_tokens}, Tiempo: {response_ms} ms]"
        )
        print()


if __name__ == "__main__":
    main()
