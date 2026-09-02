import requests


class RaspberryService:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def get_telemetry(self, timeout: float = 1.0) -> dict:
        """
        Obtiene la telemetría actual desde la Raspberry Pi.

        Lanza requests.RequestException si existe un problema
        de comunicación HTTP.
        """
        response = requests.get(
            f"{self.base_url}/api/telemetry",
            timeout=timeout
        )

        response.raise_for_status()

        return response.json()
    
    def trigger_capture(self, timeout: float = 45.0) -> dict:
        """
        Solicita a la Raspberry Pi el disparo de la cámara
        y devuelve la información de la captura realizada.

        Lanza requests.RequestException si existe un problema
        de comunicación HTTP.
        """
        response = requests.get(
            f"{self.base_url}/api/trigger_only",
            timeout=timeout
        )

        response.raise_for_status()

        return response.json()