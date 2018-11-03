import asyncio
import logging
import time

from hbmqtt.client import MQTTClient
from hbmqtt.mqtt.constants import QOS_0

from pymata_aio.pymata_core import PymataCore
from pymata_aio.constants import Constants as FirmataConstants

# MQTT server address
serverAddress='mqtt://192.168.0.147:1883'

# Pin Constants
FAN_PIN = 4
FIRE_PIN = 5
HEATER_LOW_PIN = 6
HEATER_HIGH_PIN = 7
LIGHT_PIN = 11

# Mode constants
MODE_OFF = 'OFF'
MODE_TO_LOW = 'TO_LOW'
MODE_TO_HIGH = 'TO_HIGH'
MODE_TO_OFF = 'TO_OFF'
MODE_ON_LOW = 'LOW'
MODE_ON_HIGH = 'HIGH'

# State
currentBrightness = 0
requestedBrightness = 0
lastBrightness = 255
currentMode = MODE_OFF
requestedMode = MODE_OFF
switchModeAt = time.time()

logger = logging.getLogger(__name__)

mqttClient = MQTTClient(config={
    'keep_alive': 5,
    'ping_delay': 1,
    'auto_reconnect': True
})

board = PymataCore()


async def init_firmata():
    """ Initialize Firmata connection """

    await board.start_aio()

    await board.set_pin_mode(FAN_PIN, FirmataConstants.OUTPUT)
    await board.set_pin_mode(FIRE_PIN, FirmataConstants.OUTPUT)
    await board.set_pin_mode(HEATER_LOW_PIN, FirmataConstants.OUTPUT)
    await board.set_pin_mode(HEATER_HIGH_PIN, FirmataConstants.OUTPUT)
    await board.set_pin_mode(LIGHT_PIN, FirmataConstants.PWM)

    await board.digital_write(FAN_PIN, 0)
    await board.digital_write(FIRE_PIN, 0)
    await board.digital_write(HEATER_LOW_PIN, 0)
    await board.digital_write(HEATER_HIGH_PIN, 0)
    await board.analog_write(LIGHT_PIN, 0)


async def update_light_by_brightness(brightness):
    """ Apply brightness to physical light """

    await board.digital_write(FIRE_PIN, (1 if brightness > 0 else 0))
    await board.analog_write(LIGHT_PIN, brightness)


async def update_heater_by_mode(mode):
    """ Apply heater mode to physical heater """

    # Off mode, no fan, no heating
    if mode == MODE_OFF:
        await board.digital_write(FAN_PIN, 0)
        await board.digital_write(HEATER_LOW_PIN, 0)
        await board.digital_write(HEATER_HIGH_PIN, 0)

    # Transition mode, fan on, heater off
    if mode == MODE_TO_LOW or mode == MODE_TO_HIGH or mode == MODE_TO_OFF:
        await board.digital_write(FAN_PIN, 1)
        await board.digital_write(HEATER_LOW_PIN, 0)
        await board.digital_write(HEATER_HIGH_PIN, 0)

    # Low mode, fan on, heater to low
    if mode == MODE_ON_LOW:
        await board.digital_write(FAN_PIN, 1)
        await board.digital_write(HEATER_LOW_PIN, 0)
        await board.digital_write(HEATER_HIGH_PIN, 1)

    # High mode, fan on, heater to high
    if mode == MODE_ON_HIGH:
        await board.digital_write(FAN_PIN, 1)
        await board.digital_write(HEATER_LOW_PIN, 1)
        await board.digital_write(HEATER_HIGH_PIN, 1)


async def init_connection():
    """ Initialize MQTT connection and subscribe to subjects """

    logger.info('Connecting to broker')
    await mqttClient.connect(uri=serverAddress, cleansession=True)

    logger.info('Subscribing to subjects')
    await mqttClient.subscribe([
        ('/fireplace/heater/state_cmd', QOS_0),
        ('/fireplace/light/state_cmd', QOS_0),
        ('/fireplace/light/brightness_cmd', QOS_0)
    ])


async def publish_heater_state():
    """ Send information about the current heater state """

    logger.info('Publishing state %s and for heater' % (currentMode))
    await mqttClient.publish('/fireplace/heater/state', currentMode.encode('ascii'), QOS_0)


async def publish_light_state_and_brightness():
    """ Send information about the current light state and brightness """

    state = 'ON' if (currentBrightness > 0) else 'OFF'

    logger.info('Publishing state %s and brightness %d for light' % (state, currentBrightness))
    await mqttClient.publish('/fireplace/light/state', state.encode('utf-8'), QOS_0)
    await mqttClient.publish('/fireplace/light/brightness', ('%d' % currentBrightness).encode('ascii'), QOS_0)


async def process_light_state_cmd(state):
    """ Process light state command """
    global requestedBrightness

    if state == 'ON' and requestedBrightness == 0:
        requestedBrightness = lastBrightness

    if state == 'OFF' and requestedBrightness > 0:
        requestedBrightness = 0


async def process_light_brightness_cmd(brightness):
    """ Process light brightness command """
    global requestedBrightness, lastBrightness

    if brightness != requestedBrightness:
        requestedBrightness = max(min(255, brightness), 0)

        if brightness != 0:
            lastBrightness = requestedBrightness


