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
    
    def download_file(
        self,
        remote_path: str,
        local_path: str,
        timeout: float = 15.0
    ) -> str:
        """
        Descarga un archivo desde la Raspberry Pi mediante
        el endpoint /api/proxy_download y lo guarda localmente.

        Retorna la ruta local del archivo descargado.

        Lanza requests.RequestException si ocurre un problema
        de comunicación HTTP.
        """
        with requests.get(
            f"{self.base_url}/api/proxy_download",
            params={"path": remote_path},
            stream=True,
            timeout=timeout
        ) as response:

            response.raise_for_status()

            with open(local_path, "wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        file.write(chunk)

        return local_path