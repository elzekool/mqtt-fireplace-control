# Fireplace Control script

I use this Python script to control my electric fireplace trough MQTT. The controller is removed from
the original board and is replaced by a Arduino Pro Mini. This Arduino is programmed with the generic Firmata
firmware that is part of the Arduino IDE.

## Usage

**WARNING:** This code is as-is without any waranty! Messing with electrical appliances can be dangerous for
you and your house. Use at your own risc!

1. Make sure you are running Python 3.7. I use the following gist https://gist.github.com/elzekool/c8f77986927e4ffbd4d3fb47a9f926f8 to install this on my Raspberry PI
2. Clone this repository somewhere (e.g. ~/fireplace-control)
3. It is advised to use a virtual environment. Creating a virtual environment can be done with `python3.7 -m venv venv/` where the last bit determines where the environment is stored. Use `source venv/bin/activate` to activate the environment.
4. Install dependencies with `pip install -r requirements.txt`
5. Make sure you configured the MQTT server in `server.py`
6. Start the server with `python3.7 server.py`

## MQTT topics

* **/fireplace/heater/state** here the latest state is published, possible values are `OFF`, `TO_OFF`, `LOW`, `TO_LOW`, `HIGH`, `TO_HIGH`. All values with `TO_` prefixed are temporary states.
* **/fireplace/heater/state_cmd** here a state change command can be issued. Allowed values: `OFF`, `LOW`, `HIGH`
* **/fireplace/light/state** here the latest state is published, possible values are `OFF`, `ON`
* **/fireplace/light/state_cmd** here a state change command can be issued. Allowed values: `OFF`, `ON`. `ON` will use the last set brightness.
* **/fireplace/light/brightness** here the brightness will be published. Value in range from 0 to 255.
* **/fireplace/light/brightness_cmd** here a brightness command can be issued. Allowed value range is 0 to 255.

## Firmata pins

* **Pin 4** Fan pin, this controls the heater fan.  Should be set on a few seconds before and after enabling the heater.

* **Pin 5** Flame pin, this is what rotates the flame screen. Is used toghether with the Light pin.

* **Pin 6** Heater Low pin, make sure the fan is enabled for setting this one to on.

* **Pin 7** Heater High pin, make sure the fan and low heater pins are enabled for setting this one to on.

* **Pin 11** Light pin, this a PWM pin that controls the lighting for the flames. The flame pin should also be on.