async def process_heater_state_cmd(mode):
    """ Process light brightness command """
    global requestedMode

    requestedMode = mode

async def process_mqtt_messages():
    """ Process incoming MQTT messages """

    while True:
        message = await mqttClient.deliver_message()
        packet = message.publish_packet

        logger.info('%s => %s' % (packet.variable_header.topic_name, packet.payload.data.decode('ascii')))

        if packet.variable_header.topic_name == '/fireplace/light/state_cmd':
            await process_light_state_cmd(packet.payload.data.decode('ascii'))

        if packet.variable_header.topic_name == '/fireplace/light/brightness_cmd':
            await process_light_brightness_cmd(int(packet.payload.data.decode('ascii'), base=10))

        if packet.variable_header.topic_name == '/fireplace/heater/state_cmd':
            await process_heater_state_cmd(packet.payload.data.decode('ascii'))


async def process_light_state_changes():
    """ Make sure the current light setting matches the requested setting """

    global currentBrightness, requestedBrightness

    while True:

        # If current brightness is same as requested sleep a while and continue loop
        if currentBrightness == requestedBrightness:
            await asyncio.sleep(0.1)
            continue

        # Update actual light state
        await update_light_by_brightness(requestedBrightness)

        # Update current state and publish result
        currentBrightness = requestedBrightness
        await publish_light_state_and_brightness()


async def process_heater_state_changes():
    """ Process heater state changes """

    global currentMode, requestedMode, switchModeAt

    while True:

        # We are in transition state to OFF and time has elapsed
        if currentMode == MODE_TO_OFF and time.time() > switchModeAt:
            await update_heater_by_mode(MODE_OFF)
            currentMode = MODE_OFF
            await publish_heater_state()
            continue

        # We are in transition state to LOW and time has elapsed
        if currentMode == MODE_TO_LOW and time.time() > switchModeAt:
            await update_heater_by_mode(MODE_ON_LOW)
            currentMode = MODE_ON_LOW
            await publish_heater_state()
            continue

        # We are in transition state to HIGH and time has elapsed
        if currentMode == MODE_TO_HIGH and time.time() > switchModeAt:
            await update_heater_by_mode(MODE_ON_HIGH)
            currentMode = MODE_ON_HIGH
            await publish_heater_state()
            continue

        # Requested mode matches current mode
        if requestedMode == MODE_OFF and (currentMode == MODE_OFF or currentMode == MODE_TO_OFF):
            await asyncio.sleep(0.1)
            continue

        # Requested mode matches current mode
        if requestedMode == MODE_ON_LOW and (currentMode == MODE_ON_LOW or currentMode == MODE_TO_LOW):
            await asyncio.sleep(0.1)
            continue

        # Requested mode matches current mode
        if requestedMode == MODE_ON_HIGH and (currentMode == MODE_ON_HIGH or currentMode == MODE_TO_HIGH):
            await asyncio.sleep(0.1)
            continue

        # Requested OFF, we are in transition to go on so we can safely go of directly
        if requestedMode == MODE_OFF and (currentMode == MODE_TO_LOW or currentMode == MODE_TO_HIGH):
            await update_heater_by_mode(MODE_OFF)
            currentMode = MODE_OFF
            await publish_heater_state()
            continue

        # Requested LOW, we are currently in HIGH setting so we can safely go to low directly
        if requestedMode == MODE_ON_LOW and (currentMode == MODE_ON_HIGH or currentMode == MODE_TO_OFF):
            await update_heater_by_mode(MODE_ON_LOW)
            currentMode = MODE_ON_LOW
            await publish_heater_state()
            continue

        # Requested HIGH we are currently in LOW setting so we can safely go to low directly
        if requestedMode == MODE_ON_HIGH and (currentMode == MODE_ON_LOW or currentMode == MODE_TO_OFF):
            await update_heater_by_mode(MODE_ON_HIGH)
            currentMode = MODE_ON_HIGH
            await publish_heater_state()
            continue

        # Requested off but we can't transition directly
        if requestedMode == MODE_OFF:
            await update_heater_by_mode(MODE_TO_OFF)
            switchModeAt = time.time() + 10
            currentMode = MODE_TO_OFF
            await publish_heater_state()
            continue

        # Requested low but we can't transition directly
        if requestedMode == MODE_ON_LOW:
            await update_heater_by_mode(MODE_TO_LOW)
            switchModeAt = time.time() + 3
            currentMode = MODE_TO_LOW
            await publish_heater_state()
            continue

        # Requested high but we can't transition directly
        if requestedMode == MODE_ON_HIGH:
            await update_heater_by_mode(MODE_TO_HIGH)
            switchModeAt = time.time() + 3
            currentMode = MODE_TO_HIGH
            await publish_heater_state()
            continue


async def main():
    """ Main subroutine """

    # Initialize Firmata connection and MQTT connection
    await asyncio.gather(
        init_firmata(),
        init_connection()
    )

    # Send initial state
    await asyncio.gather(
        publish_heater_state(),
        publish_light_state_and_brightness()
    )

    # Start the actual processing (this will be endless loops)
    await asyncio.gather(
        process_mqtt_messages(),
        process_light_state_changes(),
        process_heater_state_changes()
    )


# Main entry point
if __name__ == '__main__':
    formatter = '[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.INFO, format=formatter)

    asyncio.get_event_loop().run_until_complete(main())
