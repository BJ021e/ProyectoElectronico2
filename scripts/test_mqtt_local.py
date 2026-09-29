import getpass
import threading

import paho.mqtt.client as mqtt


HOST = "127.0.0.1"
PORT = 1883
TOPIC = "pe2/diagnostico/local"

connected = threading.Event()
subscribed = threading.Event()
received = threading.Event()

errors = []


def on_connect(
    client,
    userdata,
    flags,
    reason_code,
    properties,
):
    print("Resultado de conexión:", reason_code)

    if reason_code == 0:
        connected.set()
        client.subscribe(TOPIC, qos=1)
    else:
        errors.append(str(reason_code))
        connected.set()


def on_subscribe(
    client,
    userdata,
    mid,
    reason_codes,
    properties,
):
    print("Suscripción confirmada:", reason_codes)
    subscribed.set()


def on_message(client, userdata, message):
    print("Mensaje recibido:", message.payload.decode())
    received.set()


def main():
    password = getpass.getpass(
        "Contraseña MQTT de pe2_diag: "
    )

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        protocol=mqtt.MQTTv5,
    )

    client.username_pw_set(
        "pe2_diag",
        password,
    )

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message

    try:
        print("Conectando al broker local...")

        client.connect(HOST, PORT, keepalive=30)
        client.loop_start()

        if not connected.wait(timeout=8):
            raise RuntimeError(
                "Tiempo de espera agotado durante la conexión."
            )

        if errors:
            raise RuntimeError(
                "Autenticación o conexión rechazada: "
                + errors[0]
            )

        if not subscribed.wait(timeout=8):
            raise RuntimeError(
                "No se confirmó la suscripción MQTT."
            )

        message = "PE2_MQTT_LOCAL_OK"

        publication = client.publish(
            TOPIC,
            message,
            qos=1,
        )

        publication.wait_for_publish(timeout=5)

        if not received.wait(timeout=8):
            raise RuntimeError(
                "El mensaje no regresó al cliente."
            )

        print("DIAGNOSTICO MQTT LOCAL: CORRECTO")

    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
