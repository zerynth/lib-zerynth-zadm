from wireless import wifi
# this example is based on Particle Photon
# change the following line to use a different wifi driver
from broadcom.bcm43362 import bcm43362 as wifi_driver
import streams

# Import the Zerynth ADM library
from zadm import zadm

streams.serial()

sleep(1000)
print("STARTING...")

# define a RPC function: generate a random number
def do_random(a,b):
    return random(a,b)

methods = {
    "random":do_random
}

# send events on button pressed
def on_btn():
    z.send_event({"my_button":"pressed"})
    z.send_notification("BUTTON!","PRESSED!")

onPinFall(BTN0,on_btn,debounce=1000)



# Create a device instance by passing the device UID and TOKEN (copy and paste from the ADM panel)
# enable logging to debug and pass in the dictionary of remotely callable functions
z = zadm.Device("DEVICE UID HERE", "DEVICE TOKEN HERE", log=True, rpc = methods)

try:
    # connect to the wifi network (Set your SSID and password below)
    wifi_driver.auto_init()
    for i in range(0,5):
        try:
            wifi.link("NETWORK SSID",wifi.WIFI_WPA2,"NETWORK PASSWORD")
            break
        except Exception as e:
            print("Can't link",e)
    else:
        print("Impossible to link!")
        while True:
            sleep(1000)

    # Start the device instance!
    # It immediately returns while a background thread keeps trying to connect and receive messages.
    # As soon as a RPC call is received, do_random is automatically called and the result send back to the ADM.
    # If the device button is pressed long enough, a notification and an event are sent to the ADM that dispatches them to all connected templates and apps
    z.start()
    
    # Do whatever you need here
    while True:
        print(".")
        sleep(5000)
        
except Exception as e:
    print(e)


