################################################################################
# FOTA Updates
#
# Created by Zerynth Team 2015 CC
# Authors: G. Baldi,  D. Mazzei
###############################################################################

##
## This example only works on a FOTA enabled Virtual Machine!
##


from wireless import wifi
# this example is based on a ESP8266 device
# change the following line to use a different wifi driver
from espressif.esp8266wifi import esp8266wifi as wifi_driver

import streams

# Import the Zerynth ADM library
from zadm import zadm
# Import the fota library
import fota

streams.serial()

sleep(1000)
print("STARTING...")


def fota_callback(event):
    if event == 0:
        print("FOTA Started")
    elif event == 1:
        print("FOTA record is changing")
    elif event == 2:
        print("device is going to RESET!")
        sleep(2000)
    return True
        

# Create a device instance by passing the device UID and TOKEN (copy and paste from the ADM panel)
# enable logging to debug
z = zadm.Device("DEVICE-UID-HERE", "DEVICE-TOKEN-HERE", log=False, fota_callback = fota_callback)

try:
    # Get information about the currently running configuration
    # Check documentation here: https://docs.zerynth.com/latest/official/core.zerynth.stdlib/docs/official_core.zerynth.stdlib_fota.html
    rec = fota.get_record()
    bcslot = rec[4]
    valid_runtime = rec[0]

    # connect to the wifi network (Set your SSID and password below)
    wifi_driver.auto_init()
    for i in range(0,5):
        try:
            wifi.link("SSID",wifi.WIFI_WPA2,"password")
            break
        except Exception as e:
            print("Can't link!",e)
    else:
        print("Impossible to link!")
        while True:
            sleep(1000)

    # Start the device instance!
    # It immediately returns while a background thread keeps trying to connect and receive messages
    z.start()

    
    # Do whatever you need here
    if valid_runtime:
        msg = "Hello, this is Bytecode running on slot "+str(bcslot)
    else:
        msg = "Hello, this is Bytecode runnung on slot ??"
    
    pinMode(LED0, OUTPUT)
    
    # blink a led and print some message
    while True:
        print(msg)
        sleep(5000)
        pinToggle(LED0)
        
except Exception as e:
    print(e)


