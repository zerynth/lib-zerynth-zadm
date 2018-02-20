"""
.. module:: zerynthadm

.. _lib.zerynth.zadm:

*******************
Zerynth ADM Library
*******************

The Zerynth ADM library can be used yo ease the connection to the :ref:`Zerynth ADM sandbox <zadm>`.
It takes care of connecting to the ADM and listening for incoming messages. Moreover it seamlessly enables RPC calls and mobile integration.
For Virtual Machines supporting FOTA updates, the Zerynth ADM also performs the FOTA process automatically when requested.

========================
Zerynth ADM Step by Step
========================

Using the ADM library is very simple: 

* obtain device credentials (UID and TOKEN): can be copied and pasted directly from Zerynth Studio (ADM panel) or the Zerynth Toolchain
* optionally define a dictionary of remotely callable functions
* create an instance of the Device class with the desired configuration
* start the device instance
* send and receive messages from connected templates and apps

Check the provided examples for more details.

    """

import socket
import json
import threading
import streams
import queue
import timers
import vm
import fota
import base64
import mcu
import gc

__define(__OTA_ONLY_BC,0)
__define(__OTA_BC_AND_VM,1)

__define(__OTA_IDLE,0)
__define(__OTA_STARTED,1)
__define(__OTA_RECEIVING_BC,2)
__define(__OTA_RECEIVING_VM,3)
__define(__OTA_RECEIVING_BC_CRC,4)
__define(__OTA_RECEIVING_VM_CRC,5)

class Device():
    """
================
The Device class
================

.. class:: Device(uid,token,ip=None,address="things.zerynth.com",heartbeat=60,rpc=None,log=False,fota_callback=None,low_res=False)

        Creates a Device instance with uid :samp:`uid` and token :samp:`token`. All other parameters are optional and have default values.

        * :samp:`ip` is the ip address of the ADM. This argument is used when the network driver does not support hostname resolution
        * :samp:`address` is the hostname of the ADM instance. It is used by default and resolved to an ip address when the network driver supports the functionality
        * :samp:`heartbeat` is the number of seconds between heartbeat messages. If the ADM detects that a connected device is not sending heartbeat messages two times in a row, it automatically terminates the connection. Heartbeat messages are automatically sent by the Device class. The ADM may not accept the specified heartbeat time and force the device to use another, based on network traffic and other parameters.
        * :samp:`rpc` is a dictionary with keys representing function names and values representing actual Python functions. When a RPC call is made to the ADM, the message is relayed to the connected device. The Device class, scans the :samp:`rpc` dictionary and if a key matching the requested call is found, the corresponding function is executed (in the Device class thread). The result (or the exception message) is then sent back to the ADM that relays it to the caller.
        * :samp:`log`, if true prints logging messages to the device serial console
        * :samp:`fota_callback`, is a function accepting one ore more arguments that will be called at different steps of the FOTA process. The argument will be set to:

            * :samp:`0`, when the FOTA process is started
            * :samp:`1`, when the FOTA process needs to update the FOTA record
            * :samp:`2`, when the FOTA process needs to reseet the device at the end of the FOTA process
            
            the :samp:`fota_callback` can return a boolean value. If the return value is True, the FOTA process continues, otherwise it is stopped.

        * :samp:`low_res`, if true makes the FOTA process a bit less performant but more lightweight (needed for low-resource devices)

    """
    def __init__(self,uid,token,ip=None,port=12345,address="things.zerynth.com",heartbeat=60,rpc=None,log=False,fota_callback=None,low_res=False):
        self.heartbeat = heartbeat
        self.address = address
        self.port = port
        if not rpc:
            self.rpc = {}
        else:
            self.rpc = rpc
        self.logged = False
        self.reconnecting = False
        self.wq = queue.Queue(maxsize=2)
        if log:
            self.log = self._log
        else:
            self.log = self._nolog
        self.uid = uid
        self.token = token
        self._sock = None
        self._rth = None
        self._hth = None
        self._wth = None
        self.ts = 0
        self.ip = ip
        self.ota = __OTA_IDLE
        self.ota_type = __OTA_ONLY_BC
        self.fota_callback = fota_callback
        self.low_res = low_res

    def _log(self,*args):
        print(timers.now(),*args)

    def _nolog(self,*args):
        pass

    
    def start(self):
        """
.. method:: start()

        Starts the connection process and creates background threads to handle incoming and outgoing messages.
        It returns immediately.
                
        """
        while not self.logged:
            self.logged = self.login()
            sleep(5000)
        if self._rth is None:
            self._rth = thread(self._readloop)

        if not self.low_res:
            if self._hth is None:
                self._hth = thread(self._htbm)
            if self._wth is None:
                self._wth = thread(self._writeloop)
        else:
            self._whth = thread(self._writeloop_htbm)
        self.reconnecting=False

    
    def login(self):
        self.log("Trying to connect with uid",self.uid,"and token",self.token)
        self._sock = socket.socket()
        # set keepalive when supported
        # self._sock.setsockopt(socket.SOL_SOCKET,socket.SO_KEEPALIVE,1)
        # self._sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_KEEPIDLE,20000)
        # self._sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_KEEPINTVL,5)
        # self._sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_KEEPCNT,3)
        self._client = streams.SocketStream(self._sock)
        try:
            if not self.ip:
                self.ip = __builtins__.__default_net["sock"][0].gethostbyname(self.address)
            self._sock.connect((self.ip,self.port))
        except:
            self.log("Can't connect!")
            self._closeall()
            return False
        try:
            vminfo = vm.info()
            data = {
                "uid":self.uid,
                "token":self.token,
                "platform":vminfo[1],
                "vmuid":vminfo[0],
                "hearbeat":self.heartbeat,
            }
            try:
                rec = fota.get_record()
                data["ota"] = True
                if rec[0]:
                    data["bc"]=rec[4]
                    data["vm"]=rec[1]
                    data["chunk"]=rec[8]
            except:
                data["ota"] = False

            self._send(data)
            msg = self._getmsg()
            if "err" in msg:
                self.log("oops, error",msg)
                self._closeall()
                return False
            if "ts" in msg:
                self.ts = msg["ts"] #current time
            if "htbm" in msg:
                self.heartbeat = msg["htbm"]
            try:
                fota.accept()
            except:
                pass
        except Exception as e:
            self.log("Login exception!",e)
            self._closeall()
            return False
        return True
    
    
    def _reconnect(self):
        if self.reconnecting:
            return
        self.reconnecting=True
        if self.logged:
            self._closeall()
            self.logged = False
        self.start()

    def _send(self,msg):
        try:
            bb = json.dumps(msg)
            self.log("Sending",msg)
            self._client.write(bb)
            self._client.write("\n")
        except Exception as e:
            self.log("Exception in send",e,msg)

    def send(self,msg):
        """
.. method:: send(msg)

        Send a raw message to the ADM. :samp:`msg` is a dictionary that will be serialized to JSON and sent.
                
        """        
        self.wq.put(msg,False,1000)
    
    
    def _getmsg(self):
        self.log("Getting message")
        line = self._client.readline()
        self.log("Got message",line)
        if not line:
            raise IOError
        msg = json.loads(line)
        return msg

    def _closeall(self):
        try:
            self._sock.close()
        except:
            pass
    
    def _htbm(self):
        while True:
            while self.reconnecting:
                sleep(1000)
            self.log("Sleeping for",self.heartbeat)
            sleep(1000*self.heartbeat)
            try:
                self.send({"cmd":"HTBM"})
            except:
                self.log("Exception in htbm")
                self._reconnect()

    def _writeloop(self):
        while True:
            while self.reconnecting:
                sleep(1000)
            try:
                msg = self.wq.get()
                self._send(msg)
            except Exception as e:
                self.log("Exception in writeloop",e)
                self._reconnect()

    def _writeloop_htbm(self):
        _last_htb = timers.now()
        while True:
            while self.reconnecting:
                sleep(1000)
            try:
                try:
                    timeout = 1000*self.heartbeat - (timers.now() - _last_htb)
                    if timeout <= 0:
                        raise QueueEmpty
                    msg = self.wq.get(timeout = timeout)
                except QueueEmpty:
                    self._send({"cmd":"HTBM"})
                    _last_htb = timers.now()
                else:
                    self._send(msg)
            except Exception as e:
                self.log("Exception in writeloop+htbm",e)
                self._reconnect()

    def _ota_fail(self,reason):
        self.send({"cmd":"OTA","payload":{"ko":1,"reason":reason}})
    
    def _readloop(self):
        while True:
            while self.reconnecting:
                sleep(1000)
            try:
                msg = self._getmsg()
                if "cmd" in msg and msg["cmd"]=="CALL" and "method" in msg and msg["method"] in self.rpc and "id" in msg:
                    if "args" in msg:
                        args=msg["args"]
                    else:
                        args=[]
                    
                    ret = False
                    if "ret" in msg:
                        ret = msg["ret"]
                    try:
                        self.log("calling",msg["method"])
                        res = self.rpc[msg["method"]](*args)
                        #print(timers.now(),"called",msg["method"])
                    except Exception as e:
                        self.log("Exception in rpc",e)
                        if ret:
                            self.send({"cmd":"RETN","id":msg["id"],"error":str(e)})
                    else:
                        if ret:
                            self.send({"cmd":"RETN","id":msg["id"],"res":res})
                    res=None
                elif "terminate" in msg:
                    self.log("Terminating...")
                    self._closeall()
                elif "cmd" in msg and msg["cmd"]=="OTA":
                    self.log("OTA message")
                    try:
                        rec = fota.get_record()
                    except:
                        self.log("OTA unsupported")
                        self._ota_fail("OTA unsupported")
                        continue

                    if "chunk" in msg:
                        self.chunk = msg["chunk"]
                        self.vmsize = msg["vmsize"]
                        self.bcsize = msg["bcsize"]
                        self.bcslot = msg["bc"]
                        self.vmslot = msg["vm"]

                        if self.bcslot==rec[4] or (self.vmsize and self.vmslot==rec[1]):
                            self.log("Invalid OTA request!")
                            self._ota_fail("Bad slots")
                            continue

                        if self.vmsize<=0:
                            self.ota_type = __OTA_ONLY_BC
                            self.next_bcaddr = fota.find_bytecode_slot()
                            self.next_vmaddr = -1
                        else:
                            self.ota_type = __OTA_BC_AND_VM
                            self.next_vmaddr = fota.find_vm_slot()
                            self.next_bcaddr = fota.find_bytecode_slot()

                        if self.fota_callback and not self.fota_callback(0):
                            self.log("OTA",0,"stopped by callback")
                            self._ota_fail("stopped by callback")
                            continue

                        if self.next_bcaddr>0:
                            self.log("ERASE BC SLOT",hex(self.next_bcaddr), self.bcsize)
                            fota.erase_slot(self.next_bcaddr, self.bcsize)
                            

                        if self.next_vmaddr>0:
                            self.log("ERASE VM SLOT",hex(self.next_vmaddr), self.vmsize)
                            fota.erase_slot(self.next_vmaddr, self.vmsize)

                        self.ota = __OTA_RECEIVING_BC
                        self.cblock = 0
                        self.csize = 0
                        self.send({"cmd":"OTA","payload":{"b":0,"t":"b"}})

                    elif "bin" in msg and (self.ota==__OTA_RECEIVING_BC or self.ota==__OTA_RECEIVING_VM):
                        thebin = base64.standard_b64decode(msg["bin"])
                        if self.ota == __OTA_RECEIVING_BC:
                            if msg["t"]!="b":
                                self.log("Bad OTA message!")
                                self._ota_fail("BC only ota")
                                continue
                            addr = self.next_bcaddr
                            tsize = self.bcsize
                        elif self.ota == __OTA_RECEIVING_VM and self.ota_type==__OTA_BC_AND_VM:
                            addr = self.next_bcaddr if msg["t"]=="b" else self.next_vmaddr
                            tsize = self.bcsize if msg["t"]=="b" else self.vmsize

                        self.log("WRITING BLOCK",self.cblock,"at",hex(addr+self.chunk*self.cblock),len(thebin))
                        fota.write_slot(addr+self.chunk*self.cblock,thebin)
                        self.cblock+=1
                        self.csize+=len(thebin)
                        if self.csize<tsize:
                            #keep sending blocks
                            self.send({"cmd":"OTA","payload":{"b":self.cblock,"t":msg["t"]}})
                        else:
                            #ask for crc
                            self.ota = __OTA_RECEIVING_BC_CRC if msg["t"]=="b" else __OTA_RECEIVING_VM_CRC
                            self.send({"cmd":"OTA","payload":{"c":0,"t":msg["t"]}})
                    elif "crc" in msg:
                        if msg["t"]=="b":
                            chk = fota.checksum_slot(self.next_bcaddr,self.bcsize)
                            fota.close_slot(self.next_bcaddr)
                        else:
                            chk = fota.checksum_slot(self.next_vmaddr,self.vmsize)
                            fota.close_slot(self.next_vmaddr)
                        if not chk:
                            self.log("Skipping CRC")
                        
                        for i,b in enumerate(chk):
                            k = int(msg["crc"][i*2:i*2+2],16)
                            if k!=b:
                                self.log("Bad crc!")
                                self._ota_fail("Bad CRC")
                                break
                        else:
                            self.log("OTA OK")
                            if msg["t"]=="b" and self.ota_type==__OTA_BC_AND_VM:
                                #start VM download
                                self.send({"cmd":"OTA","payload":{"b":0,"t":"v"}})
                                self.ota = __OTA_RECEIVING_VM
                                self.cblock = 0
                                self.csize = 0
                                self.log("Vm begin")
                            else:
                                # try OTA!
                                if self.fota_callback and not self.fota_callback(1):
                                    self.log("OTA",1,"stopped by callback")
                                    self._ota_fail("stopped by callback")
                                    continue
                                fota.attempt(self.bcslot,self.vmslot)
                                if self.fota_callback and not self.fota_callback(2):
                                    self.log("OTA",2,"stopped by callback")
                                    self._ota_fail("stopped by callback")
                                    continue
                                self._closeall()
                                self.log("resetting...")
                                sleep(1000)
                                mcu.reset()
                    elif "ok" in msg:
                        if msg["bc"] == rec[4] and msg["vm"] == rec[1]:
                            self.send({"cmd":"OTA","payload":{"ok":1}})
                        else:
                            self._ota_fail("not ready")
            except Exception as e:
                self.log("Exception in readloop",e)
                self._reconnect()
        
        
        
    def send_event(self,payload):
        """
.. method:: send_event(payload)

        Send an event message containing the payload :samp:`payload` to the ADM. Payload is given as a dictionary and then serialized to JSON.
                
        """
        self.send({"cmd":"EVNT","payload":payload})
        
        
    def send_notification(self,title,text):
        """
.. method:: send_notification(title,text)

        Send a push notification to connected apps and templates. The notification must have a :samp:`title` and a :samp:`text`.
                
        """
        self.send({"cmd":"NTFY","payload":{"text":text,"title":title}})
        
    
        
        
